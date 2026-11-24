"""Which existing topics mean the same as a new suggestion, judged by Devin.

One Devin session is kept only for this. Each suggestion is sent to it with the
whole topic list, and its answer is read back a little later. The key and the
session's instructions come from the environment (TOPICS_DEVIN_API_KEY and
TOPICS_DEVIN_PROMPT); without both, nothing is checked.
"""

import asyncio
import json
import os
import re
import secrets

import aiohttp
from firebase_admin import db

API = "https://api.devin.ai/v3"
SESSION = "/Cafe Topics/Matcher"
MOST = 5
WAIT, EVERY = 300, 5
ANSWER = (
    "Answer with one line of JSON and nothing else: "
    '{{"id": "{tag}", "similar": [{{"n": <number in the list>, '
    '"why": "<at most 8 words>"}}]}}. List at most {most}, closest first, '
    "and only topics a member would answer the same way. An empty list is a "
    "fine answer."
)


class Unavailable(Exception):
    """The check could not be made; staff review without it."""


def ready():
    return bool(os.getenv("TOPICS_DEVIN_API_KEY") and os.getenv("TOPICS_DEVIN_PROMPT"))


async def call(http, method, path, **more):
    async with http.request(method, API + path, **more) as reply:
        if reply.status >= 400:
            raise Unavailable(f"Devin API {reply.status}")
        return await reply.json()


def question(text, topics, tag):
    listed = "\n".join(f"{spot}. {topic}" for spot, topic in enumerate(topics, 1))
    return (
        f"Existing topics:\n{listed}\n\nNew suggestion: {json.dumps(text)}\n\n"
        + ANSWER.format(tag=tag, most=MOST)
    )


def answer(messages, tag, topics):
    """The topics Devin named in its reply to this question, or None so far."""
    for message in reversed(messages):
        if message.get("source") != "devin":
            continue
        for found in re.findall(r"\{.*\}", message.get("message", ""), re.S):
            try:
                reply = json.loads(found)
            except ValueError:
                continue
            if not isinstance(reply, dict) or reply.get("id") != tag:
                continue
            close = []
            for match in reply.get("similar") or []:
                spot = match.get("n") if isinstance(match, dict) else None
                if isinstance(spot, int) and 1 <= spot <= len(topics):
                    why = " ".join(str(match.get("why") or "").split())[:80]
                    close.append((topics[spot - 1], why))
            return close[:MOST]
    return None


async def ask(http, org, text):
    """Send the question to the kept session, or to a new one when it is gone."""
    kept = db.reference(SESSION).get() or {}
    if kept.get("id"):
        try:
            await call(
                http,
                "POST",
                f"/organizations/{org}/sessions/{kept['id']}/messages",
                json={"message": text},
            )
            return kept["id"]
        except Unavailable:
            pass
    made = await call(
        http,
        "POST",
        f"/organizations/{org}/sessions",
        json={
            "prompt": os.environ["TOPICS_DEVIN_PROMPT"] + "\n\n" + text,
            "title": "BrawlKit similar topics",
            "tags": ["brawlkit-topics"],
            "knowledge_ids": [],
            "secret_ids": [],
            "repos": [],
        },
    )
    db.reference(SESSION).set({"id": made["session_id"]})
    return made["session_id"]


async def similar(text, topics):
    """Up to MOST (topic, why) pairs that mean the same as text, closest first."""
    if not ready():
        raise Unavailable("not set up")
    tag = secrets.token_hex(4)
    headers = {"Authorization": f"Bearer {os.environ['TOPICS_DEVIN_API_KEY']}"}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as http:
            me = await call(http, "GET", "/self")
            org = me.get("devin_sessions_org_id") or me["org_id"]
            session = await ask(http, org, question(text, topics, tag))
            path = f"/organizations/{org}/sessions/{session}/messages"
            for _ in range(WAIT // EVERY):
                await asyncio.sleep(EVERY)
                messages, after = [], None
                while True:
                    params = {"first": 100, **({"after": after} if after else {})}
                    page = await call(http, "GET", path, params=params)
                    messages += page.get("items", [])
                    after = page.get("end_cursor")
                    if not page.get("has_next_page") or not after:
                        break
                close = answer(messages, tag, topics)
                if close is not None:
                    return close
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as error:
        raise Unavailable(str(error)) from error
    raise Unavailable("no answer in time")


async def setup(bot):
    pass

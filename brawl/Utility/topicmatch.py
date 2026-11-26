"""Which existing topics mean the same as a new suggestion, judged by Devin.

One Devin session is kept for this (the daily poll keeps its own, through
`reply`). Each suggestion is sent to it with the
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
    for found in replies(messages, tag):
        close = []
        for match in found.get("similar") or []:
            spot = match.get("n") if isinstance(match, dict) else None
            if isinstance(spot, int) and 1 <= spot <= len(topics):
                why = " ".join(str(match.get("why") or "").split())[:80]
                close.append((topics[spot - 1], why))
        return close[:MOST]
    return None


async def ask(http, org, text, kept_at, prompt, title):
    """Send the question to the kept session, or to a new one when it is gone."""
    kept = db.reference(kept_at).get() or {}
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
            "prompt": prompt + "\n\n" + text,
            "title": title,
            "tags": ["brawlkit-topics"],
            "knowledge_ids": [],
            "secret_ids": [],
            "repos": [],
        },
    )
    db.reference(kept_at).set({"id": made["session_id"]})
    return made["session_id"]


async def reply(
    text,
    read,
    kept_at=SESSION,
    prompt=None,
    title="BrawlKit similar topics",
    wait=WAIT,
    every=EVERY,
):
    """Ask the kept Devin session and give back what read makes of its messages,
    once that is no longer None. The session's instructions are the prompt, or
    TOPICS_DEVIN_PROMPT when none is given."""
    prompt = prompt or os.getenv("TOPICS_DEVIN_PROMPT")
    if not os.getenv("TOPICS_DEVIN_API_KEY") or not prompt:
        raise Unavailable("not set up")
    headers = {"Authorization": f"Bearer {os.environ['TOPICS_DEVIN_API_KEY']}"}
    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as http:
            me = await call(http, "GET", "/self")
            org = me.get("devin_sessions_org_id") or me["org_id"]
            session = await ask(http, org, text, kept_at, prompt, title)
            path = f"/organizations/{org}/sessions/{session}/messages"
            for _ in range(wait // every):
                await asyncio.sleep(every)
                messages, after = [], None
                while True:
                    params = {"first": 100, **({"after": after} if after else {})}
                    page = await call(http, "GET", path, params=params)
                    messages += page.get("items", [])
                    after = page.get("end_cursor")
                    if not page.get("has_next_page") or not after:
                        break
                found = read(messages)
                if found is not None:
                    return found
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as error:
        raise Unavailable(str(error)) from error
    raise Unavailable("no answer in time")


def replies(messages, tag):
    """Every JSON object Devin answered this question with, newest first."""
    for message in reversed(messages):
        if message.get("source") != "devin":
            continue
        for found in re.findall(r"\{.*\}", message.get("message", ""), re.S):
            try:
                answered = json.loads(found)
            except ValueError:
                continue
            if isinstance(answered, dict) and answered.get("id") == tag:
                yield answered


async def similar(text, topics):
    """Up to MOST (topic, why) pairs that mean the same as text, closest first."""
    tag = secrets.token_hex(4)
    return await reply(
        question(text, topics, tag), lambda messages: answer(messages, tag, topics)
    )


async def setup(bot):
    pass

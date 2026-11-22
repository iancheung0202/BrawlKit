import asyncio
import os
import time
import urllib.parse

import requests

API = "https://api.brawlstars.com/v1"
BRAWLTOOLS = "https://api.brawltools.net"
CDN = "https://cdn.brawlify.com"
HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {os.environ['BRAWL_STARS_API_KEY']}",
}
BRAWL_TOOLS_HEADERS = {"Accept": "application/json"}
# Used until the list of brawlers has been read once.
BRAWLERS = 112
BRAWLERS_FOR = 6 * 3600
IMAGES = {}
released = {"count": BRAWLERS, "at": 0}
# Game modes by their id, used until today's events have been read once.
MODES = {
    48000000: "Gem Grab",
    48000005: "Brawl Ball",
    48000002: "Heist",
    48000003: "Bounty",
    48000017: "Hot Zone",
    48000020: "Knockout",
    48000006: "Solo Showdown",
    48000009: "Duo Showdown",
}
MODES_FOR = 3600
playable = {"modes": MODES, "at": 0}


async def fetch(url: str, headers: dict):
    try:
        response = await asyncio.to_thread(
            requests.get, url, headers=headers, timeout=15
        )
    except requests.RequestException:
        return None
    return response.json() if response.ok else None


def player_url(tag: str) -> str:
    return f"/players/{urllib.parse.quote(clean_tag(tag))}"


async def get_player(tag: str):
    return await fetch(API + player_url(tag), HEADERS)


async def get_stats(tag: str):
    data = await fetch(BRAWLTOOLS + player_url(tag), BRAWL_TOOLS_HEADERS)
    return data.get("data") if data else None


async def get_battles(tag: str) -> list:
    data = await fetch(f"{API}{player_url(tag)}/battlelog", HEADERS)
    return data.get("items", []) if data else []


async def get_icon(brawler_id: int):
    data = await fetch(f"{BRAWLTOOLS}/brawlers/{brawler_id}", BRAWL_TOOLS_HEADERS)
    return data["data"][0]["iconId"]


async def brawler_count() -> int:
    """How many brawlers the game has, read from the live list a few times a day."""
    if time.time() - released["at"] > BRAWLERS_FOR:
        released["at"] = time.time()
        data = await fetch(f"{BRAWLTOOLS}/brawlers", BRAWL_TOOLS_HEADERS)
        if data and data.get("data"):
            released["count"] = len(data["data"])
    return released["count"]


async def modes() -> dict:
    """The game modes in today's events, by id, read from the live list hourly."""
    if time.time() - playable["at"] > MODES_FOR:
        playable["at"] = time.time()
        data = await fetch(f"{BRAWLTOOLS}/events", BRAWL_TOOLS_HEADERS)
        found = {
            mode["scId"]: mode["name"]
            for event in ((data or {}).get("data") or {}).get("activeEvents", [])
            for mode in event.get("gameMode") or []
        }
        if found:
            playable["modes"] = dict(list(found.items())[:25])
    return playable["modes"]


async def image(path: str) -> bytes:
    """A picture from the Brawl Stars art host, kept after the first read."""
    if path not in IMAGES:
        try:
            response = await asyncio.to_thread(requests.get, CDN + path, timeout=10)
        except requests.RequestException:
            return b""
        if not response.ok:
            return b""
        if len(IMAGES) > 2000:
            IMAGES.pop(next(iter(IMAGES)))
        IMAGES[path] = response.content
    return IMAGES[path]


async def images(paths) -> dict:
    paths = list(dict.fromkeys(paths))
    return dict(zip(paths, await asyncio.gather(*(image(path) for path in paths))))


def clean_tag(tag: str) -> str:
    return "#" + tag.strip().upper().lstrip("#")


async def setup(bot):
    pass

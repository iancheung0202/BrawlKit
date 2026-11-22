import asyncio
import os
import urllib.parse

import requests

API = "https://api.brawlstars.com/v1"
BRAWLTOOLS = "https://api.brawltools.net"
HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {os.environ['BRAWL_STARS_API_KEY']}",
}
BRAWL_TOOLS_HEADERS = {"Accept": "application/json"}


async def fetch(url: str, headers: dict):
    response = await asyncio.to_thread(requests.get, url, headers=headers)
    return response.json() if response.ok else None


async def get_player(tag: str):
    return await fetch(f"{API}/players/{urllib.parse.quote(tag)}", HEADERS)


async def get_stats(tag: str):
    data = await fetch(
        f"{BRAWLTOOLS}/players/{urllib.parse.quote(tag)}", BRAWL_TOOLS_HEADERS
    )
    return data.get("data") if data else None


async def get_icon(brawler_id: int):
    data = await fetch(f"{BRAWLTOOLS}/brawlers/{brawler_id}", BRAWL_TOOLS_HEADERS)
    return data["data"][0]["iconId"]


def clean_tag(tag: str) -> str:
    return "#" + tag.strip().upper().lstrip("#")


async def setup(bot):
    pass

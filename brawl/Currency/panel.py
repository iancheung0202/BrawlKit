import discord

from brawl.Currency.config import BREW, HOME, SELL
from brawl.Utility.style import BLUE, GOLD, GREEN, RED

STATIONS = {
    "brew": "Brew Station",
    "clock_in": "Clock In",
    "shop": "Shop",
    "stamps": "Stamp Card",
    "inventory": "Inventory",
    "invites": "Invites",
    "table": "Table",
}
COLORS = {"info": BLUE, "good": GREEN, "bad": RED, "gold": GOLD}
NEXT = {
    "chat": "Chat to earn Beans and fill Today's Order.",
    "brew": f"Start a brew with {BREW}.",
    "sell": f"Sell it with {SELL} when it is ready.",
    "sell_now": f"Sell it with {SELL}.",
    "home": f"Open {HOME} to see Today's Order.",
}


def panel(station, headline, body="", next=None, tone="info"):
    embed = discord.Embed(title=headline, description=body, color=COLORS[tone])
    embed.set_author(name=STATIONS[station])
    if next:
        embed.description += f"\n-# **Next:** {NEXT.get(next, next)}"
    return embed


async def setup(bot):
    pass

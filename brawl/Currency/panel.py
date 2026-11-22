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
    "brew": f"Start your next brew with {BREW}.",
    "sell": f"Sell it with {SELL} when it is ready.",
    "roast": f"Pick a roast with {BREW} to start a brew.",
    "home": f"Open {HOME} to see Today's Order.",
}


def panel(station, headline, body="", next=None, tone="info"):
    embed = discord.Embed(title=headline, description=body, color=COLORS[tone])
    embed.set_author(name=STATIONS[station])
    if next:
        embed.description += f"\n\n{NEXT.get(next, next)}"
    return embed


# The same steps as they are drawn on a strip, where a command cannot be a link.
DRAWN = {
    "brew": "Start another brew with /brew",
    "sell": "Sell it with /sell when it is ready",
    "ready": "Sell it with /sell in the bot channel",
}


def notice(text, tone="info"):
    """A one-line answer: a refusal, a confirmation, a short notice."""
    return discord.Embed(description=text, color=COLORS[tone])


def framed(file, title=None, *lines, tone="info"):
    """A card inside an embed under a short title and a few plain lines. Use as **framed(...)."""
    embed = discord.Embed(
        title=title,
        description="\n".join(line for line in lines if line) or None,
        color=COLORS[tone],
    )
    if not embed.description:
        return {"file": file}
    embed.set_image(url=f"attachment://{file.filename}")
    return {"embed": embed, "file": file}


def reframed(file, title, *lines, tone="info"):
    """The same, for editing a message that already shows a card."""
    sent = framed(file, title, *lines, tone=tone)
    return {"embed": sent.get("embed"), "attachments": [file]}


async def setup(bot):
    pass

from brawl.Currency.card import BLUE, GOLD, GREEN, MUTED, RED, WHITE, Card
from brawl.Currency.config import PERFECT_BREW_CHANCE, ROAST_TYPES, UNLOCK_REQ

TINTS = {
    "light": (150, 215, 120),
    "medium": (225, 160, 90),
    "dark": (150, 110, 215),
    "golden": GOLD,
}


def hours(seconds):
    return f"{round(seconds / 3600)}h"


def chip(card, x, y, label, odds, fill=WHITE):
    w = card.measure(label, 16) + card.measure(odds, 13) + 34
    card.slot(x, y, w, 30)
    card.text(x + 10, y + 5, label, 16, fill, "la", 2)
    card.text(x + w - 10, y + 8, odds, 13, MUTED, "ra", 2)
    return x + w + 8


def draw_brewing(brew):
    """A strip for a brew that just started."""
    roast = ROAST_TYPES[brew["roast"]]
    card = Card.strip(brew.get("next"))
    card.tag(32, 12, "BREW STARTED", BLUE, WHITE)
    card.icon("brewing", 34, 44, 76)
    card.text(122, 44, roast["name"], 26)
    ready = f"Ready in {hours(brew['time'])}" if brew["time"] else "Ready now"
    card.text(122, 82, ready, 16, MUTED, "la", 2)
    state, color = {
        "insured": ("Insured", GREEN),
        "free": ("Insured for free", GREEN),
        "safe": ("Never burns", GREEN),
        "first": ("First brew, free and can't burn", GREEN),
        "open": (f"Not insured, {roast['weights'][0]}% burn chance", GOLD),
    }[brew["insurance"]]
    card.text(122, 102, state, 16, color, "la", 2)
    card.text(604, 46, "You paid", 13, MUTED, "ra", 2)
    paid = f"{brew['paid']:,}" if brew["paid"] else "Free"
    card.text(604, 62, paid, 22, GOLD, "ra")
    card.icon("kit/bean", 574 - card.measure(paid, 22), 62, 26)
    left = f"{brew['beans']:,} left"
    card.text(604, 100, left, 15, MUTED, "ra", 2)
    return card.jpg()


def draw_sold(sale):
    """A strip for a sold brew: what it paid and why."""
    roast = ROAST_TYPES[sale["roast"]]
    tokens = sale["tokens"]
    card = Card.strip(sale.get("next"))
    label, fill, color = (
        ("BURNT", RED, WHITE)
        if not tokens
        else (
            ("PERFECT BREW", GOLD, (0, 0, 0))
            if sale["perfect"]
            else ("SOLD", GREEN, (0, 0, 0))
        )
    )
    card.tag(32, 12, label, fill, color)
    card.icon("ready" if tokens else "empty", 34, 44, 76)
    card.text(122, 44, roast["name"], 26)
    for row, (line, tint) in enumerate(sale["notes"][:2]):
        card.text(122, 82 + row * 20, card.fit(line, 16, 330), 16, tint, "la", 2)
    card.text(604, 46, "You earned", 13, MUTED, "ra", 2)
    earned = f"+{tokens}"
    card.text(604, 62, earned, 26, GOLD if tokens else MUTED, "ra")
    card.icon("kit/token", 570 - card.measure(earned, 26), 64, 28)
    card.text(604, 102, f"{sale['have']:,} Tokens now", 15, MUTED, "ra", 2)
    return card.jpg()


async def setup(bot):
    pass

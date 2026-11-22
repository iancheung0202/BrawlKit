import re
import time

from brawl.Currency.card import (
    BLACK,
    GOLD,
    GREEN,
    GREY,
    MUTED,
    RED,
    WHITE,
    Card,
    item_icon,
    plain,
)
from brawl.Currency.config import ITEM_STATIONS, LADDER
from brawl.Currency.helper import STORE_ITEMS

PER_PAGE = 6
SUPERCELL = "<:account:1486161374601154601>"
SORTS = {
    "Price: low to high": ("cost", False),
    "Price: high to low": ("cost", True),
    "Name: A to Z": ("name", False),
    "Name: Z to A": ("name", True),
}
FILTERS = {
    "All items": lambda item: True,
    "Bean items": lambda item: item["currency"] == "beans",
    "Token items": lambda item: item["currency"] == "tokens",
    "Effect items": lambda item: item["item"] is not None,
    "Supercell items": lambda item: item["supercell"],
}
UNITS = ((86400, "day"), (3600, "hour"), (60, "minute"))
TOKEN_WEIGHT = 1000


def every(seconds):
    size, unit = next((unit for unit in UNITS if seconds >= unit[0]), UNITS[-1])
    count = round(seconds / size)
    return f"Once every {count} {unit}s" if count != 1 else f"Once a {unit}"


def built_in():
    for item, data in STORE_ITEMS.items():
        cost, currency = data["price"].split()[:2]
        yield {
            "name": data["name"],
            "description": data["description"],
            "cost": int(cost),
            "currency": "tokens" if "token" in currency.lower() else "beans",
            "stock": -1,
            "item": item,
            "icon": item_icon(item),
            "cooldown": data.get("cooldown", 0),
            "station": ITEM_STATIONS.get(item, "effects"),
            "supercell": False,
            "role": None,
            "count": 10 if item.endswith("_10") else 1,
        }


MENTION = re.compile(r"<(@&|@!?|#)(\d+)>")
FINDERS = {"@&": "get_role", "@": "get_member", "@!": "get_member", "#": "get_channel"}


def clean(name):
    """Drops the emoji and separators the server puts in front of names."""
    return plain(name).lstrip("»┊|·-• ").strip() or "Unknown"


def words(guild, text):
    """Mentions cannot be drawn, so they become the name they point to."""

    def named(match):
        found = getattr(guild, FINDERS[match[1]])(int(match[2]))
        name = getattr(found, "display_name", None) or getattr(found, "name", "")
        return ("#" if match[1] == "#" else "") + clean(name) if found else ""

    return plain(MENTION.sub(named, str(text)))


def reward_icon(title, supercell=False):
    """Server rewards have no art of their own, so they share four icons."""
    if supercell:
        return "kit/icon_shop"
    if title.isdigit():
        return "kit/icon_role"
    return "kit/icon_xp" if re.search(r"\bXP\b", title) else "kit/icon_reward"


def custom(guild, rows):
    for row in rows or []:
        if not row:
            continue
        name, role = str(row[0]), None
        if name.isdigit():
            role = guild.get_role(int(name))
            name = clean(role.name) if role else "Unknown role"
        supercell = SUPERCELL in str(row[0])
        yield {
            "name": plain(name),
            "description": words(guild, row[1]),
            "cost": int(row[2]),
            "currency": str(row[3]).lower(),
            "stock": row[5] if len(row) > 5 else -1,
            "item": None,
            "icon": reward_icon(str(row[0]), supercell),
            "cooldown": 0,
            "station": "shop",
            "supercell": supercell,
            "role": role.id if role and row[4] is False else None,
            "count": 1,
        }


def listing(guild, rows, sort, show):
    key, reverse = SORTS[sort]
    items = [
        item for item in (*built_in(), *custom(guild, rows)) if FILTERS[show](item)
    ]

    def order(item):
        if key == "name":
            return item["name"].lower()
        return item["cost"] * (TOKEN_WEIGHT if item["currency"] == "tokens" else 1)

    items.sort(key=order, reverse=reverse)
    return [items[spot : spot + PER_PAGE] for spot in range(0, len(items), PER_PAGE)]


def span(seconds):
    size, unit = next((unit for unit in UNITS if seconds >= unit[0]), UNITS[-1])
    count = max(round(seconds / size), 1)
    return f"{count} {unit}{'s' * (count != 1)}"


def status(item, shop):
    """The tag on a tile, the line beside its price, and whether it can be bought."""
    key = item["item"]
    if item["station"] in shop["locked"]:
        return (f"LEVEL {LADDER[item['station']][0]}", GREY, WHITE), "", False
    if item["role"] in shop["owned"]:
        return ("OWNED", GREEN, BLACK), "", False
    if item["stock"] == 0:
        return ("SOLD OUT", RED, WHITE), "", False
    if key in shop["active"]:
        ends = f"Ends in {span(shop['active'][key] - time.time())}"
        return ("ACTIVE", GREEN, BLACK), ends, not shop["waits"].get(key)
    if shop["waits"].get(key):
        return None, f"Buy again in {span(shop['waits'][key])}", False
    if key in shop["today"]:
        left = max(shop["limit"] - shop["today"][key], 0)
        return None, f"{left} of {shop['limit']} left today", left >= item["count"]
    if item["stock"] > 0:
        return (f"{item['stock']} LEFT", GOLD, BLACK), "", True
    return None, every(item["cooldown"]) if item["cooldown"] else "", True


def draw_shop(shop):
    """Two columns of tiles: icon, name, what it does, a price button, one note."""
    items = shop["items"]
    rows = max(-(-len(items) // 2), 1)
    card = Card(900, 222 + rows * 132, shop["background"])
    card.title("SHOP", "Pay with Beans or Tokens. Buy an item with /buy.")
    beans, tokens = f"{shop['beans']:,}", f"{shop['tokens']:,}"
    left = card.width - 122 - card.measure(beans, 24) - card.measure(tokens, 24)
    card.pill(card.pill(left - 62, 38, "kit/bean", beans), 38, "kit/token", tokens)
    card.panel(26, 124, 848, 58 + rows * 132)
    card.tag(42, 112, shop["show"].upper())
    card.text(854, 136, f"Page {shop['page']} of {shop['pages']}", 17, GOLD, "ra", 2)
    if not items:
        card.text(450, 240, "Nothing matches this filter.", 20, MUTED, "mm", 2)
    for spot, item in enumerate(items):
        x, y = 42 + spot % 2 * 412, 174 + spot // 2 * 132
        tag, words, open_ = status(item, shop)
        card.slot(x, y, 404, 118)
        card.icon(item["icon"], x + 14, y + 14, 60)
        room = 302 - (card.measure(tag[0], 15) + 20 if tag else 0)
        card.text(
            x + 88,
            y + 8,
            card.fit(item["name"], 21, room),
            21,
            WHITE if open_ else MUTED,
        )
        for row, line in enumerate(card.wrap(item["description"], 14, 302)):
            card.text(x + 88, y + 37 + row * 18, line, 14, MUTED, "la", 2)
        short = shop[item["currency"]] < item["cost"]
        card.price(
            x + 88,
            y + 78,
            item["currency"],
            item["cost"],
            GREEN if open_ and not short else GREY,
            (255, 150, 150) if short and open_ else WHITE,
        )
        card.text(x + 390, y + 86, words, 14, MUTED, "ra", 2)
        if tag:
            card.tag(x + 396, y - 9, *tag, right=True)
    return card.jpg()


USE = {
    "star_drop": "Open it with /stardrop.",
    "star_drop_10": "Open them with /stardrop.",
    "mega_box": "Open it with /megabox.",
    "mega_box_10": "Open them with /megabox.",
    "message_pin": "Use it with /pin.",
    "custom_credit": "Use it with /customize.",
}
CLAIM = "Open a ticket to claim it."
ROLE = "The role is on your profile now."


def after(item):
    """What the member should know or do right after buying a shop item."""
    if item in USE:
        return USE[item]
    duration = STORE_ITEMS[item].get("duration", 0)
    if not duration:
        return "It took effect right away."
    size, unit = next(unit for unit in UNITS if duration >= unit[0])
    count = round(duration / size)
    return f"Active for {count} {unit}{'s' * (count != 1)}."


def draw_purchase(sale):
    """A strip: what was bought, what to do next, what it cost, what is left."""
    card = Card(640, 150, sale["background"])
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "PURCHASED", GREEN, BLACK)
    card.icon(sale["icon"], 34, 46, 68)
    card.text(120, 44, card.fit(sale["name"], 26, 300), 26)
    for row, line in enumerate(card.wrap(sale["next"], 16, 300)):
        card.text(120, 80 + row * 20, line, 16, MUTED, "la", 2)
    card.text(604, 42, "You paid", 13, MUTED, "ra", 2)
    paid = f"{sale['cost']:,}"
    card.text(604, 58, paid, 22, GOLD, "ra")
    card.icon(f"kit/{sale['currency'][:-1]}", 572 - card.measure(paid, 22), 58, 26)
    left = f"{sale[sale['currency']]:,} {sale['currency'].title()} left"
    card.text(604, 100, left, 15, MUTED, "ra", 2)
    return card.jpg()


async def setup(bot):
    pass

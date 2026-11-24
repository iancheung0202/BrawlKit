import re
import time

from brawl.Currency.card import BLACK, GOLD, GREEN, MUTED, Card, item_icon, plain
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
            "buy": data["name"],
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


# Server rewards have no art of their own, so they share these.
REWARD_ICONS = ("kit/icon_shop", "kit/icon_role", "kit/icon_xp", "kit/icon_reward")


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
            "buy": str(row[0]),
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
    """The small line under an item, and whether it can be bought."""
    key = item["item"]
    if item["station"] in shop["locked"]:
        return f"Unlocks at Level {LADDER[item['station']][0]}", False
    if item["role"] in shop["owned"]:
        return "You own this", False
    if item["stock"] == 0:
        return "Sold out", False
    if key in shop.get("held", ()):
        return "In your bag, start it with /use", False
    if key in shop["active"]:
        ends = f"Active, ends in {span(shop['active'][key] - time.time())}"
        return ends, not shop["waits"].get(key)
    if shop["waits"].get(key):
        return f"Buy again in {span(shop['waits'][key])}", False
    if key in shop["today"]:
        left = max(shop["limit"] - shop["today"][key], 0)
        return f"{left} of {shop['limit']} left today", left >= item["count"]
    if item["stock"] > 0:
        return f"{item['stock']} left in stock", True
    return every(item["cooldown"]) if item["cooldown"] else "", True


def short(item, shop):
    """How much more the member needs to pay for an item; 0 when they have enough."""
    return max(item["cost"] - shop[item["currency"]], 0)


def buyable(items, shop):
    """The items the member can pay for and buy right now."""
    return [item for item in items if status(item, shop)[1] and not short(item, shop)]


def row(item, shop, emote, reply):
    """One shop row as Discord text: picture and name, what it does, one small note."""
    note, open_ = status(item, shop)
    missing = short(item, shop)
    if open_ and missing:
        unit = item["currency"].title()[: -1 if missing == 1 else None]
        note = f"You need {missing:,} more {unit}"
    lines = [f"## {emote} {item['name']}", item["description"]]
    return "\n".join(lines + [f"-# {reply} {note}"] * bool(note))


USE = {
    "star_drop": "Open it with /stardrop.",
    "star_drop_10": "Open them with /stardrop.",
    "mega_box": "Open it with /megabox.",
    "mega_box_10": "Open them with /megabox.",
    "message_pin": "Use it with /pin.",
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


NEXT = {
    "message_pin": "Use /pin to pin a message",
    "reset_chat_cap": "Use /balance to view today's Beans",
    "thermometer_boost": "Use /thermometer to view the heat",
    "instant_brew": "Use /brew to start another",
}


def bought(item):
    """The `/how` page and the command to run next for an item just bought."""
    if item.startswith("star_drop"):
        return "rates", "Use /stardrop to open it"
    if item.startswith("mega_box"):
        return "rates", "Use /megabox to open it"
    return "effects", NEXT.get(item, "Use /use to start it")


def draw_purchase(sale):
    """A strip: what was bought, what to do next, what it cost, what is left."""
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "PURCHASED", GREEN, BLACK)
    card.icon(sale["icon"], 34, 46, 68)
    card.text(122, 44, card.fit(sale["name"], 26, 300), 26)
    for row, line in enumerate(card.wrap(sale["next"], 16, 300)):
        card.text(122, 82 + row * 20, line, 16, MUTED, "la", 2)
    card.text(604, 46, "You paid", 13, MUTED, "ra", 2)
    paid = f"{sale['cost']:,}"
    card.text(604, 62, paid, 22, GOLD, "ra")
    card.icon(f"kit/{sale['currency'][:-1]}", 572 - card.measure(paid, 22), 62, 26)
    left = f"{sale[sale['currency']]:,} {sale['currency'].title()} left"
    card.text(604, 102, left, 15, MUTED, "ra", 2)
    return card.jpg()


async def setup(bot):
    pass

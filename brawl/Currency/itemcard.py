import time

from brawl.Currency.card import (
    BLACK,
    GOLD,
    GREEN,
    GREY,
    MUTED,
    SCALE,
    WHITE,
    Card,
    icon,
    item_icon,
)
from brawl.Currency.helper import STORE_ITEMS

HELD = (
    ("star_drops", "Star Drop", "items/star_drop", "/stardrop"),
    ("mega_boxes", "Mega Box", "items/mega_box", "/megabox"),
    ("pins", "Message Pin", "items/message_pin", "/pin"),
    ("credits", "Credit", "items/custom_credit", "/customize"),
)
UNITS = ((86400, "day"), (3600, "hour"), (60, "minute"))


def plural(count, word):
    return f"{count:,} {word}{('es' if word.endswith('x') else 's') * (count != 1)}"


def ends(expires_at):
    left = max(expires_at - time.time(), 60)
    size, unit = next(unit for unit in UNITS if left >= unit[0])
    return f"ends in {plural(round(left / size), unit)}"


def lasts(seconds):
    size, unit = next(unit for unit in UNITS if seconds >= unit[0])
    return plural(round(seconds / size), unit)


def does(item):
    from brawl.Currency.howcard import EFFECTS

    return next(
        (text for _, _, items in EFFECTS for key, text in items if key == item), ""
    )


def item_rows(card, top, rows):
    """One row per effect item: its picture, its name and where it stands."""
    for row, (item, state, color) in enumerate(rows):
        y = top + row * 44
        card.icon(item_icon(item), 30, y, 36)
        card.text(78, y + 6, STORE_ITEMS[item]["name"], 20)
        card.text(606, y + 9, state, 16, color, "ra", 2)


def draw_inventory(member):
    """Tiles for what the member holds, then the bag and the effect items running."""
    held = member["held"]
    sections = [
        (name, color, rows)
        for name, color, rows in (
            (
                "BAG",
                GOLD,
                [(item, "Start it with /use", GOLD) for item in member.get("bag", ())],
            ),
            (
                "RUNNING",
                GREEN,
                [
                    (effect["item"], ends(effect["expires_at"]), MUTED)
                    for effect in member["effects"]
                ],
            ),
        )
        if rows
    ]
    height = sum(46 + len(rows) * 44 for _, _, rows in sections) or 64
    card = Card(640, 218 + height, member["background"])
    card.text(20, 12, "Inventory", 30)
    for spot, (key, name, picture, command) in enumerate(HELD):
        x, count = 16 + spot * 153, held.get(key) or 0
        card.slot(x, 58, 147, 96)
        image = icon(picture, 40)
        card.paste(image, x + 73 - image.width / SCALE / 2, 65)
        card.text(
            x + 73, 120, plural(count, name), 16, WHITE if count else GREY, "mm", 2
        )
        card.text(x + 73, 140, command, 13, MUTED if count else GREY, "mm", 2)
    top = 178
    if not sections:
        card.panel(16, 166, 608, 64)
        card.text(
            36,
            186,
            "No effect items yet. They boost your Beans and brews.",
            18,
            MUTED,
            "la",
            2,
        )
    for name, color, rows in sections:
        card.panel(16, top, 608, 26 + len(rows) * 44)
        card.tag(32, top - 12, name, color, BLACK)
        item_rows(card, top + 16, rows)
        top += 46 + len(rows) * 44
    card.text(20, card.height - 38, "Find more items in /shop.", 16, GOLD, "la", 2)
    return card.jpg()


def draw_bag(bag):
    """What is waiting in the bag: each item, what it does and how long it lasts."""
    items = bag["items"]
    card = Card(640, 96 + len(items) * 44, bag["background"])
    card.text(20, 12, "Bag", 30)
    card.text(620, 24, "Starts when you use it", 16, MUTED, "ra", 2)
    card.panel(16, 58, 608, 20 + len(items) * 44)
    item_rows(
        card,
        70,
        [(item, lasts(STORE_ITEMS[item]["duration"]), GREEN) for item in items],
    )
    for row, item in enumerate(items):
        x = 90 + card.measure(STORE_ITEMS[item]["name"], 20)
        card.text(
            x, 70 + row * 44 + 10, card.fit(does(item), 15, 500 - x), 15, MUTED, "la", 2
        )
    return card.jpg()


def draw_started(item):
    """A strip for an effect item that just started."""
    card = Card.strip()
    card.tag(32, 12, "STARTED", GREEN, BLACK)
    card.icon(item["icon"], 34, 46, 68)
    card.text(122, 44, card.fit(item["name"], 26, 300), 26)
    held = item.get("heat")
    line = f"Thermometer held at {held}" if held is not None else "Working for you now"
    card.text(122, 82, line, 16, MUTED, "la", 2)
    card.text(604, 46, "Lasts", 13, MUTED, "ra", 2)
    card.text(604, 62, item["lasts"], 22, GREEN, "ra")
    return card.jpg()


async def setup(bot):
    pass

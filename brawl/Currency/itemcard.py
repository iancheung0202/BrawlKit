import time

from brawl.Currency.card import GOLD, GREY, MUTED, SCALE, WHITE, Card, icon, item_icon

HELD = (
    ("star_drops", "Star Drop", "kit/icon_ranked_starr_drop", "/stardrop"),
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


def draw_inventory(member):
    """Tiles for what the member holds, then one row per active effect item."""
    effects, held = member["effects"], member["held"]
    rows = max(len(effects), 1)
    card = Card(640, 238 + rows * 44, member["background"])
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
    card.panel(16, 166, 608, 20 + rows * 44)
    if not effects:
        card.text(36, 186, "No effect items are active.", 18, MUTED, "la", 2)
    for row, effect in enumerate(effects):
        y = 178 + row * 44
        card.icon(item_icon(effect["item"]), 30, y, 36)
        card.text(78, y + 6, effect["name"], 20)
        card.text(606, y + 9, ends(effect["expires_at"]), 16, MUTED, "ra", 2)
    card.text(20, card.height - 38, "Find more items in /shop.", 16, GOLD, "la", 2)
    return card.jpg()


async def setup(bot):
    pass

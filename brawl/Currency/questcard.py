import time

from brawl.Currency.card import BLUE, GOLD, GREEN, MUTED, WHITE, Card

UNITS = ((86400, "day"), (3600, "hour"), (60, "minute"))
TAGS = {
    "daily": ("TODAY'S ORDER", GOLD, (0, 0, 0)),
    "weekly": ("WEEKLY QUESTS", BLUE, WHITE),
    "monthly": ("MONTHLY QUESTS", GREEN, (0, 0, 0)),
}
ROW, HEAD, FOOT, GAP = 54, 46, 40, 26


def resets(end_time):
    left = max(end_time - time.time(), 60)
    size, unit = next(unit for unit in UNITS if left >= unit[0])
    count = round(left / size)
    return f"Resets in {count} {unit}{'s' * (count != 1)}"


def tall(section):
    return HEAD + max(len(section["tasks"]), 1) * ROW + FOOT


def draw_quests(member):
    """One panel per quest list: its tasks, when it resets and what it pays."""
    sections = member["sections"]
    height = 30 + sum(tall(section) + GAP for section in sections)
    height += 62 if member["locked"] else 0
    card = Card(640, height + 24, member["background"])
    y = 30
    for section in sections:
        label, fill, color = TAGS[section["kind"]]
        card.panel(16, y, 608, tall(section))
        card.tag(32, y - 12, label, fill, color)
        card.text(604, y + 14, resets(section["end_time"]), 15, MUTED, "ra", 2)
        if not section["tasks"]:
            card.text(
                36,
                y + HEAD + 12,
                (
                    "Clock in at the store to get today's order."
                    if section["kind"] == "daily"
                    else "Nothing to do here right now."
                ),
                18,
                MUTED,
                "la",
                2,
            )
        for row, task in enumerate(section["tasks"]):
            card.task(34, y + HEAD + row * ROW, 572, *task)
        card.text(36, y + tall(section) - 32, section["reward"], 15, GOLD, "la", 2)
        y += tall(section) + GAP
    if member["locked"]:
        card.panel(16, y - 8, 608, 50)
        card.text(36, y + 6, member["locked"], 17, MUTED, "la", 2)
    return card.jpg()


async def setup(bot):
    pass

from brawl.Currency.card import GOLD, GREEN, GREY, MUTED, WHITE, Card, named, plain
from brawl.Currency.config import TABLE_QUEST_TYPES, TABLE_SEATS, TABLE_SEATS_NEEDED

QUEST = TABLE_QUEST_TYPES["bean_collector"]


def rgb(color):
    """'#fa0' or '#ffaa00' as the tuple the card draws with."""
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(part * 2 for part in color)
    return tuple(int(color[spot : spot + 2], 16) for spot in (0, 2, 4))


def short(beans):
    return f"{beans // 1000}k" if beans % 1000 == 0 else f"{beans:,}"


def quest(card, y, table):
    """The weekly Bean quest as a timeline: a bar with a stop at each step."""
    beans, done = table["weekly_beans"], table["tier"]
    targets = QUEST["targets"]
    left, width = 56, 508
    card.bar(left, y + 30, width, 16, beans / targets[-1])
    for step, (target, reward) in enumerate(zip(targets, QUEST["rewards"])):
        x = left + width * target / targets[-1]
        color = GREEN if step < done else GOLD if step == done else GREY
        card.text(x, y, short(target), 16, color, "ma", 2)
        card.check(x - 13, y + 25, step < done)
        text = f"+{reward:,}"
        half = (card.measure(text, 14) + 20) / 2
        card.icon("kit/bean", x - half, y + 60, 18)
        card.text(x - half + 20, y + 60, text, 14, color, "la", 2)


def draw_table(table):
    """One table: who sits there, this week's Beans and the shared quest."""
    color = rgb(table["color"])
    seats = table["members"]
    rows = (len(seats) + 1) // 2
    recognized = len(seats) >= TABLE_SEATS_NEEDED
    top = 208 if recognized else 150
    card = Card(640, top + 30 + rows * 44 + 24, table["background"])
    card.panel(16, 24, 608, card.height - 40)
    card.tag(32, 12, table.get("tag", "TABLE"), color, WHITE)
    card.text(36, 42, card.fit(plain(table["name"]), 30, 380), 30)
    motto = card.fit(f"\"{plain(table['motto'])}\"", 15, 380)
    card.text(36, 82, motto, 15, MUTED, "la", 2)
    beans = f"{table['weekly_beans']:,}"
    card.text(604, 48, beans, 28, GOLD, "ra")
    card.icon("kit/bean", 566 - card.measure(beans, 28), 46, 34)
    card.text(604, 84, "this week", 13, MUTED, "ra", 2)
    if recognized:
        quest(card, 112, table)
    else:
        label = f"{len(seats)} / {TABLE_SEATS_NEEDED} seats to start the quest"
        card.bar(36, 112, 568, 24, len(seats) / TABLE_SEATS_NEEDED, color, label)
    card.text(36, top, "Seated", 17, WHITE, "la", 2)
    card.text(604, top + 2, f"{len(seats)} / {TABLE_SEATS}", 14, MUTED, "ra", 2)
    for spot, (name, share, host, you, avatar) in enumerate(seats):
        x, y = 36 + spot % 2 * 288, top + 30 + spot // 2 * 44
        card.slot(x, y, 280, 38, GOLD if you else (0, 0, 0))
        card.avatar(avatar, x + 8, y + 6, 26, 6)
        name = card.fit(named(name), 16, 110 if host else 150)
        card.text(x + 44, y + 9, name, 16, WHITE, "la", 2)
        if host:
            card.text(
                x + 52 + card.measure(name, 16), y + 11, "HOST", 12, color, "la", 2
            )
        card.text(x + 268, y + 10, f"{share:,}", 15, GOLD if share else GREY, "ra", 2)
    return card.jpg()


def draw_table_reward(reward):
    """A strip sent to each member when their table is paid."""
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, reward["tag"], rgb(reward["color"]), WHITE)
    card.icon(f"kit/{reward['currency']}", 34, 46, 72)
    card.text(122, 44, reward["headline"], 24, GOLD)
    for row, line in enumerate(card.wrap(reward["line"], 15, 470)):
        card.text(122, 82 + row * 19, line, 15, MUTED, "la", 2)
    return card.jpg()


async def setup(bot):
    pass

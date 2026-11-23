from brawl.Currency.card import (
    GOLD,
    GREEN,
    GREY,
    MUTED,
    WHITE,
    Card,
    gain,
    named,
    plain,
)
from brawl.Currency.config import (
    TABLE_QUEST_TYPES,
    TABLE_SEATS,
    TABLE_SEATS_NEEDED,
    TABLE_WINNER_STAMPS,
    TABLE_WINNER_TOKENS,
)

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
    card.text(36, y - 24, "Weekly quest", 13, GOLD, "la", 2)
    card.text(
        46 + card.measure("Weekly quest", 13),
        y - 24,
        "Beans the table earns, and what each member gets",
        13,
        MUTED,
        "la",
        2,
    )
    left, width = 44, 524
    card.bar(left, y + 30, width, 16, beans / targets[-1])
    for step, (target, reward) in enumerate(zip(targets, QUEST["rewards"])):
        x = left + width * target / targets[-1]
        color = GREEN if step < done else GOLD if step == done else GREY
        card.text(x, y, short(target), 16, color, "ma", 2)
        card.stop(x - 13, y + 25, step < done)
        text = f"+{reward:,}"
        half = (card.measure(text, 14) + 20) / 2
        card.icon("kit/bean", x - half, y + 60, 18)
        card.text(x - half + 20, y + 60, text, 14, color, "la", 2)


def top_prize(card, y):
    """What every member of the week's top table gets."""
    card.icon("kit/icon_trophy", 36, y - 4, 26)
    card.text(78, y, "Top table of the week", 15, WHITE, "la", 2)
    x = 604
    card.text(x, y + 1, "each", 13, MUTED, "ra", 2)
    x -= card.measure("each", 13) + 10
    for picture, amount in (
        ("kit/icon_ranked_round_token", TABLE_WINNER_STAMPS),
        ("kit/token", TABLE_WINNER_TOKENS),
    ):
        card.text(x, y - 2, f"+{amount}", 17, GOLD, "ra")
        x -= card.measure(f"+{amount}", 17) + 26
        card.icon(picture, x, y - 2, 22)
        x -= 12


def draw_table(table):
    """One table: who sits there, this week's Beans and the shared quest."""
    color = rgb(table["color"])
    seats = table["members"]
    rows = (len(seats) + 1) // 2
    recognized = len(seats) >= TABLE_SEATS_NEEDED
    top = 276 if recognized else 318
    card = Card(640, top + 30 + rows * 44 + 24, table["background"])
    card.panel(16, 24, 608, card.height - 40)
    card.tag(32, 12, table.get("tag", "TABLE"), color, WHITE)
    card.text(36, 42, card.fit(plain(table["name"]), 30, 380), 30)
    motto = card.fit(f"\"{plain(table['motto'])}\"", 15, 380)
    card.text(36, 82, motto, 15, MUTED, "la", 2)
    beans = f"{table['weekly_beans']:,}"
    card.text(604, 48, beans, 28, GOLD, "ra")
    card.icon("kit/bean", 566 - card.measure(beans, 28), 46, 34)
    card.text(604, 84, "total this week", 13, MUTED, "ra", 2)
    if recognized:
        quest(card, 136, table)
        top_prize(card, 236)
    else:
        label = f"{len(seats)} / {TABLE_SEATS_NEEDED} seats to start the quest"
        card.bar(36, 112, 568, 24, len(seats) / TABLE_SEATS_NEEDED, color, label)
        quest(card, 178, {"weekly_beans": 0, "tier": -1})
        top_prize(card, 278)
    card.text(36, top, "Seated", 17, WHITE, "la", 2)
    card.text(604, top + 2, f"{len(seats)} / {TABLE_SEATS}", 14, MUTED, "ra", 2)
    for spot, (name, share, host, you, avatar) in enumerate(seats):
        x, y = 36 + spot % 2 * 288, top + 30 + spot // 2 * 44
        card.slot(x, y, 280, 38)
        card.avatar(avatar, x + 8, y + 6, 26, 6)
        tags = [
            (tag, tint)
            for tag, on, tint in (("HOST", host, color), ("YOU", you, MUTED))
            if on
        ]
        room = 150 - sum(card.measure(tag, 12) + 8 for tag, _ in tags)
        name = card.fit(named(name), 16, room)
        card.text(x + 44, y + 9, name, 16, GOLD if you else WHITE, "la", 2)
        at = x + 52 + card.measure(name, 16)
        for tag, tint in tags:
            card.text(at, y + 11, tag, 12, tint, "la", 2)
            at += card.measure(tag, 12) + 8
        card.text(x + 268, y + 10, f"{share:,}", 15, GOLD if share else GREY, "ra", 2)
    return card.jpg()


def draw_no_table(member):
    """For a member with no seat: what a table pays and how to get one."""
    card = Card(640, 318, member["background"])
    card.panel(16, 24, 608, 278)
    card.tag(32, 12, "TABLE", GOLD)
    card.text(36, 42, "You have no table yet", 28)
    line = f"Sit with {TABLE_SEATS_NEEDED} or more members. Beans you all earn in chat pay everyone."
    card.text(36, 80, line, 14, MUTED, "la", 2)
    quest(card, 136, {"weekly_beans": 0, "tier": 0})
    top_prize(card, 236)
    card.text(
        36,
        270,
        "Join one with /table seat, or start one with /table reserve",
        14,
        GOLD,
        "la",
        2,
    )
    return card.jpg()


def draw_table_reward(reward):
    """A strip sent to each member when their table is paid."""
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, reward["tag"], rgb(reward["color"]), WHITE)
    card.icon(f"kit/{reward['currency']}", 34, 46, 72)
    card.text(122, 44, reward["headline"], 24, GOLD)
    x = 138 + card.measure(reward["headline"], 24)
    for picture, amount in reward.get("more", ()):
        if amount:
            card.icon(picture, x, 44, 28)
            card.text(x + 34, 44, gain(picture, amount), 24, GOLD)
            x += 50 + card.measure(gain(picture, amount), 24)
    for row, line in enumerate(card.wrap(reward["line"], 15, 470)):
        card.text(122, 82 + row * 19, line, 15, MUTED, "la", 2)
    return card.jpg()


async def setup(bot):
    pass

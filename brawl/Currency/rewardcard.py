from brawl.Currency.card import BLUE, GOLD, GREEN, MUTED, SCALE, WHITE, Card, box
from brawl.Currency.config import (
    DAILY_BEANS,
    ROAST_TYPES,
    TUTORIAL_BEANS,
    TUTORIAL_TOKENS,
)

BLACK = (0, 0, 0)
SHIFT = ["Brew your first coffee", "Sell it", "Clock in"]
PASSES = {
    "brawl_pass": "kit/icon_brawl_pass",
    "brawl_pass_plus": "kit/icon_brawl_pass_plus",
}


def gains(card, x, y, rewards, size=26):
    """Rewards side by side, each as its icon and a +amount."""
    for picture, amount in rewards:
        label = f"+{amount:,}"
        card.icon(picture, x, y + 2, size + 2)
        card.text(x + size + 10, y, label, size, GOLD)
        x += size + 28 + card.measure(label, size)
    return x


def tasks(card, y, order, extra=0):
    card.panel(16, y, 608, 30 + len(order) * 56 + extra)
    card.tag(32, y - 12, "TODAY'S ORDER")
    card.next_order(604, y + 8, "ra")
    for row, (name, state, done, part) in enumerate(order):
        card.task(36, y + 42 + row * 56, 568, name, state, done, part)


def week(card, x, y, streak):
    """Seven dots for the week of the streak; the seventh pays 4x."""
    day = (streak - 1) % 7 + 1
    for spot in range(1, 8):
        fill = GOLD if spot <= day else (40, 50, 110)
        card.draw.ellipse(
            box(x + (spot - 1) * 24, y, 16, 16),
            fill=fill,
            outline=BLACK,
            width=2 * SCALE,
        )


def draw_clock_in(shift):
    """The reward for clocking in, the streak, and the order it started."""
    order = shift["tasks"]
    card = Card(640, 150 + (72 + len(order) * 56) * bool(order), shift["background"])
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "CLOCKED IN", GREEN)
    rewards = [("kit/bean", shift["beans"])]
    if shift["tokens"]:
        rewards.append(("kit/token", shift["tokens"]))
    gains(card, 36, 46, rewards, 30)
    for row, note in enumerate(shift["notes"][:2]):
        card.text(36, 90 + row * 19, card.fit(note, 15, 340), 15, MUTED, "la", 2)
    streak = shift["streak"]
    card.text(604, 44, f"{streak}-day streak", 22, WHITE, "ra")
    week(card, 444, 80, streak)
    left = 7 - (streak - 1) % 7 - 1
    card.text(
        604,
        104,
        "4x Beans today" if not left else f"4x Beans in {left} day{'s' * (left != 1)}",
        14,
        GOLD if not left else MUTED,
        "ra",
        2,
    )
    if order:
        tasks(card, 162, order, 14)
    return card.jpg()


def draw_order(progress):
    """Today's Order after a task moved: where it stands and what it paid."""
    order = progress["tasks"]
    card = Card(640, 126 + len(order) * 56)
    tasks(card, 24, order, 56)
    y = 68 + len(order) * 56 - 6
    rewards = [("kit/bean", progress["beans"])] if progress["beans"] else []
    if progress["stamp"]:
        rewards.append(("kit/icon_ranked_round_token", 1))
    card.text(
        36,
        y + 6,
        "Order complete" if progress["stamp"] else "You earned",
        17,
        MUTED,
        "la",
        2,
    )
    width = sum(48 + card.measure(f"+{amount:,}", 20) for _, amount in rewards) - 28
    gains(card, 604 - width, y + 2, rewards, 20)
    return card.jpg()


def draw_shift(shift):
    """The first shift: three steps, the one to do now, and the Tokens at the end."""
    step, done = shift["step"], shift["step"] > len(SHIFT)
    card = Card(640, 226)
    card.panel(16, 24, 608, 186)
    card.tag(
        32,
        12,
        "FIRST SHIFT DONE" if done else "YOUR FIRST SHIFT",
        GREEN if done else BLUE,
        BLACK if done else WHITE,
    )
    for row, name in enumerate(SHIFT):
        y = 56 + row * 48
        card.check(36, y, row + 1 < step)
        now = row + 1 == step
        card.text(
            78,
            y - 1,
            name,
            22,
            MUTED if row + 1 < step else GOLD if now else WHITE,
            "la",
            2,
        )
        if now:
            card.tag(92 + card.measure(name, 22), y + 2, "NOW")
    card.icon("kit/token", 506, 50, 52)
    card.text(532, 108, f"+{TUTORIAL_TOKENS} Tokens", 20, GOLD, "ma")
    card.text(532, 136, f"+{TUTORIAL_BEANS + DAILY_BEANS:,} Beans", 20, GOLD, "ma")
    card.text(
        532,
        168,
        "Paid" if done else "for your first shift",
        14,
        GREEN if done else MUTED,
        "ma",
        2,
    )
    return card.jpg()


def draw_level_up(member):
    """A strip posted in chat when a member levels up."""
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "LEVEL UP", BLUE, WHITE)
    card.avatar(member["avatar"], 34, 44, 76)
    card.text(126, 42, card.fit(member["name"], 20, 280), 20, MUTED, "la", 2)
    card.icon("kit/icon_xp", 122, 68, 44)
    card.text(172, 70, f"Level {member['level']}", 32, GOLD)
    rewards = [("kit/bean", member["beans"])]
    if member["tokens"]:
        rewards.append(("kit/token", member["tokens"]))
    width = sum(50 + card.measure(f"+{amount:,}", 22) for _, amount in rewards) - 28
    gains(card, 604 - width, 44, rewards, 22)
    for row, (label, name) in enumerate(member["unlocks"][:2]):
        card.text(
            604, 82 + row * 20, card.fit(f"{label} {name}", 15, 230), 15, GREEN, "ra", 2
        )
    return card.jpg()


def draw_redeemed(sale):
    """A strip for a redeemed pass: what it cost and what is left."""
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "REDEEMED", GREEN)
    card.icon(PASSES[sale["tier"]], 34, 44, 76)
    card.text(196, 44, sale["name"], 26)
    x = 196
    for picture, amount in (
        ("kit/icon_ranked_round_token", sale["stamps"]),
        ("kit/token", sale["cost"]),
    ):
        card.icon(picture, x, 86, 26)
        card.text(x + 32, 88, f"{amount:,}", 19, GOLD)
        x += 54 + card.measure(f"{amount:,}", 19)
    card.text(604, 46, "You have left", 13, MUTED, "ra", 2)
    x = 604
    for picture, amount in (
        ("kit/token", sale["tokens"]),
        ("kit/icon_ranked_round_token", sale["left"]),
    ):
        label = f"{amount:,}"
        card.text(x, 66, label, 20, WHITE, "ra")
        x -= card.measure(label, 20) + 30
        card.icon(picture, x, 66, 24)
        x -= 14
    card.text(
        604,
        104,
        f"Pass {sale['month']} of {sale['limit']} this month",
        14,
        MUTED,
        "ra",
        2,
    )
    return card.jpg()


def draw_ready(brew):
    """The Sell Alarm strip sent when a brew finishes."""
    roast = ROAST_TYPES.get(brew["roast"], ROAST_TYPES["light"])
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "BREW READY", GREEN)
    card.icon("ready", 34, 44, 76)
    card.text(124, 44, roast["name"], 26)
    card.text(124, 84, "Sell it to collect your Tokens", 17, MUTED, "la", 2)
    best = max(roast["payout"])
    card.text(604, 46, "Pays up to", 13, MUTED, "ra", 2)
    card.text(604, 62, f"{best}", 26, GOLD, "ra")
    card.icon("kit/token", 570 - card.measure(f"{best}", 26), 64, 28)
    return card.jpg()


async def setup(bot):
    pass

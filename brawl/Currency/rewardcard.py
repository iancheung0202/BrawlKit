import time

from brawl.Currency.card import (
    BLUE,
    GOLD,
    GREEN,
    GREY,
    MUTED,
    RED,
    SCALE,
    WHITE,
    Card,
    box,
)
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
    # Work done before clocking in is paid now, so the order shows what it paid.
    pay = shift.get("order")
    extra = 42 if pay else 0
    card = Card(
        640, 150 + (72 + len(order) * 56 + extra) * bool(order), shift["background"]
    )
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
        tasks(card, 162, order, 14 + extra)
        if pay:
            order_pay(card, 206 + len(order) * 56 - 6, pay)
    return card.jpg()


def order_pay(card, y, progress):
    """Under the tasks: what the order just paid."""
    rewards = [("kit/bean", progress["beans"])] if progress["beans"] else []
    if progress["stamp"]:
        rewards.append(("kit/icon_ranked_round_token", 1))
    card.text(
        36,
        y + 6,
        done_label(progress) if progress["stamp"] else "You earned",
        17,
        GREEN if progress.get("redeem") else MUTED,
        "la",
        2,
    )
    width = sum(48 + card.measure(f"+{amount:,}", 20) for _, amount in rewards) - 28
    gains(card, 604 - width, y + 2, rewards, 20)


def draw_order(progress):
    """Today's Order after a task moved: where it stands and what it paid."""
    order = progress["tasks"]
    card = Card(640, 126 + len(order) * 56)
    tasks(card, 24, order, 56)
    order_pay(card, 68 + len(order) * 56 - 6, progress)
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


def done_label(order):
    """What a finished order says: the pass to redeem, once there are Stamps for it."""
    if order.get("redeem"):
        return f"{order['redeem']} ready, use /redeem"
    return "Order complete"


def earned(order):
    rewards = [("kit/bean", order["beans"])]
    if order["stamp"]:
        rewards.append(("kit/icon_ranked_round_token", 1))
    return rewards


def right(card, y, rewards, size):
    """Rewards ending at the right edge of a strip."""
    width = sum(size + 28 + card.measure(f"+{n:,}", size) for _, n in rewards) - 18
    gains(card, 604 - width, y, rewards, size)


def draw_paid(order):
    """A strip for an order that finished with no other card to carry it."""
    pass_name = order.get("redeem")
    card = Card.strip(
        pass_name and f"Redeem your {pass_name} with /redeem.", small=True
    )
    card.tag(32, 12, "TODAY'S ORDER")
    card.avatar(order["avatar"], 34, 40, 52)
    card.text(100, 40, card.fit(order["name"], 16, 260), 16, MUTED, "la", 2)
    done = order["stamp"]
    card.text(
        100, 62, "Order complete" if done else "Task done", 26, GREEN if done else WHITE
    )
    card.text(604, 42, "You earned", 13, MUTED, "ra", 2)
    right(card, 62, earned(order), 22)
    return card.jpg()


def draw_chat(reward):
    """A strip posted when chatting pays Beans: the gain and today's limit."""
    order = reward.get("order")
    card = Card.strip(foot=bool(order), small=True)
    card.tag(32, 12, "CHAT BEANS", GOLD)
    card.avatar(reward["avatar"], 34, 40, 52)
    card.text(100, 40, card.fit(reward["name"], 16, 180), 16, MUTED, "la", 2)
    gain = f"+{reward['beans']:,}"
    card.icon("kit/bean", 98, 62, 30)
    card.text(134, 62, gain, 26, GOLD)
    if reward["boosted"]:
        card.icon("items/effect", 142 + card.measure(gain, 26), 64, 26)
    done = reward["today"] >= reward["limit"]
    color = GREEN if done else GOLD
    left = max(0, int(reward["reset"] - time.time())) // 60
    card.icon("kit/icon_clock", 300, 44, 15)
    card.text(322, 42, f"{left // 60}h {left % 60}m", 13, MUTED, "la", 2)
    count = f"{reward['today']:,} / {reward['limit']:,}"
    card.text(604, 40, count, 17, color, "ra", 2)
    card.bar(300, 66, 304, 20, reward["today"] / reward["limit"], color)
    if order:
        label = done_label(order) if order["stamp"] else "Order task done"
        card.text(36, card.foot, label, 15, GREEN if order["stamp"] else GOLD, "la", 2)
        right(card, card.foot - 2, earned(order), 15)
    return card.jpg()


def draw_level_up(member):
    """A strip posted in chat when a member levels up."""
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "LEVEL UP", BLUE, WHITE)
    card.avatar(member["avatar"], 34, 44, 76)
    card.text(122, 42, card.fit(member["name"], 20, 280), 20, MUTED, "la", 2)
    card.icon("kit/icon_xp", 122, 68, 44)
    card.text(172, 70, f"Level {member['level']}", 32, GOLD)
    rewards = [("kit/bean", member["beans"])]
    if member["tokens"]:
        rewards.append(("kit/token", member["tokens"]))
    right(card, 44, rewards, 22)
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
        102,
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
    card = Card.strip(brew.get("next"), small=True)
    card.tag(32, 12, "BREW READY", GREEN)
    card.icon("ready", 34, 40, 52)
    card.text(100, 40, "From your Sell Alarm", 16, MUTED, "la", 2)
    card.text(100, 62, roast["name"], 26)
    best = max(roast["payout"])
    card.text(604, 42, "Pays up to", 13, MUTED, "ra", 2)
    card.text(604, 62, f"{best}", 22, GOLD, "ra")
    card.icon("kit/token", 572 - card.measure(f"{best}", 22), 62, 26)
    return card.jpg()


def draw_topic(topic):
    """The strip a member is sent when staff approve or turn down their topic."""
    approved = topic["approved"]
    card = Card.strip(
        "It now shows up in /topic with your name."
        if approved
        else "Suggest another one from /topic."
    )
    card.tag(
        32,
        12,
        "TOPIC APPROVED" if approved else "TOPIC TURNED DOWN",
        GREEN if approved else RED,
        BLACK if approved else WHITE,
    )
    card.icon("kit/icon_chat", 34, 52, 52)
    width = 380 if approved else 500
    card.text(100, 44, "Your topic", 14, MUTED, "la", 2)
    for row, line in enumerate(card.wrap(topic["text"], 19, width)):
        card.text(100, 64 + row * 26, line, 19)
    if approved:
        card.text(604, 52, "You earned", 13, MUTED, "ra", 2)
        right(card, 72, [("kit/bean", topic["beans"])], 24)
    return card.jpg()


async def setup(bot):
    pass

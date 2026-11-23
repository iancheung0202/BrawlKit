import time

from brawl.Currency.card import (
    BACKGROUND,
    BLUE,
    GOLD,
    GREEN,
    MUTED,
    NAME_WIDTH,
    WHITE,
    Card,
)
from brawl.Currency.config import (
    BACKGROUNDS,
    REFERRAL_BRIDGE_STAMPS,
    REFERRAL_TRAINEE_STAMPS,
    ROAST_TYPES,
    STAMP_BOX_EVERY,
    STAMP_BOXES,
    STAMP_GOALS,
    STAMP_MONTHLY_LIMIT,
    STAMP_PRICE_STREAK,
    TABLE_WINNER_STAMPS,
    TABLE_WINNER_TOKENS,
    THERMOMETER_LEVELS,
)
from brawl.Currency.db import u_background
from brawl.Currency.heat import level_of
from brawl.Currency.ladder import next_unlock
from brawl.Currency.stationcard import HEAT, flame

STAMP_ROW = 15


def clock(seconds):
    hours, minutes = divmod(int(seconds) // 60, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def draw_order(card, tasks, store):
    card.panel(26, 118, 414, 250)
    card.tag(42, 106, "TODAY'S ORDER")
    if not tasks:
        card.icon("kit/icon_inbox", 198, 158, 70)
        card.text(233, 252, "Clock in to get today's order", 23, WHITE, "ma", 2)
        return card.text(
            233,
            290,
            card.fit(f"Press Clock In in #{store}", 18, 370),
            18,
            GOLD,
            "ma",
            2,
        )
    done = sum(task[2] for task in tasks)
    card.text(420, 132, f"{done} of {len(tasks)} done", 20, GOLD, "ra")
    card.icon("kit/icon_ranked_round_token", 46, 337, 20)
    card.text(72, 340, "Complete all for 1 Stamp", 14, GOLD, "la", 2)
    for row, (name, state, finished, part) in enumerate(tasks):
        card.task(46, 166 + row * 58, 374, name, state, finished, part)
    card.next_order(420, 340, "ra")


def draw_brew(card, brew, unlocked):
    card.panel(460, 118, 414, 250)
    card.tag(476, 106, "BREW STATION", BLUE, WHITE)
    if not unlocked:
        card.icon("empty", 482, 162, 110)
        card.text(606, 176, "Locked", 26, MUTED)
        card.text(606, 212, "Opens at Level 1", 19, MUTED, "la", 2)
        return card.text(482, 326, "Chat to level up", 17, GOLD, "la", 2)
    if not brew:
        card.icon("empty", 482, 162, 110)
        card.text(606, 176, "Nothing brewing", 26)
        card.text(606, 212, "Beans turn into Tokens here", 19, MUTED, "la", 2)
        return card.text(482, 326, "Use /brew to start one", 17, GOLD, "la", 2)
    roast = ROAST_TYPES[brew["roast_type"]]
    left = brew["end_time"] - time.time()
    ready = left <= 0
    card.icon("ready" if ready else "brewing", 482, 162, 110)
    card.text(606, 160, roast["name"], 26)
    card.text(
        606,
        196,
        "Ready to sell!" if ready else f"Ready in {clock(left)}",
        19,
        GREEN if ready else MUTED,
        "la",
        2,
    )
    card.bar(606, 228, 246, 22, 1 if ready else 1 - left / roast["time"], GREEN)
    if brew.get("insured"):
        card.text(606, 260, "Insured", 16, GREEN, "la", 2)
    hint = "Use /sell to collect your Tokens" if ready else "Come back when it is ready"
    card.text(482, 326, hint, 17, GOLD, "la", 2)


def draw_heat(card, heat, beans):
    """One row: the thermometer now, what a message pays, and what it paid today."""
    level = level_of(min(heat, 100))
    tint = HEAT[level[1]]
    card.panel(26, 388, 848, 68)
    card.tag(42, 376, "THERMOMETER", tint)
    card.icon(flame(level), 44, 404, 40)
    card.text(94, 410, level[1], 24, tint)
    x = 116 + card.measure(level[1], 24)
    pay = level[2] or THERMOMETER_LEVELS[-2][2]
    card.icon("kit/bean", x, 399, 24)
    line = (
        f"+{pay} a message, no daily limit"
        if level[2]
        else f"+{pay} a message when Warm"
    )
    card.text(x + 30, 400, line, 18, GOLD if level[2] else WHITE, "la", 2)
    card.text(x, 428, "Extra Beans, outside the chat task", 14, MUTED, "la", 2)
    gain = f"+{beans:,} today"
    card.text(854, 411, gain, 19, GOLD, "ra", 2)
    card.icon("kit/bean", 822 - card.measure(gain, 19), 409, 26)


def draw_home(member):
    card = Card(900, 512, member["background"])
    under = card.header(
        member["name"],
        member["avatar"],
        member["level"],
        member["xp"],
        member["xp_needed"],
        member["beans"],
        member["tokens"],
        member["stamps"],
    )
    card.text(under, 91, next_unlock(member["level"]), 12, MUTED, "la", 2)
    if member.get("rep"):
        x = 130 + card.measure(card.fit(member["name"], 32, NAME_WIDTH), 32)
        card.icon("kit/icon_like", x, 27, 26)
        card.text(x + 32, 27, f"{member['rep']:,}", 20, WHITE, "la", 2)
    draw_order(card, member["tasks"], member.get("store", "the store"))
    card.icon("kit/icon_calendar", 44, 132, 20)
    card.text(70, 136, f"{member['streak']}-day streak", 15, MUTED, "la", 2)
    draw_brew(card, member["brew"], member["brewing"])
    draw_heat(card, member.get("heat", 0), member.get("heat_beans", 0))
    draw_more(card, 476)
    return card.jpg()


def draw_more(card, y):
    """One line: what the other pages pay, so their buttons get pressed."""
    pays = (
        ("Stamp Card", (("items/mega_box", f"x{STAMP_BOXES}"),)),
        (
            "Invites",
            (
                (
                    "kit/icon_ranked_round_token",
                    f"+{REFERRAL_TRAINEE_STAMPS + REFERRAL_BRIDGE_STAMPS}",
                ),
                ("kit/token", "+50%"),
            ),
        ),
        (
            "Table",
            (
                ("kit/token", f"+{TABLE_WINNER_TOKENS}"),
                ("kit/icon_ranked_round_token", f"+{TABLE_WINNER_STAMPS}"),
            ),
        ),
    )
    card.text(30, y, "MORE WAYS TO EARN BELOW", 15, GOLD, "la", 2)
    x = 874
    for name, prizes in reversed(pays):
        for picture, amount in reversed(prizes):
            x -= card.measure(amount, 16)
            card.text(x, y - 1, amount, 16, WHITE, "la", 2)
            x -= 28
            card.icon(picture, x, y - 4, 24)
            x -= 8
        x -= card.measure(name, 15)
        card.text(x, y, name, 15, MUTED, "la", 2)
        x -= 34


def draw_stamp_card(member):
    card = Card(900, 580, member["background"])
    stamps = member["stamps"]
    card.title("STAMP CARD", "You get a Stamp each day you finish Today's Order.")
    card.stat(
        "Passes redeemed this month",
        f"{member['redeemed']} of {STAMP_MONTHLY_LIMIT}",
    )
    card.panel(26, 118, 848, 232)
    card.stamps(
        84,
        156,
        stamps,
        max(STAMP_GOALS.values()),
        STAMP_ROW,
        52,
        19,
        (STAMP_BOX_EVERY, "items/mega_box", STAMP_BOXES),
    )
    card.text(48, 308, f"{stamps} Stamps", 24)
    boxes = f"on every {STAMP_BOX_EVERY}th Stamp"
    x = 450 - (card.measure(boxes, 16) + 40) / 2
    card.icon("items/mega_box", x, 306, 28)
    card.text(x + 32, 320, str(STAMP_BOXES), 15, WHITE, "ra", 2)
    card.text(x + 40, 312, boxes, 16, MUTED, "la", 2)
    today = (
        "Stamped today"
        if member["stamped"]
        else (
            f"{member['done']} of {member['tasks']} tasks done today"
            if member["tasks"]
            else "Clock in to get today's order"
        )
    )
    card.text(852, 310, today, 19, GREEN if member["stamped"] else GOLD, "ra", 2)
    tiers = (
        ("brawl_pass", "Brawl Pass", (20, 60, 170, 200)),
        ("brawl_pass_plus", "Brawl Pass Plus", (90, 40, 170, 200)),
    )
    for spot, (tier, name, fill) in enumerate(tiers):
        x = 26 + spot * 434
        need = STAMP_GOALS[tier]
        left = need - stamps
        card.panel(x, 372, 414, 136, fill)
        card.icon(f"kit/icon_{tier}", x + 16, 388, 78)
        card.text(x + 162, 384, name, 27)
        cost = f"Costs {need} Stamps and"
        card.text(x + 162, 422, cost, 18, MUTED, "la", 2)
        token = x + 170 + card.measure(cost, 18)
        card.icon("kit/token", token, 418, 28)
        card.text(token + 34, 421, f"{member['prices'][tier]:,}", 19, WHITE, "la", 2)
        card.bar(
            x + 162,
            456,
            232,
            26,
            stamps / need,
            GREEN if left <= 0 else GOLD,
            (
                "Ready to use /redeem"
                if left <= 0
                else f"{left} more Stamp{'s' * (left != 1)}"
            ),
        )
    draw_streak(card, member["streak"], 520)
    return card.jpg()


def draw_streak(card, streak, y):
    """How the Clock In streak lowers the Token price of a pass."""
    start, lowest = STAMP_PRICE_STREAK
    card.icon("kit/icon_calendar", 30, y, 32)
    card.text(72, y + 5, f"{streak}-day streak", 20, GOLD)
    line = (
        f"Passes cost fewer Tokens from a {start}-day streak"
        if streak < start
        else (
            f"Your passes cost fewer Tokens each day, down to {lowest} days"
            if streak < lowest
            else "Your passes are at their lowest Token price"
        )
    )
    card.text(872, y + 9, line, 16, MUTED, "ra", 2)


def background(user_id):
    name = u_background(user_id).get()
    return name if name in BACKGROUNDS else BACKGROUND


async def setup(bot):
    pass

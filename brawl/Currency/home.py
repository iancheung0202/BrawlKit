import time

from brawl.Currency.card import BACKGROUND, BLUE, GOLD, GREEN, MUTED, RED, WHITE, Card
from brawl.Currency.config import (
    BACKGROUNDS,
    ROAST_TYPES,
    STAMP_GOALS,
    STAMP_MONTHLY_LIMIT,
)
from brawl.Currency.db import u_background
from brawl.Currency.ladder import next_unlock

STAMP_ROW = 15


def clock(seconds):
    hours, minutes = divmod(int(seconds) // 60, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def goal(stamps):
    for tier, name in (
        ("brawl_pass", "Brawl Pass"),
        ("brawl_pass_plus", "Brawl Pass Plus"),
    ):
        if stamps < STAMP_GOALS[tier]:
            return tier, name
    return "brawl_pass_plus", "Brawl Pass Plus"


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


def draw_stamps(card, stamps, level, streak):
    card.panel(26, 388, 848, 132)
    card.tag(42, 376, "STAMP CARD", RED, WHITE)
    tier, name = goal(stamps)
    need = STAMP_GOALS[tier]
    have = min(stamps, need)
    card.icon("kit/icon_ranked_round_token", 46, 416, 46)
    card.text(104, 408, f"{have} of {need} Stamps", 24, GOLD)
    card.text(854, 412, name, 20, WHITE, "ra")
    card.icon(f"kit/icon_{tier}", 786 - card.measure(name, 20), 406, 34)
    left = need - have
    card.bar(
        104,
        444,
        750,
        28,
        have / need,
        GOLD if left else GREEN,
        f"{left} more to redeem" if left else "Ready to redeem",
    )
    card.text(46, 492, next_unlock(level), 15, MUTED, "la", 2)
    card.text(854, 492, f"{streak}-day streak", 15, MUTED, "ra", 2)


def draw_home(member):
    card = Card(900, 540, member["background"])
    card.header(
        member["name"],
        member["avatar"],
        member["level"],
        member["xp"],
        member["xp_needed"],
        member["beans"],
        member["tokens"],
    )
    draw_order(card, member["tasks"], member.get("store", "the store"))
    draw_brew(card, member["brew"], member["brewing"])
    draw_stamps(card, member["stamps"], member["level"], member["streak"])
    return card.jpg()


def draw_stamp_card(member):
    card = Card(900, 532, member["background"])
    stamps = member["stamps"]
    card.title("STAMP CARD", "You get a Stamp each day you finish Today's Order.")
    card.stat(
        "Passes this month", f"{member['redeemed']} of {STAMP_MONTHLY_LIMIT} redeemed"
    )
    card.panel(26, 118, 848, 232)
    card.stamps(84, 156, stamps, max(STAMP_GOALS.values()), STAMP_ROW, 52, 19)
    card.text(48, 308, f"{stamps} Stamps", 24)
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
            "Ready to redeem" if left <= 0 else f"{left} more Stamp{'s' * (left != 1)}",
        )
    return card.jpg()


def background(user_id):
    name = u_background(user_id).get()
    return name if name in BACKGROUNDS else BACKGROUND


async def setup(bot):
    pass

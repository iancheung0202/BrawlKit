"""The /how pages: one summary card per part of the cafe, drawn once and kept."""

import re
from functools import lru_cache

from brawl.Currency.brewcard import TINTS, hours
from brawl.Currency.card import (
    BLACK,
    BLUE,
    GOLD,
    GREEN,
    MUTED,
    PLACES,
    RED,
    SCALE,
    SLOT,
    WHITE,
    Card,
    box,
    icon,
    item_icon,
    shade,
)
from brawl.Currency.config import (
    BOOSTER_DAILY_BEANS,
    BOSS_ODDS,
    BOSS_SECONDS,
    BOSS_VISITS,
    CHAT_BOOST_MULTIPLIER,
    CHAT_BOOSTED_REWARD,
    CHAT_LIMITS,
    CHAT_MESSAGES,
    CHAT_REWARD,
    CHAT_WEEKEND_MULTIPLIER,
    DAILY_BEANS,
    DAILY_GAMBLING_LIMITS,
    ITEM_STATIONS,
    LADDER,
    LUCKY_DAILY_CHANCE,
    ORDER_STATION_TASKS,
    ORDER_TASK_LEVELS,
    PERFECT_BREW_CHANCE,
    QUEST_BEAN_REWARDS,
    QUEST_BONUS_BEANS,
    REFERRAL_ACCOUNT_DAYS,
    REFERRAL_BRIDGE_STAMPS,
    REFERRAL_STEPS,
    REP_PAID_DAILY,
    REP_TOKENS,
    ROAST_TYPES,
    STAMP_BOX_EVERY,
    STAMP_BOXES,
    STAMP_GOALS,
    STAMP_MONTHLY_LIMIT,
    STAMP_PRICE_RANGES,
    STAMP_PRICE_STREAK,
    STREAK_BEAN_MULTIPLIER,
    STREAK_DAYS,
    STREAK_TOKENS,
    TABLE_KICK_DAYS,
    TABLE_QUEST_TYPES,
    TABLE_SEATS,
    TABLE_SEATS_NEEDED,
    TABLE_WINNER_STAMPS,
    TABLE_WINNER_TOKENS,
    THERMOMETER_COOLING,
    THERMOMETER_DAILY_TOKEN_DROPS,
    THERMOMETER_LEVELS,
    THERMOMETER_MAX,
    THERMOMETER_MESSAGE_HEAT,
    TOPIC_BEANS,
    ULTRA_DAILY_BONUS,
    UNLOCK_REQ,
    WELCOME_BUTTON_REWARD,
    XP_BOOSTER_MULTIPLIER,
    XP_COOLDOWN,
    XP_PER_MESSAGE,
    XP_ULTRA_MULTIPLIER,
)
from brawl.Currency.dropcard import rates_image
from brawl.Currency.gambling import MAX_BET, MIN_BET, ULTRA_MAX_BET
from brawl.Currency.helper import STORE_ITEMS
from brawl.Currency.levels import LEVEL_REWARDS, level_up_reward, xp_for_level
from brawl.Currency.stationcard import outcomes

WIDTH = 900
BACKGROUND = "gym"
ORDER_BEANS = (1 + ORDER_STATION_TASKS) * QUEST_BEAN_REWARDS[
    "daily"
] + QUEST_BONUS_BEANS["daily"]


def span(low, high):
    return f"{low:,}" if low == high else f"{low:,}–{high:,}"


def percent(chance):
    return f"{chance * 100:g}%"


def icon_width(picture, size):
    return icon(picture, size).width / SCALE


def fitted(card, picture, x, y, size):
    """Draws an icon inside a size x size square, whatever its shape."""
    height = min(size, int(size * size / max(icon_width(picture, size), size)))
    card.icon(
        picture,
        x + (size - icon_width(picture, height)) / 2,
        y + (size - height) / 2,
        height,
    )


def arrow(card, x, y, size=12, fill=GOLD):
    """A small arrow head pointing right, centered on (x, y)."""
    points = [
        (x - size * 0.6, y - size),
        (x + size * 0.7, y),
        (x - size * 0.6, y + size),
    ]
    card.draw.polygon(
        [(a * SCALE, b * SCALE) for a, b in points],
        fill=fill,
        outline=BLACK,
        width=2 * SCALE,
    )


def rule(card, y):
    card.draw.line(
        [(46 * SCALE, y * SCALE), (854 * SCALE, y * SCALE)],
        fill=(0, 0, 0, 90),
        width=2 * SCALE,
    )


def pill_width(card, picture, name, value):
    w = 22 + (32 if picture else 0) + card.measure(name, 16)
    return w + (card.measure(value, 17) + 12 if value else 0)


def pill(card, x, y, picture, name, value="", fill=GOLD):
    """One line in a slot: an icon, a name and its number. Returns the next x."""
    w = pill_width(card, picture, name, value)
    card.slot(x, y, w, 36)
    at = x + 10
    if picture:
        fitted(card, picture, at, y + 5, 26)
        at += 32
    card.text(at, y + 8, name, 16, WHITE, "la", 2)
    if value:
        card.text(x + w - 11, y + 7, value, 17, fill, "ra", 2)
    return x + w + 8


def pills(card, x, y, row, limit=854):
    """Pills left to right, wrapping at the panel edge; returns the y below."""
    at = x
    for picture, name, value, *fill in row:
        if at > x and at + pill_width(card, picture, name, value) > limit:
            at, y = x, y + 44
        at = pill(card, at, y, picture, name, value, *fill)
    return y + 44


def table(card, y, rows, left=190):
    """Rows like the drop rates: a colored name on the left, its pills beside."""
    for spot, (name, color, row) in enumerate(rows):
        if spot:
            rule(card, y - 6)
        card.text(46, y + 6, name, 20, color)
        y = pills(card, left, y, row) + 8
    return y - 8


def node(card, x, y, picture, name, line, color=WHITE, size=70):
    """One step of a flow: a big icon, its name and one number under it."""
    if size:
        card.icon(picture, x - icon_width(picture, size) / 2, y, size)
    card.text(x, y + size + 6, name, 22, color, "ma")
    card.text(x, y + size + 36, line, 15, MUTED, "ma", 2)


def flow(card, y, steps, size=70, arrows=True):
    gap = 848 / len(steps)
    for spot, step in enumerate(steps):
        x = 26 + gap * (spot + 0.5)
        node(card, x, y, *step, size=size)
        if spot and arrows:
            arrow(card, x - gap / 2, y + size / 2)


# What a member finds in each place, as the /balance pages show it.
PLACE_HOLDS = {
    "COUNTER": [
        ("kit/icon_quest", "Today's Order", ""),
        ("brewing", "Brew Station", ""),
        ("kit/icon_xp", "Level", ""),
        ("kit/icon_ranked_round_token", "Stamp Card", ""),
    ],
    "CHAT": [
        ("kit/bean", "Chat Beans", ""),
        ("kit/icon_wasabi_power", "Thermometer", ""),
        ("kit/icon_megaboss_big", "Boss Inspection", ""),
    ],
    "INVENTORY": [
        ("items/star_drop", "Star Drops", ""),
        ("items/mega_box", "Mega Boxes", ""),
        ("kit/icon_box", "Effect items", ""),
    ],
    "COMMUNITY": [
        ("kit/icon_trophy", "Table", ""),
        ("kit/icon_inbox", "Invites", ""),
        ("game/3v3", "Team Finder", ""),
        ("kit/icon_chat", "Topics", ""),
    ],
}


def page(place, title, height, picture=None):
    """A page under its place's sign: the place's icon and name, then the title.

    A page that belongs to no place has its own picture, or none, and the title.
    """
    if place is None:
        card = Card(WIDTH, height, BACKGROUND)
        if picture:
            fitted(card, picture, 34, 28, 64)
        card.text(112 if picture else 34, 36, title, 42)
        return card
    color, scene, picture = PLACES[place]
    card = Card(WIDTH, height, scene)
    fitted(card, picture, 34, 28, 64)
    card.text(112, 24, place, 18, color)
    card.text(112, 48, title, 38)
    return card


def section(card, top, height, label, fill=GOLD, color=BLACK):
    card.panel(26, top, 848, height)
    card.tag(42, top - 12, label, fill, color)


def split(card, x, y, width, parts):
    """One bar split by odds; each part is (odds, label, color)."""
    card.draw.rounded_rectangle(
        box(x, y, width, 34), 8 * SCALE, fill=SLOT, outline=BLACK, width=3 * SCALE
    )
    at = x + 3
    for odds, label, color in parts:
        part = (width - 6) * odds
        card.draw.rectangle(box(at + 1, y + 3, part - 2, 28), fill=color)
        if card.measure(label, 17) < part - 4:
            card.text(at + part / 2, y + 6, label, 17, WHITE, "ma", 2)
        card.text(at + part / 2, y + 40, percent(odds), 13, MUTED, "ma", 2)
        at += part


def loop():
    """Chat to Shop in five steps, each with its one number."""
    roasts = list(ROAST_TYPES.values())
    tokens = [pay for roast in roasts for pay in roast["payout"] if pay]
    return [
        (
            "kit/icon_chat",
            "Chat",
            f"every {CHAT_MESSAGES[0]} to {CHAT_MESSAGES[1]} messages",
        ),
        ("kit/bean", "Beans", f"+{CHAT_REWARD[0]} to +{CHAT_REWARD[1]}", GOLD),
        (
            "brewing",
            "Brew",
            f"{hours(roasts[0]['time'])} to {hours(roasts[-1]['time'])}",
        ),
        ("kit/token", "Tokens", f"+{min(tokens)} to +{max(tokens)}", GOLD),
        ("kit/icon_shop", "Shop", "perks and rewards"),
    ]


# The store for someone new, a row a flow: (icon, name, two short lines, name colour)
BANNER = (
    (
        "HOW TO START",
        GOLD,
        BLACK,
        (
            ("kit/icon_chat", "Chat", ("Talk in", "any channel"), WHITE),
            ("kit/bean", "Beans", ("You earn these", "as you chat"), GOLD),
            ("brewing", "Brew", ("Spend Beans", "on a coffee"), WHITE),
            ("kit/token", "Tokens", ("Sell the coffee", "to get these"), GOLD),
            ("kit/icon_shop", "Shop", ("Spend both on", "free rewards"), WHITE),
        ),
    ),
    (
        "STAMP CARD",
        GREEN,
        WHITE,
        (
            (
                "kit/icon_calendar",
                "Clock In",
                ("Press the button", "once a day"),
                WHITE,
            ),
            (
                "kit/icon_quest",
                "Today's Order",
                ("Finish the tasks", "it gives you"),
                WHITE,
            ),
            (
                "kit/icon_ranked_round_token",
                "Stamp",
                ("You get one for", "each finished order"),
                GREEN,
            ),
            (
                "kit/icon_brawl_pass",
                "Brawl Pass",
                (f"Trade {STAMP_GOALS['brawl_pass']} Stamps", "for a real one"),
                GOLD,
            ),
        ),
    ),
)


@lru_cache
def panel_banner(flow):
    """One flow in plain words, as the picture under its text on the store panel."""
    label, fill, color, steps = BANNER[flow]
    card = Card(WIDTH, 200)
    card.panel(2, 14, WIDTH - 4, 180)
    card.tag(18, 2, label, fill, color)
    gap = (WIDTH - 4) / len(steps)
    for spot, (picture, name, lines, tint) in enumerate(steps):
        x = 2 + gap * (spot + 0.5)
        card.icon(picture, x - icon_width(picture, 70) / 2, 36, 70)
        card.text(x, 112, name, 22, tint, "ma")
        for line, words in enumerate(lines):
            card.text(x, 142 + line * 19, words, 15, MUTED, "ma", 2)
        if spot:
            arrow(card, x - gap / 2, 71)
    return card.jpg().getvalue()


@lru_cache
def start_page(title="HOW THE CAFE WORKS"):
    """The whole cafe on one card: the loop, what each currency buys, a day."""
    card = page(None, title, 1030)
    section(card, 124, 162, "THE LOOP")
    flow(card, 146, loop())

    top = 318
    section(card, top, 216, "FOUR PLACES IN /BALANCE")
    for row, (place, row_pills) in enumerate(PLACE_HOLDS.items()):
        y = top + 24 + row * 48
        if row:
            rule(card, y - 6)
        color, _, picture = PLACES[place]
        fitted(card, picture, 46, y, 36)
        card.text(92, y + 5, place.title(), 22, color)
        pills(card, 248, y, row_pills)

    top = 566
    section(card, top, 230, "WHAT EACH ONE IS FOR")
    uses = [
        (
            "kit/icon_xp",
            "XP",
            WHITE,
            [
                ("kit/icon_key", "New stations", ""),
                ("kit/icon_role", "Level roles", ""),
            ],
        ),
        (
            "kit/bean",
            "Beans",
            GOLD,
            [
                ("brewing", "Brews", ""),
                ("items/star_drop", "Star Drops", ""),
                ("kit/coin_pile_03", "Games", ""),
            ],
        ),
        (
            "kit/token",
            "Tokens",
            GOLD,
            [
                ("kit/icon_shop", "Shop rewards", ""),
                ("kit/icon_box", "Effect items", ""),
                ("items/mega_box", "Mega Boxes", ""),
            ],
        ),
        (
            "kit/icon_ranked_round_token",
            "Stamps",
            GREEN,
            [
                ("kit/icon_brawl_pass", "Brawl Pass", str(STAMP_GOALS["brawl_pass"])),
                (
                    "kit/icon_brawl_pass_plus",
                    "Brawl Pass Plus",
                    str(STAMP_GOALS["brawl_pass_plus"]),
                ),
            ],
        ),
    ]
    for row, (picture, name, color, row_pills) in enumerate(uses):
        y = top + 26 + row * 50
        if row:
            rule(card, y - 7)
        fitted(card, picture, 46, y, 36)
        card.text(92, y + 5, name, 22, color)
        arrow(card, 204, y + 18, 9)
        pills(card, 228, y, row_pills)

    top = 828
    section(card, top, 150, "EVERY DAY, FROM 00:00 UTC")
    flow(
        card,
        top + 22,
        [
            ("kit/icon_calendar", "Clock In", f"+{DAILY_BEANS:,} Beans"),
            ("kit/icon_quest", "Today's Order", f"+{ORDER_BEANS:,} Beans"),
            ("kit/icon_ranked_round_token", "Stamp", "+1 a day", GREEN),
            (
                "kit/icon_brawl_pass",
                "Brawl Pass",
                f"{STAMP_GOALS['brawl_pass']} Stamps",
                GOLD,
            ),
        ],
        size=56,
    )
    card.hint("Pick a topic below for the numbers.")
    return card.jpg().getvalue()


def mean(roast):
    """Average Tokens for one sale, counting the perfect brew chance."""
    total = sum(roast["weights"])
    average = sum(pay * odds for pay, odds in zip(roast["payout"], roast["weights"]))
    return average / total * (1 + PERFECT_BREW_CHANCE / 100)


def payouts(card, x, y, width, roast, tint):
    """One bar split by odds: each part is a payout, with the Tokens written in."""
    total = sum(roast["weights"])
    card.draw.rounded_rectangle(
        box(x, y, width, 34), 8 * SCALE, fill=SLOT, outline=BLACK, width=3 * SCALE
    )
    at = x + 3
    highest = max(roast["payout"])
    for pay, odds in zip(roast["payout"], roast["weights"]):
        part = (width - 6) * odds / total
        fill = RED if not pay else shade(tint, 0.55 + 0.45 * pay / highest)
        card.draw.rectangle(box(at + 1, y + 3, part - 2, 28), fill=fill)
        label = str(pay) if pay else ""
        if label and card.measure(label, 17) < part - 4:
            card.text(at + part / 2, y + 6, label, 17, WHITE, "ma", 2)
        share = f"{odds * 100 / total:g}%"
        card.text(at + part / 2, y + 40, share, 13, MUTED if pay else RED, "ma", 2)
        at += part


@lru_cache
def brewing_page():
    """Every roast side by side, then everything that changes a brew."""
    row = 118
    top = 144 + len(ROAST_TYPES) * row
    card = page("COUNTER", "BREWING", top + 342)
    section(card, 124, len(ROAST_TYPES) * row + 24, "ROASTS")
    card.note(124, "One brew at a time", 858)
    card.text(372, 142, "Tokens you can get, by chance", 14, MUTED, "la", 2)
    for spot, (key, roast) in enumerate(ROAST_TYPES.items()):
        y = 164 + spot * row
        if spot:
            rule(card, y - 8)
        card.icon("brewing", 44, y + 6, 64)
        card.text(122, y, roast["name"], 24, TINTS[key])
        card.icon("kit/bean", 122, y + 34, 22)
        cost = f"{roast['cost']:,}"
        card.text(150, y + 34, cost, 19, GOLD)
        x = 162 + card.measure(cost, 19)
        card.icon("kit/icon_clock", x, y + 37, 17)
        card.text(x + 23, y + 36, hours(roast["time"]), 17, MUTED, "la", 2)
        if roast["insurance_cost"]:
            burn = roast["weights"][0] / sum(roast["weights"])
            price = f"{roast['insurance_cost']:,}"
            card.icon("items/free_insurance", 122, y + 64, 22)
            card.text(150, y + 66, price, 16, GREEN, "la", 2)
            note = f"stops the {percent(burn)} burn"
            card.text(156 + card.measure(price, 16), y + 67, note, 15, MUTED, "la", 2)
        else:
            card.text(
                122,
                y + 67,
                f"Never burns. Needs {UNLOCK_REQ} brews",
                15,
                GREEN,
                "la",
                2,
            )
        payouts(card, 372, y + 22, 356, roast, TINTS[key])
        card.text(854, y + 8, "Average", 14, MUTED, "ra", 2)
        average = f"{mean(roast):.2f}"
        card.text(854, y + 26, average, 26, GOLD, "ra")
        card.icon("kit/token", 818 - card.measure(average, 26), y + 28, 28)

    section(card, top + 22, 272, "WHAT CHANGES A BREW")
    columns = [530 + spot * 108 for spot in range(len(ROAST_TYPES))]
    for x, (key, roast) in zip(columns, ROAST_TYPES.items()):
        card.text(x, top + 44, roast["name"].split()[0], 16, TINTS[key], "ra", 2)
    roasts = list(ROAST_TYPES.values())
    burns = [not roast["payout"][0] for roast in roasts]
    low = [min(pay for pay in roast["payout"] if pay) for roast in roasts]
    best = [max(roast["payout"]) * 2 for roast in roasts]
    usual = [max(zip(roast["weights"], roast["payout"]))[1] for roast in roasts]
    lines = (
        (
            "ready",
            "A perfect brew pays up to",
            f"{PERFECT_BREW_CHANCE}% of sales, 25% with Expert Barista",
            GOLD,
            [str(pay) for pay in best],
        ),
        (
            "items/free_insurance",
            "An insured burn pays",
            "free with Barista's Protection",
            GREEN,
            [str(pay) if burn else "" for pay, burn in zip(low, burns)],
        ),
        (
            "items/burnt_to_perfect",
            "With Resurrection, a burn pays",
            "the top payout, x2",
            GREEN,
            [str(pay) if burn else "" for pay, burn in zip(best, burns)],
        ),
        (
            "kit/icon_role",
            "Master Barista adds",
            "half the usual payout",
            GOLD,
            [f"+{max(pay // 2, 1)}" for pay in usual],
        ),
        (
            "items/half_brew_time",
            "Turbo Brewing time",
            "half as long",
            MUTED,
            [hours(roast["time"] // 2) for roast in roasts],
        ),
    )
    for row, (picture, name, note, color, cells) in enumerate(lines):
        y = top + 70 + row * 44
        rule(card, y - 5)
        fitted(card, picture, 46, y + 2, 30)
        card.text(86, y - 1, name, 17, WHITE, "la", 2)
        card.text(86, y + 20, note, 13, MUTED, "la", 2)
        for x, cell in zip(columns, cells):
            card.text(
                x,
                y + 5,
                cell or "none",
                20 if cell else 14,
                color if cell else MUTED,
                "ra",
                2 if not cell else None,
            )
    return card.jpg().getvalue()


@lru_cache
def beans_page():
    """Where Beans come from: chat, its daily limit, Clock In and the rest."""
    card = page("CHAT", "BEANS", 990)
    section(card, 124, 382, "CHAT")
    for spot in range(10):
        card.icon("kit/icon_chat", 46 + spot * 30, 156, 24)
    arrow(card, 366, 168)
    card.icon("kit/bean", 388, 148, 40)
    reward = f"+{span(*CHAT_REWARD)}"
    card.text(434, 150, reward, 30, GOLD)
    every = f"every {span(*CHAT_MESSAGES)} messages"
    card.text(446 + card.measure(reward, 30), 162, every, 16, MUTED, "la", 2)

    card.text(46, 208, "Daily limit", 15, MUTED, "la", 2)
    card.text(750, 208, "Mon to Fri", 15, MUTED, "ra", 2)
    card.text(854, 208, "Sat, Sun", 15, MUTED, "ra", 2)
    highest = max(CHAT_LIMITS.values()) * CHAT_WEEKEND_MULTIPLIER
    names = {"member": "Member", "booster": "Booster", "ultra": "Ultra Tier"}
    tints = {"member": GOLD, "booster": (255, 115, 250), "ultra": BLUE}
    for row, (key, limit) in enumerate(CHAT_LIMITS.items()):
        y = 232 + row * 34
        card.text(46, y + 2, names[key], 18, WHITE, "la", 2)
        weekend = limit * CHAT_WEEKEND_MULTIPLIER
        card.bar(150, y, 510, 24, weekend / highest, shade(tints[key], 0.45))
        card.bar(150, y, 510, 24, limit / highest, tints[key])
        card.text(750, y + 1, f"{limit:,}", 19, GOLD, "ra")
        card.text(854, y + 1, f"{weekend:,}", 19, WHITE, "ra")
    item_heads(card, 344)
    card.text(46, 344, "Items", 14, MUTED, "la", 2)
    for row, (key, does) in enumerate(EFFECTS[0][2]):
        rule(card, 362 + row * 40)
        item_row(card, 364 + row * 40, key, does)

    top = 538
    section(card, top, 236, "CLOCK IN")
    for day in range(1, STREAK_DAYS + 1):
        last = day == STREAK_DAYS
        x = 46 + (day - 1) * 86
        w = 78 if not last else 292
        card.slot(x, top + 26, w, 68, GOLD if last else BLACK)
        card.text(x + 10, top + 32, f"Day {day}", 14, GOLD if last else MUTED, "la", 2)
        if last:
            card.icon("kit/bean", x + 60, top + 52, 32)
            beans = f"+{DAILY_BEANS * STREAK_BEAN_MULTIPLIER:,}"
            card.text(x + 98, top + 54, beans, 26, GOLD)
            at = x + 110 + card.measure(beans, 26)
            card.icon("kit/token", at, top + 54, 30)
            card.text(at + 36, top + 56, f"+{span(*STREAK_TOKENS)}", 22, GOLD)
        else:
            card.icon("kit/bean", x + 8, top + 58, 20)
            card.text(x + 30, top + 58, f"{DAILY_BEANS}", 19, WHITE)
    terms = [
        ("", f"{DAILY_BEANS}", "base"),
        ("", f"{BOOSTER_DAILY_BEANS}", "Booster base"),
        ("x", "2", "Daily Doubler"),
        ("x", "2", f"lucky, {percent(LUCKY_DAILY_CHANCE)}"),
        ("x", f"{STREAK_BEAN_MULTIPLIER}", f"Day {STREAK_DAYS}"),
        ("+", f"{ULTRA_DAILY_BONUS:,}", "Ultra Tier"),
    ]
    card.text(46, top + 112, "How it adds up", 15, MUTED, "la", 2)
    for spot, (sign, amount, name) in enumerate(terms):
        x = 100 + spot * 134
        if spot == 1:
            card.text(x - 67, top + 148, "or", 17, MUTED, "ma", 2)
        elif sign:
            card.text(x - 67, top + 142, sign, 26, WHITE, "ma")
        card.text(x, top + 138, amount, 30, GOLD, "ma")
        card.text(x, top + 176, name, 15, MUTED, "ma", 2)
    card.icon("items/streak_insurance", 46, top + 202, 22)
    card.text(
        76,
        top + 204,
        "A missed day starts again at Day 1. Streak Shield saves it once.",
        15,
        MUTED,
        "la",
        2,
    )

    top = 806
    steps = TABLE_QUEST_TYPES["bean_collector"]["rewards"]
    heat = [level[2] for level in THERMOMETER_LEVELS if level[2]]
    section(card, top, 134, "MORE BEANS")
    first, last = level_up_reward(1)[0], level_up_reward(max(LEVEL_REWARDS))[0]
    flow(
        card,
        top + 24,
        [
            ("kit/icon_quest", f"+{ORDER_BEANS:,}", "Today's Order", GOLD),
            ("kit/icon_xp", f"+{span(first, last)}", "each level up", GOLD),
            (
                "kit/icon_wasabi_power_hot",
                f"+{span(min(heat), max(heat))}",
                "per message, hot chat",
                GOLD,
            ),
            (
                "kit/icon_trophy",
                f"+{span(min(steps), max(steps))}",
                "table quest step",
                GOLD,
            ),
            ("kit/icon_inbox", f"+{WELCOME_BUTTON_REWARD}", "welcome a member", GOLD),
        ],
        size=40,
        arrows=False,
    )
    return card.jpg().getvalue()


STATION_ICONS = {
    "brewing": "brewing",
    "shop": "kit/icon_shop",
    "drops": "items/star_drop",
    "boss": "kit/icon_megaboss_big",
    "thermometer": "kit/icon_wasabi_power_hot",
    "tables": "kit/icon_trophy",
    "games": "kit/coin_pile_03",
    "effects": "kit/icon_box",
    "boxes": "items/mega_box",
    "style": "items/custom_credit",
}


def total_xp(level):
    return sum(xp_for_level(below) for below in range(level))


@lru_cache
def levels_page():
    """XP in, the ladder of stations, and what each level pays."""
    card = page("COUNTER", "LEVELS", 806)
    section(card, 124, 132, "XP")
    card.icon("kit/icon_chat", 46, 150, 34)
    arrow(card, 104, 168)
    card.icon("kit/icon_xp", 124, 148, 40)
    gain = f"+{span(*XP_PER_MESSAGE)}"
    card.text(180, 150, gain, 30, GOLD)
    once = f"one message every {XP_COOLDOWN} seconds"
    card.text(192 + card.measure(gain, 30), 162, once, 16, MUTED, "la", 2)
    low, high = XP_PER_MESSAGE
    roles = (
        ("Member", 1),
        ("Booster", XP_BOOSTER_MULTIPLIER),
        ("Ultra Tier", XP_ULTRA_MULTIPLIER),
    )
    for spot, (name, times) in enumerate(roles):
        card.text(46 + spot * 130, 196, name, 14, MUTED, "la", 2)
        card.text(46 + spot * 130, 214, span(low * times, high * times), 20, GOLD)
    card.text(854, 218, "Next level needs 100 x level + 75 XP", 15, MUTED, "ra", 2)

    top = 288
    section(card, top, 262, "WHAT EACH LEVEL OPENS")
    stations = sorted(LADDER.items(), key=lambda station: station[1][0])
    w = (816 - 8 * 4) / 5
    for spot, (key, (level, name, _)) in enumerate(stations):
        x, y = 42 + spot % 5 * (w + 8), top + 26 + spot // 5 * 114
        card.slot(x, y, w, 106)
        fitted(card, STATION_ICONS[key], x + w - 60, y + 8, 48)
        card.text(x + 12, y + 8, "LEVEL", 13, MUTED, "la", 2)
        card.text(x + 12, y + 22, str(level), 30, GOLD)
        card.text(x + 12, y + 61, card.fit(name, 17, w - 20), 17, WHITE, "la", 2)
        card.text(x + 12, y + 83, f"{total_xp(level):,} XP", 13, MUTED, "la", 2)

    top = 582
    section(card, top, 174, "WHEN YOU LEVEL UP")
    highest = max(LEVEL_REWARDS)
    left, width = 136, 700
    card.text(46, top + 30, "Roles", 17, WHITE, "la", 2)
    card.text(46, top + 92, "Tokens", 17, WHITE, "la", 2)
    card.bar(left, top + 66, width, 14, 1, BLUE)
    for level in LEVEL_REWARDS:
        x = left + width * level / highest
        fitted(card, "kit/icon_role", x - 13, top + 22, 26)
        card.text(x, top + 47, str(level), 14, WHITE, "ma", 2)
    for level in range(10, highest + 1, 10):
        x = left + width * level / highest
        card.icon("kit/token", x - 9, top + 88, 18)
        card.text(x, top + 108, f"+{level_up_reward(level)[1]}", 14, GOLD, "ma", 2)
    card.icon("kit/bean", 46, top + 136, 22)
    first, last = level_up_reward(1)[0], level_up_reward(highest)[0]
    rising = f"+{first} at Level 1, rising to +{last} at Level {highest}"
    card.text(76, top + 138, rising, 16, MUTED, "la", 2)
    return card.jpg().getvalue()


@lru_cache
def order_page():
    """The daily order, the Stamp it gives, and what Stamps buy."""
    each, bonus = QUEST_BEAN_REWARDS["daily"], QUEST_BONUS_BEANS["daily"]
    card = page("COUNTER", "TODAY'S ORDER", 732)
    section(card, 124, 304, "THE ORDER")
    flow(
        card,
        146,
        [
            ("kit/icon_calendar", "Clock In", "starts the order"),
            ("kit/icon_chat", "Chat task", f"+{each}", GOLD),
            ("kit/icon_quest", "Station task", f"+{each}", GOLD),
            ("kit/icon_quest", "Station task", f"+{each}", GOLD),
            ("kit/icon_ranked_round_token", "All done", f"+{bonus} and 1 Stamp", GREEN),
        ],
        size=56,
    )
    levels = ORDER_TASK_LEVELS
    chat = ("kit/bean", "Earn your daily chat limit", "")
    note = "Thermometer Beans are extra and not counted"
    card.text(212 + pill_width(card, *chat), 298, note, 13, MUTED, "la", 2)
    table(
        card,
        288,
        [
            ("Chat task", GOLD, [chat]),
            (
                "Station tasks",
                BLUE,
                [
                    ("brewing", "Start a brew", f"Lv {levels['brew_start']}"),
                    ("ready", "Sell a brew", f"Lv {levels['brew_sells']}"),
                    (
                        "kit/icon_shop",
                        "Buy from the shop",
                        f"Lv {levels['shop_purchases']}",
                    ),
                    (
                        "kit/icon_megaboss_big",
                        "Join a boss inspection",
                        f"Lv {levels['boss_inspections']}",
                    ),
                    (
                        "kit/icon_wasabi_power_hot",
                        "Get a thermometer drop",
                        f"Lv {levels['thermometer_bonuses']}",
                    ),
                ],
            ),
        ],
        left=206,
    )
    card.text(46, 372, f"{ORDER_STATION_TASKS} picked each day", 15, MUTED, "la", 2)

    top = 460
    section(card, top, 222, "STAMPS AND PASSES")
    card.note(top, f"{STAMP_MONTHLY_LIMIT} passes a month for the whole server", 858)
    passes = (
        ("brawl_pass", "Brawl Pass", (20, 60, 170, 200)),
        ("brawl_pass_plus", "Brawl Pass Plus", (90, 40, 170, 200)),
    )
    for spot, (key, name, fill) in enumerate(passes):
        x = 42 + spot * 414
        goal, (low, high) = STAMP_GOALS[key], STAMP_PRICE_RANGES[key]
        card.panel(x, top + 28, 402, 96, fill)
        card.icon(f"kit/icon_{key}", x + 14, top + 46, 60)
        card.text(x + 126, top + 42, name, 24)
        card.icon("kit/icon_ranked_round_token", x + 126, top + 82, 24)
        card.text(x + 156, top + 83, str(goal), 20, GREEN)
        at = x + 172 + card.measure(str(goal), 20)
        card.icon("kit/token", at, top + 82, 24)
        card.text(at + 30, top + 83, str(high), 20, GOLD)
        at += 40 + card.measure(str(high), 20)
        card.text(
            at, top + 87, f"{low} at Day {STAMP_PRICE_STREAK[1]}", 14, MUTED, "la", 2
        )
    y = top + 138
    card.icon("kit/icon_calendar", 46, y, 28)
    card.text(84, y + 4, "Clock In streak", 18, GOLD)
    x = 98 + card.measure("Clock In streak", 18)
    card.text(x, y + 7, "saves", 15, WHITE, "la", 2)
    x += card.measure("saves", 15) + 8
    card.icon("kit/token", x, y + 4, 22)
    saves = (
        STAMP_PRICE_RANGES["brawl_pass"][1] - STAMP_PRICE_RANGES["brawl_pass"][0]
    ) // STAMP_PRICE_STREAK[1]
    each = f"{saves} a pass each day"
    card.text(x + 28, y + 7, each, 15, GOLD, "la", 2)
    x += 46 + card.measure(each, 15)
    end = f"Day {STAMP_PRICE_STREAK[1]}"
    card.text(854, y + 7, end, 14, MUTED, "ra", 2)
    card.bar(x, y + 8, 842 - card.measure(end, 14) - x, 14, 1, GREEN)
    card.icon("items/mega_box", 46, top + 182, 26)
    card.text(
        80,
        top + 186,
        f"x{STAMP_BOXES} Mega Boxes on every {STAMP_BOX_EVERY}th Stamp",
        16,
        GREEN,
        "la",
        2,
    )
    return card.jpg().getvalue()


def lasting(seconds):
    if not seconds:
        return "now"
    count, unit = (
        (seconds // 86400, "d") if seconds >= 86400 else (seconds // 3600, "h")
    )
    return f"{count}{unit}"


EFFECTS = (
    (
        "CHAT",
        GOLD,
        (
            ("chat_bean_boost", f"each reward +{span(*CHAT_BOOSTED_REWARD)}"),
            ("chat_boost", f"chat Beans and limit x{CHAT_BOOST_MULTIPLIER}"),
            ("reset_chat_cap", "today's limit starts over"),
        ),
    ),
    (
        "CLOCK IN",
        GREEN,
        (("double_daily", "Beans x2"), ("streak_insurance", "saves one missed day")),
    ),
    (
        "BREWING",
        (225, 160, 90),
        (
            ("free_insurance", "every brew insured"),
            ("perfect_brew_boost", "perfect brew 25%"),
            ("burnt_to_perfect", "a burn pays the top, x2"),
            ("half_brew_time", "half the brew time"),
            ("instant_brew", "your brew is ready"),
            ("sell_alarm", "a DM when it is ready"),
        ),
    ),
    (
        "THERMOMETER",
        RED,
        (
            ("thermometer_boost", "+30 heat"),
            ("freeze_thermometer", "heat stays where it is"),
        ),
    ),
)


ITEM_COLUMNS = (("Level", 560), ("Price", 660), ("Lasts", 750), ("Buy again", 854))


def item_heads(card, y):
    for name, x in ITEM_COLUMNS:
        card.text(x, y, name, 14, MUTED, "ra", 2)


def item_row(card, y, key, does):
    """One effect item as a table row: what it does, level, price, length, cooldown."""
    item = STORE_ITEMS[key]
    fitted(card, item_icon(key), 46, y + 3, 30)
    card.text(86, y + 7, item["name"], 18, WHITE, "la", 2)
    card.text(286, y + 9, does, 15, MUTED, "la", 2)
    opens = LADDER[ITEM_STATIONS.get(key, "effects")][0]
    card.text(560, y + 8, str(opens), 17, WHITE, "ra", 2)
    amount, currency = item["price"].split()
    amount = f"{int(amount):,}"
    card.text(660, y + 7, amount, 18, GOLD, "ra")
    coin = "kit/token" if "token" in currency else "kit/bean"
    card.icon(coin, 634 - card.measure(amount, 18), y + 7, 20)
    card.text(750, y + 8, lasting(item["duration"]), 17, GREEN, "ra", 2)
    card.text(854, y + 8, lasting(item["cooldown"]), 17, MUTED, "ra", 2)


@lru_cache
def effects_page():
    """Every effect item in one table: what it does, costs and how long."""
    count = sum(len(items) for _, _, items in EFFECTS)
    level = LADDER["effects"][0]
    height = 240 + count * 40 + len(EFFECTS) * 34
    card = page("INVENTORY", "EFFECT ITEMS", height)
    section(card, 124, height - 172, "ITEMS")
    item_heads(card, 142)
    y = 166
    for group, color, items in EFFECTS:
        rule(card, y + 2)
        card.text(46, y + 10, group, 13, color, "la", 2)
        y += 34
        for key, does in items:
            item_row(card, y, key, does)
            y += 40
    card.hint("Timed items wait in your bag, one of each. Start one with /use.")
    return card.jpg().getvalue()


@lru_cache
def stations_page():
    """The thermometer's heat levels and the boss's odds."""
    card = page("CHAT", "THERMOMETER AND BOSS", 786)
    section(card, 124, 454, "THERMOMETER")
    card.icon("kit/icon_chat", 46, 148, 26)
    arrow(card, 92, 162, 9)
    heat = f"+{span(*THERMOMETER_MESSAGE_HEAT)} heat"
    card.text(108, 150, heat, 20, GOLD)
    card.text(
        120 + card.measure(heat, 20), 154, "each main chat message", 15, MUTED, "la", 2
    )
    drops = (
        f"No Bean limit, {THERMOMETER_DAILY_TOKEN_DROPS} Token drops a day"
        f" from Level {LADDER['thermometer'][0]}"
    )
    card.note(124, drops, 858)
    levels = sorted(THERMOMETER_LEVELS)
    cooling = dict(
        zip(
            ("Cold", "Warm", "Hot", "Boiling"),
            (lost for _, lost in reversed(THERMOMETER_COOLING)),
        )
    )
    tints = {"Cold": BLUE, "Warm": GOLD, "Hot": (255, 140, 40), "Boiling": RED}
    left, width = 190, 664
    rows = (
        ("EXTRA BEANS", "per message"),
        ("COOLS", "per minute"),
        ("TOKEN DROPS", "per message"),
    )
    for row, (name, each) in enumerate(rows):
        rule(card, 256 + row * 40)
        card.text(46, 262 + row * 40, name, 13, WHITE, "la", 2)
        card.text(46, 278 + row * 40, each, 12, MUTED, "la", 2)
    card.text(46, 198, "HEAT", 13, WHITE, "la", 2)
    for spot, (start, name, beans, tokens) in enumerate(levels):
        end = levels[spot + 1][0] if spot + 1 < len(levels) else THERMOMETER_MAX
        x = left + width * start / THERMOMETER_MAX
        w = width * (end - start) / THERMOMETER_MAX
        card.draw.rectangle(
            box(x + 1, 192, w - 2, 26), fill=tints[name], outline=BLACK, width=2 * SCALE
        )
        card.text(x + w / 2, 195, name, 16, WHITE, "ma", 2)
        card.text(
            x + 4, 222, f"{start}{'+' * (spot + 1 == len(levels))}", 14, MUTED, "la", 2
        )
        mid = x + w / 2
        card.text(mid, 265, f"+{beans}", 20, GOLD if beans else MUTED, "ma")
        total = percent(sum(odds for odds, _ in tokens))
        card.text(mid, 345, total, 20, GOLD if tokens else MUTED, "ma")
        for row, (odds, amounts) in enumerate(reversed(tokens)):
            if len(tokens) == 1:
                break
            at = 376 + row * 18
            text = f"{percent(odds)} for {amounts[0]}"
            card.text(mid, at, text, 13, MUTED, "ma", 2)
        card.text(mid, 306, str(cooling[name]), 18, WHITE, "ma", 2)
    item_heads(card, 462)
    card.text(46, 462, "Items", 14, MUTED, "la", 2)
    y = 482
    for key, does in next(
        items for group, _, items in EFFECTS if group == "THERMOMETER"
    ):
        rule(card, y - 2)
        item_row(card, y, key, does)
        y += 40
    top = 618
    section(card, top, 118, "BOSS INSPECTION", RED, WHITE)
    facts = (
        f"{BOSS_VISITS} visits a day at any time, {BOSS_SECONDS // 60} minutes"
        f" to press one button, from Level {LADDER['boss'][0]}"
    )
    card.note(top, facts, 858)
    card.icon("kit/icon_megaboss_big", 46, top + 24, 70)
    outcomes(card, 170, top + 38, 684)
    return card.jpg().getvalue()


@lru_cache
def social_page():
    """Tables: the weekly quest. Invites: what each step pays both sides."""
    quest = TABLE_QUEST_TYPES["bean_collector"]
    card = page("COMMUNITY", "TABLES AND INVITES", 704)
    section(card, 124, 262, "TABLES")
    card.note(124, "New week on Sunday, 00:00 UTC", 858)
    card.text(46, 170, "Table earns", 15, MUTED, "la", 2)
    card.text(46, 228, "Each gets", 15, MUTED, "la", 2)
    left, width = 150, 660
    card.bar(left, 198, width, 16, 0.5)
    for spot, (target, reward) in enumerate(zip(quest["targets"], quest["rewards"])):
        x = left + width * (spot + 1) / len(quest["targets"])
        card.stop(x - 14, 192, spot < 2)
        card.text(x, 170, f"{target // 1000}k", 17, WHITE, "ma", 2)
        card.icon("kit/bean", x - 38, 228, 18)
        card.text(x - 16, 228, f"+{reward:,}", 16, GOLD, "la", 2)
    rule(card, 266)
    card.text(46, 284, "Seats", 15, MUTED, "la", 2)
    for seat in range(TABLE_SEATS):
        needed = seat < TABLE_SEATS_NEEDED
        card.draw.rounded_rectangle(
            box(46 + seat * 38, 308, 30, 30),
            7 * SCALE,
            fill=GOLD if needed else SLOT,
            outline=BLACK,
            width=3 * SCALE,
        )
    card.text(46, 348, f"{TABLE_SEATS_NEEDED} seats start the quest", 15, GOLD, "la", 2)
    card.text(854, 284, "Top table of the week, each member", 15, MUTED, "ra", 2)
    x = 854
    for picture, amount in (
        ("kit/icon_ranked_round_token", TABLE_WINNER_STAMPS),
        ("kit/token", TABLE_WINNER_TOKENS),
    ):
        prize = f"+{amount}"
        card.text(x, 306, prize, 26, GOLD, "ra")
        x -= card.measure(prize, 26) + 36
        card.icon(picture, x, 308, 28)
        x -= 18
    card.icon("kit/icon_trophy", x - 44, 304, 36)

    top = 418
    section(card, top, 236, "INVITES")
    pictures = ("brewing", "ready", "kit/token")
    card.text(854, top + 24, "You get", 14, MUTED, "ra", 2)
    for spot, (_, role, need, coin, yours) in enumerate(REFERRAL_STEPS):
        y = top + 46 + spot * 44
        rule(card, y - 4)
        fitted(card, pictures[spot], 46, y + 2, 32)
        card.text(90, y, role, 18, WHITE, "la", 2)
        card.text(90, y + 22, need, 12, MUTED, "la", 2)
        size = 24 if len(yours) < 6 else 18
        card.text(854, y + 28 - size, yours, size, GOLD, "ra")
        card.icon(coin, 820 - card.measure(yours, size), y + 5, 26)
    rule(card, top + 46 + len(REFERRAL_STEPS) * 44 - 4)
    checks = (
        "Joined by your link",
        "New to the server",
        f"Account {REFERRAL_ACCOUNT_DAYS}+ days old",
    )
    x = 46
    for line in checks:
        card.tick(x + 2, top + 192, 22)
        card.text(x + 34, top + 194, line, 16, WHITE, "la", 2)
        x += 34 + card.measure(line, 16) + 34
    card.note(top, "Starts over on the 1st of each month", 858)
    return card.jpg().getvalue()


@lru_cache
def games_page():
    """Bets, limits and what each result pays."""
    card = page(None, "GAMES", 738, "kit/coin_pile_03")
    section(card, 124, 118, "COIN FLIP")
    card.note(124, "Games pay Beans only", 858)
    card.text(46, 148, "Call heads or tails", 15, MUTED, "la", 2)
    sides = [
        (0.5, "Win: bet x2", shade(GREEN, 0.6)),
        (0.5, "Lose: bet gone", shade(RED, 0.6)),
    ]
    split(card, 46, 172, 808, sides)

    top = 274
    section(card, top, 250, "BLACKJACK")
    results = (
        ("21 on two cards", 2.5, GOLD),
        ("Win", 2, GREEN),
        ("Tie", 1, WHITE),
        ("Give up", 0.5, MUTED),
        ("Lose", 0, RED),
    )
    card.text(46, top + 24, "What comes back, times your bet", 15, MUTED, "la", 2)
    for row, (name, back, color) in enumerate(results):
        y = top + 50 + row * 32
        card.text(46, y + 2, name, 18, WHITE, "la", 2)
        card.bar(220, y, 540, 24, back / 2.5, color)
        card.text(854, y, f"x{back:g}", 22, color, "ra")
    card.text(
        46,
        top + 216,
        "Double down doubles the bet. The dealer draws to 17.",
        15,
        MUTED,
        "la",
        2,
    )

    top = 556
    section(card, top, 134, "LIMITS")
    plays = DAILY_GAMBLING_LIMITS
    card.text(560, top + 24, "Member", 15, MUTED, "ra", 2)
    card.text(854, top + 24, "Ultra Tier", 15, MUTED, "ra", 2)
    lines = (
        ("kit/bean", "Bet", span(MIN_BET, MAX_BET), span(MIN_BET, ULTRA_MAX_BET)),
        (
            "kit/icon_clock",
            "Games a day, each game",
            str(plays["coinflip"]),
            str(plays["coinflip"] * 2),
        ),
    )
    for row, (picture, name, member, ultra) in enumerate(lines):
        y = top + 50 + row * 38
        if row:
            rule(card, y - 5)
        fitted(card, picture, 46, y, 26)
        card.text(84, y + 3, name, 18, WHITE, "la", 2)
        card.text(560, y + 1, member, 22, GOLD, "ra")
        card.text(854, y + 1, ultra, 22, GOLD, "ra")
    return card.jpg().getvalue()


@lru_cache
def teams_page():
    """The team finder, what rep pays, and what adding a topic costs."""
    card = page("COMMUNITY", "TEAM FINDER AND TOPICS", 640)
    section(card, 124, 176, "TEAM FINDER")
    steps = (
        ("kit/icon_event", "Request", "Pick a region and what you play"),
        ("game/3v3", "Team up", "Teammates press Claim"),
        ("kit/icon_like", "Close", "Select who played with you"),
    )
    flow(card, 150, steps, 64)

    top = 332
    section(card, top, 146, "REP")
    rows = (
        ("kit/icon_like", "Play with a host who selects you", "+1 rep"),
        (
            "kit/token",
            f"Every rep also pays a Token, up to {REP_PAID_DAILY} reps a day",
            f"+{REP_TOKENS} each",
        ),
    )
    for row, (picture, name, value) in enumerate(rows):
        y = top + 28 + row * 40
        if row:
            rule(card, y - 6)
        fitted(card, picture, 46, y, 28)
        card.text(86, y + 4, name, 18, WHITE, "la", 2)
        card.text(854, y + 1, value, 22, GOLD, "ra")
        if picture == "kit/token":
            card.icon(picture, 818 - card.measure(value, 22), y + 2, 26)
    card.text(
        46,
        top + 112,
        "One rep per host a day. Rep shows on /balance and /leaderboard, and earns roles.",
        15,
        MUTED,
        "la",
        2,
    )

    top = 510
    section(card, top, 104, "TOPICS")
    fitted(card, "kit/icon_chat", 46, top + 28, 28)
    card.text(86, top + 32, "/topic gives the chat a question", 18, WHITE, "la", 2)
    card.text(854, top + 29, "Free", 22, GOLD, "ra")
    rule(card, top + 62)
    fitted(card, "kit/bean", 46, top + 68, 28)
    card.text(
        86,
        top + 72,
        "Get your own topic approved by staff",
        18,
        WHITE,
        "la",
        2,
    )
    card.text(854, top + 69, f"+{TOPIC_BEANS}", 22, GOLD, "ra")
    card.icon("kit/bean", 820 - card.measure(f"+{TOPIC_BEANS}", 22), top + 70, 26)
    return card.jpg().getvalue()


def rates_page():
    return rates_image(page("INVENTORY", "DROP RATES", 828))


# In the order of the places: Counter, Chat, Inventory, Community, then games.
PAGES = {
    "start": ("Start here", start_page),
    "order": ("Today's Order", order_page),
    "brewing": ("Brewing", brewing_page),
    "levels": ("Levels", levels_page),
    "beans": ("Beans", beans_page),
    "stations": ("Thermometer and Boss", stations_page),
    "effects": ("Effect items", effects_page),
    "rates": ("Drop rates", rates_page),
    "social": ("Tables and Invites", social_page),
    "teams": ("Team Finder and Topics", teams_page),
    "games": ("Games", games_page),
}


async def setup(bot):
    pass

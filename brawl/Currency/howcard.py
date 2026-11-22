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
    DAILY_GAMBLING_LIMITS,
    INVITEE_BREW_BEANS,
    INVITEE_SELL_BEANS,
    ITEM_STATIONS,
    LADDER,
    ORDER_TASK_LEVELS,
    REFERRAL_ACCOUNT_DAYS,
    REFERRAL_BRIDGE_BEANS,
    REFERRAL_MASTER_SELLS,
    REFERRAL_TRAINEE_BEANS,
    STAMP_MONTHLY_LIMIT,
    STAMP_PRICE_RANGES,
    TABLE_KICK_DAYS,
    TABLE_SEATS,
    TABLE_SEATS_NEEDED,
    TABLE_WINNER_TOKENS,
    THERMOMETER_COOLING,
    THERMOMETER_DAILY_TOKEN_DROPS,
    THERMOMETER_MAX,
    THERMOMETER_MESSAGE_HEAT,
    XP_BOOSTER_MULTIPLIER,
    XP_COOLDOWN,
    XP_PER_MESSAGE,
    XP_ULTRA_MULTIPLIER,
    CHAT_BOOST_MULTIPLIER,
    CHAT_BOOSTED_REWARD,
    CHAT_LIMITS,
    CHAT_MESSAGES,
    CHAT_REWARD,
    CHAT_WEEKEND_MULTIPLIER,
    DAILY_BEANS,
    LUCKY_DAILY_CHANCE,
    ORDER_STATION_TASKS,
    PERFECT_BREW_CHANCE,
    QUEST_BEAN_REWARDS,
    QUEST_BONUS_BEANS,
    ROAST_TYPES,
    STAMP_GOALS,
    STREAK_BEAN_MULTIPLIER,
    STREAK_DAYS,
    STREAK_TOKENS,
    TABLE_QUEST_TYPES,
    THERMOMETER_LEVELS,
    ULTRA_DAILY_BONUS,
    UNLOCK_REQ,
    WELCOME_BUTTON_REWARD,
)
from brawl.Currency.dropcard import rates_image
from brawl.Currency.gambling import MAX_BET, MIN_BET, ULTRA_MAX_BET
from brawl.Currency.helper import STORE_ITEMS
from brawl.Currency.levels import LEVEL_REWARDS, level_up_reward, xp_for_level

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
        picture, x + (size - icon_width(picture, height)) / 2, y + (size - height) / 2, height
    )


def arrow(card, x, y, size=12, fill=GOLD):
    """A small arrow head pointing right, centered on (x, y)."""
    points = [(x - size * 0.6, y - size), (x + size * 0.7, y), (x - size * 0.6, y + size)]
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


def page(title, line, height):
    card = Card(WIDTH, height, BACKGROUND)
    card.title(title, line)
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


@lru_cache
def start_page():
    """The whole cafe on one card: the loop, what each currency buys, a day."""
    card = page("HOW THE CAFE WORKS", "Chat, brew, spend. A new day starts at 00:00 UTC.", 782)
    roasts = list(ROAST_TYPES.values())
    tokens = [pay for roast in roasts for pay in roast["payout"] if pay]
    section(card, 124, 162, "THE LOOP")
    flow(
        card,
        146,
        [
            ("items/message_pin", "Chat", f"{span(*CHAT_MESSAGES)} messages"),
            ("kit/bean", "Beans", f"+{span(*CHAT_REWARD)}", GOLD),
            ("brewing", "Brew", f"{hours(roasts[0]['time'])} to {hours(roasts[-1]['time'])}"),
            ("kit/token", "Tokens", f"+{min(tokens)} to +{max(tokens)}", GOLD),
            ("kit/icon_shop", "Shop", "rewards and passes"),
        ],
    )

    top = 318
    section(card, top, 230, "WHAT EACH ONE IS FOR", BLUE, WHITE)
    uses = [
        ("kit/icon_xp", "XP", WHITE, [("brewing", "New stations", ""), ("kit/icon_role", "Level roles", "")]),
        (
            "kit/bean",
            "Beans",
            GOLD,
            [("brewing", "Brews", ""), ("items/star_drop", "Star Drops", ""), ("kit/coin_pile_03", "Games", "")],
        ),
        (
            "kit/token",
            "Tokens",
            GOLD,
            [
                ("kit/icon_shop", "Shop rewards", ""),
                ("items/effect", "Effect items", ""),
                ("items/mega_box", "Mega Boxes", ""),
                ("kit/icon_brawl_pass", "Passes", ""),
            ],
        ),
        (
            "kit/icon_ranked_round_token",
            "Stamps",
            GREEN,
            [
                ("kit/icon_brawl_pass", "Brawl Pass", str(STAMP_GOALS["brawl_pass"])),
                ("kit/icon_brawl_pass_plus", "Brawl Pass Plus", str(STAMP_GOALS["brawl_pass_plus"])),
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

    top = 580
    section(card, top, 150, "EVERY DAY", GREEN)
    flow(
        card,
        top + 22,
        [
            ("kit/icon_clock", "Clock In", f"+{DAILY_BEANS:,} Beans"),
            ("kit/icon_quest", "Today's Order", f"+{ORDER_BEANS:,} Beans"),
            ("kit/icon_ranked_round_token", "Stamp", "+1 a day", GREEN),
            ("kit/icon_brawl_pass", "Brawl Pass", f"{STAMP_GOALS['brawl_pass']} Stamps", GOLD),
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
    card = page("BREWING", "Pay Beans, wait, then sell for Tokens. One brew at a time.", top + 342)
    section(card, 124, len(ROAST_TYPES) * row + 24, "ROASTS")
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
            card.text(122, y + 67, f"Never burns. Needs {UNLOCK_REQ} brews", 15, GREEN, "la", 2)
        payouts(card, 372, y + 22, 356, roast, TINTS[key])
        card.text(854, y + 8, "Average", 14, MUTED, "ra", 2)
        average = f"{mean(roast):.2f}"
        card.text(854, y + 26, average, 26, GOLD, "ra")
        card.icon("kit/token", 818 - card.measure(average, 26), y + 28, 28)

    section(card, top + 22, 272, "WHAT CHANGES A BREW", BLUE, WHITE)
    columns = [530 + spot * 108 for spot in range(len(ROAST_TYPES))]
    for x, (key, roast) in zip(columns, ROAST_TYPES.items()):
        card.text(x, top + 44, roast["name"].split()[0], 16, TINTS[key], "ra", 2)
    roasts = list(ROAST_TYPES.values())
    burns = [not roast["payout"][0] for roast in roasts]
    low = [min(pay for pay in roast["payout"] if pay) for roast in roasts]
    best = [max(roast["payout"]) * 2 for roast in roasts]
    usual = [
        max(zip(roast["weights"], roast["payout"]))[1] for roast in roasts
    ]
    lines = (
        ("ready", "A perfect brew pays up to", f"{PERFECT_BREW_CHANCE}% of sales, 25% with Expert Barista", GOLD,
         [str(pay) for pay in best]),
        ("items/free_insurance", "An insured burn pays", "free with Barista's Protection", GREEN,
         [str(pay) if burn else "" for pay, burn in zip(low, burns)]),
        ("items/burnt_to_perfect", "With Resurrection, a burn pays", "the top payout, x2", GREEN,
         [str(pay) if burn else "" for pay, burn in zip(best, burns)]),
        ("kit/icon_role", "Master Barista adds", "half the usual payout", GOLD,
         [f"+{max(pay // 2, 1)}" for pay in usual]),
        ("items/half_brew_time", "Turbo Brewing time", "half as long", MUTED,
         [hours(roast["time"] // 2) for roast in roasts]),
    )
    for row, (picture, name, note, color, cells) in enumerate(lines):
        y = top + 70 + row * 44
        rule(card, y - 5)
        fitted(card, picture, 46, y + 2, 30)
        card.text(86, y - 1, name, 17, WHITE, "la", 2)
        card.text(86, y + 20, note, 13, MUTED, "la", 2)
        for x, cell in zip(columns, cells):
            card.text(x, y + 5, cell or "none", 20 if cell else 14, color if cell else MUTED, "ra", 2 if not cell else None)
    return card.jpg().getvalue()


@lru_cache
def beans_page():
    """Where Beans come from: chat, its daily limit, Clock In and the rest."""
    card = page("BEANS", "Chat and clock in every day. Beans pay for brews.", 990)
    section(card, 124, 382, "CHAT")
    for spot in range(10):
        card.icon("items/message_pin", 46 + spot * 30, 156, 24)
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
    section(card, top, 236, "CLOCK IN", GREEN)
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
        76, top + 204, "A missed day starts again at Day 1. Streak Shield saves it once.", 15, MUTED, "la", 2
    )

    top = 806
    steps = TABLE_QUEST_TYPES["bean_collector"]["rewards"]
    heat = [level[2] for level in THERMOMETER_LEVELS if level[2]]
    section(card, top, 134, "MORE BEANS", BLUE, WHITE)
    first, last = level_up_reward(1)[0], level_up_reward(max(LEVEL_REWARDS))[0]
    flow(
        card,
        top + 24,
        [
            ("kit/icon_quest", f"+{ORDER_BEANS:,}", "Today's Order", GOLD),
            ("kit/icon_xp", f"+{span(first, last)}", "each level up", GOLD),
            ("kit/icon_wasabi_power_hot", f"+{span(min(heat), max(heat))}", "a message, hot chat", GOLD),
            ("kit/icon_trophy", f"+{span(min(steps), max(steps))}", "table quest step", GOLD),
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
    "effects": "items/effect",
    "boxes": "items/mega_box",
    "style": "items/custom_credit",
}


def total_xp(level):
    return sum(xp_for_level(below) for below in range(level))


@lru_cache
def levels_page():
    """XP in, the ladder of stations, and what each level pays."""
    card = page("LEVELS", "Chat to earn XP. Each level opens something new.", 806)
    section(card, 124, 132, "XP")
    card.icon("items/message_pin", 46, 150, 34)
    arrow(card, 104, 168)
    card.icon("kit/icon_xp", 124, 148, 40)
    gain = f"+{span(*XP_PER_MESSAGE)}"
    card.text(180, 150, gain, 30, GOLD)
    once = f"one message every {XP_COOLDOWN} seconds"
    card.text(192 + card.measure(gain, 30), 162, once, 16, MUTED, "la", 2)
    low, high = XP_PER_MESSAGE
    roles = (("Member", 1), ("Booster", XP_BOOSTER_MULTIPLIER), ("Ultra Tier", XP_ULTRA_MULTIPLIER))
    for spot, (name, times) in enumerate(roles):
        card.text(46 + spot * 130, 196, name, 14, MUTED, "la", 2)
        card.text(46 + spot * 130, 214, span(low * times, high * times), 20, GOLD)
    card.text(854, 218, "Next level needs 100 x level + 75 XP", 15, MUTED, "ra", 2)

    top = 288
    section(card, top, 262, "WHAT EACH LEVEL OPENS", BLUE, WHITE)
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
    section(card, top, 174, "WHEN YOU LEVEL UP", GREEN)
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
    card = page("TODAY'S ORDER", "Clock in to get it. Finish it for a Stamp.", 804)
    section(card, 124, 312, "THE ORDER")
    flow(
        card,
        146,
        [
            ("kit/icon_clock", "Clock In", "starts the order"),
            ("items/message_pin", "Chat task", f"+{each}", GOLD),
            ("kit/icon_quest", "Station task", f"+{each}", GOLD),
            ("kit/icon_quest", "Station task", f"+{each}", GOLD),
            ("kit/icon_ranked_round_token", "All done", f"+{bonus} and 1 Stamp", GREEN),
        ],
        size=56,
    )
    levels = ORDER_TASK_LEVELS
    limits = span(min(CHAT_LIMITS.values()), max(CHAT_LIMITS.values()))
    table(
        card,
        288,
        [
            ("Chat task", GOLD, [("kit/bean", "Your daily chat limit", limits)]),
            (
                "Station tasks",
                BLUE,
                [
                    ("brewing", "Start a brew", f"Lv {levels['brew_start']}"),
                    ("ready", "Sell a brew", f"Lv {levels['brew_sells']}"),
                    ("kit/icon_shop", "Buy from the shop", f"Lv {levels['shop_purchases']}"),
                ],
            ),
            ("Boss", RED, [("kit/icon_megaboss_big", "Taking part ticks a station task", "")]),
        ],
        left=206,
    )

    top = 468
    section(card, top, 286, "STAMPS AND PASSES", GREEN)
    passes = (
        ("brawl_pass", "kit/icon_brawl_pass", "Brawl Pass"),
        ("brawl_pass_plus", "kit/icon_brawl_pass_plus", "Brawl Pass Plus"),
    )
    for row, (key, picture, name) in enumerate(passes):
        y = top + 28 + row * 104
        goal, (low, high) = STAMP_GOALS[key], STAMP_PRICE_RANGES[key]
        card.slot(42, y, 816, 96)
        card.icon(picture, 56, y + 24, 44)
        card.text(140, y + 10, name, 22, GOLD)
        card.icon("kit/icon_ranked_round_token", 138, y + 46, 34)
        card.text(180, y + 50, f"{goal} Stamps", 22, GREEN)
        card.text(420, y + 12, "Price by Clock In streak", 14, MUTED, "la", 2)
        prices = ((10, high), (55, (high + low) // 2), (100, low))
        for spot, (days, price) in enumerate(prices):
            x = 420 + spot * 142
            card.text(x, y + 34, f"{days}{'+' * (spot == 2)} days", 15, WHITE, "la", 2)
            card.icon("kit/token", x, y + 56, 24)
            card.text(x + 30, y + 57, f"{price}", 20, GOLD)
            if spot:
                arrow(card, x - 22, y + 62, 8)
    card.icon("kit/icon_ranked_round_token", 46, top + 242, 26)
    card.text(80, top + 246, "1 Stamp a day", 16, GREEN, "la", 2)
    month = f"{STAMP_MONTHLY_LIMIT} passes a month for the whole server"
    card.text(854, top + 246, month, 16, MUTED, "ra", 2)
    return card.jpg().getvalue()


def lasting(seconds):
    if not seconds:
        return "now"
    count, unit = (seconds // 86400, "d") if seconds >= 86400 else (seconds // 3600, "h")
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
        (("thermometer_boost", "+30 heat"), ("freeze_thermometer", "heat stays where it is")),
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
    card = page("EFFECT ITEMS", f"Boosts you buy in the shop. Most open at Level {level}.", height)
    section(card, 124, height - 172, "ITEMS")
    item_heads(card, 142)
    y = 166
    for group, color, items in EFFECTS:
        card.draw.rectangle(box(46, y + 6, 808, 22), fill=(*shade(color, 0.5), 150))
        card.text(56, y + 8, group, 14, WHITE, "la", 2)
        y += 34
        for key, does in items:
            item_row(card, y, key, does)
            y += 40
    card.hint("Buy again: how long before you can buy the same item again.")
    return card.jpg().getvalue()


@lru_cache
def stations_page():
    """The thermometer's heat levels and the boss's odds."""
    card = page("THERMOMETER AND BOSS", "Busy chat pays extra. The boss drops in with gifts.", 800)
    section(card, 124, 382, "THERMOMETER")
    card.icon("items/message_pin", 46, 148, 26)
    arrow(card, 92, 162, 9)
    heat = f"+{span(*THERMOMETER_MESSAGE_HEAT)} heat"
    card.text(108, 150, heat, 20, GOLD)
    card.text(120 + card.measure(heat, 20), 154, "each main chat message", 15, MUTED, "la", 2)
    drops = f"{THERMOMETER_DAILY_TOKEN_DROPS} Token drops a day, from Level {LADDER['thermometer'][0]}"
    card.text(854, 154, drops, 15, MUTED, "ra", 2)
    levels = sorted(THERMOMETER_LEVELS)
    cooling = dict(zip(("Cold", "Warm", "Hot", "Boiling"), (lost for _, lost in reversed(THERMOMETER_COOLING))))
    tints = {"Cold": BLUE, "Warm": GOLD, "Hot": (255, 140, 40), "Boiling": RED}
    left, width = 190, 664
    for row, name in enumerate(("Beans a message", "Token drop", "Cools a minute")):
        rule(card, 256 + row * 40)
        card.text(46, 268 + row * 40, name, 16, MUTED, "la", 2)
    card.text(46, 196, "Heat", 16, MUTED, "la", 2)
    for spot, (start, name, beans, tokens) in enumerate(levels):
        end = levels[spot + 1][0] if spot + 1 < len(levels) else THERMOMETER_MAX
        x = left + width * start / THERMOMETER_MAX
        w = width * (end - start) / THERMOMETER_MAX
        card.draw.rectangle(
            box(x + 1, 192, w - 2, 26), fill=tints[name], outline=BLACK, width=2 * SCALE
        )
        card.text(x + w / 2, 195, name, 16, WHITE, "ma", 2)
        card.text(x + 4, 222, f"{start}{'+' * (spot + 1 == len(levels))}", 14, MUTED, "la", 2)
        mid = x + w / 2
        card.text(mid, 265, f"+{beans}" if beans else "0", 20, GOLD if beans else MUTED, "ma")
        if not tokens:
            card.text(mid, 307, "none", 15, MUTED, "ma", 2)
        for row, (odds, amounts) in enumerate(reversed(tokens)):
            amount = span(min(amounts), max(amounts))
            at = 307 if len(tokens) == 1 else 298 + row * 18
            card.text(mid, at, f"{percent(odds)} for {amount}", 15, GOLD, "ma", 2)
        card.text(mid, 346, str(cooling[name]), 18, WHITE, "ma", 2)
    item_heads(card, 390)
    card.text(46, 390, "Items", 14, MUTED, "la", 2)
    y = 410
    for key, does in next(items for group, _, items in EFFECTS if group == "THERMOMETER"):
        rule(card, y - 2)
        item_row(card, y, key, does)
        y += 40
    top = 546
    section(card, top, 204, "BOSS INSPECTION", RED, WHITE)
    card.icon("kit/icon_megaboss_big", 46, top + 26, 76)
    names = {"mega_box": "Mega Box", "star_drop": "Star Drop", "nothing": "Air"}
    colors = {"mega_box": GREEN, "star_drop": GOLD, "nothing": RED}
    card.text(150, top + 22, "Press one button. What you get", 15, MUTED, "la", 2)
    parts = [(odds, names[key], shade(colors[key], 0.6)) for key, odds in BOSS_ODDS]
    split(card, 150, top + 46, 704, parts)
    flow(
        card,
        top + 116,
        [
            ("kit/icon_megaboss_big", f"{span(*BOSS_VISITS)} visits", "a day, any time"),
            ("kit/icon_clock", f"{BOSS_SECONDS // 60} minutes", "to press, once each"),
            ("kit/icon_quest", "1 task ticked", "in Today's Order", GREEN),
            ("kit/icon_xp", f"Level {LADDER['boss'][0]}", "to take part"),
        ],
        size=0,
        arrows=False,
    )
    return card.jpg().getvalue()


@lru_cache
def social_page():
    """Tables: the weekly quest. Invites: what each step pays both sides."""
    quest = TABLE_QUEST_TYPES["bean_collector"]
    card = page("TABLES AND INVITES", "Team up for a weekly goal. Bring friends for more.", 732)
    section(card, 124, 262, "TABLES")
    card.text(46, 148, "Weekly quest: Beans the table earns together", 15, MUTED, "la", 2)
    card.text(854, 148, "for each member", 15, MUTED, "ra", 2)
    left, width = 86, 728
    card.bar(left, 198, width, 16, 0.5)
    for spot, (target, reward) in enumerate(zip(quest["targets"], quest["rewards"])):
        x = left + width * (spot + 1) / len(quest["targets"])
        card.check(x - 14, 192, spot < 2)
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
    card.text(854, 284, "Top table of the week", 15, MUTED, "ra", 2)
    prize = f"+{TABLE_WINNER_TOKENS} each"
    card.text(854, 306, prize, 26, GOLD, "ra")
    card.icon("kit/token", 818 - card.measure(prize, 26), 308, 28)
    card.icon("kit/icon_trophy", 760 - card.measure(prize, 26), 304, 36)
    card.text(854, 348, "New week on Sunday, 00:00 UTC", 15, MUTED, "ra", 2)

    top = 418
    section(card, top, 264, "INVITES", BLUE, WHITE)
    steps = (
        ("brewing", "They brew", f"+{REFERRAL_TRAINEE_BEANS:,}", "kit/bean", f"+{INVITEE_BREW_BEANS}", "Trainee Barista"),
        ("ready", "They sell", f"+{REFERRAL_BRIDGE_BEANS:,}", "kit/bean", f"+{INVITEE_SELL_BEANS}", "Bridge Barista"),
        ("kit/token", f"{REFERRAL_MASTER_SELLS} sells in all", "+50% a sale", "kit/token", "", "Master Barista"),
    )
    for name, x in (("They get", 430), ("Role", 560), ("You get", 854)):
        card.text(x, top + 24, name, 14, MUTED, "la" if name == "Role" else "ra", 2)
    for spot, (picture, when, yours, coin, theirs, role) in enumerate(steps):
        y = top + 46 + spot * 44
        rule(card, y - 4)
        fitted(card, picture, 46, y + 2, 32)
        card.text(90, y + 7, when, 19, WHITE, "la", 2)
        if theirs:
            card.text(430, y + 7, theirs, 19, WHITE, "ra", 2)
            card.icon("kit/bean", 402 - card.measure(theirs, 19), y + 8, 20)
        card.text(560, y + 9, role, 16, MUTED, "la", 2)
        card.text(854, y + 4, yours, 24, GOLD, "ra")
        card.icon(coin, 820 - card.measure(yours, 24), y + 5, 26)
    rule(card, top + 46 + len(steps) * 44 - 4)
    checks = ("Joined by your link", "New to the server", f"Account {REFERRAL_ACCOUNT_DAYS}+ days old")
    x = 46
    for line in checks:
        card.icon("kit/icon_ranked_round_token", x, top + 190, 26)
        card.text(x + 34, top + 194, line, 16, WHITE, "la", 2)
        x += 34 + card.measure(line, 16) + 34
    card.text(46, top + 232, "Roles and the sell count start over on the 1st of each month.", 15, MUTED, "la", 2)
    return card.jpg().getvalue()


@lru_cache
def games_page():
    """Bets, limits and what each result pays."""
    card = page("GAMES", f"Bet Beans for fun. Games open at Level {LADDER['games'][0]}.", 738)
    section(card, 124, 118, "COIN FLIP")
    card.text(46, 148, "Call heads or tails", 15, MUTED, "la", 2)
    sides = [(0.5, "Win: bet x2", shade(GREEN, 0.6)), (0.5, "Lose: bet gone", shade(RED, 0.6))]
    split(card, 46, 172, 808, sides)

    top = 274
    section(card, top, 250, "BLACKJACK", BLUE, WHITE)
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
    card.text(46, top + 216, "Double down doubles the bet. The dealer draws to 17.", 15, MUTED, "la", 2)

    top = 556
    section(card, top, 134, "LIMITS", GREEN)
    plays = DAILY_GAMBLING_LIMITS
    card.text(560, top + 24, "Member", 15, MUTED, "ra", 2)
    card.text(854, top + 24, "Ultra Tier", 15, MUTED, "ra", 2)
    lines = (
        ("kit/bean", "Bet", span(MIN_BET, MAX_BET), span(MIN_BET, ULTRA_MAX_BET)),
        ("kit/icon_clock", "Games a day, each game", str(plays["coinflip"]), str(plays["coinflip"] * 2)),
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


def rates_page():
    return rates_image(BACKGROUND)


PAGES = {
    "start": ("Start here", start_page),
    "levels": ("Levels", levels_page),
    "beans": ("Beans", beans_page),
    "order": ("Today's Order", order_page),
    "brewing": ("Brewing", brewing_page),
    "effects": ("Effect items", effects_page),
    "rates": ("Drop rates", rates_page),
    "stations": ("Thermometer and Boss", stations_page),
    "social": ("Tables and Invites", social_page),
    "games": ("Games", games_page),
}


async def setup(bot):
    pass

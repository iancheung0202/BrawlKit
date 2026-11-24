"""The four pages of /balance: Counter, Chat, Inventory and Community."""

import time

from PIL import Image, ImageDraw

from brawl.Currency.card import (
    ASSETS,
    BLACK,
    BLUE,
    GOLD,
    GREEN,
    GREY,
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
    named,
    plain,
)
from brawl.Currency.config import (
    BOSS_VISITS,
    LADDER,
    REFERRAL_MASTER_SELLS,
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
    TABLE_SEATS,
    TABLE_SEATS_NEEDED,
    TOPIC_BEANS,
)
from brawl.Currency.helper import STORE_ITEMS
from brawl.Currency.itemcard import HELD, ends, plural
from brawl.Currency.ladder import next_unlock
from brawl.Currency.stationcard import heat_panel
from brawl.Currency.tablecard import ink, quest, rgb, top_prize

STAMP_ROW = 15
PASSES = (
    ("brawl_pass", "Brawl Pass", (20, 60, 170, 200), (80, 140, 255)),
    ("brawl_pass_plus", "Brawl Pass Plus", (90, 40, 170, 200), (200, 120, 255)),
)
BOSS_GOT = {
    "mega_box": ("items/mega_box", "Mega Box"),
    "star_drop": ("items/star_drop", "Star Drop"),
    "nothing": ("kit/icon_air", "Air"),
}


def clock(seconds):
    hours, minutes = divmod(max(int(seconds), 0) // 60, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def timer(card, y, text, right=604):
    """A grey line with a clock over a panel's top right corner."""
    x = card.note(y, text, right)
    card.icon("kit/icon_clock", x - 22, y - 17, 14)


def pay(card, right, y, pays, size=17):
    """Icons and amounts ending at right; returns where they start."""
    for picture, amount in reversed(pays):
        right -= card.measure(amount, size)
        card.text(right, y, amount, size, GOLD, "la", 2)
        right -= size + 9
        card.icon(picture, right, y - 2, size + 5)
        right -= 12
    return right


def strike(card, x, y, label, size, fill):
    """A price that no longer applies, with a line through it."""
    card.text(x, y, label, size, fill, "la", 2)
    at = (y + size * 0.62) * SCALE
    card.draw.line(
        [((x - 2) * SCALE, at), ((x + card.measure(label, size) + 2) * SCALE, at)],
        fill=RED,
        width=3 * SCALE,
    )


def ring(card, x, y, radius, tint):
    card.draw.ellipse(
        box(x - radius, y - radius, radius * 2, radius * 2),
        outline=tint,
        width=3 * SCALE,
    )


def draw_header(place, member, sign=None):
    """Every page opens the same way: the place, then the wallet.

    A page outside /balance gives its own sign: color, scene and icon."""
    color, scene, picture = sign or PLACES[place]
    card = Card(900, 92, scene)
    art = Image.open(f"{ASSETS}bg/{scene}.jpg").convert("RGBA")
    width, height = 900 * SCALE, 92 * SCALE
    art = art.resize((width, art.height * width // art.width))
    top = int((art.height - height) * 0.62)
    art = art.crop((0, top, width, top + height))
    art.alpha_composite(Image.new("RGBA", art.size, (10, 12, 40, 120)))
    card.image = art
    card.draw = ImageDraw.Draw(card.image, "RGBA")
    card.icon(picture, 24, 21, 50)
    card.text(88, 22, place, 38, color)
    pills = (
        ("kit/bean", f"{member['beans']:,}", "Beans"),
        ("kit/token", f"{member['tokens']:,}", "Tokens"),
        ("kit/icon_ranked_round_token", f"{member['stamps']:,}", "Stamps"),
    )
    left = 908 - sum(card.measure(value, 24) + 96 for _, value, _ in pills)
    for name, value, label in pills:
        middle = left + (card.measure(value, 24) + 62) / 2
        card.text(middle, 63, label, 13, WHITE, "ma", 2)
        left = card.pill(left, 19, name, value)
    return card.jpg()


def draw_order(card, tasks, store):
    card.panel(26, 28, 414, 250)
    card.tag(42, 16, "TODAY'S ORDER")
    if not tasks:
        card.icon("kit/icon_inbox", 198, 68, 70)
        card.text(233, 162, "Clock in to get today's order", 23, WHITE, "ma", 2)
        line = card.fit(f"Press Clock In in #{store}", 18, 370)
        return card.text(233, 200, line, 18, GOLD, "ma", 2)
    done = sum(task[2] for task in tasks)
    card.text(420, 42, f"{done} of {len(tasks)} done", 20, GOLD, "ra")
    card.icon("kit/icon_ranked_round_token", 46, 247, 20)
    card.text(72, 250, "Complete all for 1 Stamp", 14, GOLD, "la", 2)
    for row, (name, state, finished, part) in enumerate(tasks):
        card.task(46, 76 + row * 58, 374, name, state, finished, part)
    card.next_order(420, 250, "ra")


def draw_brew(card, brew, unlocked):
    card.panel(460, 28, 414, 150)
    card.tag(476, 16, "BREW STATION")
    if not unlocked or not brew:
        card.icon("empty", 480, 48, 84)
        title, line, hint = (
            ("Nothing brewing", "Beans turn into Tokens here", "Use /brew to start one")
            if unlocked
            else (
                "Locked",
                f"Opens at Level {LADDER['brewing'][0]}",
                "Chat to level up",
            )
        )
        card.text(580, 46, title, 24, WHITE if unlocked else MUTED)
        card.text(580, 80, line, 17, MUTED, "la", 2)
        return card.text(580, 142, hint, 15, GOLD, "la", 2)
    roast = ROAST_TYPES[brew["roast_type"]]
    left = brew["end_time"] - time.time()
    ready = left <= 0
    card.icon("ready" if ready else "brewing", 480, 48, 84)
    card.text(580, 46, roast["name"], 24)
    pay(card, 852, 52, [("kit/token", f"up to {max(roast['payout'])}")], 15)
    state = "Ready to sell!" if ready else f"Ready in {clock(left)}"
    card.text(580, 80, state, 17, GREEN if ready else MUTED, "la", 2)
    card.bar(580, 108, 272, 20, 1 if ready else 1 - left / roast["time"], GREEN)
    hint = "Use /sell to collect your Tokens" if ready else "Come back when it is ready"
    card.text(580, 142, hint, 15, GOLD, "la", 2)
    if brew.get("insured"):
        card.text(852, 142, "Insured", 15, GREEN, "ra", 2)


def draw_counter(member):
    """Today's Order, the Brew Station and the level, on the member's background."""
    card = Card(900, 302, member["background"])
    draw_order(card, member["tasks"], member.get("store", "the store"))
    draw_brew(card, member["brew"], member["brewing"])
    card.panel(460, 198, 414, 80)
    card.tag(476, 186, "LEVEL")
    card.icon("kit/icon_xp", 478, 216, 44)
    level = str(member["level"])
    card.text(536, 220, level, 30, GOLD)
    x = 552 + card.measure(level, 30)
    label = f"{member['xp']:,} / {member['xp_needed']:,}"
    card.bar(x, 218, 852 - x, 24, member["xp"] / member["xp_needed"], BLUE, label)
    card.text(x, 250, next_unlock(member["level"]), 13, MUTED, "la", 2)
    return card.jpg()


def draw_stamps(member):
    """The Stamp Card: the grid, both passes and what the streak saves."""
    card = Card(900, 386, member["background"])
    stamps, tokens = member["stamps"], member["tokens"]
    card.panel(26, 28, 848, 184)
    card.tag(42, 16, "STAMP CARD")
    redeemed = (
        f"{member['redeemed']} of {STAMP_MONTHLY_LIMIT} passes"
        " redeemed by the server this month"
    )
    card.text(854, 8, redeemed, 13, MUTED, "ra", 2)
    # A pass ring goes under its spot, so the Mega Box there stays on top.
    for tier, _, _, tint in PASSES:
        spot = STAMP_GOALS[tier] - 1
        ring(card, 86 + spot % STAMP_ROW * 52, 68 + spot // STAMP_ROW * 42, 20, tint)
    for row in range(max(STAMP_GOALS.values()) // STAMP_ROW):
        have = stamps - STAMP_ROW * row
        card.stamps(
            86,
            68 + row * 42,
            have if have >= 0 else -1,
            STAMP_ROW,
            STAMP_ROW,
            52,
            17,
            (STAMP_BOX_EVERY, "items/mega_box", STAMP_BOXES),
        )
    card.text(48, 180, f"{stamps} Stamps", 20)
    key = (("Next", GOLD), *((name, tint) for _, name, _, tint in PASSES))
    wide = sum(22 + card.measure(name, 15) for name, _ in key) + 22 * (len(key) - 1)
    x = 430 - wide / 2
    for name, tint in key:
        ring(card, x + 7, 190, 7, tint)
        card.text(x + 22, 182, name, 15, MUTED, "la", 2)
        x += 44 + card.measure(name, 15)
    today = (
        "Stamped today"
        if member["stamped"]
        else (
            f"{member['done']} of {member['order']} tasks done today"
            if member["order"]
            else "Clock in to get today's order"
        )
    )
    card.text(852, 181, today, 17, GREEN if member["stamped"] else GOLD, "ra", 2)
    for spot, (tier, name, fill, _) in enumerate(PASSES):
        x = 26 + spot * 434
        need, price = STAMP_GOALS[tier], member["prices"][tier]
        full = STAMP_PRICE_RANGES[tier][1]
        card.panel(x, 228, 414, 96, fill)
        card.icon(f"kit/icon_{tier}", x + 14, 246, 60)
        card.text(x + 126, 242, name, 24)
        if stamps >= need and tokens >= price:
            card.text(x + 400, 249, "/redeem", 15, GREEN, "ra", 2)
        card.icon("kit/icon_ranked_round_token", x + 126, 282, 24)
        card.bar(x + 154, 281, 76, 26, min(stamps / need, 1), GREEN)
        have = f"{min(stamps, need):,} / {need:,}"
        card.text(x + 192, 293, have, 15, WHITE, "mm", 2)
        card.icon("kit/token", x + 240, 282, 24)
        card.bar(x + 268, 281, 132, 26, min(tokens / price, 1), GOLD)
        label = f"{min(tokens, price):,} / {price:,}"
        was = f"{full:,}" if price < full else ""
        wide = card.measure(label, 15) + (8 + card.measure(was, 15) if was else 0)
        at = x + 268 + (132 - wide) / 2
        card.text(at, 285, label, 15, WHITE, "la", 2)
        if was:
            strike(
                card, at + card.measure(label, 15) + 8, 285, was, 15, (200, 205, 230)
            )
    draw_streak(card, 338, member["streak"], member["prices"])
    return card.jpg()


def draw_streak(card, y, streak, prices):
    """How much the Clock In streak takes off a pass, and where that stops."""
    start, lowest = STAMP_PRICE_STREAK
    tier = PASSES[0][0]
    card.icon("kit/icon_calendar", 30, y, 28)
    days = f"{streak}-day streak"
    card.text(68, y + 4, days, 18, GOLD)
    x = 82 + card.measure(days, 18)
    card.text(x, y + 7, "saves", 15, WHITE, "la", 2)
    x += card.measure("saves", 15) + 8
    card.icon("kit/token", x, y + 4, 22)
    x += 28
    saved = f"{STAMP_PRICE_RANGES[tier][1] - prices[tier]} a pass"
    card.text(x, y + 7, saved, 15, GOLD, "la", 2)
    x += card.measure(saved, 15) + 18
    end = f"Day {lowest}"
    card.text(872, y + 7, end, 14, MUTED, "ra", 2)
    right = 872 - card.measure(end, 14)
    part = min(max(streak - start, 0), lowest - start) / (lowest - start)
    card.bar(x, y + 8, right - 12 - x, 14, part, GREEN)


def draw_boss(card, y, visits, locked):
    """The day's visits as stops on one line: what each gave, or that it was missed."""
    if locked:
        card.note(y, f"From Level {LADDER['boss'][0]}")
    else:
        timer(card, y, f"Cycle restarts in {clock(86400 - time.time() % 86400)}")
    card.panel(16, y, 608, 88, (96, 20, 30, 215))
    card.tag(32, y - 12, "BOSS INSPECTION", RED, WHITE)
    step = 568 / BOSS_VISITS
    card.draw.line(
        [
            ((36 + step / 2) * SCALE, (y + 36) * SCALE),
            ((604 - step / 2) * SCALE, (y + 36) * SCALE),
        ],
        fill=(255, 255, 255, 50),
        width=3 * SCALE,
    )
    for spot in range(BOSS_VISITS):
        x = 36 + step * (spot + 0.5)
        got = visits[spot] if spot < len(visits) else None
        if got in BOSS_GOT:
            picture, label = BOSS_GOT[got]
            color = WHITE
        else:
            picture = "kit/icon_megaboss_big"
            label, color = ("Missed", RED) if got else ("Not yet", MUTED)
        image = icon(picture, 38)
        if color is not WHITE:
            grey = image.convert("LA").convert("RGB").split()
            faint = image.getchannel("A").point(lambda value: value * 2 // 3)
            image = Image.merge("RGBA", (*grey, faint))
        card.draw.ellipse(box(x - 24, y + 12, 48, 48), fill=(60, 12, 20, 255))
        card.paste(
            image, x - image.width / SCALE / 2, y + 36 - image.height / SCALE / 2
        )
        card.text(x, y + 64, label, 14, color, "ma", 2)


def draw_chat(member):
    """Chat Beans, the Thermometer and the boss's visits today."""
    card = Card(640, 382, PLACES["CHAT"][1])
    y = 24
    earned, limit = member["chat"]
    timer(card, y, f"Daily cap resets in {clock(member['chat_resets'] - time.time())}")
    card.panel(16, y, 608, 58)
    card.tag(32, y - 12, "CHAT BEANS")
    card.icon("kit/bean", 36, y + 14, 30)
    label = f"{min(earned, limit):,} / {limit:,}"
    card.bar(82, y + 18, 522, 22, earned / limit, GOLD, label)
    y += 88
    heat_panel(card, y, member["cup"])
    draw_boss(card, y + 166, member["boss"], member.get("boss_locked"))
    return card.jpg()


def tile(card, x, y, w, picture, name, line, tint=MUTED, tag=None, on=True):
    """An item on a tile that leans a little; w is the tile's full width."""
    h, lean = 96, 5
    corners = ((x + lean, y), (x + w, y), (x + w - lean, y + h), (x, y + h))
    card.draw.polygon(
        [(a * SCALE, b * SCALE) for a, b in corners],
        fill=SLOT,
        outline=BLACK,
        width=3 * SCALE,
    )
    middle, room = x + w / 2, w - 16
    image = icon(picture, 40)
    card.paste(image, middle + 1 - image.width / SCALE / 2, y + 9)
    size = 16 if card.measure(name, 16) <= room else 13
    name = card.fit(name, size, room)
    card.text(middle, y + 62, name, size, WHITE if on else GREY, "mm", 2)
    card.text(middle - 1, y + 80, line, 13, tint if on else GREY, "mm", 2)
    if tag:
        card.tag(x + w + 2, y - 10, *tag, right=True)


def draw_held(member):
    """What the member opens or spends, one tile each."""
    card = Card(640, 128, PLACES["INVENTORY"][1])
    wide = (608 - 8 * (len(HELD) - 1)) // len(HELD)
    for spot, (key, name, picture, command) in enumerate(HELD):
        count = member["held"].get(key) or 0
        x = 16 + spot * (wide + 8)
        tile(card, x, 16, wide, picture, plural(count, name), command, on=bool(count))
    return card.jpg()


def draw_effects(member):
    """The member's effect items: the ones running, then the ones in the bag."""
    items = [
        (
            effect["item"],
            ends(effect["expires_at"]).capitalize(),
            GREEN,
            ("ACTIVE", GREEN, BLACK),
        )
        for effect in member["effects"]
    ] + [(item, "/use", MUTED, ("IN BAG", GOLD, BLACK)) for item in member["bag"]]
    rows = -(-len(items) // 4)
    top = 24
    tall = 28 + rows * 112 if items else 64
    card = Card(640, top + tall + 16, PLACES["INVENTORY"][1])
    card.panel(16, top, 608, tall)
    card.tag(32, top - 12, "EFFECT ITEMS")
    card.note(top, "Find more items in /shop")
    if not items:
        line = "No effect items yet. They boost your Beans and brews."
        card.text(36, top + 23, line, 15, MUTED, "la", 2)
    for spot, (item, line, tint, tag) in enumerate(items):
        x, y = 30 + spot % 4 * 147, top + 26 + spot // 4 * 112
        tile(
            card, x, y, 139, item_icon(item), STORE_ITEMS[item]["name"], line, tint, tag
        )
    return card.jpg()


def draw_table(table):
    """The member's table, or how to get one."""
    seats = (table or {}).get("members", ())
    rows = -(-len(seats) // 3) if table else 1
    short = bool(table) and len(seats) < TABLE_SEATS_NEEDED
    tall = 212 + rows * 38 + 42 * short
    card = Card(640, 24 + tall + 16, PLACES["COMMUNITY"][1])
    color = rgb(table["color"]) if table else GOLD
    card.panel(16, 24, 608, tall)
    card.tag(32, 12, "TABLE", color, ink(color))
    if not table:
        card.text(36, 40, "You have no table yet", 24)
        line = f"Sit with {TABLE_SEATS_NEEDED} or more members. Beans you all earn in chat pay everyone."
        card.text(36, 72, line, 13, MUTED, "la", 2)
        quest(card, 104, {"weekly_beans": 0, "tier": 0})
        top_prize(card, 196)
        line = "Join one with /table seat, or start one with /table reserve"
        card.text(36, 232, line, 14, GOLD, "la", 2)
        return card.jpg()
    name = card.fit(plain(table["name"]), 24, 240)
    card.text(36, 40, name, 24)
    seated = f"{len(seats)} / {TABLE_SEATS} seated"
    card.text(48 + card.measure(name, 24), 49, seated, 13, MUTED, "la", 2)
    motto = card.fit(f"\"{plain(table['motto'])}\"", 13, 380)
    card.text(36, 72, motto, 13, MUTED, "la", 2)
    beans = f"{table['weekly_beans']:,}"
    card.text(604, 40, beans, 22, GOLD, "ra")
    card.icon("kit/bean", 572 - card.measure(beans, 22), 39, 26)
    card.text(604, 68, "weekly quest total", 12, MUTED, "ra", 2)
    y = 104
    if short:
        label = f"{len(seats)} / {TABLE_SEATS_NEEDED} seats to start the quest"
        card.bar(36, y, 568, 24, len(seats) / TABLE_SEATS_NEEDED, color, label)
        y += 42
    quest(card, y, table if not short else {"weekly_beans": 0, "tier": -1})
    top_prize(card, y + 92)
    for spot, (who, share, host, you, avatar) in enumerate(seats):
        x, top = 36 + spot % 3 * 192, y + 124 + spot // 3 * 38
        card.slot(x, top, 184, 32)
        card.avatar(avatar, x + 6, top + 5, 22, 5)
        tag = "HOST" if host else ""
        who = card.fit(named(who), 15, 84 - card.measure(tag, 11))
        card.text(x + 36, top + 7, who, 15, GOLD if you else WHITE, "la", 2)
        if tag:
            card.text(x + 42 + card.measure(who, 15), top + 10, tag, 11, color, "la", 2)
        card.text(x + 176, top + 8, f"{share:,}", 14, GOLD if share else GREY, "ra", 2)
    return card.jpg()


def draw_invites(invites):
    """This month's invites and the three referral steps."""
    y = 24
    card = Card(640, y + 246 + 16, PLACES["COMMUNITY"][1])
    card.panel(16, y, 608, 246)
    card.tag(32, y - 12, "INVITES")
    card.icon("kit/icon_inbox", 36, y + 16, 28)
    count = str(invites["valid"])
    card.text(80, y + 12, count, 26, GOLD)
    unit = "invite" if invites["valid"] == 1 else "invites"
    card.text(88 + card.measure(count, 26), y + 22, unit, 15, WHITE, "la", 2)
    card.text(604, y + 10, invites["month"], 16, WHITE, "ra", 2)
    left = f"{invites['left']} left the server"
    card.text(604, y + 32, left, 13, RED if invites["left"] else MUTED, "ra", 2)
    x = 592 - card.measure(left, 13)
    card.text(x, y + 32, f"{invites['total']} joined", 13, MUTED, "ra", 2)
    done = invites["done"]
    goal = next((key for key, *_ in REFERRAL_STEPS if not done.get(key)), None)
    for row, (key, name, need, picture, reward) in enumerate(REFERRAL_STEPS):
        top = y + 54 + row * 52
        had = done.get(key, False)
        # Only the step to go for next is lit.
        card.slot(36, top, 568, 46, lit=key == goal)
        card.check(46, top + 9, had)
        card.text(88, top + 5, name, 16, GREEN if had else WHITE, "la", 2)
        if key == "master_done" and not had:
            sells = min(done.get("sells", 0), REFERRAL_MASTER_SELLS)
            at = 96 + card.measure(name, 16)
            card.text(
                at, top + 7, f"{sells} / {REFERRAL_MASTER_SELLS}", 13, GOLD, "la", 2
            )
        card.text(88, top + 26, need, 12, MUTED, "la", 2)
        card.text(588, top + 15, reward, 15, GREY if had else GOLD, "ra", 2)
        card.icon(picture, 560 - card.measure(reward, 15), top + 12, 22)
    foot = y + 218
    card.icon("kit/icon_calendar", 36, foot - 2, 18)
    days = invites["days"]
    left = f"{days} day{'s' * (days != 1)} left" if goal else "All done"
    card.text(62, foot, left, 13, RED if goal else GREEN, "la", 2)
    reset = "Starts over on the 1st, so you can earn these again."
    card.text(72 + card.measure(left, 13), foot, reset, 13, MUTED, "la", 2)
    return card.jpg()


def figure(card, x, y, picture, count, unit):
    """A panel's main number: its picture, the count, then what is counted."""
    card.icon(picture, x, y + 17, 28)
    card.text(x + 40, y + 14, count, 24, GOLD)
    card.text(x + 48 + card.measure(count, 24), y + 23, unit, 15, WHITE, "la", 2)


def draw_teams(member):
    """The member's rep and approved topics, and what each one pays."""
    y = 24
    card = Card(640, y + 62 + 16, PLACES["COMMUNITY"][1])
    card.panel(16, y, 300, 62)
    card.tag(32, y - 12, "TEAM FINDER")
    figure(card, 36, y, "kit/icon_like", f"{member['rep']:,}", "rep")
    card.text(296, y + 13, "each rep", 13, MUTED, "ra", 2)
    x = 288 - card.measure("each rep", 13)
    pay(card, x, y + 12, [("kit/token", f"+{REP_TOKENS}")], 15)
    paid = min(member["rep_paid"], REP_PAID_DAILY)
    card.text(296, y + 36, f"{paid} of {REP_PAID_DAILY} paid today", 12, MUTED, "ra", 2)
    card.panel(324, y, 300, 62)
    card.tag(340, y - 12, "TOPICS")
    figure(card, 344, y, "kit/icon_chat", f"{member['topics']:,}", "approved")
    card.text(604, y + 23, "each topic", 13, MUTED, "ra", 2)
    x = 596 - card.measure("each topic", 13)
    pay(card, x, y + 22, [("kit/bean", f"+{TOPIC_BEANS}")], 15)
    return card.jpg()


async def setup(bot):
    pass

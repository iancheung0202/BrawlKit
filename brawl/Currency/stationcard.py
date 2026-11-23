from brawl.Currency.card import (
    BLUE,
    GOLD,
    GREEN,
    GREY,
    MUTED,
    RED,
    WHITE,
    Card,
    named,
    plain,
)
from brawl.Currency.config import (
    BOSS_ODDS,
    BOSS_SECONDS,
    THERMOMETER_DAILY_TOKEN_DROPS,
    THERMOMETER_LEVELS,
)
from brawl.Currency.heat import level_of, next_up

HEAT = {"Boiling": RED, "Hot": (255, 140, 40), "Warm": GOLD, "Cold": BLUE}
BOSS = {
    "mega_box": ("items/mega_box", "1 Mega Box", "The boss is impressed", GREEN),
    "star_drop": ("items/star_drop", "1 Star Drop", "The boss barely noticed", GOLD),
    "nothing": ("kit/icon_air", "Air", "The boss is not happy", RED),
}
SHOWN = 12


def percent(odds):
    return f"{odds * 100:g}%"


def tokens(drops):
    """'0.5% chance for 5 Tokens', rarest last, one line per kind of drop."""
    lines = []
    for odds, amounts in reversed(drops):
        low, high = min(amounts), max(amounts)
        amount = f"{low}" if low == high else f"{low}-{high}"
        lines.append(f"{percent(odds)} chance for {amount} Token{'s' * (high != 1)}")
    return lines


def pays(level):
    """'+5 Beans a message' for a level that pays."""
    return f"+{level[2]} Beans a message"


def chance(drops):
    """All of a level's Token drops in one line: '1.85% chance of 1 to 5 Tokens'."""
    amounts = [amount for _, kinds in drops for amount in kinds]
    low, high = min(amounts), max(amounts)
    amount = "1 Token" if high == 1 else f"{low} to {high} Tokens"
    return f"{percent(sum(odds for odds, _ in drops))} chance of {amount}"


def flame(level):
    return "kit/icon_wasabi_power_hot" if level[2] else "kit/icon_wasabi_power"


def draw_heat(news):
    """A strip posted in chat when the thermometer moves to another level."""
    level = news["level"]
    start, name, beans, drops = level
    above = next_up(level)
    card = Card.strip(foot=True)
    card.tag(32, 12, "THERMOMETER", HEAT[name])
    card.icon(flame(level), 34, 46, 72)
    verb = "is now" if news["rose"] else "cooled to"
    card.text(122, 44, f"Chat {verb} {name}", 28, HEAT[name])
    if beans:
        card.text(122, 84, "Extra Beans every message, no limit.", 16, MUTED, "la", 2)
        card.text(122, 104, "They do not count for the chat task.", 16, MUTED, "la", 2)
        gain = f"+{beans}"
        card.text(604, 54, gain, 30, GOLD, "ra")
        card.icon("kit/bean", 564 - card.measure(gain, 30), 54, 34)
        card.text(604, 88, "Beans a message", 13, MUTED, "ra", 2)
        card.text(604, 106, chance(drops), 13, GOLD, "ra", 2)
    else:
        card.text(122, 84, "No bonus right now.", 16, MUTED, "la", 2)
        card.text(122, 104, "Nobody is chatting.", 16, MUTED, "la", 2)
    if news["rose"]:
        line = f"Keep it going. {above[1]} at {above[0]}%" if above else "Hottest level"
    else:
        line = "Come back and chat to heat it up."
    card.text(36, card.foot, line, 15, GOLD, "la", 2)
    if above:
        card.text(604, card.foot, f"{above[1]}: {pays(above)}", 15, MUTED, "ra", 2)
    return card.jpg()


def draw_thermometer(cup):
    """The heat now, what each message earns, and the four levels."""
    heat = min(cup["heat"], 100)
    now = level_of(heat)
    mine = cup.get("drops") is not None
    down = 64 if mine else 0
    card = Card(640, 456 + down, cup["background"])
    card.panel(16, 24, 608, 416 + down)
    card.tag(32, 12, "THERMOMETER", HEAT[now[1]])
    card.icon(flame(now), 34, 48, 60)
    card.text(108, 44, now[1], 34, HEAT[now[1]])
    line = (
        "Every message pays extra Beans, with no daily limit."
        if now[2]
        else "No bonus right now."
    )
    card.text(108, 86, line, 16, MUTED, "la", 2)
    card.bar(36, 122, 568, 26, heat / 100, HEAT[now[1]], f"{heat}%")
    if mine:
        card.slot(36, 162, 278, 50)
        card.icon("kit/bean", 46, 170, 34)
        card.text(88, 166, f"+{cup.get('beans', 0):,}", 22, GOLD)
        card.text(88, 191, "Extra today, not in the chat task", 13, MUTED, "la", 2)
        card.slot(326, 162, 278, 50)
        card.icon("kit/token", 336, 170, 34)
        left = f"{cup['drops']} of {THERMOMETER_DAILY_TOKEN_DROPS}"
        card.text(378, 166, left, 22, GOLD)
        card.text(378, 191, "Your Token drops today", 13, MUTED, "la", 2)
    for row, level in enumerate(THERMOMETER_LEVELS):
        start, name, beans, drops = level
        y = 162 + down + row * 60
        card.slot(36, y, 568, 54, GOLD if level is now else (0, 0, 0))
        card.text(52, y + 6, name, 20, HEAT[name])
        span = f"{start}% and up" if start else "Under 50%"
        card.text(52, y + 31, span, 13, MUTED, "la", 2)
        if not beans:
            card.text(196, y + 16, "No bonus", 18, GREY, "la", 2)
            continue
        card.icon("kit/bean", 172, y + 12, 30)
        card.text(208, y + 15, f"+{beans} Beans", 19)
        card.icon("kit/token", 330, y + 12, 30)
        if len(drops) == 1:
            card.text(368, y + 17, tokens(drops)[0], 16, WHITE, "la", 2)
            continue
        # Several kinds of drop: 'chance for amount' in two columns, commonest first.
        for spot, (odds, amounts) in enumerate(reversed(drops)):
            x = 368 + spot % 2 * 118
            text = f"{percent(odds)} for {amounts[0]}"
            card.text(x, y + 8 + spot // 2 * 20, text, 15, WHITE, "la", 2)
    frozen = cup.get("frozen")
    hint = (
        f"Frozen by {named(frozen[0])} for {frozen[1]} more minute{'s' * (frozen[1] != 1)}."
        if frozen
        else "Chat in the main channels to heat it up. It cools every minute."
    )
    card.text(
        36, 406 + down, card.fit(hint, 15, 568), 15, BLUE if frozen else GOLD, "la", 2
    )
    return card.jpg()


def draw_token_drop(drop):
    """A strip posted in chat when the thermometer drops Tokens."""
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "JACKPOT" if drop["jackpot"] else "TOKEN DROP", GOLD)
    card.icon("kit/token", 34, 46, 72)
    amount = drop["amount"]
    card.text(122, 44, f"+{amount} Token{'s' * (amount != 1)}", 26, GOLD)
    card.text(122, 82, f"The chat is {drop['level'].lower()}.", 16, MUTED, "la", 2)
    count = f"Drop {drop['count']} of {THERMOMETER_DAILY_TOKEN_DROPS} today"
    card.text(122, 102, count, 16, MUTED, "la", 2)
    card.text(604, 46, "You have", 13, MUTED, "ra", 2)
    have = f"{drop['tokens']:,}"
    card.text(604, 62, have, 22, GOLD, "ra")
    card.icon("kit/token", 572 - card.measure(have, 22), 62, 26)
    return card.jpg()


def chip(card, x, y, outcome, odds):
    picture, name, _, color = BOSS[outcome]
    w = card.measure(name, 16) + card.measure(percent(odds), 16) + 62
    card.slot(x, y, w, 36)
    card.icon(picture, x + 8, y + 4, 28)
    card.text(x + 44, y + 8, name, 16, WHITE, "la", 2)
    card.text(x + w - 12, y + 8, percent(odds), 16, color, "ra", 2)
    return x + w + 10


def draw_boss(background):
    """The boss walks in: what to do, how long, and what it can pay."""
    card = Card(640, 196, background)
    card.panel(16, 24, 608, 156)
    card.tag(32, 12, "BOSS INSPECTION", RED, WHITE)
    card.icon("kit/icon_megaboss_big", 34, 46, 68)
    card.text(118, 44, "The boss is here", 28)
    line = f"Pick one thing to do. You have {BOSS_SECONDS // 60} minutes."
    card.text(118, 84, line, 16, MUTED, "la", 2)
    x = 36
    for outcome, odds in BOSS_ODDS:
        x = chip(card, x, 128, outcome, odds)
    assert x <= 614
    return card.jpg()


def draw_boss_result(result):
    """A strip only the member sees: how the boss took it and what they got."""
    picture, name, headline, color = BOSS[result["outcome"]]
    card = Card.strip(result.get("next"))
    card.tag(32, 12, "BOSS INSPECTION", color)
    card.icon(picture, 34, 48, 64)
    card.text(118, 42, headline, 24, color)
    for row, line in enumerate(card.wrap(plain(result["line"]), 15, 340)):
        card.text(118, 78 + row * 19, line, 15, MUTED, "la", 2)
    card.text(604, 46, "You got", 13, MUTED, "ra", 2)
    card.text(604, 62, name, 20, GREY if result["outcome"] == "nothing" else GOLD, "ra")
    return card.jpg()


def draw_boss_results(results):
    """When the boss leaves: everyone who tried, best result first."""
    order = [outcome for outcome, _ in BOSS_ODDS]
    people = sorted(results["people"], key=lambda person: order.index(person[1]))
    shown, more = people[:SHOWN], len(people) - SHOWN
    rows = max(1, (len(shown) + 1) // 2)
    card = Card(640, 124 + rows * 44 + 26 * (more > 0), results["background"])
    card.panel(16, 24, 608, card.height - 40)
    card.tag(32, 12, "BOSS INSPECTION", GREY, WHITE)
    card.text(36, 42, "The boss has left", 26)
    count = len(people)
    line = f"{count} {'person' if count == 1 else 'people'} tried to impress the boss."
    card.text(36, 78, line if count else "Nobody tried this time.", 16, MUTED, "la", 2)
    if not count:
        card.text(36, 112, "Be quick next time: it lasts 2 minutes.", 15, GOLD, "la", 2)
    for spot, (name, outcome) in enumerate(shown):
        picture, reward, _, color = BOSS[outcome]
        x, y = 36 + spot % 2 * 288, 108 + spot // 2 * 44
        card.slot(x, y, 280, 38, color)
        card.icon(picture, x + 240, y + 4, 30)
        card.text(x + 12, y + 8, card.fit(named(name), 17, 190), 17, WHITE, "la", 2)
    if more > 0:
        card.text(36, card.height - 46, f"and {more} more", 15, MUTED, "la", 2)
    return card.jpg()


async def setup(bot):
    pass

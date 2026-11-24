import time

from PIL import Image

from brawl.Currency.card import (
    BLACK,
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
    icon,
    named,
    plain,
    shade,
)
from brawl.Currency.config import (
    BOSS_ODDS,
    BOSS_SECONDS,
    THERMOMETER_DAILY_TOKEN_DROPS,
    THERMOMETER_LEVELS,
    THERMOMETER_MAX,
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


def rate(level):
    """What one message is worth at this level: ('+5', '1%')."""
    return f"+{level[2]}", percent(sum(odds for odds, _ in level[3]))


def flame(level):
    return "kit/icon_wasabi_power_hot" if level[2] else "kit/icon_wasabi_power"


def figure(card, picture, x, y, text="", on=True, size=30):
    """An icon and its number: one size, one baseline, one gap. Off is faint.

    Returns where the figure ends.
    """
    image = icon(picture, size)
    if not on:
        grey = image.convert("LA").convert("RGB").split()
        faint = image.getchannel("A").point(lambda value: value // 3)
        image = Image.merge("RGBA", (*grey, faint))
    card.paste(image, x, y)
    x += image.width / SCALE
    if text:
        number = size * 4 // 5
        card.text(x + 8, y + 2, text, number, GOLD)
        x += 8 + card.measure(text, number)
    return x


def drop_row(card, x, y, drops, size=30):
    """The day's Token drops: each one had shows its Tokens, the rest are faint."""
    for spot in range(THERMOMETER_DAILY_TOKEN_DROPS):
        had = spot < len(drops)
        text = str(drops[spot]) if had and drops[spot] else ""
        x = figure(card, "kit/token", x, y, text, had, size) + (16 if text else 10)
    return x


def heat_bar(card, x, y, w, heat, tint):
    """The heat with a tick where each level starts; one not reached is light."""
    card.bar(x, y, w, 14, heat / THERMOMETER_MAX, tint)
    for start, name, _, _ in sorted(THERMOMETER_LEVELS)[1:]:
        at = x + w * start / THERMOMETER_MAX
        card.draw.line(
            [(at * SCALE, (y + 3) * SCALE), (at * SCALE, (y + 11) * SCALE)],
            fill=BLACK if heat >= start else (185, 195, 235),
            width=2 * SCALE,
        )
        reached = HEAT[name] if heat >= start else MUTED
        card.text(at, y + 18, name, 11, reached, "ma", 2)


def heads(card, x, y, level, tint):
    """EXTRA BEANS and TOKEN DROPS, each with what a message is worth now."""
    for at, head, each in zip(
        (x, x + 218), ("EXTRA BEANS", "TOKEN DROPS"), rate(level)
    ):
        card.text(at, y, head, 13, WHITE, "la", 2)
        at += card.measure(head, 13) + 8
        card.text(at, y, f"{each} per message", 13, tint, "la", 2)


def heat_panel(card, y, cup):
    """The thermometer for one member: the level, their extra Beans, their drops."""
    heat = cup["heat"]
    level = level_of(min(heat, 100))
    tint = HEAT[level[1]]
    drops = cup["drops"]
    if cup.get("resets"):
        left = max(0, int(cup["resets"] - time.time())) // 60
        clock = f"{left // 60}h {left % 60}m" if left >= 60 else f"{left}m"
        x = card.note(y, f"Token drop cap resets in {clock}")
        card.icon("kit/icon_clock", x - 22, y - 17, 14)
    card.panel(16, y, 608, 136, (*shade(tint, 0.3), 215))
    card.tag(32, y - 12, "THERMOMETER", tint)
    card.icon(flame(level), 36, y + 26, 52)
    card.text(98, y + 26, level[1], 28, tint)
    card.text(98, y + 62, f"{heat}% heat", 16, WHITE, "la", 2)
    if cup.get("frozen"):
        by, left = cup["frozen"]
        frozen = card.fit(f"Frozen by {named(by)} for {left}m", 13, 190)
        card.text(200, y - 18, frozen, 13, BLUE, "la", 2)
    left = 212
    heads(card, left, y + 16, level, tint)
    figure(card, "kit/bean", left, y + 37, f"+{cup['beans']:,}")
    drop_row(card, left + 218, y + 37, drops)
    card.text(left, y + 72, "Arrives once a minute", 12, MUTED, "la", 2)
    had = f"{len(drops)} of {THERMOMETER_DAILY_TOKEN_DROPS} today"
    card.text(left + 218, y + 72, had, 12, MUTED, "la", 2)
    heat_bar(card, 36, y + 96, 568, heat, tint)


def draw_heat(news):
    """A strip posted in chat when the thermometer moves to another level."""
    level = news["level"]
    name = level[1]
    above = next_up(level)
    card = Card.strip(foot=True)
    card.tag(32, 12, "THERMOMETER", HEAT[name])
    card.icon(flame(level), 34, 46, 72)
    verb = "is now" if news["rose"] else "cooled to"
    card.text(122, 42, f"Chat {verb} {name}", 28, HEAT[name])
    beans, odds = rate(level)
    x = figure(card, "kit/bean", 122, 84, beans, bool(level[2]), 26) + 18
    x = figure(card, "kit/token", x, 84, odds, bool(level[3]), 26) + 12
    card.text(x, 89, "per message", 15, MUTED, "la", 2)
    if news["rose"]:
        line = f"Keep it going. {above[1]} at {above[0]}%" if above else "Hottest level"
    else:
        line = "Come back and chat to heat it up."
    card.text(36, card.foot, line, 15, GOLD, "la", 2)
    if above:
        beans, odds = rate(above)
        x = 604 - card.measure("per message", 15)
        card.text(604, card.foot, "per message", 15, MUTED, "ra", 2)
        for picture, text in (("kit/token", odds), ("kit/bean", beans)):
            x -= card.measure(text, 15) + 10
            card.text(x, card.foot, text, 15, GOLD, "la", 2)
            x -= 24
            card.icon(picture, x, card.foot - 2, 19)
        card.text(x - 8, card.foot, above[1], 15, HEAT[above[1]], "ra", 2)
    return card.jpg()


def draw_thermometer(cup):
    """The member's thermometer, then what each level is worth."""
    now = level_of(min(cup["heat"], 100))
    top = 24 + 136 + 30
    tall = 44 + len(THERMOMETER_LEVELS) * 40
    card = Card(640, top + tall + 16, cup["background"])
    heat_panel(card, 24, cup)
    card.panel(16, top, 608, tall)
    card.tag(32, top - 12, "LEVELS")
    card.text(36, top + 20, "HEAT", 13, WHITE, "la", 2)
    for at, head in ((200, "EXTRA BEANS"), (380, "TOKEN DROPS")):
        card.text(at, top + 20, head, 13, WHITE, "la", 2)
        at += card.measure(head, 13) + 8
        card.text(at, top + 20, "per message", 13, MUTED, "la", 2)
    y = top + 44
    for level in THERMOMETER_LEVELS:
        start, name, _, drops = level
        card.draw.line(
            [(28 * SCALE, (y - 4) * SCALE), (612 * SCALE, (y - 4) * SCALE)],
            fill=(255, 255, 255, 40),
            width=SCALE,
        )
        if level is now:
            card.draw.rectangle(
                box(28, y - 4, 584, 40), fill=(*shade(HEAT[name], 0.4), 255)
            )
        card.text(36, y + 5, name, 20, HEAT[name])
        x = 46 + card.measure(name, 20)
        card.text(x, y + 10, f"{start}%", 13, MUTED, "la", 2)
        beans, odds = rate(level)
        figure(card, "kit/bean", 200, y + 5, beans, bool(level[2]), 24)
        x = figure(card, "kit/token", 380, y + 5, odds, bool(drops), 24)
        if len(drops) > 1:
            for spot, (chance, amounts) in enumerate(reversed(drops)):
                part = f"{percent(chance)} for {amounts[0]}"
                at = x + 18 + spot % 2 * 78
                card.text(at, y + 2 + spot // 2 * 16, part, 12, MUTED, "la", 2)
        y += 40
    return card.jpg()


def draw_token_drop(drop):
    """A strip posted in chat when the thermometer drops Tokens."""
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "JACKPOT" if drop["jackpot"] else "TOKEN DROP", GOLD)
    card.icon("kit/token", 34, 46, 72)
    amount = drop["amount"]
    card.text(122, 42, f"+{amount} Token{'s' * (amount != 1)}", 26, GOLD)
    x = drop_row(card, 122, 86, drop["drops"], 24)
    count = f"{len(drop['drops'])} of {THERMOMETER_DAILY_TOKEN_DROPS} today"
    card.text(x + 4, 91, count, 14, MUTED, "la", 2)
    card.text(604, 46, "You have", 13, MUTED, "ra", 2)
    have = f"{drop['tokens']:,}"
    card.text(604, 62, have, 22, GOLD, "ra")
    card.icon("kit/token", 572 - card.measure(have, 22), 62, 26)
    return card.jpg()


def outcomes(card, x, y, w):
    """What the boss can give, each on a round spot with how likely it is."""
    step = w / len(BOSS_ODDS)
    for spot, (outcome, odds) in enumerate(BOSS_ODDS):
        picture, name, _, color = BOSS[outcome]
        at = x + step * spot
        card.icon(picture, at, y, 44)
        card.text(at + 54, y + 2, name, 17, WHITE, "la", 2)
        card.text(at + 54, y + 24, percent(odds), 15, color, "la", 2)


def draw_boss(background):
    """The boss walks in: what to do, how long, and what it can pay."""
    card = Card(640, 204, background)
    card.note(24, f"Leaves in {BOSS_SECONDS // 60} minutes")
    card.panel(16, 24, 608, 164, (96, 20, 30, 215))
    card.tag(32, 12, "BOSS INSPECTION", RED, WHITE)
    card.icon("kit/icon_megaboss_big", 34, 46, 60)
    card.text(108, 46, "The boss is here", 28)
    card.text(108, 82, "Press one button", 16, MUTED, "la", 2)
    outcomes(card, 40, 126, 564)
    return card.jpg()


def draw_boss_result(result):
    """A strip only the member sees: how the boss took it and what they got."""
    picture, name, headline, color = BOSS[result["outcome"]]
    card = Card.strip()
    card.tag(32, 12, "BOSS INSPECTION", RED, WHITE)
    card.icon(picture, 34, 48, 64)
    card.text(118, 42, headline, 24, color)
    for row, line in enumerate(card.wrap(plain(result["line"]), 15, 340)):
        card.text(118, 78 + row * 19, line, 15, MUTED, "la", 2)
    card.text(604, 46, "You got", 13, MUTED, "ra", 2)
    card.text(604, 62, name, 20, GREY if result["outcome"] == "nothing" else GOLD, "ra")
    return card.jpg()


def draw_boss_results(results):
    """When the boss leaves: who got what, one column for each result."""
    people = results["people"]
    groups = [
        [(named(name), *face) for name, got, *face in people if got == outcome]
        for outcome, _ in BOSS_ODDS
    ]
    rows = min(SHOWN // len(groups), max(map(len, groups), default=0))
    card = Card(
        640,
        166 + rows * 28 + 22 * any(len(g) > rows for g in groups),
        results["background"],
    )
    card.panel(16, 24, 608, card.height - 40, (96, 20, 30, 215))
    card.tag(32, 12, "BOSS INSPECTION", RED, WHITE)
    card.text(36, 42, "The boss has left", 26)
    count = len(people)
    line = f"{count} {'person' if count == 1 else 'people'} tried"
    card.text(604, 50, line if count else "Nobody tried", 16, MUTED, "ra", 2)
    step = 568 / len(groups)
    for spot, ((outcome, _), names) in enumerate(zip(BOSS_ODDS, groups)):
        picture, reward, _, color = BOSS[outcome]
        x = 40 + step * spot
        figure(card, picture, x, 88, on=bool(names), size=44)
        card.text(x + 54, 90, reward, 17, WHITE if names else GREY, "la", 2)
        card.text(x + 54, 112, str(len(names)), 15, color if names else GREY, "la", 2)
        for row, (name, *face) in enumerate(names[:rows]):
            y = 144 + row * 28
            card.avatar(face[0] if face else b"", int(x), y, 22, 6)
            card.text(x + 30, y + 3, card.fit(name, 15, step - 46), 15, WHITE, "la", 2)
        if len(names) > rows:
            more = f"and {len(names) - rows} more"
            card.text(x, 146 + rows * 28, more, 14, MUTED, "la", 2)
    return card.jpg()


async def setup(bot):
    pass

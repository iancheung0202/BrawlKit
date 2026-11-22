import io
from functools import lru_cache

from brawl.Currency.card import (
    BLUE,
    GOLD,
    MUTED,
    SCALE,
    WHITE,
    Card,
    icon,
    item_icon,
    tinted,
)
from brawl.Currency.config import (
    DROP_BONUS,
)
from brawl.Currency.config import DROP_UPGRADES as UPGRADES
from brawl.Currency.config import (
    EFFECT_FALLBACK_TOKENS,
    MEGA_BOX_BASE,
    MEGA_BOX_BASE_RARITY,
    MEGA_BOX_EXTRA,
    MEGA_BOX_ITEMS,
    STAR_DROP_RATES,
)
from brawl.Currency.helper import COLORS

ICONS = {"beans": "kit/bean", "tokens": "kit/token"}
PER_ROW = 5


def rgb(rarity):
    color = COLORS[rarity]
    return color >> 16, color >> 8 & 255, color & 255


def title(rarity):
    return rarity.replace("_", " ").title()


def plural(count, word):
    return f"{count:,} {word}{'s' * (count != 1)}"


def label(reward):
    if reward["kind"] == "effect":
        return reward["name"]
    return plural(reward["amount"], reward["kind"].title()[:-1])


def waiting(unopened):
    return f"{unopened} more to open" if unopened else ""


def wrap(card, text, width):
    words = text.split()
    if card.measure(text, 15) <= width or len(words) < 2:
        return [card.fit(text, 15, width)]
    half = min(
        range(1, len(words)),
        key=lambda cut: abs(len(" ".join(words[:cut])) - len(" ".join(words[cut:]))),
    )
    return [
        card.fit(" ".join(part), 13, width) for part in (words[:half], words[half:])
    ]


def picture(reward):
    return ICONS.get(reward["kind"]) or item_icon(reward.get("item"))


def draw_star_drop(drop):
    """A strip: the drop, its rarity, then the upgrades or the reward."""
    card = Card(640, 218, drop["background"])
    rarity, rewards, used = drop["rarity"], drop["rewards"], drop["upgrades"]
    card.panel(16, 16, 608, 148)
    card.paste(tinted("kit/icon_ranked_starr_drop", 112, rgb(rarity)), 32, 34)
    card.text(196, 28, f"{title(rarity)} Star Drop", 32, rgb(rarity))
    card.text(620, 172, waiting(drop["unopened"]), 16, MUTED, "ra", 2)
    if rewards:
        for row, reward in enumerate(rewards):
            y = 78 + row * 40
            card.icon(picture(reward), 196, y, 32)
            card.text(240, y + 3, label(reward), 22)
            if reward.get("note"):
                x = 252 + card.measure(label(reward), 22)
                card.text(x, y + 8, reward["note"], 15, MUTED, "la", 2)
        hint = (
            "Press Open Next to open another."
            if drop["unopened"]
            else "That was your last Star Drop."
        )
    else:
        for spot in range(UPGRADES):
            x = 196 + spot * 50
            card.slot(x, 78, 40, 40, GOLD if spot == used else (0, 0, 0))
            if spot < used:
                card.icon("kit/icon_ranked_round_token", x + 1, 78, 40)
        card.text(196, 126, f"{used} of {UPGRADES} upgrades used", 16, MUTED, "la", 2)
        hint = (
            "Each upgrade can raise the rarity."
            if used < UPGRADES
            else "Press Unlock to see your reward."
        )
    card.text(20, 172, hint, 16, GOLD, "la", 2)
    return card.jpg()


def draw_mega_box(box):
    """A grid with one tile per item, so the card grows with the box."""
    rewards, total = box["rewards"], box["total"]
    rows = -(-total // PER_ROW)
    card = Card(640, 88 + rows * 96, box["background"])
    left = total - len(rewards)
    card.panel(16, 16, 608, 22 + rows * 96)
    for spot in range(total):
        x, y = 30 + spot % PER_ROW * 117, 30 + spot // PER_ROW * 96
        latest = left and spot == len(rewards) - 1
        card.slot(x, y, 111, 86, GOLD if latest else (0, 0, 0))
        if spot >= len(rewards):
            card.text(x + 55, y + 43, "?", 36, MUTED, "mm")
            continue
        reward = rewards[spot]
        image = icon(picture(reward), 38)
        card.paste(image, x + 55 - image.width / SCALE / 2, y + 7)
        lines = wrap(card, label(reward), 101)
        for row, line in enumerate(lines):
            size = 15 if len(lines) == 1 else 13
            card.text(
                x + 55,
                y + 67 - (len(lines) - 1 - row * 2) * 7,
                line,
                size,
                WHITE,
                "mm",
                2,
            )
    if left:
        hint = f"Press Tap to reveal {plural(left, 'more item')}."
    elif box["unopened"]:
        hint = "Press Open Next to open another."
    else:
        hint = "That was your last Mega Box."
    y = card.height - 40
    card.text(20, y, hint, 16, GOLD, "la", 2)
    card.text(620, y, waiting(box["unopened"]), 16, MUTED, "ra", 2)
    return card.jpg()


def percent(chance):
    return f"{chance * 100:g}%"


def payout(drop):
    low, high = drop.get("range") or [drop["amount"]] * 2
    return f"{low:,}" if low == high else f"{low:,}–{high:,}"


def chip(card, x, y, name, amount, odds="", outline=(0, 0, 0)):
    """One possible reward: its icon, how much, and how likely it is."""
    w = 44 + card.measure(amount, 17) + (card.measure(odds, 14) + 8 if odds else 0)
    card.slot(x, y, w + 8, 34, outline)
    card.icon(name, x + 7, y + 5, 24)
    card.text(x + 38, y + 6, amount, 17, WHITE, "la", 2)
    if odds:
        card.text(x + w, y + 9, odds, 14, MUTED, "ra", 2)
    return x + w + 16


def draw_rates(background):
    return io.BytesIO(rates_image(background))


@lru_cache
def rates_image(background):
    rates, drops = STAR_DROP_RATES["rarity_rates"], STAR_DROP_RATES["drops"]
    card = Card(900, 828, background)
    card.title("DROP RATES", "What a Star Drop or a Mega Box can give you.")
    card.panel(26, 124, 848, 40 + len(rates) * 60)
    card.tag(42, 112, "STAR DROPS")
    for row, (rarity, chance) in enumerate(rates.items()):
        y = 154 + row * 60
        if row:
            card.draw.line(
                [(46 * SCALE, (y - 7) * SCALE), (854 * SCALE, (y - 7) * SCALE)],
                fill=(0, 0, 0, 90),
                width=2 * SCALE,
            )
        card.paste(tinted("kit/icon_ranked_starr_drop", 46, rgb(rarity)), 44, y)
        card.text(102, y + 1, title(rarity), 22, rgb(rarity))
        card.text(102, y + 28, f"{percent(chance)} chance", 14, MUTED, "la", 2)
        weight = sum(drop.get("weight", 1) for drop in drops[rarity])
        x = 262
        for drop in drops[rarity]:
            odds = (
                percent(drop.get("weight", 1) / weight)
                if len(drops[rarity]) > 1
                else ""
            )
            x = chip(card, x, y + 6, ICONS[drop["type"]], payout(drop), odds)
        if rarity in DROP_BONUS:
            chip(
                card,
                x,
                y + 6,
                "items/effect",
                "Effect item",
                percent(DROP_BONUS[rarity]),
                GOLD,
            )
    top = 196 + len(rates) * 60
    card.panel(26, top, 848, 210)
    card.tag(42, top - 12, "MEGA BOXES", BLUE, WHITE)
    card.icon("items/mega_box", 46, top + 30, 84)
    card.text(160, top + 22, "How many items a box holds", 15, MUTED, "la", 2)
    for spot, (count, odds) in enumerate(MEGA_BOX_ITEMS.items()):
        x = 160 + spot * 116
        card.slot(x, top + 46, 106, 64)
        card.text(x + 53, top + 50, str(count), 26, GOLD, "ma")
        card.text(x + 53, top + 86, percent(odds), 14, MUTED, "ma", 2)
    card.text(46, top + 128, f"Items 1 to {MEGA_BOX_BASE}", 15, MUTED, "la", 2)
    x = 160
    for rarity, odds in MEGA_BOX_BASE_RARITY.items():
        low, high = drops[rarity][0]["range"]
        x = chip(card, x, top + 122, "kit/bean", f"{low:,}–{high:,}", percent(odds))
    card.text(46, top + 170, "Every item after", 15, MUTED, "la", 2)
    x = 160
    for prize, odds in MEGA_BOX_EXTRA.items():
        if prize == "effect":
            x = chip(
                card, x, top + 164, "items/effect", "Effect item", percent(odds), GOLD
            )
        else:
            x = chip(card, x, top + 164, "kit/token", str(prize), percent(odds))
    card.hint(
        f"If every effect item is already active, you get {EFFECT_FALLBACK_TOKENS} Tokens in its place."
    )
    return card.jpg().getvalue()


async def setup(bot):
    pass

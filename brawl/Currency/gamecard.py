from brawl.Currency.card import (
    BLACK,
    BLUE,
    GOLD,
    GREEN,
    MUTED,
    RED,
    SCALE,
    WHITE,
    Card,
    box,
    shade,
)

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = "♠♥♦♣"
DECK = [(rank, suit) for rank in RANKS for suit in SUITS]
INK = {"♠": (20, 24, 50), "♣": (20, 24, 50), "♥": (225, 45, 60), "♦": (225, 45, 60)}
TONES = {"good": GREEN, "bad": RED, "even": GOLD, "play": BLUE}
CARD_W, CARD_H, STEP = 58, 80, 66


def total(cards):
    """Aces count 11 until that would bust the hand, then 1."""
    value = sum(
        11 if rank == "A" else 10 if rank in "JQK" else int(rank) for rank, _ in cards
    )
    aces = sum(rank == "A" for rank, _ in cards)
    while value > 21 and aces:
        value, aces = value - 10, aces - 1
    return value


def suit(draw, mark, x, y, size, color):
    """The font has no suit symbols, so each one is drawn from circles and triangles."""
    x, y, size = x * SCALE, y * SCALE, size * SCALE
    half, lobe = size / 2, size * 0.29

    def dot(cx, cy, r):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    def stem():
        draw.polygon(
            [(x, y + size * 0.1), (x - lobe, y + half), (x + lobe, y + half)],
            fill=color,
        )

    if mark == "♦":
        draw.polygon(
            [(x, y - half), (x + half * 0.8, y), (x, y + half), (x - half * 0.8, y)],
            fill=color,
        )
    elif mark == "♥":
        dot(x - lobe * 0.85, y - lobe * 0.6, lobe)
        dot(x + lobe * 0.85, y - lobe * 0.6, lobe)
        draw.polygon(
            [
                (x - half * 1.08, y - lobe * 0.1),
                (x + half * 1.08, y - lobe * 0.1),
                (x, y + half),
            ],
            fill=color,
        )
    elif mark == "♠":
        dot(x - lobe * 0.85, y + lobe * 0.3, lobe)
        dot(x + lobe * 0.85, y + lobe * 0.3, lobe)
        draw.polygon(
            [
                (x - half * 1.08, y - lobe * 0.2),
                (x + half * 1.08, y - lobe * 0.2),
                (x, y - half),
            ],
            fill=color,
        )
        stem()
    else:
        dot(x, y - lobe * 0.9, lobe)
        dot(x - lobe * 1.05, y + lobe * 0.35, lobe)
        dot(x + lobe * 1.05, y + lobe * 0.35, lobe)
        stem()


def playing_card(card, x, y, face):
    """A face-up card, or the back of one when face is None."""
    card.draw.rounded_rectangle(
        box(x, y + 4, CARD_W, CARD_H), 8 * SCALE, fill=(0, 0, 0, 120)
    )
    card.draw.rounded_rectangle(
        box(x, y, CARD_W, CARD_H),
        8 * SCALE,
        fill=WHITE if face else BLUE,
        outline=BLACK,
        width=3 * SCALE,
    )
    if not face:
        card.draw.rounded_rectangle(
            box(x + 8, y + 8, CARD_W - 16, CARD_H - 16),
            5 * SCALE,
            outline=shade(BLUE, 1.5),
            width=2 * SCALE,
        )
        return card.text(x + CARD_W / 2, y + 22, "?", 30, WHITE, "ma")
    rank, mark = face
    card.text(x + CARD_W / 2, y + 6, rank, 28, INK[mark], "ma", 0)
    suit(card.draw, mark, x + CARD_W / 2, y + 56, 24, INK[mark])


def hand(card, y, name, cards, hidden=False):
    shown = "?" if hidden else str(total(cards))
    card.text(36, y + 14, name, 18, MUTED, "la", 2)
    card.text(36, y + 36, shown, 30, GOLD)
    step = min(STEP, (card.width - 350) / max(len(cards) - 1, 1))
    for spot, face in enumerate(cards):
        playing_card(card, 122 + spot * step, y, None if hidden and not spot else face)


def stake(card, y, game):
    """The right side of every game card: the bet, then the Beans left."""
    bet = f"{game['bet']:,}"
    card.text(card.width - 36, y, "Bet", 13, MUTED, "ra", 2)
    card.text(card.width - 36, y + 16, bet, 22, GOLD, "ra")
    card.icon("kit/bean", card.width - 68 - card.measure(bet, 22), y + 16, 26)
    if "beans" in game:
        card.text(
            card.width - 36, y + 54, f"{game['beans']:,} Beans left", 15, MUTED, "ra", 2
        )


def verdict(card, y, game):
    card.text(36, y, game["headline"], 26, TONES[game["tone"]])
    card.text(36, y + 36, game["line"], 16, MUTED, "la", 2)


def draw_blackjack(game):
    """Both hands, then what happened or what to do next."""
    card = Card(640, 330, game["background"])
    card.panel(16, 24, 608, 290)
    card.tag(32, 12, "BLACKJACK", TONES[game["tone"]], BLACK)
    hand(card, 46, "Dealer", game["dealer"], game["tone"] == "play")
    hand(card, 140, "You", game["player"])
    stake(card, 46, game)
    verdict(card, 236, game)
    return card.jpg()


def draw_coinflip(game):
    """A strip: the coin, what happened, the bet and the Beans left."""
    card = Card(640, 150)
    card.panel(16, 24, 608, 110)
    card.tag(32, 12, "COIN FLIP", TONES[game["tone"]], BLACK)
    card.draw.ellipse(
        box(36, 50, 68, 68), fill=shade(GOLD, 0.6), outline=BLACK, width=3 * SCALE
    )
    card.draw.ellipse(box(40, 50, 60, 60), fill=GOLD)
    card.text(70, 58, game["side"][0].upper(), 36, WHITE, "ma")
    card.text(122, 44, game["headline"], 26, TONES[game["tone"]])
    for row, line in enumerate(card.wrap(game["line"], 16, 300)):
        card.text(122, 82 + row * 20, line, 16, MUTED, "la", 2)
    stake(card, 42, game)
    return card.jpg()


async def setup(bot):
    pass

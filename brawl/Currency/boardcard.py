from brawl.Currency.card import GOLD, GREEN, MUTED, SCALE, WHITE, Card, icon, named

PER_PAGE = 10
PODIUM = 3
MEDALS = {1: GOLD, 2: (205, 215, 230), 3: (224, 140, 80)}
# Second, first, third from left to right, the winner standing tallest.
STANDS = {2: (36, 12), 1: (229, 0), 3: (422, 12)}


def face(card, board, avatar, x, y, size, corner):
    if avatar is None:
        wide = icon(board["icon"], size).width / SCALE
        return card.icon(board["icon"], x + (size - wide) / 2, y, size)
    card.avatar(avatar, x, y, size, corner)


def stat(card, x, y, name, text, size, color, anchor="ra"):
    """A number with its icon in front, drawn from the right or the middle."""
    wide = card.measure(text, size)
    mark = icon(name, size + 6).width / SCALE + 6 if name else 0
    left = x - wide if anchor == "ra" else x - (wide + mark) / 2 + mark
    if name:
        card.icon(name, left - mark, y - 2, size + 6)
    card.text(left, y, text, size, color, "la", 2)
    return wide + mark


def board_height(rows):
    return 170 if any(row[3] for row in rows) else 144


def podium(card, board, top, rows):
    for rank, name, value, note, you, avatar in rows:
        x, drop = STANDS[rank]
        y, size = top + drop, 64 if rank == 1 else 52
        card.slot(x, y, 182, board_height(rows) - drop, MEDALS[rank])
        face(card, board, avatar, x + 91 - size // 2, y + 14, size, 12)
        card.tag(x + 10, y - 8, f"#{rank}", MEDALS[rank])
        if you:
            card.tag(x + 172, y - 8, "YOU", GREEN, right=True)
        below = y + size + 22
        name = card.fit(named(name), 17, 162)
        card.text(x + 91, below, name, 17, WHITE, "ma", 2)
        stat(card, x + 91, below + 26, board["value_icon"], value, 17, GOLD, "ma")
        if note:
            stat(card, x + 91, below + 50, board["note_icon"], note, 13, MUTED, "ma")


def draw_board(board):
    """One page of a leaderboard: the top three on a podium, the rest in rows."""
    rows = board["rows"]
    first = [row for row in rows if row[0] <= PODIUM]
    rest = rows[len(first) :]
    noted = any(row[3] for row in first)
    top = 108 + (164 + 26 * noted) * bool(first)
    card = Card(640, top + len(rest) * 44 + 54, board["background"])
    widest = max((card.measure(row[2], 17) for row in rest), default=0)
    card.panel(16, 24, 608, card.height - 40)
    card.tag(32, 12, "LEADERBOARD", GOLD)
    card.icon(board["icon"], 36, 48, 40)
    wide = icon(board["icon"], 40).width / SCALE
    card.text(48 + wide, 50, board["title"], 28)
    if board.get("yours"):
        card.text(604, 46, "Your rank", 13, MUTED, "ra", 2)
        card.text(604, 62, f"#{board['yours']}", 22, GOLD, "ra")
    podium(card, board, 112, first)
    for spot, (rank, name, value, note, you, avatar) in enumerate(rest):
        y = top + spot * 44
        card.slot(36, y, 568, 38, GOLD if you else (0, 0, 0))
        card.text(62, y + 9, f"{rank}", 17, MUTED, "ma", 2)
        used = stat(card, 590, y + 9, board["value_icon"], value, 17, GOLD)
        used += widest - card.measure(value, 17)
        if note:
            used += 18 + stat(
                card, 572 - used, y + 12, board["note_icon"], note, 13, MUTED
            )
        face(card, board, avatar, 90, y + 6, 26, 6)
        name = card.fit(named(name), 17, 446 - used)
        card.text(126, y + 9, name, 17, WHITE, "la", 2)
    page = f"Page {board['page']} of {board['pages']}"
    card.text(36, card.height - 46, page, 14, MUTED, "la", 2)
    card.text(604, card.height - 46, board["total"], 14, MUTED, "ra", 2)
    return card.jpg()


async def setup(bot):
    pass

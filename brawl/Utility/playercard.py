import io
from datetime import datetime, timezone

from PIL import Image

from brawl.Currency.card import (
    ASSETS,
    BLACK,
    GOLD,
    GREEN,
    GREY,
    MUTED,
    RED,
    SCALE,
    SLOT,
    WHITE,
    Card,
    box,
    font,
    named,
)
from brawl.Utility import api

BRAWLERS_PER_PAGE = 15
BATTLES_PER_PAGE = 5
PINK = (235, 70, 215)
# A role not earned yet, light enough to count against the dark row.
EMPTY = (92, 96, 150)
LEAGUES = ["Bronze", "Silver", "Gold", "Diamond", "Mythic", "Legendary", "Masters"]
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
# A brawler's frame, by the most trophies it ever had.
FRAMES = [
    (3000, (255, 230, 110)),
    (2000, (255, 90, 170)),
    (1000, (160, 100, 255)),
    (750, GOLD),
    (500, (190, 200, 230)),
    (250, (224, 140, 80)),
    (0, (150, 95, 60)),
]


def league(rank):
    """Ranked 1 to 22 as a name: three steps in each league, then Pro."""
    if rank >= 22:
        return "Pro"
    rank = max(rank, 1) - 1
    return f"{LEAGUES[rank // 3]} {ROMAN[rank % 3]}"


def league_art(rank):
    return f"/ranked/tiered/{58000000 + min(max(rank, 1), 22) - 1}.png"


def brawler_art(brawler_id):
    return f"/brawlers/borderless/{brawler_id}.png"


def icon_art(icon_id):
    return f"/profile-icons/regular/{icon_id}.png"


def mode_art(event):
    return f"/game-modes/regular/{48000000 + event['modeId']}.png"


def fame_icon(stats):
    tier = (stats.get("fameTierName") or "").split(" ")[0].lower()
    return f"game/fame_{tier}" if tier else "game/fame"


def fame_name(stats):
    """METEORIC FAME II as Meteoric II."""
    tier, _, step = (stats.get("fameTierName") or "").partition(" FAME")
    return f"{tier.title()}{step}" if tier else "No Fame"


def name_color(player):
    try:
        value = int(player.get("nameColor", "0xFFFFFF"), 16)
    except ValueError:
        return WHITE
    return (value >> 16 & 255, value >> 8 & 255, value & 255)


def drawn(text):
    """A game name without the letters the card font has no shape for."""
    kept = "".join(
        letter
        for letter in named(text)
        if letter == " " or font(10).getmask(letter).getbbox()
    )
    return " ".join(kept.split()) or "Player"


async def face(tag, stats):
    """What the top of every player card needs, with its two pictures fetched."""
    club = stats.get("club") or {}
    paths = [icon_art(stats["icon"]["id"])]
    if club.get("badgeId"):
        paths.append(f"/club-badges/regular/{club['badgeId']}.png")
    art = await api.images(paths)
    return {
        "name": stats.get("name", ""),
        "color": name_color(stats),
        "tag": api.clean_tag(tag),
        "icon": art[paths[0]],
        "club": club.get("name"),
        "badge": art[paths[-1]] if club.get("badgeId") else None,
    }


def stamp(card, source, x, y, size):
    """A picture fitted inside a square: an asset by name, or art by its bytes."""
    try:
        if isinstance(source, str):
            image = Image.open(f"{ASSETS}{source}.png")
        else:
            image = Image.open(io.BytesIO(source))
        image = image.convert("RGBA")
    except Exception:
        return
    ratio = size * SCALE / max(image.size)
    image = image.resize(
        (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
        Image.LANCZOS,
    )
    card.image.alpha_composite(
        image,
        (
            round(x * SCALE + (size * SCALE - image.width) / 2),
            round(y * SCALE + (size * SCALE - image.height) / 2),
        ),
    )


def portrait(card, data, x, y, size, outline=BLACK):
    card.avatar(data, x, y, size, max(4, size // 6))
    if outline != BLACK:
        card.draw.rounded_rectangle(
            box(x - 2, y - 2, size + 4, size + 4),
            (size // 6 + 2) * SCALE,
            outline=outline,
            width=2 * SCALE,
        )


def head(card, player, label, small=False):
    """Who the card is about: player icon, name in its game colour, tag."""
    card.panel(16, 24, 608, card.height - 40)
    card.tag(32, 12, label, GOLD)
    size = 44 if small else 72
    card.avatar(player["icon"], 36, 50, size)
    left = 50 + size
    name = card.fit(drawn(player["name"]), 24 if small else 30, 300)
    card.text(left, 46 if small else 52, name, 24 if small else 30, player["color"])
    card.text(left + 2, 76 if small else 90, player["tag"], 14, MUTED, "la", 2)
    if player.get("club") and not small:
        club = card.fit(drawn(player["club"]), 15, 170)
        card.text(604, 58, club, 15, MUTED, "ra", 2)
        if player.get("badge"):
            stamp(card, player["badge"], 574 - card.measure(club, 15), 54, 24)


def tile(card, x, y, w, picture, value, label):
    card.slot(x, y, w, 70)
    stamp(card, picture, x + 10, y + 13, 44)
    card.text(x + 64, y + 11, value, 21, GOLD)
    card.text(x + 64, y + 41, card.fit(label, 13, w - 72), 13, MUTED, "la", 2)


def draw_profile(profile):
    """The front of a profile: nine numbers as tiles, then brawlers owned."""
    stats, art = profile["stats"], profile["art"]
    card = Card(640, 488, profile["background"])
    head(card, profile["player"], "PROFILE")
    record = min(max(stats.get("recordRank", 0), 0), 12)
    tiles = [
        (
            "game/trophies",
            stats.get("trophies", 0),
            f"Best {stats.get('highestTrophies', 0):,}",
        ),
        (
            art.get(league_art(stats.get("ranked", 0))),
            stats.get("rankedPoints", 0),
            league(stats.get("ranked", 0)),
        ),
        (
            art.get(league_art(stats.get("highestRanked", 0))),
            stats.get("highestRankedPoints", 0),
            f"Best {league(stats.get('highestRanked', 0))}",
        ),
        ("game/3v3", stats.get("3vs3Victories", 0), "3v3 wins"),
        ("game/solo", stats.get("soloVictories", 0), "Solo wins"),
        ("game/duo", stats.get("duoVictories", 0), "Duo wins"),
        (
            fame_icon(stats),
            stats.get("famePoints", 0),
            fame_name(stats),
        ),
        (
            f"game/record_{record}",
            stats.get("recordPoints", 0),
            f"Records {ROMAN[record - 1]}" if record else "Records",
        ),
        ("game/totalprestige", stats.get("totalPrestigeLevel", 0), "Prestige"),
    ]
    for spot, (picture, value, label) in enumerate(tiles):
        x, y = 36 + spot % 3 * 193, 140 + spot // 3 * 82
        tile(card, x, y, 182, picture, f"{value:,}", label)
    owned, total = len(stats.get("brawlers", [])), profile["brawlers"]
    total = max(total, owned)
    card.slot(36, 386, 375, 70)
    card.text(50, 395, "Brawlers", 13, MUTED, "la", 2)
    card.bar(50, 418, 347, 26, owned / total, PINK, f"{owned} / {total}")
    streak = f"{stats.get('highestWinStreak', 0):,}"
    tile(card, 422, 386, 182, "game/streak", streak, "Best win streak")
    return card.jpg()


def frame(trophies):
    return next(color for least, color in FRAMES if trophies >= least)


def count(card, x, y, name, number):
    stamp(card, name, x, y, 13)
    card.text(x + 15, y, f"{number}", 12, MUTED, "la", 2)


def draw_brawlers(page):
    """One page of brawlers: portrait, power, trophies and what is unlocked."""
    rows = -(-len(page["brawlers"]) // 5)
    card = Card(640, 164 + rows * 142, page["background"])
    head(card, page["player"], "BRAWLERS", small=True)
    card.text(604, 58, page["sort"], 15, MUTED, "ra", 2)
    for spot, brawler in enumerate(page["brawlers"]):
        x, y = 36 + spot % 5 * 115, 112 + spot // 5 * 142
        best = brawler.get("highestTrophies", 0)
        card.slot(x, y, 108, 134, frame(best))
        portrait(card, page["art"].get(brawler_art(brawler["id"])), x + 24, y + 12, 60)
        card.draw.ellipse(
            box(x + 10, y + 6, 26, 26), fill=PINK, outline=BLACK, width=2 * SCALE
        )
        card.text(x + 23, y + 19, f"{brawler['power']}", 14, WHITE, "mm", 2)
        name = card.fit(brawler["name"].title(), 14, 98)
        card.text(x + 54, y + 78, name, 14, WHITE, "ma", 2)
        trophies = f"{brawler['trophies']:,}"
        wide = card.measure(trophies, 15) + 20
        prize = (
            "game/prestigetrophy" if brawler["trophies"] >= 1000 else "game/trophies"
        )
        stamp(card, prize, x + 54 - wide / 2, y + 96, 16)
        card.text(x + 74 - wide / 2, y + 95, trophies, 15, GOLD, "la", 2)
        parts = ("gadgets", "starPowers", "gears")
        icons = ("game/gadgets", "game/star_powers", "game/gears")
        for place, (part, name) in enumerate(zip(parts, icons)):
            count(card, x + 13 + place * 30, y + 115, name, len(brawler.get(part, [])))
    foot = f"Page {page['page']} of {page['pages']}"
    card.text(36, card.height - 46, foot, 14, MUTED, "la", 2)
    card.text(604, card.height - 46, page["total"], 14, MUTED, "ra", 2)
    return card.jpg()


def ago(stamp_text, now=None):
    try:
        then = datetime.strptime(stamp_text, "%Y%m%dT%H%M%S.%fZ")
    except (TypeError, ValueError):
        return ""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    minutes = max(int((now - then).total_seconds() // 60), 0)
    if minutes < 60:
        return f"{minutes}m ago"
    if minutes < 1440:
        return f"{minutes // 60}h ago"
    return f"{minutes // 1440}d ago"


def spaced(text):
    """brawlBall as Brawl Ball."""
    words = "".join(f" {letter}" if letter.isupper() else letter for letter in text)
    return words.strip().title()


def sides(battle, tag):
    """The player's side first, then the other side when there is exactly one."""
    teams = battle.get("teams") or [[player] for player in battle.get("players", [])]
    mine = next(
        (team for team in teams if any(player.get("tag") == tag for player in team)),
        teams[0] if teams else [],
    )
    others = [team for team in teams if team is not mine]
    return mine, others[0] if len(others) == 1 else []


def outcome(battle):
    """The word and colour for how it ended: a result, or a place in Showdown."""
    if "rank" in battle:
        teams = battle.get("teams") or battle.get("players") or []
        good = battle["rank"] <= max(len(teams) // 2, 1)
        return f"#{battle['rank']}", GREEN if good else RED
    result = battle.get("result", "")
    words = {
        "victory": ("Win", GREEN),
        "defeat": ("Loss", RED),
        "draw": ("Draw", MUTED),
    }
    return words.get(result, ("", MUTED))


def kind(battle):
    names = {"ranked": "Ladder", "soloRanked": "Ranked"}
    return names.get(battle.get("type"), spaced(battle.get("type", "")))


def draw_battles(page):
    """One page of recent battles: mode, both sides as portraits, how it ended."""
    card = Card(640, 164 + len(page["battles"]) * 78, page["background"])
    head(card, page["player"], "BATTLES", small=True)
    tag, art = page["player"]["tag"], page["art"]
    for spot, item in enumerate(page["battles"]):
        battle, event = item.get("battle", {}), item.get("event", {})
        y = 112 + spot * 78
        word, color = outcome(battle)
        card.slot(36, y, 568, 70, color if word else BLACK)
        if event.get("modeId") is not None:
            stamp(card, art.get(mode_art(event)), 46, y + 15, 40)
        mode = spaced(event.get("mode") or battle.get("mode") or "Battle")
        card.text(96, y + 9, card.fit(mode, 16, 132), 16, WHITE, "la", 2)
        place = card.fit(event.get("map") or "", 12, 132)
        card.text(96, y + 31, place, 12, MUTED, "la", 2)
        card.text(96, y + 47, kind(battle), 11, GREY, "la", 2)
        mine, others = sides(battle, tag)
        star = (battle.get("starPlayer") or {}).get("tag")
        size = 34 if max(len(mine), len(others)) <= 3 else 24
        x, top = 240, y + (70 - size) // 2
        for team in (mine, others):
            for player in team:
                picture = art.get(brawler_art(player["brawler"]["id"]))
                starred = GOLD if player.get("tag") == star else BLACK
                portrait(card, picture, x, top, size, starred)
                x += size + 6
            if team is mine and others:
                card.text(x + 9, y + 26, "VS", 13, MUTED, "ma", 2)
                x += 24
        change = battle.get("trophyChange")
        card.text(590, y + (6 if change else 14), word, 18, color, "ra")
        when = ago(item.get("battleTime"))
        card.text(590, y + (29 if change else 39), when, 11, MUTED, "ra", 2)
        if change:
            text = f"{change:+}"
            stamp(card, "game/trophies", 570 - card.measure(text, 13), y + 46, 14)
            card.text(590, y + 45, text, 13, GOLD, "ra", 2)
    foot = f"Page {page['page']} of {page['pages']}"
    card.text(36, card.height - 46, foot, 14, MUTED, "la", 2)
    return card.jpg()


def draw_milestones(sheet):
    """A member's milestone roles: one row a category, a bar to the next role."""
    card = Card(640, 172 + len(sheet["rows"]) * 72, sheet["background"])
    head(card, sheet["player"], sheet["label"])
    for spot, row in enumerate(sheet["rows"]):
        y = 140 + spot * 72
        reached = sum(row["value"] >= goal for goal in row["goals"])
        done = reached == len(row["goals"])
        card.slot(36, y, 568, 64, GOLD if done else BLACK)
        stamp(card, row["icon"], 46, y + 12, 40)
        card.text(98, y + 10, row["name"], 17, WHITE, "la", 2)
        role = card.fit(named(row["role"] or "No role yet"), 13, 196)
        card.text(98, y + 35, role, 13, row["color"] if row["role"] else GREY, "la", 2)
        goal = row["goals"][min(reached, len(row["goals"]) - 1)]
        label = f"{row['value']:,}" if done else f"{row['value']:,} / {goal:,}"
        card.bar(306, y + 9, 284, 26, row["value"] / goal, GOLD, label)
        for step in range(len(row["goals"])):
            card.draw.rounded_rectangle(
                box(306 + step * 22, y + 43, 16, 9),
                3 * SCALE,
                fill=GOLD if step < reached else EMPTY,
                outline=BLACK,
                width=2 * SCALE,
            )
        total = len(row["goals"])
        left = f"{reached} of {total} role{'s' * (total != 1)}"
        left = "All roles earned" if done else left
        card.text(590, y + 40, left, 12, MUTED, "ra", 2)
    return card.jpg()


def draw_request(sheet):
    """A team request: who is asking, what for, and the seats on the team."""
    card = Card(640, 328, sheet["background"])
    head(card, sheet["player"], sheet["label"])
    tile(card, 36, 140, 182, sheet["mode_art"], sheet["mode"], sheet["kind"])
    tile(card, 229, 140, 182, "game/trophies", f"{sheet['trophies']:,}", "Trophies")
    rank = sheet["ranked"]
    tile(card, 422, 140, 182, sheet["league_art"], f"{rank[1]:,}", league(rank[0]))
    card.slot(36, 222, 568, 74)
    for seat in range(sheet["seats"] + 1):
        x = 50 + seat * 56
        if seat < len(sheet["faces"]):
            portrait(
                card, sheet["faces"][seat], x, 235, 48, GOLD if not seat else BLACK
            )
        else:
            card.draw.rounded_rectangle(
                box(x, 235, 48, 48),
                8 * SCALE,
                fill=EMPTY,
                outline=BLACK,
                width=2 * SCALE,
            )
    free = sheet["seats"] + 1 - len(sheet["faces"])
    if not sheet["open"]:
        card.text(590, 246, "Closed", 20, GREY, "ra")
    elif free:
        card.text(590, 246, f"{free} open", 20, GOLD, "ra")
    else:
        card.text(590, 246, "Full", 20, GREEN, "ra")
    return card.jpg()


async def setup(bot):
    pass

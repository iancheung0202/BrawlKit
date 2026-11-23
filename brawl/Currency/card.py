import asyncio
import io
import os
import re
import time
from functools import lru_cache

import discord
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = "assets/"
SCALE = 2
WHITE, BLACK = (255, 255, 255), (0, 0, 0)
# The widest a name is drawn in the header, so it stays clear of the balances.
NAME_WIDTH = 300
GOLD, GREEN, BLUE, RED = (255, 200, 30), (60, 215, 80), (40, 130, 255), (255, 70, 80)
MUTED = (190, 205, 255)
GREY = (160, 165, 185)
GREY = (90, 96, 120)
PANEL = (8, 18, 70, 185)
LIT = (52, 50, 104)
SLOT = (6, 12, 48)
BACKGROUND = "gym"


@lru_cache
def font(size):
    return ImageFont.truetype(ASSETS + "LilitaOne-Regular.ttf", size * SCALE)


@lru_cache
def gain(picture, amount):
    """How a reward reads: +5 for a currency, x5 for Mega Boxes."""
    return f"x{amount:,}" if picture == "items/mega_box" else f"+{amount:,}"


def icon(name, height):
    image = Image.open(f"{ASSETS}{name}.png").convert("RGBA")
    width = max(1, round(image.width * height * SCALE / image.height))
    return image.resize((width, height * SCALE), Image.LANCZOS)


MARKUP = re.compile(
    r"<a?:\w+:\d+>|[*_`~|]|[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]"
)


EMOJI = re.compile(r"<a?:\w+:\d+>|[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")


def named(text):
    """A display name as typed, minus the emoji the font cannot draw."""
    return " ".join(EMOJI.sub("", str(text)).split()) or "Member"


def plain(text):
    """Discord markup and emoji cannot be drawn, so cards show the words only."""
    return " ".join(MARKUP.sub("", str(text)).split())


def item_icon(item):
    """Every shop item has one icon, used wherever the item is shown."""
    name = f"items/{item}"
    return name if os.path.exists(f"{ASSETS}{name}.png") else "items/effect"


@lru_cache
def backdrop(name, width, height, dim):
    image = Image.open(f"{ASSETS}bg/{name}.jpg").convert("RGB")
    size = (width * SCALE, height * SCALE)
    ratio = max(size[0] / image.width, size[1] / image.height)
    image = image.resize(
        (int(image.width * ratio) + 1, int(image.height * ratio) + 1), Image.LANCZOS
    )
    left, top = (image.width - size[0]) // 2, (image.height - size[1]) // 2
    image = image.crop((left, top, left + size[0], top + size[1]))
    image = image.filter(ImageFilter.GaussianBlur(2 * SCALE)).convert("RGBA")
    return Image.alpha_composite(image, Image.new("RGBA", size, (0, 0, 20, dim)))


@lru_cache
def tinted(name, height, color):
    image = icon(name, height)
    hue = Image.new("RGB", (1, 1), color).convert("HSV").getpixel((0, 0))[0]
    h, s, v = image.convert("RGB").convert("HSV").split()
    h = Image.composite(
        Image.new("L", image.size, hue), h, s.point(lambda x: 255 * (x > 60))
    )
    result = Image.merge("HSV", (h, s, v)).convert("RGBA")
    result.putalpha(image.getchannel("A"))
    return result


def shade(color, factor):
    return tuple(max(0, min(255, int(value * factor))) for value in color[:3])


def box(x, y, w, h):
    return [x * SCALE, y * SCALE, (x + w) * SCALE, (y + h) * SCALE]


class Card:
    def __init__(self, width, height, background=None, dim=95):
        """A card on a member's background, or a strip on none (transparent)."""
        self.width, self.height = width, height
        self.clear = background is None
        if self.clear:
            self.image = Image.new(
                "RGBA", (width * SCALE, height * SCALE), (0, 0, 0, 0)
            )
        else:
            self.image = backdrop(background, width, height, dim).copy()
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    @classmethod
    def strip(cls, step=None, foot=False, small=False):
        """A one-panel strip, one line taller when it also says what to do next.

        foot leaves that line empty for the caller to fill at card.foot, or that
        many lines, 26 apart. A small strip is for one number: a 52 picture, a
        name over the value.
        """
        extra = 30 + 26 * (int(foot) - 1) if step or foot else 0
        tall = 82 if small else 110
        card = cls(640, tall + 40 + extra)
        card.panel(16, 24, 608, tall + extra)
        card.foot = tall + 28
        if extra:
            y = (tall + 20) * SCALE
            card.draw.line(
                [(34 * SCALE, y), (606 * SCALE, y)],
                fill=(255, 255, 255, 40),
                width=SCALE,
            )
        if step:
            card.text(36, card.foot, "Next", 15, GOLD, "la", 2)
            card.text(
                44 + card.measure("Next", 15), card.foot, step, 15, MUTED, "la", 2
            )
        return card

    def panel(self, x, y, w, h, fill=PANEL):
        layer = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle(box(x, y + 5, w, h), 16 * SCALE, fill=(0, 0, 0, 110))
        if self.clear:
            fill = (*shade(fill, 1.25), 255)
        draw.rounded_rectangle(
            box(x, y, w, h), 16 * SCALE, fill=fill, outline=BLACK, width=3 * SCALE
        )
        self.image = Image.alpha_composite(self.image, layer)
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def text(self, x, y, text, size=22, fill=WHITE, anchor="la", stroke=None):
        stroke = (max(2, size // 9) if stroke is None else stroke) * SCALE
        spot = (x * SCALE, y * SCALE)
        style = dict(
            font=font(size), anchor=anchor, stroke_width=stroke, stroke_fill=BLACK
        )
        self.draw.text((spot[0], spot[1] + stroke), text, fill=BLACK, **style)
        self.draw.text(spot, text, fill=fill, **style)

    def measure(self, text, size):
        return font(size).getlength(text) / SCALE

    def fit(self, text, size, width):
        while len(text) > 1 and self.measure(text, size) > width:
            text = text[:-2].rstrip() + "…"
        return text

    def wrap(self, text, size, width, limit=2):
        lines, words = [], text.split()
        while words and len(lines) < limit:
            line = words.pop(0)
            while words and self.measure(f"{line} {words[0]}", size) <= width:
                line += " " + words.pop(0)
            lines.append(line)
        if words:
            lines[-1] = self.fit(lines[-1] + " " + " ".join(words), size, width)
        return [self.fit(line, size, width) for line in lines]

    def paste(self, image, x, y):
        self.image.alpha_composite(image, (round(x * SCALE), round(y * SCALE)))

    def icon(self, name, x, y, height):
        self.paste(icon(name, height), x, y)

    def avatar(self, data, x, y, size, corner=12):
        try:
            image = Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception:
            image = Image.open(ASSETS + "DefaultIcon.png").convert("RGBA")
        image = image.resize((size * SCALE, size * SCALE), Image.LANCZOS)
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, *image.size], corner * SCALE, fill=255
        )
        edge = min(3, corner // 3)
        self.draw.rounded_rectangle(
            box(x - edge, y - edge, size + edge * 2, size + edge * 2),
            (corner + edge) * SCALE,
            fill=BLACK,
        )
        self.image.paste(image, (x * SCALE, y * SCALE), mask)

    def bar(self, x, y, w, h, part, fill=GOLD, label=None):
        self.draw.rounded_rectangle(
            box(x, y, w, h), 5 * SCALE, fill=SLOT, outline=BLACK, width=3 * SCALE
        )
        if part > 0:
            full = max(h, w * min(part, 1)) - 6
            self.draw.rounded_rectangle(
                box(x + 3, y + 3, full, h - 6), 3 * SCALE, fill=fill
            )
            self.draw.rounded_rectangle(
                box(x + 3, y + 3, full, h * 0.45 - 3), 3 * SCALE, fill=shade(fill, 1.25)
            )
        if label:
            self.text(x + w / 2, y + h / 2 - 1, label, int(h * 0.62), WHITE, "mm", 2)

    def pill(self, x, y, name, value):
        w = self.measure(value, 24) + 62
        self.draw.rounded_rectangle(
            box(x, y, w, 38), 8 * SCALE, fill=SLOT, outline=BLACK, width=3 * SCALE
        )
        self.icon(name, x - 12, y, 38)
        self.text(x + 36, y + 5, value, 24, WHITE, "la", 2)
        return x + w + 34

    def tag(self, x, y, label, fill=GOLD, color=BLACK, right=False):
        w = self.measure(label, 15) + 22
        x -= w * right
        corners = [(x, y + 24), (x + 6, y), (x + w, y), (x + w - 6, y + 24)]
        self.draw.polygon(
            [(a * SCALE, b * SCALE) for a, b in corners],
            fill=fill,
            outline=BLACK,
            width=2 * SCALE,
        )
        self.draw.text(
            ((x + w / 2) * SCALE, (y + 11) * SCALE),
            label,
            font=font(15),
            fill=color,
            anchor="mm",
        )

    def button(self, x, y, w, h, fill=GREEN):
        """A chunky game button: dark lip below, lighter band on top."""
        self.draw.rounded_rectangle(
            box(x, y, w, h + 4),
            8 * SCALE,
            fill=shade(fill, 0.55),
            outline=BLACK,
            width=3 * SCALE,
        )
        self.draw.rounded_rectangle(
            box(x + 3, y + 3, w - 6, h - 6), 5 * SCALE, fill=fill
        )
        self.draw.rounded_rectangle(
            box(x + 3, y + 3, w - 6, h * 0.45 - 3), 5 * SCALE, fill=shade(fill, 1.2)
        )

    def price(self, x, y, currency, cost, fill=GREEN, color=WHITE):
        """A price button; returns its width so the caller can place what follows."""
        cost = f"{cost:,}"
        w = self.measure(cost, 19) + 54
        self.button(x, y, w, 30, fill)
        self.icon(f"kit/{currency[:-1]}", x + 9, y + 3, 24)
        self.text(x + 40, y + 3, cost, 19, color, "la", 2)
        return w

    def tick(self, x, y, size=28, mark="kit/icon_check"):
        """A done mark filling a size x size box. The Stamp icon is for Stamps only."""
        mark = icon(mark, round(size * (1.3 if mark == "kit/icon_checkpoint" else 1.2)))
        self.paste(
            mark,
            x + (size - mark.width / SCALE) / 2,
            y + (size - mark.height / SCALE) / 2,
        )

    def stop(self, x, y, done):
        """A step on a timeline: a checkpoint badge once it is reached."""
        if done:
            return self.tick(x, y, mark="kit/icon_checkpoint")
        self.check(x, y, False)

    def check(self, x, y, done):
        if done:
            return self.tick(x, y)
        self.draw.rounded_rectangle(
            box(x, y, 28, 28), 6 * SCALE, fill=SLOT, outline=BLACK, width=3 * SCALE
        )

    def task(self, x, y, w, name, state, done, part):
        self.check(x, y, done)
        room = w - 54 - self.measure(state, 17)
        self.text(
            x + 42,
            y - 1,
            self.fit(name, 21, room),
            21,
            MUTED if done else WHITE,
            "la",
            2,
        )
        self.text(x + w, y + 1, state, 17, GREEN if done else GOLD, "ra", 2)
        self.bar(x + 42, y + 30, w - 42, 14, part, GREEN if done else GOLD)

    def next_order(self, x, y, anchor="la"):
        """A small grey line: how long until the next order comes in."""
        left = int(86400 - time.time() % 86400) // 60
        label = f"Next order in {left // 60}h {left % 60}m"
        width = 22 + self.measure(label, 14)
        x -= {"la": 0, "ma": width / 2, "ra": width}[anchor]
        self.icon("kit/icon_clock", x, y + 2, 15)
        self.text(x + 22, y, label, 14, MUTED, "la", 2)

    def stamps(self, x, y, have, total, per_row, gap, radius=19, prize=None):
        """Rows of Stamp slots. prize is (every, icon, amount): the slots that pay."""
        stamp = icon("kit/icon_ranked_round_token", int(radius * 2.5))
        for spot in range(total):
            cx = x + (spot % per_row) * gap
            cy = y + (spot // per_row) * (gap + 2)
            if spot < have:
                self.paste(
                    stamp, cx - stamp.width / SCALE / 2, cy - stamp.height / SCALE / 2
                )
                continue
            self.draw.ellipse(
                box(cx - radius, cy - radius, radius * 2, radius * 2),
                fill=SLOT,
                outline=GOLD if spot == have else BLACK,
                width=3 * SCALE,
            )
            if prize and (spot + 1) % prize[0] == 0:
                size = int(radius * 1.5)
                self.icon(prize[1], cx - size / 2, cy - size / 2, size)
                self.text(cx + radius, cy + 2, str(prize[2]), 15, WHITE, "ra", 2)

    def header(self, name, avatar, level, xp, xp_needed, beans, tokens, stamps):
        self.avatar(avatar, 29, 25, 68)
        self.text(116, 20, self.fit(name, 32, NAME_WIDTH), 32)
        self.icon("kit/icon_xp", 110, 58, 40)
        label = f"LEVEL {level}"
        self.text(158, 62, label, 20, GOLD)
        pills = (
            ("kit/bean", f"{beans:,}"),
            ("kit/token", f"{tokens:,}"),
            ("kit/icon_ranked_round_token", f"{stamps:,}"),
        )
        left = self.width - 26 + 34
        left -= sum(self.measure(value, 24) + 96 for _, value in pills)
        start = 170 + self.measure(label, 20)
        self.bar(
            start,
            62,
            # Shorter when long balances reach this far left.
            min(180, left - 62 - start),
            26,
            xp / xp_needed,
            BLUE,
            f"{xp:,} / {xp_needed:,}",
        )
        for picture, value in pills:
            left = self.pill(left, 38, picture, value)
        return start

    def title(self, title, line):
        self.text(34, 22, title, 42)
        self.text(36, 76, line, 19, MUTED, "la", 2)

    def stat(self, label, value):
        x = self.width - 254
        self.panel(x, 24, 228, 70)
        self.text(x + 114, 34, label, 14, MUTED, "ma", 2)
        self.text(x + 114, 54, value, 23, GOLD, "ma")

    def hint(self, text):
        self.text(36, self.height - 40, text, 18, GOLD, "la", 2)

    def slot(self, x, y, w, h, outline=BLACK, lit=False):
        """A row's box; lit marks the one row to look at with a lighter fill."""
        self.draw.rounded_rectangle(
            box(x, y, w, h),
            10 * SCALE,
            fill=LIT if lit else SLOT,
            outline=outline,
            width=3 * SCALE,
        )

    def jpg(self):
        """The finished image: a JPEG, or a trimmed PNG for a transparent strip."""
        data = io.BytesIO()
        if self.clear:
            left, top, right, bottom = self.image.getbbox()
            pad = 4 * SCALE
            self.image.crop(
                (
                    max(left - pad, 0),
                    max(top - pad, 0),
                    min(right + pad, self.image.width),
                    min(bottom + pad, self.image.height),
                )
            ).save(data, "PNG", compress_level=6)
        else:
            self.image.convert("RGB").save(data, "JPEG", quality=90, subsampling=0)
        data.seek(0)
        return data


FACES = {}


async def roster(guild, ids):
    """Members by id. The bot does not keep the whole server loaded, so ask for the rest."""
    ids = [int(member_id) for member_id in ids]
    missing = [member_id for member_id in ids if guild.get_member(member_id) is None]
    for start in range(0, len(missing), 100):
        try:
            await guild.query_members(user_ids=missing[start : start + 100], cache=True)
        except Exception:
            break
    return [guild.get_member(member_id) for member_id in ids]


async def faces(members):
    """Small avatars for a list of members, fetched together and kept."""

    async def face(member):
        if member is None:
            return b""
        key = member.display_avatar.key
        if key not in FACES:
            try:
                FACES[key] = await member.display_avatar.replace(size=64).read()
            except Exception:
                return b""
            if len(FACES) > 2000:
                FACES.pop(next(iter(FACES)))
        return FACES[key]

    return await asyncio.gather(*(face(member) for member in members))


async def render(draw, *args, name="card"):
    """Draws off the event loop so a slow card never stalls the bot."""
    data = await asyncio.to_thread(draw, *args)
    kind = "png" if data.getvalue().startswith(b"\x89PNG") else "jpg"
    return discord.File(data, f"{name}.{kind}")


async def setup(bot):
    pass

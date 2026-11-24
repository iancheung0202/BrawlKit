"""The Golden Bean: a community event with an end.

One member holds the Golden Bean. A reply to any of their messages in a main
chat channel steals it. Held time adds up to the second, every full minute of
it is a ticket, and when the event ends one ticket is drawn for the prize.

Everything the event needs is in this file. To end it for good, delete this
file, tests/test_goldenbean.py and assets/kit/golden_bean.png. Nothing else in
the bot refers to them. Its saved data sits under one database node (ROOT).
"""

import asyncio
import random
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from firebase_admin import db

from brawl.Currency import ladder
from brawl.Currency.card import (
    ASSETS,
    GOLD,
    GREEN,
    MUTED,
    SCALE,
    WHITE,
    Card,
    faces,
    icon,
    named,
    render,
    roster,
)
from brawl.Currency.db import G_ROOT, u_mega_boxes
from brawl.Currency.helper import MAIN_CHAT_CHANNELS, MAIN_GUILD_ID

# The event starts the first time the bot loads this file and runs this long.
DAYS = 14
PRIZE = ("Brawl Pass Plus", "kit/icon_brawl_pass_plus")
# Held time adds up across holds; this much of it is one ticket.
TICKET_SECONDS = 60
# The top 5 and the winner are posted here, not in chat.
NEWS_CHANNEL = 1396565294582857738
# One hold counts for this long, then the bean falls to the floor.
HOLD_SECONDS = 30 * 60
# A member's first take of the day (UTC) pays this many Mega Boxes on the spot.
FIRST_TAKE_BOXES = 1
# Tickets and the Mega Box need this cafe level, so a fresh account earns nothing.
# Time held below it is kept and counts once the member gets there.
MIN_LEVEL = 2
# The reaction moves at most once in this long, however fast the bean does.
MOVE_SECONDS = 2
BOARD_ROWS = 5

# The one sentence every card uses for the rule.
RULE = f"Every minute you hold is a ticket to win {PRIZE[0]}"
STEAL = "Reply to steal it"

ROOT = f"{G_ROOT}/{MAIN_GUILD_ID}/golden_bean_event"
BEAN = "kit/golden_bean"
EMOJI = "golden_bean"
FALLBACK = "\U0001fad8"


def now():
    return time.time()


def today():
    return datetime.fromtimestamp(now(), timezone.utc).strftime("%Y-%m-%d")


def plural(count, word):
    return f"{count:,} {word}{'s' * (count != 1)}"


def replied_to(message):
    """The id of the member this message replies to, if it is a reply."""
    if message.type != discord.MessageType.reply or not message.reference:
        return None
    target = message.reference.resolved
    return target.author.id if isinstance(target, discord.Message) else None


def wide(picture, height):
    return icon(picture, height).width / SCALE


def prize_line(card, y):
    """What the tickets are for, with the prize's own picture."""
    card.icon(PRIZE[1], 34, y - 2, 20)
    card.text(42 + wide(PRIZE[1], 20), y, RULE, 15, MUTED, "la", 2)


def draw_taken(take):
    """A strip posted when a member takes the bean: who, and what they got."""
    card = Card.strip(foot=True, small=True)
    card.tag(32, 12, "GOLDEN BEAN", GOLD)
    card.avatar(take["avatar"], 34, 40, 52)
    card.icon(BEAN, 68, 66, 28)
    card.text(104, 40, card.fit(named(take["name"]), 16, 280), 16, MUTED, "la", 2)
    verb = "Stole" if take["stolen"] else "Picked up"
    card.text(104, 60, f"{verb} the Golden Bean", 24, GOLD)
    if take["boxes"]:
        gain = f"x{take['boxes']}"
        card.text(604, 48, gain, 28, WHITE, "ra")
        card.icon("items/mega_box", 560 - card.measure(gain, 28), 44, 40)
        card.text(604, 84, "first take today", 13, MUTED, "ra", 2)
    else:
        card.text(604, 52, plural(take["tickets"], "ticket"), 22, WHITE, "ra")
    prize_line(card, card.foot)
    card.text(604, card.foot, STEAL, 15, GOLD, "ra", 2)
    return card.jpg()


def draw_floor(_):
    """A strip posted when nobody holds the bean."""
    card = Card.strip(foot=True, small=True)
    card.tag(32, 12, "GOLDEN BEAN", GOLD)
    card.icon(BEAN, 40, 38, 56)
    card.text(104, 40, "Nobody holds it", 16, MUTED, "la", 2)
    card.text(104, 60, "The Golden Bean is on the floor", 24, GOLD)
    prize_line(card, card.foot)
    card.text(604, card.foot, "Next message takes it", 15, GOLD, "ra", 2)
    return card.jpg()


def clock(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}m {seconds % 60}s" if seconds >= 60 else f"{seconds}s"


def draw_board(board):
    """Who has the most tickets and how long until the draw. `/golden` adds
    the member who asked: their own row when they are not in the top."""
    rows = list(board["rows"])
    you = board.get("you")
    if you and you["row"]:
        rows.append(you["row"])
    card = Card(640, 132 + 46 * len(rows) + 46)
    card.panel(16, 24, 608, card.height - 40)
    card.tag(32, 12, "GOLDEN BEAN", GOLD)
    card.note(24, board["ends"])
    card.icon(PRIZE[1], 36, 50, 40)
    x = 48 + wide(PRIZE[1], 40)
    card.text(x, 46, "Tickets", 26, GOLD)
    card.text(x, 80, RULE, 15, MUTED, "la", 2)
    most = max((row[1] for row in rows), default=1) or 1
    for spot, (name, tickets, avatar, place, holds) in enumerate(rows):
        y = 116 + spot * 46
        card.avatar(avatar, 36, y, 34, 8)
        if holds:
            card.icon(BEAN, 58, y + 16, 20)
        mine = you and place == you["place"]
        name = card.fit(f"{place}. {named(name)}", 15, 360)
        card.text(82, y - 2, name, 15, GOLD if mine else WHITE, "la", 2)
        card.bar(82, y + 18, 440, 14, tickets / most, GOLD)
        card.text(604, y + 6, f"{tickets:,}", 20, WHITE, "ra")
    foot = card.height - 44
    left = you["line"] if you else plural(board["players"], "member") + " in"
    card.text(36, foot, left, 15, MUTED, "la", 2)
    card.text(604, foot, STEAL, 15, GOLD, "ra", 2)
    return card.jpg()


def draw_winner(win):
    """The draw: one ticket picked, and whose it was."""
    card = Card.strip(foot=True)
    card.tag(32, 12, "GOLDEN BEAN", GREEN)
    card.avatar(win["avatar"], 36, 44, 72)
    card.icon(BEAN, 84, 82, 38)
    card.text(128, 46, card.fit(named(win["name"]), 18, 330), 18, MUTED, "la", 2)
    card.text(128, 70, f"Wins {PRIZE[0]}", 28, GOLD)
    card.icon(PRIZE[1], 604 - wide(PRIZE[1], 56), 50, 56)
    line = f"Drawn from {plural(win['total'], 'ticket')}"
    card.text(36, card.foot, line, 15, MUTED, "la", 2)
    held = f"Held {plural(win['tickets'], 'ticket')}"
    card.text(604, card.foot, held, 15, GOLD, "ra", 2)
    return card.jpg()


class GoldenBean(commands.Cog):
    """The holder lives here and in the database. The reaction only shows it:
    one task moves it to the message that last took the bean, so a burst of
    steals costs Discord one remove and one add."""

    def __init__(self, bot):
        self.bot = bot
        self.ref = db.reference(ROOT)
        saved = self.ref.get() or {}
        self.starts = saved.get("starts") or now()
        if not saved.get("starts"):
            self.ref.update({"starts": self.starts})
        self.winner = saved.get("winner")
        self.holder = saved.get("holder")
        self.last = saved.get("last")  # who let it fall; they cannot pick it up
        self.took = saved.get("took", 0)  # the message that took it; later ones win
        self.since = saved.get("since", 0)
        self.mark = self.spot(saved.get("mark"))  # where the reaction belongs
        self.shown = self.spot(saved.get("shown"))  # where the reaction is
        self.floor = saved.get("floor", True)  # the floor strip is still to post
        self.posted = saved.get("posted") or today()
        self.seconds = {int(k): v for k, v in (saved.get("seconds") or {}).items()}
        self.unsaved = set()
        self.boxes = {int(k): v for k, v in (saved.get("boxes") or {}).items()}
        self.late = {}  # replies that arrived before their target held the bean
        self.member = None
        self.levelled = set()
        self.floored = False  # the floor strip went out for this fall
        self.strip = None  # the last strip posted in chat
        self.between = 0  # messages in its channel since then
        self.emoji = FALLBACK
        self.moved = asyncio.Event()
        self.moved.set()
        self.tasks = [
            bot.loop.create_task(self.show_loop()),
            bot.loop.create_task(self.minute_loop()),
        ]

    def cog_unload(self):
        for task in self.tasks:
            if task:
                task.cancel()

    @staticmethod
    def spot(saved):
        return tuple(saved) if saved else None

    @property
    def ends(self):
        return self.starts + DAYS * 86400

    @property
    def running(self):
        return self.winner is None and now() < self.ends

    def effortful(self, message):
        """The same filter chat Beans use, so one-word spam cannot steal."""
        cafe = self.bot.get_cog("CurrencySystem")
        if cafe is None:
            return len(message.content.strip()) >= 5
        chat, author = cafe.chat_system, message.author.id
        # Chat Beans may have seen this message first and kept it as the
        # member's last one, which would make it look like a repeat of itself.
        last = chat.last_messages.get(author)
        if last == message.content.strip():
            chat.last_messages[author] = ""
        try:
            return chat.is_effortful_message(message.content, author)[0]
        finally:
            if last is not None:
                chat.last_messages[author] = last

    def offer(self, message):
        """Whether this main chat message takes the bean. Never waits, so two
        messages cannot both take it."""
        if not self.running or message.channel.id not in MAIN_CHAT_CHANNELS:
            return False
        author = message.author.id
        if self.holder is None:
            return (
                author != self.last and self.effortful(message) and self.give(message)
            )
        if author == self.holder:
            if self.mark is None:  # the marked message was deleted
                self.mark = (message.channel.id, message.id)
                self.moved.set()
            return False
        target = replied_to(message)
        if target is None or target == author or not self.effortful(message):
            return False
        if target == self.holder:
            # An older reply delivered late does not undo a newer take.
            return message.id > self.took and self.give(message)
        self.late[target] = message
        return False

    def bank(self):
        """Adds the hold that just ended to its holder's time, to the second."""
        if self.holder is not None:
            held = min(now() - self.since, HOLD_SECONDS)
            self.seconds[self.holder] = self.seconds.get(self.holder, 0) + held
            self.unsaved.add(self.holder)

    def held(self, user_id):
        """Seconds this member has held the bean, the hold in progress included."""
        going = min(now() - self.since, HOLD_SECONDS) * (user_id == self.holder)
        return self.seconds.get(user_id, 0) + going

    def tickets(self, user_id):
        return int(self.held(user_id) // TICKET_SECONDS)

    def give(self, message):
        self.bank()
        self.holder, self.member = message.author.id, message.author
        self.took, self.since, self.last = message.id, now(), None
        self.mark = (message.channel.id, message.id)
        self.floor = False
        self.moved.set()
        # Discord may deliver a reply before the message it answers.
        waiting = self.late.pop(self.holder, None)
        self.late.clear()
        if waiting and waiting.id > message.id:
            self.give(waiting)
        return True

    def drop(self, last=None):
        """Nobody holds it; the next main chat message picks it up."""
        self.bank()
        self.holder, self.member, self.mark = None, None, None
        self.last, self.floor, self.floored = last, True, False
        self.moved.set()

    async def levelled_up(self, user_id):
        if user_id not in self.levelled:
            level = await ladder.level_of(self.bot, user_id, MAIN_GUILD_ID)
            if level < MIN_LEVEL:
                return False
            self.levelled.add(user_id)
        return True

    async def tell(self, message, stolen):
        """A member's first take of the day pays Mega Boxes and is posted; so is
        a pick-up from the floor. Other steals only move the reaction."""
        user_id = message.author.id
        boxes = 0
        if self.boxes.get(user_id) != today() and await self.levelled_up(user_id):
            boxes = FIRST_TAKE_BOXES
            self.boxes[user_id] = today()
            self.ref.child("boxes").child(str(user_id)).set(today())
            held = u_mega_boxes(user_id)
            held.set((held.get() or 0) + boxes)
        if not boxes and stolen:
            return
        try:
            avatar = await message.author.display_avatar.replace(size=128).read()
        except Exception:
            avatar = None
        take = {
            "name": message.author.display_name,
            "avatar": avatar,
            "stolen": stolen,
            "boxes": boxes,
            "tickets": self.tickets(user_id),
        }
        # The message that took the bean is the one allowed in between.
        await self.chat(message.channel, draw_taken, take, 1)

    async def chat(self, channel, draw, data, allowed=0):
        """Posts a strip in chat. The strip before it goes only when the two
        would sit right after each other; one further up stays to be seen."""
        old = self.strip
        try:
            file = await render(draw, data, name="bean")
            if old and old.channel.id == channel.id and self.between <= allowed:
                try:
                    await old.delete()
                except discord.HTTPException:
                    pass
            self.strip, self.between = await channel.send(file=file), 0
        except Exception as e:
            print(f"Failed to post the Golden Bean: {e}")

    async def post(self, draw, data, **more):
        """Posts in the news channel, where nothing is ever taken down."""
        channel = self.bot.get_channel(NEWS_CHANNEL)
        if channel:
            await channel.send(file=await render(draw, data, name="bean"), **more)

    async def people(self, ids):
        guild = self.bot.get_guild(MAIN_GUILD_ID)
        members = await roster(guild, ids) if guild else [None] * len(ids)
        names = [member.display_name if member else "Member" for member in members]
        return list(zip(names, await faces(members)))

    async def counted(self):
        """Tickets of every member who has one and is high enough a level."""
        ids = {*self.seconds, *([self.holder] if self.holder else [])}
        have = {user_id: self.tickets(user_id) for user_id in ids}
        return {
            user_id: tickets
            for user_id, tickets in have.items()
            if tickets and await self.levelled_up(user_id)
        }

    async def standing(self, viewer=None):
        """The top of the board, and where the member who asked stands."""
        have = await self.counted()
        order = sorted(have, key=lambda user_id: -have[user_id])
        shown = order[:BOARD_ROWS]
        extra = viewer in have and viewer not in shown
        people = await self.people(shown + [viewer] * extra)
        rows = [
            (
                name,
                have[user_id],
                avatar,
                order.index(user_id) + 1,
                user_id == self.holder,
            )
            for user_id, (name, avatar) in zip(shown + [viewer] * extra, people)
        ]
        left = self.ends - now()
        if self.winner is not None or left <= 0:
            ends = "Draw is over"
        elif left < 86400:
            ends = f"Draw in {plural(max(1, round(left / 3600)), 'hour')}"
        else:
            ends = f"Draw in {plural(round(left / 86400), 'day')}"
        board = {"rows": rows[:BOARD_ROWS], "players": len(have), "ends": ends}
        if viewer:
            held = self.held(viewer)
            if not held:
                line = "You have not held it yet"
            elif not await self.levelled_up(viewer):
                line = f"You held it {clock(held)}. Tickets start at Level {MIN_LEVEL}"
            else:
                line = f"You held it {clock(held)}"
            board["you"] = {
                "row": rows[-1] if extra else None,
                "place": order.index(viewer) + 1 if viewer in have else 0,
                "line": line,
            }
        return board

    async def board(self):
        board = await self.standing()
        if board["rows"]:
            await self.post(draw_board, board)

    @app_commands.command(
        name="golden", description="Golden Bean: the top 5 and your own tickets"
    )
    async def golden(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        board = await self.standing(interaction.user.id)
        await interaction.followup.send(
            file=await render(draw_board, board, name="bean"), ephemeral=True
        )

    async def draw(self):
        """The event is over: one ticket is picked, and the bean goes away."""
        self.drop()
        self.floor = False
        have = await self.counted()
        holders, counts = list(have), list(have.values())
        self.winner = random.choices(holders, counts)[0] if holders else 0
        self.ref.update({"winner": self.winner})
        if not self.winner:
            return
        ((name, avatar),) = await self.people([self.winner])
        win = {
            "name": name,
            "avatar": avatar,
            "tickets": have[self.winner],
            "total": sum(counts),
        }
        await self.post(draw_winner, win, content=f"<@{self.winner}>")

    def save(self):
        while self.unsaved:
            user_id = self.unsaved.pop()
            self.ref.child("seconds").child(str(user_id)).set(self.seconds[user_id])

    async def minute(self):
        """The slow jobs: the daily top 5, a hold that ran out, the draw."""
        self.save()
        if not self.running:
            if self.winner is None:
                await self.draw()
            return
        if self.posted != today():
            self.posted = today()
            self.ref.update({"posted": self.posted})
            await self.board()
        holder = self.holder
        if holder is None:
            if self.floor and not self.floored:
                self.floored = True
                channel = self.bot.get_channel(MAIN_CHAT_CHANNELS[0])
                if channel:
                    await self.chat(channel, draw_floor, None)
            return
        if now() - self.since > HOLD_SECONDS:
            self.drop(holder)

    async def minute_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed() and self.winner is None:
            try:
                await self.minute()
            except Exception as e:
                print(f"Golden Bean minute failed: {e}")
            await asyncio.sleep(60)

    async def react(self, spot, add):
        if not spot:
            return
        channel = self.bot.get_partial_messageable(spot[0])
        message = channel.get_partial_message(spot[1])
        try:
            if add:
                await message.add_reaction(self.emoji)
            else:
                await message.remove_reaction(self.emoji, self.bot.user)
        except discord.HTTPException:
            pass  # the message is gone

    async def find_emoji(self):
        try:
            for emoji in await self.bot.fetch_application_emojis():
                if emoji.name == EMOJI:
                    return emoji
            with open(f"{ASSETS}{BEAN}.png", "rb") as picture:
                return await self.bot.create_application_emoji(
                    name=EMOJI, image=picture.read()
                )
        except Exception as e:
            print(f"No Golden Bean emoji, using {FALLBACK}: {e}")
            return FALLBACK

    async def show(self):
        """Saves the holder and moves the reaction to where it belongs now."""
        want = self.mark
        self.save()
        self.ref.update(
            {
                "starts": self.starts,
                "holder": self.holder,
                "last": self.last,
                "took": self.took,
                "since": self.since,
                "mark": want,
                "shown": self.shown,
                "floor": self.floor,
            }
        )
        if want == self.shown:
            return
        await self.react(self.shown, False)
        await self.react(want, True)
        self.shown = want
        self.ref.update({"shown": want})

    async def show_loop(self):
        await self.bot.wait_until_ready()
        self.emoji = await self.find_emoji()
        while not self.bot.is_closed():
            await self.moved.wait()
            self.moved.clear()
            try:
                await self.show()
            except Exception as e:
                print(f"Failed to move the Golden Bean: {e}")
            await asyncio.sleep(MOVE_SECONDS)

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.strip and message.channel.id == self.strip.channel.id:
            self.between += message.id != self.strip.id
        if message.author.bot or not message.guild:
            return
        stolen = self.holder is not None
        if self.offer(message):
            await self.tell(message, stolen)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        self.deleted({payload.message_id})

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        self.deleted(payload.message_ids)

    def deleted(self, message_ids):
        if self.mark and self.mark[1] in message_ids:
            self.mark = None
            self.moved.set()

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.id == self.holder:
            self.drop()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Only the bot's own Golden Bean reaction stays on a message."""
        if (
            payload.user_id == self.bot.user.id
            or payload.channel_id not in MAIN_CHAT_CHANNELS
            or str(payload.emoji) != str(self.emoji)
        ):
            return
        channel = self.bot.get_partial_messageable(payload.channel_id)
        message = channel.get_partial_message(payload.message_id)
        try:
            await message.remove_reaction(
                payload.emoji, discord.Object(payload.user_id)
            )
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(GoldenBean(bot))

import asyncio
import random
import time

import discord

from brawl.Currency import heat
from brawl.Currency.card import ASSETS, render, roster
from brawl.Currency.config import (
    GOLDEN_BEAN_BEANS,
    GOLDEN_BEAN_HOLD_SECONDS,
    GOLDEN_BEAN_MOVE_SECONDS,
    GOLDEN_BEAN_NEWS_SECONDS,
    GOLDEN_BEAN_PAY_SECONDS,
)
from brawl.Currency.db import g_golden_bean, u_golden_bean
from brawl.Currency.helper import MAIN_CHAT_CHANNELS, MAIN_GUILD_ID
from brawl.Currency.quests import get_next_daily_reset
from brawl.Currency.stationcard import draw_stolen

EMOJI = "golden_bean"
FALLBACK = "\U0001fad8"


def paid_today(user_id):
    """Beans holding the Golden Bean paid this member since the daily reset."""
    data = u_golden_bean(user_id).get() or {}
    return data.get("beans", 0) if time.time() < data.get("reset_time", 0) else 0


def replied_to(message):
    """The id of the member this message replies to, if it is a reply."""
    if message.type != discord.MessageType.reply or not message.reference:
        return None
    target = message.reference.resolved
    return target.author.id if isinstance(target, discord.Message) else None


class GoldenBean:
    """One member holds the Golden Bean; a reply to any of their messages takes it.

    The holder lives here and in the database. The reaction only shows it: one
    task moves it to the message that last took the bean, so a burst of steals
    costs Discord one remove and one add.
    """

    def __init__(self, bot, cog):
        self.bot, self.cog = bot, cog
        saved = g_golden_bean(MAIN_GUILD_ID).get() or {}
        self.holder = saved.get("holder")
        self.took = saved.get("took", 0)  # the message that took it; later ones win
        self.since = saved.get("since", 0)
        self.mark = self.spot(saved.get("mark"))  # where the reaction belongs
        self.shown = self.spot(saved.get("shown"))  # where the reaction is
        self.late = {}  # replies that arrived before their target held the bean
        self.member = None
        self.seen = (None, None, None)
        self.emoji = FALLBACK
        self.moved = asyncio.Event()
        self.moved.set()
        self.told = 0
        self.notice = None
        bot.loop.create_task(self.show_loop())
        bot.loop.create_task(self.pay_loop())

    @staticmethod
    def spot(saved):
        return tuple(saved) if saved else None

    def offer(self, message):
        """Whether this main chat message takes the bean. Never waits, so two
        messages cannot both take it."""
        if message.channel.id not in MAIN_CHAT_CHANNELS:
            return False
        if self.holder is None:
            return self.give(message)
        if message.author.id == self.holder:
            if self.mark is None:  # the marked message was deleted
                self.mark = (message.channel.id, message.id)
                self.moved.set()
            return False
        target = replied_to(message)
        if target is None or target == message.author.id:
            return False
        if target == self.holder:
            # An older reply delivered late does not undo a newer take.
            return message.id > self.took and self.give(message)
        self.late[target] = message
        return False

    def give(self, message):
        self.holder, self.member = message.author.id, message.author
        self.took, self.since = message.id, time.time()
        self.mark = (message.channel.id, message.id)
        self.moved.set()
        # Discord may deliver a reply before the message it answers.
        waiting = self.late.pop(self.holder, None)
        self.late.clear()
        if waiting and waiting.id > message.id:
            self.give(waiting)
        return True

    def drop(self):
        """Nobody holds it; the next main chat message picks it up."""
        self.holder, self.member, self.mark = None, None, None
        self.moved.set()

    def deleted(self, message_ids):
        if self.mark and self.mark[1] in message_ids:
            self.mark = None
            self.moved.set()

    def left(self, user_id):
        if user_id == self.holder:
            self.drop()

    async def who(self):
        """The holder's name and picture for a card, or None."""
        holder = self.holder
        if holder is None:
            return None
        if self.seen[0] != holder:
            member = self.member
            if member is None or member.id != holder:
                guild = self.bot.get_guild(MAIN_GUILD_ID)
                member = (await roster(guild, [holder]))[0] if guild else None
            try:
                avatar = await member.display_avatar.replace(size=128).read()
            except Exception:
                avatar = None
            name = member.display_name if member else "Someone"
            self.seen = (holder, name, avatar)
        return {"name": self.seen[1], "avatar": self.seen[2]}

    async def tell(self, message, stolen):
        """A strip for a member's first take, or any take in a Cold chat."""
        user_id = message.author.id
        first = not (u_golden_bean(user_id).get() or {}).get("told")
        cold = not heat.level_of(min(self.cog.thermometer_heat, 100))[2]
        recent = time.time() - self.told < GOLDEN_BEAN_NEWS_SECONDS
        if not first and (not cold or recent):
            return
        self.told = time.time()
        try:
            card = await render(
                draw_stolen, {**await self.who(), "stolen": stolen}, name="bean"
            )
            if self.holder != user_id:
                return
            old, self.notice = self.notice, await message.channel.send(file=card)
            u_golden_bean(user_id).update({"told": True})
            if old:
                await old.delete()
        except Exception as e:
            print(f"Failed to post the Golden Bean: {e}")

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

    async def fake(self, payload):
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

    async def find_emoji(self):
        try:
            for emoji in await self.bot.fetch_application_emojis():
                if emoji.name == EMOJI:
                    return emoji
            with open(f"{ASSETS}kit/golden_bean.png", "rb") as picture:
                return await self.bot.create_application_emoji(
                    name=EMOJI, image=picture.read()
                )
        except Exception as e:
            print(f"No Golden Bean emoji, using {FALLBACK}: {e}")
            return FALLBACK

    async def show(self):
        """Saves the holder and moves the reaction to where it belongs now."""
        want = self.mark
        saved = {
            "holder": self.holder,
            "took": self.took,
            "since": self.since,
            "mark": want,
            "shown": self.shown,
        }
        g_golden_bean(MAIN_GUILD_ID).set(saved)
        if want == self.shown:
            return
        await self.react(self.shown, False)
        await self.react(want, True)
        self.shown = want
        g_golden_bean(MAIN_GUILD_ID).update({"shown": want})

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
            await asyncio.sleep(GOLDEN_BEAN_MOVE_SECONDS)

    async def pay(self):
        """Pays whoever holds the bean right now, unless they held it too long."""
        holder = self.holder
        if holder is None or time.time() - self.since > GOLDEN_BEAN_HOLD_SECONDS:
            return
        await self.cog.add_beans(holder, GOLDEN_BEAN_BEANS)
        u_golden_bean(holder).update(
            {
                "beans": paid_today(holder) + GOLDEN_BEAN_BEANS,
                "reset_time": get_next_daily_reset(),
            }
        )

    async def pay_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            # A random moment each minute, so nobody can time a steal for it.
            wait = random.uniform(0, GOLDEN_BEAN_PAY_SECONDS)
            await asyncio.sleep(wait)
            try:
                await self.pay()
            except Exception as e:
                print(f"Failed to pay the Golden Bean: {e}")
            await asyncio.sleep(GOLDEN_BEAN_PAY_SECONDS - wait)


async def setup(bot):
    pass

import asyncio
import functools
import random
import re
import time

import discord
from discord import app_commands
from discord.ext import commands
from firebase_admin import db

from brawl.Currency import wallet
from brawl.Currency.card import render
from brawl.Currency.config import (
    BUY,
    DROP_BONUS,
    DROP_UPGRADES,
    EFFECT_FALLBACK_TOKENS,
    MEGA_BOX_BASE,
    MEGA_BOX_BASE_RARITY,
    MEGA_BOX_EXTRA,
    MEGA_BOX_ITEMS,
    STAR_DROP_RATES,
)
from brawl.Currency.db import (
    sync_shop_effects,
    u_mega_boxes,
    u_mega_boxes_pending,
    u_shop_effects,
    u_star_drops,
    u_star_drops_pending,
)
from brawl.Currency.dropcard import draw_mega_box, draw_star_drop
from brawl.Currency.helper import (
    MAIN_GUILD_ID,
    MEGA_BOX_EMOTE,
    NO_EMOTE,
    STAR_DROP_EMOTE,
    STORE_ITEMS,
)
from brawl.Currency.home import background
from brawl.Currency.ladder import locked
from brawl.Currency.panel import notice

OWNER = 692254240290242601
RARITIES = list(STAR_DROP_RATES["rarity_rates"])
STEP_CHANCE, JUMP_CHANCE = 0.4, 0.5
GACHA_ITEMS = ("star_drop", "star_drop_10", "mega_box", "mega_box_10")


def roll(odds):
    return random.choices(list(odds), list(odds.values()))[0]


def roll_rarity():
    return roll(STAR_DROP_RATES["rarity_rates"])


def roll_items():
    return roll(MEGA_BOX_ITEMS)


def new_drop(rarity):
    return {
        "final_rarity": rarity,
        "current_rarity": RARITIES[0],
        "upgrades_used": 0,
        "created_at": int(time.time()),
    }


def new_box(items):
    return {
        "total_items": items,
        "items_remaining": items,
        "rewards": [],
        "created_at": int(time.time()),
    }


def reward_of(saved):
    if isinstance(saved, dict):
        return saved
    amount = re.search(r"`([\d,]+)` (Beans|Tokens)", saved)
    if amount:
        return {
            "kind": amount[2].lower(),
            "amount": int(amount[1].replace(",", "")),
        }
    name = re.search(r"`([^`]+)`", saved)
    name = name[1] if name else "Effect item"
    item = next(
        (key for key, data in STORE_ITEMS.items() if data["name"] == name), None
    )
    return {"kind": "effect", "item": item, "name": name}


async def pay(user_id, kind, amount):
    await wallet.change(user_id, **{kind: amount}, reason="drop")
    return {"kind": kind, "amount": amount}


async def pay_drop(user_id, rarity):
    drops = STAR_DROP_RATES["drops"][rarity]
    drop = random.choices(drops, [drop.get("weight", 1) for drop in drops])[0]
    amount = drop.get("amount") or random.randint(*drop["range"])
    return await pay(user_id, drop["type"], amount)


async def give_effect(user_id, guild_id, skip=()):
    held = sync_shop_effects(user_id, operation="get") or {}
    free = [
        item
        for item, data in STORE_ITEMS.items()
        if item not in GACHA_ITEMS
        and item not in skip
        and data.get("duration", 0) > 0
        and not (
            held.get(item, {}).get("active")
            and held[item].get("expires_at", 0) >= time.time()
        )
    ]
    if not free:
        reward = await pay(user_id, "tokens", EFFECT_FALLBACK_TOKENS)
        return {**reward, "note": "in place of an effect item"}
    item = random.choice(free)
    await STORE_ITEMS[item]["effect"](user_id)
    if item == "freeze_thermometer":
        frozen = u_shop_effects(user_id, item).get()
        if frozen:
            sync_shop_effects(user_id, item, "set", frozen, guild_id)
    return {
        "kind": "effect",
        "item": item,
        "name": STORE_ITEMS[item]["name"],
        "note": "bonus effect item",
    }


def in_turn(handler):
    """Runs one press at a time, so fast taps cannot pay twice or redraw out of order."""

    @functools.wraps(handler)
    async def pressed(self, interaction, button):
        await interaction.response.defer()
        async with self.turn:
            await handler(self, interaction, button)

    return pressed


class OpenView(discord.ui.View):
    name = ""
    sessions = None

    def __init__(self, user, unopened):
        super().__init__(timeout=60)
        self.user, self.unopened, self.message = user, unopened, None
        self.turn = asyncio.Lock()
        old = self.sessions.get(user.id)
        if old:
            old.stop()
        self.sessions[user.id] = self
        self.refresh()

    def card(self):
        raise NotImplementedError

    async def file(self):
        return await render(self.card, name=self.name.lower().replace(" ", ""))

    def close(self):
        if self.sessions.get(self.user.id) is self:
            del self.sessions[self.user.id]

    async def interaction_check(self, interaction):
        if interaction.user.id == self.user.id:
            return True
        await interaction.response.send_message(
            embed=notice(f"{NO_EMOTE} This is not your {self.name}.", "bad"),
            ephemeral=True,
        )
        return False

    async def show(self, interaction):
        self.refresh()
        await interaction.edit_original_response(
            attachments=[await self.file()], view=self
        )

    async def on_timeout(self):
        self.close()
        self.clear_items()
        self.add_item(
            discord.ui.Button(
                label="Session ended",
                style=discord.ButtonStyle.secondary,
                emoji="<a:clock:1382887924273774754>",
                disabled=True,
            )
        )
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class StarDropView(OpenView):
    name = "Star Drop"
    sessions = active_sessions = {}

    def __init__(self, user, unopened, pending):
        self.load(pending)
        super().__init__(user, unopened)

    def load(self, pending):
        self.final_rarity = pending["final_rarity"]
        self.current_rarity = pending["current_rarity"]
        self.current_upgrades = pending["upgrades_used"]
        self.rewards = []
        self.is_unlocked = False

    def card(self):
        return draw_star_drop(
            {
                "background": background(self.user.id),
                "rarity": self.current_rarity,
                "upgrades": self.current_upgrades,
                "rewards": self.rewards,
                "unopened": self.unopened,
            }
        )

    def refresh(self):
        upgrade, unlock, following = self.children
        ready = self.current_upgrades >= DROP_UPGRADES
        upgrade.disabled = ready or self.is_unlocked
        unlock.disabled = not ready or self.is_unlocked
        following.disabled = not self.is_unlocked or self.unopened <= 0

    @discord.ui.button(
        label="Upgrade",
        style=discord.ButtonStyle.primary,
        emoji="<:Upgrade:1447684501735211239>",
    )
    @in_turn
    async def upgrade_button(self, interaction, button):
        if self.is_unlocked or self.current_upgrades >= DROP_UPGRADES:
            return await interaction.followup.send(
                embed=notice(f"{NO_EMOTE} This Star Drop has no upgrades left.", "bad"),
                ephemeral=True,
            )
        now, final = RARITIES.index(self.current_rarity), RARITIES.index(
            self.final_rarity
        )
        if self.current_upgrades == DROP_UPGRADES - 1:
            now = final
        elif now < final and random.random() < STEP_CHANCE:
            now = min(now + 1 + (random.random() < JUMP_CHANCE), final)
        self.current_rarity = RARITIES[now]
        self.current_upgrades += 1
        u_star_drops_pending(self.user.id).update(
            {
                "current_rarity": self.current_rarity,
                "upgrades_used": self.current_upgrades,
            }
        )
        await self.show(interaction)

    @discord.ui.button(
        label="Unlock",
        style=discord.ButtonStyle.success,
        emoji="<a:unlocked:1390755948926079037>",
    )
    @in_turn
    async def unlock_button(self, interaction, button):
        if self.current_upgrades < DROP_UPGRADES:
            return await interaction.followup.send(
                embed=notice(
                    f"{NO_EMOTE} Use all {DROP_UPGRADES} upgrades first.", "bad"
                ),
                ephemeral=True,
            )
        if self.is_unlocked:
            return await interaction.followup.send(
                embed=notice(f"{NO_EMOTE} This Star Drop is already open.", "bad"),
                ephemeral=True,
            )
        self.is_unlocked = True
        u_star_drops_pending(self.user.id).delete()
        rarity = self.current_rarity = self.final_rarity
        self.rewards = [await pay_drop(self.user.id, rarity)]
        if random.random() < DROP_BONUS.get(rarity, 0):
            self.rewards.append(await give_effect(self.user.id, interaction.guild.id))
        if self.unopened <= 0:
            self.close()
        await self.show(interaction)

    @discord.ui.button(
        label="Open Next",
        style=discord.ButtonStyle.grey,
        emoji=STAR_DROP_EMOTE,
        disabled=True,
    )
    @in_turn
    async def next_button(self, interaction, button):
        held = u_star_drops(self.user.id).get() or 0
        if not self.is_unlocked or held <= 0:
            self.unopened = max(held, 0)
            return await self.show(interaction)
        pending = new_drop(roll_rarity())
        db.reference().update(
            {
                u_star_drops_pending(self.user.id).path: pending,
                u_star_drops(self.user.id).path: held - 1,
            }
        )
        self.unopened = held - 1
        self.load(pending)
        await self.show(interaction)


class MegaBoxView(OpenView):
    name = "Mega Box"
    sessions = active_sessions = {}

    def __init__(self, user, unopened, pending):
        self.load(pending)
        super().__init__(user, unopened)

    def load(self, pending):
        self.total_items = pending["total_items"]
        self.created_at = pending.get("created_at", int(time.time()))
        self.rewards = [reward_of(saved) for saved in pending.get("rewards") or []]
        self.rewards = self.rewards[: self.total_items - pending["items_remaining"]]

    @property
    def items_remaining(self):
        return self.total_items - len(self.rewards)

    @property
    def show_summary(self):
        return self.items_remaining <= 0

    def card(self):
        return draw_mega_box(
            {
                "background": background(self.user.id),
                "total": self.total_items,
                "rewards": self.rewards,
                "unopened": self.unopened,
            }
        )

    def refresh(self):
        tap, following = self.children
        tap.disabled = self.show_summary
        following.disabled = not self.show_summary or self.unopened <= 0

    async def reveal(self, guild_id):
        if len(self.rewards) < MEGA_BOX_BASE:
            reward = await pay_drop(self.user.id, roll(MEGA_BOX_BASE_RARITY))
        else:
            prize = roll(MEGA_BOX_EXTRA)
            if prize == "effect":
                given = [reward.get("item") for reward in self.rewards]
                reward = await give_effect(self.user.id, guild_id, given)
            else:
                reward = await pay(self.user.id, "tokens", prize)
        self.rewards.append(reward)
        if self.show_summary:
            u_mega_boxes_pending(self.user.id).delete()
            if self.unopened <= 0:
                self.close()
        else:
            u_mega_boxes_pending(self.user.id).set(self.pending())

    def pending(self):
        return {
            "total_items": self.total_items,
            "items_remaining": self.items_remaining,
            "rewards": self.rewards,
            "created_at": self.created_at,
        }

    @discord.ui.button(
        label="Tap",
        style=discord.ButtonStyle.primary,
        emoji="<:v_hand:1486225684928921763>",
    )
    @in_turn
    async def tap_button(self, interaction, button):
        if self.show_summary:
            return await interaction.followup.send(
                embed=notice(f"{NO_EMOTE} This Mega Box is empty.", "bad"),
                ephemeral=True,
            )
        await self.reveal(interaction.guild.id)
        await self.show(interaction)

    @discord.ui.button(
        label="Open Next",
        style=discord.ButtonStyle.grey,
        emoji=MEGA_BOX_EMOTE,
        disabled=True,
    )
    @in_turn
    async def next_button(self, interaction, button):
        held = u_mega_boxes(self.user.id).get() or 0
        if not self.show_summary or held <= 0:
            self.unopened = max(held, 0)
            return await self.show(interaction)
        u_mega_boxes(self.user.id).set(held - 1)
        self.unopened = held - 1
        self.load(new_box(roll_items()))
        await self.reveal(interaction.guild.id)
        await self.show(interaction)


class Gacha(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    def _roll_rarity(self):
        return roll_rarity()

    async def blocked(self, interaction, station, view, held, pending):
        if interaction.guild.id != MAIN_GUILD_ID:
            await interaction.response.send_message(
                embed=notice("This command can only be used in Brawl Cafe."),
                ephemeral=True,
            )
            return True
        if await locked(interaction, station):
            return True
        # A session left open is ended here, so a stuck message never blocks a new one.
        old = view.sessions.get(interaction.user.id)
        if old:
            async with old.turn:
                old.stop()
                await old.on_timeout()
        if held <= 0 and not pending:
            await interaction.response.send_message(
                embed=notice(
                    (
                        f"{NO_EMOTE} You have no {view.name}es. Buy one with {BUY}."
                        if view is MegaBoxView
                        else f"{NO_EMOTE} You have no {view.name}s. "
                        f"Buy one with {BUY}."
                    ),
                    "bad",
                ),
                ephemeral=True,
            )
            return True
        return False

    async def send(self, interaction, view):
        await interaction.response.send_message(file=await view.file(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(
        name="stardrop", description="Open a Star Drop for a random reward"
    )
    async def stardrop(self, interaction: discord.Interaction):
        user = interaction.user
        held = u_star_drops(user.id).get() or 0
        pending = u_star_drops_pending(user.id).get()
        if pending and not all(
            key in pending
            for key in ("final_rarity", "current_rarity", "upgrades_used")
        ):
            u_star_drops_pending(user.id).delete()
            pending = None
        if await self.blocked(interaction, "drops", StarDropView, held, pending):
            return
        if not pending:
            rarity = self._roll_rarity()
            if user.id == OWNER:
                rarity = random.choice(RARITIES[-3:])
            pending = new_drop(rarity)
            held -= 1
            db.reference().update(
                {
                    u_star_drops_pending(user.id).path: pending,
                    u_star_drops(user.id).path: held,
                }
            )
        await self.send(interaction, StarDropView(user, held, pending))

    @app_commands.command(
        name="megabox", description="Open a Mega Box for several rewards"
    )
    async def megabox(self, interaction: discord.Interaction):
        user = interaction.user
        held = u_mega_boxes(user.id).get() or 0
        pending = u_mega_boxes_pending(user.id).get()
        if pending and not all(
            key in pending for key in ("total_items", "items_remaining")
        ):
            u_mega_boxes_pending(user.id).delete()
            pending = None
        if await self.blocked(interaction, "boxes", MegaBoxView, held, pending):
            return
        if pending:
            return await self.send(interaction, MegaBoxView(user, held, pending))
        items = random.randint(7, 10) if user.id == OWNER else roll_items()
        held -= 1
        u_mega_boxes(user.id).set(held)
        view = MegaBoxView(user, held, new_box(items))
        await view.reveal(interaction.guild.id)
        view.refresh()
        await self.send(interaction, view)


async def setup(bot):
    await bot.add_cog(Gacha(bot))

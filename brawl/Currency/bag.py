import time

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency import heat
from brawl.Currency.card import BACKGROUND, item_icon, render
from brawl.Currency.db import sync_sell_alarm, sync_shop_effects, u_bag, u_shop_effects
from brawl.Currency.helper import MAIN_GUILD_ID, NO_EMOTE, STORE_ITEMS
from brawl.Currency.itemcard import draw_bag, draw_started, lasts
from brawl.Currency.panel import notice

TIMED = tuple(item for item, data in STORE_ITEMS.items() if data.get("duration", 0) > 0)
USE = "/use"


def held(user_id):
    """The timed items waiting in the bag, in shop order."""
    bag = u_bag(user_id).get() or {}
    return [item for item in TIMED if bag.get(item)]


def keep(user_id, item):
    u_bag(user_id, item).set(True)


def running(user_id):
    """The effect items working for the member right now."""
    now = time.time()
    return {
        item: data
        for item, data in (u_shop_effects(user_id).get() or {}).items()
        if isinstance(data, dict)
        and data.get("active")
        and now < data.get("expires_at", 0)
        and not (item == "streak_insurance" and data.get("uses_remaining", 0) <= 0)
    }


def blocked(user_id, guild_id, item):
    """Why a held item cannot start now, if it cannot."""
    name = STORE_ITEMS[item]["name"]
    if item not in held(user_id):
        return f"You have no {name} in your bag."
    if item in running(user_id):
        return f"Your {name} is still running. Use this one when it ends."
    if item == "freeze_thermometer" and heat.freeze(guild_id):
        return "The thermometer is already frozen. Use this when it thaws."
    return None


async def start(bot, user_id, guild_id, item):
    """Takes the item out of the bag and starts its timer."""
    await STORE_ITEMS[item]["effect"](user_id)
    u_bag(user_id, item).delete()
    economy = bot.get_cog("CurrencySystem")
    if item == "sell_alarm":
        brew = await economy.get_active_brew(user_id)
        if brew:
            sync_sell_alarm(
                user_id,
                "set",
                {
                    "roast_type": brew.get("roast_type"),
                    "end_time": brew.get("end_time"),
                    "batch_id": brew.get("batch_id"),
                    "notified": False,
                },
                guild_id,
            )
    elif item == "freeze_thermometer":
        sync_shop_effects(
            user_id, item, "set", u_shop_effects(user_id, item).get(), guild_id
        )


def note(bot, item):
    """What the member should know before starting the item."""
    if item == "freeze_thermometer":
        return (
            f"Thermometer is at {int(bot.get_cog('CurrencySystem').thermometer_heat)}"
        )
    return f"Lasts {lasts(STORE_ITEMS[item]['duration'])}"


async def use(interaction, item):
    """Starts a held item and shows it in place of the message the press came from."""
    user_id, guild_id = interaction.user.id, interaction.guild.id
    reason = blocked(user_id, guild_id, item)
    if reason:
        return await interaction.response.send_message(
            embed=notice(f"{NO_EMOTE} {reason}", "bad"), ephemeral=True
        )
    await start(interaction.client, user_id, guild_id, item)
    started = {
        "icon": item_icon(item),
        "name": STORE_ITEMS[item]["name"],
        "lasts": lasts(STORE_ITEMS[item]["duration"]),
        "heat": (
            int(interaction.client.get_cog("CurrencySystem").thermometer_heat)
            if item == "freeze_thermometer"
            else None
        ),
    }
    await interaction.response.edit_message(
        attachments=[await render(draw_started, started, name="started")],
        embed=None,
        view=None,
    )


class UseNow(discord.ui.View):
    """Under a purchase: start the item without opening the bag."""

    def __init__(self, user_id, item):
        super().__init__(timeout=300)
        self.user_id, self.item = user_id, item

    @discord.ui.button(label="Use now", style=discord.ButtonStyle.success)
    async def use_now(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                embed=notice(f"{NO_EMOTE} This is not your item.", "bad"),
                ephemeral=True,
            )
        await use(interaction, self.item)


class BagSelect(discord.ui.Select):
    def __init__(self, bot, items):
        super().__init__(
            placeholder="Pick an item to use",
            options=[
                discord.SelectOption(
                    label=STORE_ITEMS[item]["name"],
                    value=item,
                    description=note(bot, item),
                )
                for item in items
            ],
        )

    async def callback(self, interaction):
        await use(interaction, self.values[0])


class BagView(discord.ui.View):
    def __init__(self, bot, items):
        super().__init__(timeout=300)
        self.add_item(BagSelect(bot, items))


class Bag(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="use", description="Use an effect item from your bag")
    async def use(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                embed=notice("This command can only be used in Brawl Cafe."),
                ephemeral=True,
            )
        user_id = interaction.user.id
        items = held(user_id)
        if not items:
            return await interaction.response.send_message(
                embed=notice(
                    "Your bag is empty. Effect items from the shop, Star Drops "
                    "and Mega Boxes wait here until you use them."
                ),
                ephemeral=True,
            )
        bag = {"background": BACKGROUND, "items": items}
        await interaction.response.send_message(
            file=await render(draw_bag, bag, name="bag"),
            view=BagView(self.bot, items),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Bag(bot))

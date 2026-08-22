import discord
import datetime
import re

from discord import app_commands
from discord.ext import commands

from brawl.Currency.helper import YES_EMOTE, NO_EMOTE

@app_commands.context_menu(name="Effortful Message")
@commands.is_owner()
async def effortful_message(interaction: discord.Interaction, message: discord.Message):
    bot: commands.Bot = interaction.client  # type: ignore
    currency_cog = bot.get_cog("CurrencySystem")
    if not currency_cog:
        await interaction.response.send_message("❌ CurrencySystem cog not loaded.", ephemeral=True)
        return

    is_effortful, log = currency_cog.chat_system.is_effortful_message(message.content, message.author.id)
    title = f"**Effortful:** {YES_EMOTE}" if is_effortful else f"**Effortful:** {NO_EMOTE}"
    await interaction.response.send_message(
        f"## {title}\n> {log}",
        ephemeral=True
    )

async def setup(bot: commands.Bot) -> None:
    bot.tree.add_command(effortful_message)
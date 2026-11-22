import asyncio
import io

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency.helper import MAIN_GUILD_ID, NO_EMOTE
from brawl.Currency.howcard import PAGES
from brawl.Currency.panel import notice


async def page_file(topic):
    """The page is the same for everyone, so it is drawn once and kept."""
    data = await asyncio.to_thread(PAGES[topic][1])
    return discord.File(io.BytesIO(data), f"{topic}.jpg")


class TopicSelect(discord.ui.Select):
    def __init__(self, topic):
        super().__init__(
            placeholder="Pick a topic",
            custom_id="how_topic",
            options=[
                discord.SelectOption(label=name, value=key, default=key == topic)
                for key, (name, _) in PAGES.items()
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        topic = self.values[0]
        await interaction.response.edit_message(
            attachments=[await page_file(topic)], view=HowView(topic)
        )


class HowView(discord.ui.View):
    def __init__(self, topic="start"):
        super().__init__(timeout=None)
        self.add_item(TopicSelect(topic))


class How(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(HowView())

    @app_commands.command(name="how", description="See how the cafe works, with every number")
    @app_commands.describe(topic="The page to open")
    @app_commands.choices(
        topic=[app_commands.Choice(name=name, value=key) for key, (name, _) in PAGES.items()]
    )
    async def how(
        self, interaction: discord.Interaction, topic: app_commands.Choice[str] = None
    ):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                embed=notice(f"{NO_EMOTE} The cafe is only open in Brawl Stars Cafe.", "bad"),
                ephemeral=True,
            )
        topic = topic.value if topic else "start"
        await interaction.response.send_message(
            file=await page_file(topic), view=HowView(topic), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(How(bot))

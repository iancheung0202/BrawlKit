from typing import Optional
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency.helper import FREEBIES
from brawl.Currency.panel import notice
from brawl.Utility.style import GOLD, NO, YES


def claim(game: str, title: str, link: str, image: str = None):
    """The post for a freebie: what it is, and a button that opens it."""
    embed = discord.Embed(title=title, color=GOLD)
    embed.description = f"-# Free in {game}. Tap Claim to get it."
    if image:
        embed.set_image(url=f"attachment://{image}")
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Claim", url=link))
    return embed, view


class Freebie(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="freebie", description="Post a free reward to claim")
    @app_commands.describe(
        game="The game it is for",
        title="What members get, like 1x Thunder Frogs Box",
        link="The claim link",
        image="A picture to show under it",
    )
    @app_commands.choices(
        game=[app_commands.Choice(name=game, value=game) for game in FREEBIES]
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def freebie(
        self,
        interaction: discord.Interaction,
        game: str,
        title: app_commands.Range[str, 1, 200],
        link: str,
        image: Optional[discord.Attachment] = None,
    ) -> None:
        channel_id, role = FREEBIES[game]
        channel = interaction.guild.get_channel(channel_id)
        where = urlparse(link.strip())
        if channel is None or where.scheme != "https" or not where.netloc:
            await interaction.response.send_message(
                embed=notice(f"{NO} The link has to start with `https://`.", "bad"),
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        embed, view = claim(game, title, link.strip(), image and image.filename)
        sent = await channel.send(
            content=f"<@&{role}>",
            embed=embed,
            view=view,
            files=[await image.to_file()] if image else [],
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        if channel.is_news():
            try:
                await sent.publish()
            except discord.HTTPException:
                pass
        await interaction.followup.send(
            embed=notice(f"{YES} Posted in {channel.mention}.", "good"), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Freebie(bot))

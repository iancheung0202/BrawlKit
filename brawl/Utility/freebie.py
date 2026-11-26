import asyncio
import io
from typing import Optional
from urllib.parse import urlparse

import discord
import qrcode
from discord import app_commands
from discord.ext import commands

from brawl.Currency.helper import FREEBIES
from brawl.Currency.panel import notice
from brawl.Utility.style import GOLD, NO, YES


def code(link: str) -> bytes:
    """A QR code for the link, as a PNG that is never saved anywhere."""
    made = io.BytesIO()
    qrcode.make(link, box_size=8, border=3).save(made, format="PNG")
    return made.getvalue()


class ClaimView(discord.ui.View):
    """Under a freebie: Claim opens the link, and the QR code is for a phone."""

    def __init__(self, link: str = None):
        super().__init__(timeout=None)
        if link:
            self.remove_item(self.show)
            self.add_item(discord.ui.Button(label="Claim", url=link))
            self.add_item(self.show)

    @discord.ui.button(
        label="Show QR Code", style=discord.ButtonStyle.grey, custom_id="freebie_qr"
    )
    async def show(self, interaction: discord.Interaction, button: discord.ui.Button):
        links = [
            item.url
            for row in interaction.message.components
            for item in getattr(row, "children", [])
            if getattr(item, "url", None)
        ]
        if not links:
            await interaction.response.send_message(
                embed=notice(f"{NO} This freebie has no link.", "bad"), ephemeral=True
            )
            return
        picture = await asyncio.to_thread(code, links[0])
        embed = discord.Embed(
            description="Scan it with your phone to claim.", color=GOLD
        )
        embed.set_image(url="attachment://qr.png")
        await interaction.response.send_message(
            embed=embed,
            file=discord.File(io.BytesIO(picture), "qr.png"),
            ephemeral=True,
        )


def claim(game: str, title: str, link: str, image: str = None):
    """The post for a freebie: what it is, and the buttons that open it."""
    embed = discord.Embed(title=title, color=GOLD)
    embed.description = f"-# Free in {game}. Tap Claim to get it."
    if image:
        embed.set_image(url=f"attachment://{image}")
    return embed, ClaimView(link)


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
    bot.add_view(ClaimView())
    await bot.add_cog(Freebie(bot))

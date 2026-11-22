import datetime
import re

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View
from firebase_admin import db

from brawl.TeamFinder.reputationSystem import ReputationView, status_embed
from brawl.Utility.api import clean_tag, get_stats
from brawl.Utility.profile import get_ranked_tier
from brawl.Utility.style import NO, YES

CONFIGS = "/Team Find"
PANELS = "/Team Find Sticky Panel"
TAGS = "/Team Find Player Tag"
REGIONS = {
    "NA": ("North America", 0x6161F9),
    "EU": ("Europe", 0x50C450),
    "Asia": ("Asia", 0xF96262),
    "SA": ("South America", 0xF7D31A),
    "AU": ("Australia", 0x9B59B6),
}
TOOLS = "<a:tools:1390756351952687154>"
SETUP = "</teamfind setup:1390732384294408208>"
PANEL = "</teamfind panel:1390732384294408208>"
DISABLE = "</teamfind disable:1390732384294408208>"
INVITE = "https://link.brawlstars.com/invite/gameroom/en/?tag={}"
CLAIMED = "Claimed By"


def find(path: str, field: str, value: int):
    for key, entry in (db.reference(path).get() or {}).items():
        if entry[field] == value:
            return key, entry
    return None, None


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def get_requester(message: discord.Message):
    match = re.search(r"<@(\d+)>", message.content)
    return int(match.group(1)) if match else None


def get_field(embed: discord.Embed, name: str):
    for index, field in enumerate(embed.fields):
        if field.name.startswith(name):
            return index, field.value
    return None, ""


def get_remaining(embed: discord.Embed) -> int:
    match = re.search(r"\((\d+) More Player", embed.description)
    return int(match.group(1)) if match else 0


def needed(count: int) -> str:
    if count == 0:
        return "(Team Full!)"
    return f"({count} More Player{'s' if count != 1 else ''} Needed)"


async def move_panel(channel: discord.TextChannel):
    key, entry = find(PANELS, "Channel ID", channel.id)
    if not key:
        return
    ref = db.reference(PANELS).child(key)
    try:
        old = await channel.fetch_message(entry["Message ID"])
    except discord.NotFound:
        ref.delete()
        return
    await old.delete()
    new = await channel.send(
        old.content, embed=old.embeds[0] if old.embeds else None, view=PanelView()
    )
    ref.update({"Message ID": new.id})


class RequestModal(Modal):
    tag = TextInput(label="Your Player Tag", placeholder="#9L00JQRGR", max_length=15)
    category = TextInput(
        label="Category",
        placeholder="e.g. Trophies, Ranked, Challenge, etc.",
        max_length=20,
    )
    mode = TextInput(
        label="Game Mode",
        placeholder="e.g. Showdown, Brawl Ball, Hot Zone, etc.",
        max_length=20,
    )
    code = TextInput(
        label="Team Code", placeholder="Enter team join code", max_length=10
    )
    players = TextInput(
        label="Players Needed",
        placeholder="Default: 2",
        required=False,
        default="2",
        max_length=1,
    )

    def __init__(self, region: str, tag: str):
        super().__init__(title=f"Find Teammates - {region}")
        self.region = region
        self.tag.default = tag

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        tag = clean_tag(self.tag.value)
        stats = await get_stats(tag)
        if not stats:
            await interaction.followup.send(
                f"{NO} Failed to fetch profile for player tag {tag}. Please check the tag and try again."
            )
            return
        db.reference(TAGS).child(str(interaction.user.id)).update(
            {"Player Tag": tag[1:]}
        )
        _, config = find(CONFIGS, "Server ID", interaction.guild.id)
        channel = interaction.guild.get_channel(config["Channel ID"])
        if not channel:
            await interaction.followup.send(
                f"{NO} The team finder channel for this server (<#{config['Channel ID']}>) could not be found. It may have been deleted or the bot cannot see it. Please use `/teamfind setup` to set a new one if needed."
            )
            return
        name, color = REGIONS[self.region]
        players = max(int(self.players.value), 1) if self.players.value.isdigit() else 2
        category, mode = self.category.value, self.mode.value
        embed = discord.Embed(
            description=f"### {name} Team Request {needed(players)}\n-# - Coordinate with each other in the **thread** below\n-# - Click on **`Claim`** if you're 100% joining the team. \n-# - If you are the requester and **no longer need teammates**, press **`Close`**.",
            color=color,
            timestamp=now(),
        )
        embed.add_field(
            name="Player Tag",
            value=f"> [{tag}](https://brawlify.com/stats/profile/{tag[1:]})",
        )
        if "ranked" in f"{category} {mode}".lower():
            embed.add_field(
                name="Ranked",
                value=f"> {get_ranked_tier(stats.get('rankedPoints', 0))}",
            )
        else:
            embed.add_field(
                name="Trophies",
                value=f"> <:trophies:1341985600567251015> `{stats.get('trophies', 'N/A')}`",
            )
        embed.add_field(
            name="Brawlers Unlocked",
            value=f"> <a:unlocked:1390755948926079037> `{len(stats.get('brawlers', []))}`",
        )
        embed.add_field(name="Category", value=f"> {category}")
        embed.add_field(name="Game Mode", value=f"> {mode}")
        embed.add_field(name="Team Code", value=f"> {self.code.value.strip()}")
        icon = interaction.guild.icon
        embed.set_footer(
            text=interaction.guild.name, icon_url=icon.url if icon else None
        )
        role = interaction.guild.get_role(config[f"{self.region} Helper Role ID"])
        message = await channel.send(
            f"**{TOOLS} {interaction.user.mention} is requesting for teammates** - {role.mention if role else self.region}",
            embed=embed,
            view=RequestView(),
        )
        await message.create_thread(
            name=f"{interaction.user.name} - {name} Team Request",
            auto_archive_duration=1440,
        )
        await move_panel(interaction.channel)
        await interaction.followup.send(
            f"{YES} [Team Request Sent]({message.jump_url})"
        )


class RequestView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim", style=discord.ButtonStyle.green, custom_id="claim_team"
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = interaction.message
        embed = message.embeds[0]
        index, value = get_field(embed, CLAIMED)
        claims = [int(id) for id in re.findall(r"<@(\d+)>", value)]
        remaining = get_remaining(embed)
        if interaction.user.id == get_requester(message):
            error = "You want to help yourself? :joy:"
        elif interaction.user.id in claims:
            error = f"{NO} You've already joined this team."
        elif remaining == 0:
            error = f"{NO} The team is full!"
        else:
            error = None
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        claims.append(interaction.user.id)
        remaining -= 1
        embed.description = re.sub(
            r"\(.*?\)", needed(remaining), embed.description, count=1
        )
        if index is not None:
            embed.remove_field(index)
        embed.add_field(
            name=f"{CLAIMED} `({len(claims)}/{len(claims) + remaining})`",
            value="\n".join(f"- <@{id}>" for id in claims),
            inline=False,
        )
        view = RequestView()
        view.claim.disabled = remaining == 0
        code = get_field(embed, "Team Code")[1].replace("> ", "").strip()
        if code:
            view.add_item(
                Button(
                    label="Join Team",
                    style=discord.ButtonStyle.link,
                    url=INVITE.format(code),
                )
            )
        await interaction.response.edit_message(embed=embed, view=view)
        thread = await interaction.guild.fetch_channel(message.id)
        await thread.send(f"{interaction.user.mention} claimed the team request!")
        await interaction.followup.send(
            f"{YES} You have claimed the team request! Discuss in {thread.mention}",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Close", style=discord.ButtonStyle.red, custom_id="close_team"
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = interaction.message
        if (
            interaction.user.id != get_requester(message)
            and not interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                f"{NO} This is not your team request!", ephemeral=True
            )
            return
        content = re.sub(
            r"is requesting for.*", f"no longer needs teammates. {YES}", message.content
        )
        await interaction.response.edit_message(
            content=content.replace("**", "").replace(TOOLS, ""), view=ClosedView()
        )


class ClosedView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            Button(
                label="Team Request Closed",
                style=discord.ButtonStyle.grey,
                custom_id="closed_team",
                disabled=True,
            )
        )


class RegionButton(Button):
    def __init__(self, region: str):
        super().__init__(
            label=region,
            style=discord.ButtonStyle.blurple,
            custom_id=f"{region.lower()}_teamfind",
        )
        self.region = region

    async def callback(self, interaction: discord.Interaction):
        key, _ = find(CONFIGS, "Server ID", interaction.guild.id)
        if not key:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Team Finder not enabled!",
                    description=f"This server doesn't have the team finder system enabled yet. Please ask the server admin to use {SETUP} to setup the system!",
                    color=discord.Color.red(),
                    timestamp=now(),
                ),
                ephemeral=True,
            )
            return
        saved = db.reference(TAGS).child(str(interaction.user.id)).get() or {}
        await interaction.response.send_modal(
            RequestModal(self.region, saved.get("Player Tag"))
        )


class PanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        for region in REGIONS:
            self.add_item(RegionButton(region))


@app_commands.guild_only()
class TeamFind(commands.GroupCog, name="teamfind"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        if interaction.response.is_done():
            await interaction.followup.send(f"```{error}```", ephemeral=True)
        else:
            await interaction.response.send_message(f"```{error}```", ephemeral=True)

    @app_commands.command(
        name="disable", description="Disable team finder system in this server"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction):
        key, _ = find(CONFIGS, "Server ID", interaction.guild.id)
        if not key:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="We could not find your server",
                    description="Maybe you have already disabled the team finder in your server, or you have never enabled it.",
                    color=discord.Color.red(),
                    timestamp=now(),
                ),
                ephemeral=True,
            )
            return
        db.reference(CONFIGS).child(key).delete()
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Team Finder system successfully disabled",
                description=f"You can use {SETUP} at anytime to setup the system again.",
                color=discord.Color.yellow(),
                timestamp=now(),
            )
        )

    @app_commands.command(
        name="panel", description="Creates a customized team finder panel"
    )
    @app_commands.describe(
        is_sticky_panel="Want the panel to always be the last message in this channel?",
        message="The content of the message",
        title="Makes the title of the embed",
        description="Makes the description of the embed",
        color="Sets the color of the embed",
        thumbnail="Please provide a URL for the thumbnail of the embed (upper-right hand corner image)",
        image="Please provide a URL for the image of the embed (appears at the bottom of the embed)",
        footer="Sets the footer of the embed that appears at the bottom of the embed as small texts",
        footer_icon="Shows server icon in the footer of the embed? (Must have footer text first)",
        footer_time="Shows the time of the embed being sent?",
    )
    @app_commands.checks.bot_has_permissions(
        create_public_threads=True, send_messages_in_threads=True
    )
    @app_commands.checks.has_permissions(manage_messages=True, manage_guild=True)
    async def panel(
        self,
        interaction: discord.Interaction,
        is_sticky_panel: bool,
        message: str = None,
        title: str = None,
        description: str = None,
        color: str = None,
        thumbnail: str = None,
        image: str = None,
        footer: str = None,
        footer_icon: str = None,
        footer_time: bool = None,
    ):
        embed = None
        if title or description or thumbnail or image or footer:
            try:
                color = discord.Color.from_str(color)
            except (TypeError, ValueError):
                color = discord.Color.default()
            icon = interaction.guild.icon if footer_icon else None
            embed = discord.Embed(title=title, description=description, color=color)
            embed.set_thumbnail(url=thumbnail)
            embed.set_image(url=image)
            embed.set_footer(text=footer, icon_url=icon.url if icon else None)
            if footer_time:
                embed.timestamp = now()
        sent = await interaction.channel.send(message, embed=embed, view=PanelView())
        sticky = ""
        if is_sticky_panel:
            key, entry = find(PANELS, "Channel ID", interaction.channel.id)
            if key:
                db.reference(PANELS).child(key).delete()
                try:
                    old = await interaction.channel.fetch_message(entry["Message ID"])
                    await old.delete()
                except discord.NotFound:
                    pass
            db.reference(PANELS).push().set(
                {"Channel ID": interaction.channel.id, "Message ID": sent.id}
            )
            sticky = "This panel will now always be the last message in the channel."
        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"**{YES} Custom Team Finder Panel Sent!** {sticky} \n\n*Sent in the wrong channel? Delete the panel and use {PANEL} in the correct channel!*",
                color=discord.Color.green(),
                timestamp=now(),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="setup", description="Setup team finder system in the server"
    )
    @app_commands.describe(
        channel="The channel for all team requests",
        na_helper_role="NA Helper role",
        eu_helper_role="EU Helper role",
        asia_helper_role="Asia Helper role",
        sa_helper_role="SA Helper role",
        au_helper_role="AU Helper role",
    )
    @app_commands.checks.bot_has_permissions(
        create_public_threads=True, send_messages_in_threads=True, manage_channels=True
    )
    @app_commands.checks.has_permissions(manage_messages=True, manage_guild=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        na_helper_role: discord.Role,
        eu_helper_role: discord.Role,
        asia_helper_role: discord.Role,
        sa_helper_role: discord.Role,
        au_helper_role: discord.Role,
    ):
        _, config = find(CONFIGS, "Server ID", interaction.guild.id)
        if config:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Team Finder System already enabled!",
                    description=f"Your team finder channel is already set as <#{config['Channel ID']}> `({config['Channel ID']})`\n\nPlease use {PANEL} to create your team finder panel.\n\nIf you wish to disable the system, please use {DISABLE}.",
                    color=discord.Color.red(),
                    timestamp=now(),
                ),
                ephemeral=True,
            )
            return
        db.reference(CONFIGS).push().set(
            {
                "Server Name": interaction.guild.name,
                "Server ID": interaction.guild.id,
                "Channel ID": channel.id,
                "NA Helper Role ID": na_helper_role.id,
                "EU Helper Role ID": eu_helper_role.id,
                "Asia Helper Role ID": asia_helper_role.id,
                "SA Helper Role ID": sa_helper_role.id,
                "AU Helper Role ID": au_helper_role.id,
            }
        )
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Team Finder System Enabled Successfully!",
                description=(
                    f"- The team request channel has been set to {channel.mention} `({channel.id})`.\n"
                    "- **By default, all administrators can close any team requests for moderation purposes.**\n"
                    f"- To create your team finder panel, please use {PANEL}.\n"
                    f"- **Tip:** Make sure members cannot type in {channel.mention}. The system works best if only the bot is able to send messages in that channel."
                ),
                color=discord.Color.green(),
                timestamp=now(),
            )
        )

    @app_commands.command(
        name="reputation",
        description="Enable, manage, or disable reputation system in the server",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reputation(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=status_embed(interaction.guild.id),
            view=ReputationView(),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TeamFind(bot))

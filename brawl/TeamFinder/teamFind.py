import re
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, Modal, Select, TextInput, View
from firebase_admin import db

from brawl.Currency.card import faces, render, roster
from brawl.Currency.config import REP_TOKENS
from brawl.Currency.helper import MAIN_GUILD_ID, TOKEN_EMOTE
from brawl.Currency.home import background
from brawl.Currency.panel import notice
from brawl.Milestone.milestone import in_cafe
from brawl.TeamFinder.reputationSystem import (
    LIKE,
    ReputationView,
    add_rep,
    get_totals,
    status_embed,
    thank,
)
from brawl.Utility import api
from brawl.Utility.playercard import draw_request, face, league_art
from brawl.Utility.profile import linked, show_profile
from brawl.Utility.style import NO, YES

CONFIG = f"/Team Find/{MAIN_GUILD_ID}"
PANELS = "/Team Find Sticky Panel"
TAGS = "/Team Find Player Tag"
REQUESTS = "/Team Find Requests"
REGIONS = {
    "NA": "North America",
    "EU": "Europe",
    "Asia": "Asia",
    "SA": "South America",
    "AU": "Australia",
}
KINDS = ("Trophies", "Ranked", "Event")
# What the first tile of a card shows when no game mode was picked
KIND_ART = {"Ranked": "game/ranked", "Event": "kit/icon_event"}
# The stats a request card draws, kept with the request so a claim needs no lookup
KEPT = ("name", "nameColor", "icon", "club", "trophies", "ranked", "rankedPoints")
OPEN_FOR = 24 * 3600
TOOLS = "<a:tools:1390756351952687154>"
SETUP = "</teamfind setup:1390732384294408208>"
PANEL = "</teamfind panel:1390732384294408208>"
INVITE = "https://link.brawlstars.com/invite/gameroom/en/?tag={}"
OLD = f"{NO} This request is too old to join. Start a new one from the panel."


def find(path: str, field: str, value: int):
    for key, entry in (db.reference(path).get() or {}).items():
        if entry[field] == value:
            return key, entry
    return None, None


def get_config() -> dict:
    return db.reference(CONFIG).get() or {}


def get_request(message_id: int):
    return db.reference(REQUESTS).child(str(message_id)).get()


def get_requester(message: discord.Message):
    match = re.search(r"<@(\d+)>", message.content)
    return int(match.group(1)) if match else None


def left(request: dict) -> int:
    return request["seats"] - len(request.get("claims", []))


def closed_text(host_id: int) -> str:
    return f"<@{host_id}> no longer needs teammates. {YES}"


async def request_card(guild: discord.Guild, request: dict) -> discord.File:
    """Draws a request with its host first, then everyone who claimed a seat."""
    stats = request["stats"]
    rank = stats.get("ranked", 0)
    mode = f"/game-modes/regular/{request.get('mode_id')}.png"
    members = await roster(guild, [request["host"], *request.get("claims", [])])
    art = await api.images([league_art(rank), *([mode] if "mode" in request else [])])
    sheet = {
        "player": await face(request["tag"], stats),
        "label": f"{request['region'].upper()} TEAM",
        "background": background(request["host"]),
        "mode": request.get("mode", request["kind"]),
        "mode_art": art.get(mode) or KIND_ART[request["kind"]],
        "kind": request["kind"] if "mode" in request else "Any mode",
        "trophies": stats.get("trophies", 0),
        "ranked": (rank, stats.get("rankedPoints", 0)),
        "league_art": art[league_art(rank)],
        "seats": request["seats"],
        "faces": await faces(members),
        "open": request["open"],
    }
    return await render(draw_request, sheet, name="team")


async def close_request(message: discord.Message, request: dict):
    """Redraws a request as closed and forgets it."""
    request["open"] = False
    card = await request_card(message.guild, request)
    await message.edit(
        content=closed_text(request["host"]), attachments=[card], view=ClosedView()
    )
    db.reference(REQUESTS).child(str(message.id)).delete()


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


def start_embed(region: str) -> discord.Embed:
    embed = notice(
        "1. Pick what you are playing for.\n"
        "2. For Trophies, pick the game mode.\n"
        "3. Press **Continue** and enter your team code.\n"
        f"-# When you close the request, select who played. Each gets {LIKE} `1` rep "
        f"and {TOKEN_EMOTE} `{REP_TOKENS}`."
    )
    embed.title = f"Find teammates in {REGIONS[region]}"
    return embed


class RequestModal(Modal):
    def __init__(self, region: str, pick: dict, tag: str, saved: str):
        super().__init__(title=f"Find teammates in {region}")
        self.region, self.pick, self.linked = region, pick, tag
        self.code = TextInput(
            label="Team code", placeholder="The join code of your team", max_length=10
        )
        self.add_item(self.code)
        self.tag = TextInput(
            label="Your player tag",
            placeholder="#9L00JQRGR",
            default=saved,
            max_length=15,
        )
        if not tag:
            self.add_item(self.tag)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        tag = self.linked or api.clean_tag(self.tag.value)
        stats = await api.get_stats(tag)
        if not stats:
            await interaction.followup.send(
                embed=notice(
                    f"{NO} No player found for `{tag}`. Check the tag and try again.",
                    "bad",
                )
            )
            return
        if not self.linked:
            db.reference(TAGS).child(str(interaction.user.id)).update(
                {"Player Tag": tag[1:]}
            )
        config = get_config()
        channel = interaction.guild.get_channel(config.get("Channel ID", 0))
        if not channel:
            await interaction.followup.send(
                embed=notice(
                    f"{NO} The team finder channel is missing. Ask staff to run {SETUP}.",
                    "bad",
                )
            )
            return
        request = {
            "host": interaction.user.id,
            "tag": tag,
            "region": self.region,
            "code": self.code.value.strip(),
            "stats": {key: stats[key] for key in KEPT if stats.get(key) is not None},
            "open": True,
            "at": int(time.time()),
            **self.pick,
        }
        role = interaction.guild.get_role(
            config.get(f"{self.region} Helper Role ID", 0)
        )
        message = await channel.send(
            f"**{TOOLS} {interaction.user.mention} is looking for teammates** "
            f"{role.mention if role else self.region}",
            file=await request_card(interaction.guild, request),
            view=RequestView(request["code"]),
        )
        db.reference(REQUESTS).child(str(message.id)).set(request)
        await message.create_thread(
            name=f"{interaction.user.name} - {REGIONS[self.region]}",
            auto_archive_duration=1440,
        )
        await move_panel(channel)
        await interaction.followup.send(
            embed=notice(f"{YES} [Your request is up]({message.jump_url}).", "good")
        )


class StartView(View):
    """What a request is for, picked from menus before the team code is asked."""

    def __init__(self, region: str, modes: dict, tag: str, saved: str):
        super().__init__(timeout=300)
        self.region, self.modes, self.tag, self.saved = region, modes, tag, saved
        self.mode, self.kind, self.seats = None, "Trophies", 2
        self.mode_menu.options = [
            discord.SelectOption(label=name, value=str(mode_id))
            for mode_id, name in modes.items()
        ]
        self.refresh()

    def refresh(self):
        """The game mode is only asked for Trophies; Ranked and Events pick their own."""
        self.kind_menu.options = [
            discord.SelectOption(label=kind, default=kind == self.kind)
            for kind in KINDS
        ]
        self.seats_menu.options = [
            discord.SelectOption(
                label=f"{seats} teammate{'s' * (seats != 1)} needed",
                value=str(seats),
                default=seats == self.seats,
            )
            for seats in range(1, 5)
        ]
        for option in self.mode_menu.options:
            option.default = option.value == str(self.mode)
        self.clear_items()
        self.add_item(self.kind_menu)
        if self.kind == "Trophies":
            self.add_item(self.mode_menu)
        self.add_item(self.seats_menu)
        self.add_item(self.go)

    @discord.ui.select(placeholder="Playing for")
    async def kind_menu(self, interaction: discord.Interaction, select: Select):
        self.kind = select.values[0]
        self.refresh()
        await interaction.response.edit_message(view=self)

    @discord.ui.select(placeholder="Game mode")
    async def mode_menu(self, interaction: discord.Interaction, select: Select):
        self.mode = int(select.values[0])
        await interaction.response.defer()

    @discord.ui.select(placeholder="Teammates needed")
    async def seats_menu(self, interaction: discord.Interaction, select: Select):
        self.seats = int(select.values[0])
        await interaction.response.defer()

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.green)
    async def go(self, interaction: discord.Interaction, button: Button):
        pick = {"kind": self.kind, "seats": self.seats}
        if self.kind == "Trophies":
            if not self.mode:
                await interaction.response.send_message(
                    embed=notice(f"{NO} Pick a game mode first.", "bad"),
                    ephemeral=True,
                )
                return
            pick.update(mode_id=self.mode, mode=self.modes[self.mode])
        await interaction.response.send_modal(
            RequestModal(self.region, pick, self.tag, self.saved)
        )


class TeammatesView(View):
    """The host selects who really played, and each of them gets a rep."""

    def __init__(self, message: discord.Message, request: dict, members: list):
        super().__init__(timeout=300)
        self.message, self.request, self.played = message, request, []
        self.menu.options = [
            discord.SelectOption(label=member.display_name[:100], value=str(member.id))
            for member in members
        ]
        self.menu.max_values = len(members)

    @discord.ui.select(placeholder="Who played with you?", min_values=0)
    async def menu(self, interaction: discord.Interaction, select: Select):
        self.played = [int(value) for value in select.values]
        await interaction.response.defer()

    @discord.ui.button(label="Close request", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: Button):
        if not get_request(self.message.id):
            await interaction.response.edit_message(
                embed=notice(f"{NO} This request is already closed.", "bad"), view=None
            )
            return
        await interaction.response.edit_message(
            embed=notice(f"{YES} Request closed.", "good"), view=None
        )
        await close_request(self.message, self.request)
        lines = []
        for member in await roster(interaction.guild, self.played):
            result = await thank(member, self.request["host"]) if member else None
            if not result:
                continue
            tokens, roles = result
            line = f"{member.mention} earned {LIKE} `1` rep"
            line += f" and {TOKEN_EMOTE} `{tokens}`" if tokens else ""
            line += "".join(f", and the {role.mention} role" for role in roles)
            lines.append(line)
        if lines:
            thread = await interaction.guild.fetch_channel(self.message.id)
            await thread.send(
                "\n".join(lines), allowed_mentions=discord.AllowedMentions(roles=False)
            )


class RequestView(View):
    def __init__(self, code: str = None):
        super().__init__(timeout=None)
        if code:
            self.add_item(
                Button(
                    label="Join Team",
                    style=discord.ButtonStyle.link,
                    url=INVITE.format(code),
                )
            )

    @discord.ui.button(
        label="Claim", style=discord.ButtonStyle.green, custom_id="claim_team"
    )
    async def claim(self, interaction: discord.Interaction, button: Button):
        message = interaction.message
        request = get_request(message.id)
        claims = (request or {}).get("claims", [])
        if not request:
            error = OLD
        elif interaction.user.id == request["host"]:
            error = f"{NO} This is your own request."
        elif interaction.user.id in claims:
            error = f"{NO} You already joined this team."
        elif not left(request):
            error = f"{NO} The team is full."
        else:
            error = None
        if error:
            await interaction.response.send_message(
                embed=notice(error, "bad"), ephemeral=True
            )
            return
        await interaction.response.defer()
        request["claims"] = [*claims, interaction.user.id]
        db.reference(REQUESTS).child(str(message.id)).update(
            {"claims": request["claims"]}
        )
        view = RequestView(request["code"])
        view.claim.disabled = not left(request)
        await interaction.edit_original_response(
            attachments=[await request_card(interaction.guild, request)], view=view
        )
        thread = await interaction.guild.fetch_channel(message.id)
        await thread.send(f"{interaction.user.mention} joined the team.")

    @discord.ui.button(
        label="Profile", style=discord.ButtonStyle.grey, custom_id="profile_team"
    )
    async def profile(self, interaction: discord.Interaction, button: Button):
        request = get_request(interaction.message.id)
        if not request:
            await interaction.response.send_message(
                embed=notice(OLD, "bad"), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await show_profile(interaction, request["tag"], ephemeral=True)

    @discord.ui.button(
        label="Close", style=discord.ButtonStyle.red, custom_id="close_team"
    )
    async def close(self, interaction: discord.Interaction, button: Button):
        message = interaction.message
        request = get_request(message.id)
        host = request["host"] if request else get_requester(message)
        if (
            interaction.user.id != host
            and not interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                embed=notice(f"{NO} This is not your team request.", "bad"),
                ephemeral=True,
            )
            return
        if not request:
            await interaction.response.edit_message(
                content=closed_text(host), view=ClosedView()
            )
            return
        members = await roster(interaction.guild, request.get("claims", []))
        members = [member for member in members if member]
        if interaction.user.id != host or not members:
            await interaction.response.defer()
            await close_request(message, request)
            return
        await interaction.response.send_message(
            embed=notice(
                f"Select the teammates who played with you. Each gets {LIKE} `1` rep "
                f"and {TOKEN_EMOTE} `{REP_TOKENS}`."
            ),
            view=TeammatesView(message, request, members),
            ephemeral=True,
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
        if not await in_cafe(interaction):
            return
        if not get_config():
            await interaction.response.send_message(
                embed=notice(f"{NO} The team finder is not set up yet.", "bad"),
                ephemeral=True,
            )
            return
        saved = db.reference(TAGS).child(str(interaction.user.id)).get() or {}
        await interaction.response.send_message(
            embed=start_embed(self.region),
            view=StartView(
                self.region,
                await api.modes(),
                linked(interaction.user.id),
                saved.get("Player Tag"),
            ),
            ephemeral=True,
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
        self.expire.start()

    async def cog_unload(self):
        self.expire.cancel()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await in_cafe(interaction)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        if interaction.response.is_done():
            await interaction.followup.send(f"```{error}```", ephemeral=True)
        else:
            await interaction.response.send_message(f"```{error}```", ephemeral=True)

    @tasks.loop(minutes=10)
    async def expire(self):
        """Closes requests left open for a day, so the channel shows live ones."""
        channel = self.bot.get_channel(get_config().get("Channel ID", 0))
        for message_id, request in (db.reference(REQUESTS).get() or {}).items():
            if time.time() - request["at"] < OPEN_FOR:
                continue
            try:
                await close_request(
                    await channel.fetch_message(int(message_id)), request
                )
            except (AttributeError, discord.HTTPException):
                db.reference(REQUESTS).child(message_id).delete()

    @expire.before_loop
    async def ready(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="disable", description="Turn the team finder off")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(self, interaction: discord.Interaction):
        db.reference(CONFIG).delete()
        await interaction.response.send_message(
            embed=notice(f"{YES} Team finder is off. Use {SETUP} to turn it on again.")
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
                embed.timestamp = discord.utils.utcnow()
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
            sticky = " It will stay the last message in this channel."
        await interaction.response.send_message(
            embed=notice(f"{YES} Panel sent.{sticky}", "good"), ephemeral=True
        )

    @app_commands.command(
        name="setup", description="Set the team finder channel and roles"
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
        db.reference(CONFIG).set(
            {
                "Channel ID": channel.id,
                "NA Helper Role ID": na_helper_role.id,
                "EU Helper Role ID": eu_helper_role.id,
                "Asia Helper Role ID": asia_helper_role.id,
                "SA Helper Role ID": sa_helper_role.id,
                "AU Helper Role ID": au_helper_role.id,
            }
        )
        await interaction.response.send_message(
            embed=notice(
                f"{YES} Team requests now go to {channel.mention}. "
                f"Use {PANEL} to post the panel.",
                "good",
            )
        )

    @app_commands.command(
        name="reputation", description="See and edit the roles that rep earns"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reputation(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=status_embed(), view=ReputationView(), ephemeral=True
        )

    @app_commands.command(name="giverep", description="Add or take rep from a member")
    @app_commands.describe(
        user="Whose rep to change", amount="Rep to add, or a negative number to take"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giverep(
        self, interaction: discord.Interaction, user: discord.Member, amount: int
    ):
        roles = await add_rep(user, amount)
        earned = "".join(f" They earned {role.mention}." for role in roles)
        await interaction.response.send_message(
            embed=notice(
                f"{YES} {user.mention} now has {LIKE} "
                f"`{get_totals().get(user.id, 0)}` rep.{earned}",
                "good",
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TeamFind(bot))

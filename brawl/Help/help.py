import platform
import re

import discord
import firebase_admin
import psutil
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
from firebase_admin import db

from brawl.Utility.style import NO

REPLY = "<:reply:1036792837821435976>"
COLOR = 0x1DBCEB
INVITE = "https://discord.com/oauth2/authorize?client_id=1341929399913680968"
SUPPORT = "https://discord.gg/6sHxJBaszx"
ABOUT = "> <a:tools:1390756351952687154> BrawlKit is a powerful utility Discord bot **designed with all Brawl Stars communities in mind**, including **easy-to-use systems** like tickets, team finder, partnerships, welcomer, and in-game milestone roles."
NOT_AUTHOR = f"{NO} You are not the author of this command"
STAFF = "Staff"
PAGES = {
    "Utility Commands": (
        "🛠️",
        "Basic commands that everyone in the server can use.",
        {
            "": [
                "ping",
                "server",
                "user",
                "color",
                "topic",
                "embed",
                "editembed",
                "help",
            ]
        },
    ),
    "Tickets": (
        "🎫",
        "Set up and manage tickets. Start with {ticket settings}, then post a panel with {ticket button} or {ticket dropdown}.",
        {"": ["ticket"]},
    ),
    "Team Finder": (
        "🎮",
        "Let members look for teammates. Start with {teamfind setup} and the bot will guide you through it.",
        {"": ["teamfind"]},
    ),
    "Partnership Panels": (
        "🤝",
        "Manage your server's partnerships. A request opens a private thread like a ticket, and admins add or remove partners on auto-updating panels. Start with {partner setup}.",
        {"": ["partner"]},
    ),
    "Cafe": (
        "☕",
        "The Starr Beans economy, **in Brawl Stars Cafe** only.",
        {
            "Earn": ["brew", "sell", "thermometer"],
            "Spend": [
                "shop",
                "buy",
                "stardrop",
                "megabox",
                "rates",
                "redeem",
                "customize",
                "pin",
            ],
            "Play": ["blackjack", "coinflip", "table"],
            "Rank": ["balance", "leaderboard"],
            STAFF: [
                "add",
                "addinvites",
                "update-quest",
                "xp",
                "toggle-application",
            ],
        },
    ),
    "Welcomer": (
        "👋",
        "Greet new members in a channel with your own message. Start with {welcome settings}.",
        {"": ["welcome"]},
    ),
    "In-game Milestones Roles": (
        "👤",
        "Link Brawl Stars accounts and give roles for in-game milestones.",
        {"": ["profile", "verify", "milestone"]},
    ),
    "Booster Roles": (
        "💎",
        "Thank server boosters with a message and a custom role. Start with {boosterrole setup}.",
        {"": ["boosterrole"]},
    ),
}


def mention(found: dict, name: str) -> str:
    command = found.get(name.split(" ")[0])
    return f"</{name}:{command.id}>" if command else f"`/{name}`"


def entries(found: dict, names: list) -> str:
    lines = []
    for name in names:
        root, _, child = name.partition(" ")
        command = found.get(root)
        if not command:
            continue
        children = [
            option
            for option in command.options
            if option.type == discord.AppCommandOptionType.subcommand
            and child in ("", option.name)
        ]
        if not children:
            children = [command]
        for item in children:
            full = root if item is command else f"{root} {item.name}"
            lines.append(f"{mention(found, full)}\n{REPLY} {item.description}")
    return "\n\n".join(lines)


def page_embeds(found: dict, title: str, admin: bool) -> list:
    emoji, intro, groups = PAGES[title]
    for name in set(re.findall(r"{(.+?)}", intro)):
        intro = intro.replace(f"{{{name}}}", mention(found, name))
    embeds = [discord.Embed(title=f"{emoji} {title}", description=intro, color=COLOR)]
    for group, names in groups.items():
        if group == STAFF and not admin:
            continue
        text = entries(found, names)
        if text:
            embeds.append(
                discord.Embed(
                    title=group or None,
                    description=text,
                    color=discord.Color.blurple(),
                )
            )
    return embeds


def overview_embed() -> discord.Embed:
    embed = discord.Embed(title="BrawlKit Help", description=ABOUT, color=COLOR)
    embed.add_field(
        name="<:dev:1037445830749204624> Support Server",
        value=f"Head over to our **[support server]({SUPPORT})** if you have any suggestions, questions or bug reports! :writing_hand:",
    )
    embed.add_field(
        name="<:slash:1037445915348324505> Command Usage",
        value="This bot uses [slash commands](https://discord.com/blog/welcome-to-the-new-era-of-discord-apps). Type `/` or **select a category** below to see the list of available bot commands.",
    )
    return embed


def stats_embed(bot: commands.Bot) -> discord.Embed:
    memory = psutil.virtual_memory()
    uptime = next(iter(db.reference("/Vanity Uptime").get().values()))["Vanity Uptime"]
    embed = discord.Embed(
        title="BrawlKit Discord Bot Statistics <a:server:1366940847093841961>",
        color=COLOR,
    )
    embed.add_field(
        name="<:info:1037445870469267638> Package Info",
        value=f"```OS - {platform.system()}\nPython - {platform.python_version()}\ndiscord.py - {discord.__version__}\nGoogle Firebase - {firebase_admin.__version__}```",
        inline=False,
    )
    embed.add_field(
        name="<:dev:1037445830749204624>  Bot Metadata",
        value=f"> App ID: `{bot.application_id}`\n> Last Reboot: <t:{uptime}:R>\n> Servers Count: `{len(bot.guilds)}`\n> API/Bot Latency: `{round(bot.latency * 1000)}ms`",
    )
    embed.add_field(
        name="📊  Bot Process Data",
        value=f"> CPU Usage: `{psutil.cpu_percent(0.1)}%`\n> RAM Usage: `{memory.used / 1e9:.2f} GB`\n> Memory:  `{memory.used / 1024**3:.2f}/{memory.total / 1024**3:.2f} GB ({100 - memory.percent:.2f}%)`",
    )
    return embed


class PageSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Browse All Commands",
            options=[
                discord.SelectOption(label=title, emoji=page[0])
                for title, page in PAGES.items()
            ],
            custom_id="browsecommands",
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        await interaction.response.edit_message(
            embeds=page_embeds(view.found, self.values[0], view.admin), view=view
        )


class HelpPanel(View):
    def __init__(self, found: dict, author: discord.Member):
        super().__init__(timeout=300)
        self.found = found
        self.author = author
        self.admin = author.guild_permissions.administrator
        self.add_item(
            Button(label="Invite", url=INVITE, emoji="<a:robot:1366940845697400935>")
        )
        self.add_item(
            Button(
                label="Support Server",
                url=SUPPORT,
                emoji="<a:join:1366940843088543775>",
            )
        )
        self.add_item(PageSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user == self.author:
            return True
        await interaction.response.send_message(NOT_AUTHOR, ephemeral=True)
        return False

    async def on_timeout(self):
        for child in self.children:
            if not getattr(child, "url", None):
                child.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.NotFound:
            pass

    @discord.ui.button(
        label="Overview",
        style=discord.ButtonStyle.blurple,
        custom_id="overview",
        row=0,
        emoji="<a:memo:1366940844300701714>",
    )
    async def overview(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(embed=overview_embed(), view=self)

    @discord.ui.button(
        label="Statistics",
        style=discord.ButtonStyle.blurple,
        custom_id="statistics",
        row=0,
        emoji="<a:server:1366940847093841961>",
    )
    async def statistics(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            embed=stats_embed(interaction.client), view=self
        )


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="View all the bot's commands")
    @app_commands.guild_only()
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer()
        found = {
            command.name: command for command in await self.bot.tree.fetch_commands()
        }
        view = HelpPanel(found, interaction.user)
        view.message = await interaction.followup.send(
            embed=overview_embed(), view=view
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))

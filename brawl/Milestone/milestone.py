import asyncio
import random
import re

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View
from firebase_admin import db

from brawl.Currency.card import BACKGROUND, MUTED, render
from brawl.Currency.db import u_tag
from brawl.Currency.helper import MAIN_GUILD_ID, REPLY_EMOTE
from brawl.Currency.panel import notice
from brawl.Utility.api import clean_tag, get_icon, get_player, get_stats
from brawl.Utility.playercard import draw_milestones, face
from brawl.Utility.profile import keep_stats, linked
from brawl.Utility.style import NO, YES

ICON = "https://cdn.brawlify.com/profile-icons/regular/{}.png"
BANNER = "https://media.discordapp.net/attachments/791906307158048771/854639322765721600/En20201112_BS_2ndBday_Longimage.jpeg?ex=687417a4&is=6872c624&hm=43972185501ff389d021e9cb128c4397b27a1e3ce6efa65ad1184c810f0a0b71&"
COLOR = 0xFCCA50
ATTEMPTS = 30
DELAY = 10

YES_DIM = "<a:Yes_dimmed:1393015472676540436>"
WARN = "<a:warning:1391215594430402742>"
LOADING = "<a:loading:1026905298088243240>"
TOOLS = "<a:tools:1390756351952687154>"
TROPHY = "<:trophies:1341985600567251015>"
RANKED = "<a:ranked:1393007596872532139>"
FAME = "<a:global:1392272416797098045>"
SOLO = "<:solo:1341985978067451988>"
DUO = "<:duo:1341985494657142885>"
TRIO = "<:3v3:1341985474595655703>"

CATEGORIES = {
    "trophy": (f"{TROPHY} Trophies", "trophies"),
    "ranked": (f"{RANKED} Ranked (Highest)", "highestRankedPoints"),
    "fame": (f"{FAME} Fame", "famePoints"),
    "wins_solo": (f"{SOLO} Solo Wins", "soloVictories"),
    "wins_duo": (f"{DUO} Duo Wins", "duoVictories"),
    "wins_3v3": (f"{TRIO} 3v3 Wins", "3vs3Victories"),
}
# Category: (icon and name on the milestone card)
ROWS = {
    "trophy": ("game/trophies", "Trophies"),
    "ranked": ("game/ranked", "Best ranked"),
    "fame": ("game/fame", "Fame"),
    "wins_solo": ("game/solo", "Solo wins"),
    "wins_duo": ("game/duo", "Duo wins"),
    "wins_3v3": ("game/3v3", "3v3 wins"),
}
CONFIG = f"Brawl Milestone Roles/{MAIN_GUILD_ID}"
LEADERBOARD = "</leaderboard:1393376242501157006>"
MINE = "</milestone mine:1392998294732410990>"
PROFILE = "</profile:1341939588301590551>"
NOT_LINKED = f"{NO} You must verify and link your Brawl Stars account first."
FAILED = f"{WARN} Something went wrong. Please try again later."


async def in_cafe(interaction: discord.Interaction) -> bool:
    """Milestone roles belong to the cafe; anywhere else gets a short refusal."""
    if interaction.guild and interaction.guild.id == MAIN_GUILD_ID:
        return True
    await interaction.response.send_message(
        embed=notice(f"{NO} Not available here.", "bad"), ephemeral=True
    )
    return False


def get_config() -> dict:
    return db.reference(CONFIG).get() or {}


def set_config(config: dict):
    db.reference(CONFIG).set(config)


async def milestone_card(member: discord.Member, tag: str, stats: dict, label: str):
    """Syncs a member's roles, saves their numbers, and draws where they stand."""
    config = get_config()
    await sync_roles(member, config, stats)
    keep_stats(member.id, stats)
    rows = []
    for category, (_, stat) in CATEGORIES.items():
        tiers = sorted(get_tiers(config, category), key=lambda tier: tier["threshold"])
        if not tiers:
            continue
        value = stats.get(stat, 0)
        held = [tier for tier in tiers if value >= tier["threshold"]]
        role = member.guild.get_role(int(held[-1]["role_id"])) if held else None
        icon, name = ROWS[category]
        rows.append(
            {
                "icon": icon,
                "name": name,
                "value": value,
                "role": role.name if role else None,
                "color": role.color.to_rgb() if role and role.color.value else MUTED,
                "goals": [tier["threshold"] for tier in tiers],
            }
        )
    sheet = {
        "rows": rows,
        "player": await face(tag, stats),
        "label": label,
        "background": BACKGROUND,
    }
    return await render(draw_milestones, sheet, name="milestones")


def get_tiers(config: dict, category: str) -> list:
    if category.startswith("wins_"):
        return config.get("wins", {}).get(category[5:], [])
    return config.get(category, [])


def set_tiers(config: dict, category: str, tiers: list):
    if category.startswith("wins_"):
        config.setdefault("wins", {})[category[5:]] = tiers
    else:
        config[category] = tiers


def name_color(player: dict) -> int:
    try:
        return int(player.get("nameColor", "0xFFFFFF"), 16) & 0xFFFFFF
    except ValueError:
        return 0xFFFFFF


def account_embed(player: dict, tag: str, title: str, text: str, icon_id: int):
    embed = discord.Embed(title=title, description=text, color=name_color(player))
    embed.set_thumbnail(url=ICON.format(icon_id))
    embed.add_field(name="Account Tag", value=f"{TOOLS} `{tag}`")
    embed.add_field(
        name="Current Account Trophies", value=f"{TROPHY} `{player['trophies']}`"
    )
    return embed


def add_progress(embed: discord.Embed, config: dict, stats: dict, full=False):
    for category, (title, stat) in CATEGORIES.items():
        value = stats.get(stat, 0)
        tiers = sorted(get_tiers(config, category), key=lambda tier: tier["threshold"])
        unlocked = [tier for tier in tiers if value >= tier["threshold"]]
        lines = []
        for tier in tiers if full else unlocked[-1:]:
            if tier not in unlocked:
                mark = NO
            elif tier is unlocked[-1]:
                mark = YES
            else:
                mark = YES_DIM
            lines.append(
                f"> {mark} <@&{tier['role_id']}>: `{value}/{tier['threshold']}` ({tier['emoji']} {tier['name']})"
            )
        if lines:
            embed.add_field(name=title, value="\n".join(lines), inline=False)


async def sync_roles(member: discord.Member, config: dict, stats: dict):
    for category, (_, stat) in CATEGORIES.items():
        value = stats.get(stat, 0)
        tiers = sorted(get_tiers(config, category), key=lambda tier: tier["threshold"])
        unlocked = [tier for tier in tiers if value >= tier["threshold"]]
        if not unlocked:
            continue
        top = unlocked[-1]["role_id"]
        for role_id in {tier["role_id"] for tier in tiers}:
            role = member.guild.get_role(int(role_id))
            if not role:
                continue
            if role_id == top and role not in member.roles:
                await member.add_roles(role)
            if role_id != top and role in member.roles:
                await member.remove_roles(role)


async def clear_roles(member: discord.Member, config: dict):
    for category in CATEGORIES:
        for tier in get_tiers(config, category):
            role = member.guild.get_role(int(tier["role_id"]))
            if role in member.roles:
                await member.remove_roles(role)


async def category_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=category, value=category)
        for category in CATEGORIES
        if current.lower() in category
    ]


class VerifyModal(Modal, title="Link your Brawl Stars Account"):
    tag = TextInput(
        label="Your Brawl Stars Account Tag", placeholder="Example: #9L00JQRGR"
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        tag = clean_tag(self.tag.value)
        player = await get_player(tag)
        if not player or not player.get("brawlers"):
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"{NO} Invalid player tag. Please try again!"
                )
            )
            return
        icon_id = player["icon"]["id"]
        while icon_id == player["icon"]["id"]:
            brawler = random.choice(player["brawlers"])
            icon_id = await get_icon(brawler["id"])
        embed = account_embed(
            player,
            tag,
            "One more step left...",
            f"> To verify that you own the account **{player['name']}**, please **change your player icon** in Brawl Stars <:fastforward:1351972114433048719> `{brawler['name'].title()}`.\n\n-# <:info:1037445870469267638> Once you are done, click the button below!",
            icon_id,
        )
        embed.set_footer(text="You can always change your icon back afterward")
        await interaction.followup.send(embed=embed, view=IconChangeView())


class VerifyButton(Button):
    def __init__(self):
        super().__init__(
            label="Verify",
            emoji="<a:verify:1391195109302861904>",
            style=discord.ButtonStyle.blurple,
            custom_id="verify_button",
        )

    async def callback(self, interaction: discord.Interaction):
        if not await in_cafe(interaction):
            return
        tag = linked(interaction.user.id)
        if not tag:
            await interaction.response.send_modal(VerifyModal())
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        player = await get_player(tag)
        if not player:
            await interaction.followup.send(FAILED)
            return
        embed = account_embed(
            player,
            tag,
            f"{WARN} Account Already Linked",
            f"> You have previously linked **{player['name']}** to your Discord account. **Do you wish to unlink?**",
            player["icon"]["id"],
        )
        embed.set_footer(text="You will lose all your linked roles")
        await interaction.followup.send(embed=embed, view=UnlinkAccountView())


class UpdateRolesButton(Button):
    def __init__(self):
        super().__init__(
            label="Update Roles",
            emoji="<:refresh:1048779043287351408>",
            style=discord.ButtonStyle.grey,
            custom_id="update_roles",
        )

    async def callback(self, interaction: discord.Interaction):
        if not await in_cafe(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        tag = linked(interaction.user.id)
        if not tag:
            await interaction.followup.send(NOT_LINKED)
            return
        stats = await get_stats(tag)
        if not stats:
            await interaction.followup.send(FAILED)
            return
        await interaction.followup.send(
            file=await milestone_card(interaction.user, tag, stats, "ROLES UPDATED")
        )


class VerificationEmbedView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(VerifyButton())
        self.add_item(UpdateRolesButton())


class IconChangeButton(Button):
    def __init__(self):
        super().__init__(
            emoji=YES,
            style=discord.ButtonStyle.grey,
            custom_id="icon_change_button",
        )

    async def callback(self, interaction: discord.Interaction):
        if not await in_cafe(interaction):
            return
        prompt = interaction.message.embeds[0]
        tag = clean_tag(prompt.fields[0].value.split("`")[1])
        icon_id = int(re.search(r"/(\d+)\.png$", prompt.thumbnail.url).group(1))
        await interaction.response.edit_message(view=None)
        message = await interaction.followup.send(
            embed=discord.Embed(
                description=f"Verifying your account. Please wait patiently  {LOADING}",
                color=discord.Color.blurple(),
            ),
            ephemeral=True,
        )
        for attempt in range(1, ATTEMPTS + 1):
            player = await get_player(tag)
            if player and player["icon"]["id"] == icon_id:
                break
            embed = discord.Embed(
                description=f"{LOADING}  Attempt **`{attempt}`**: Icon not updated yet, checking again in `{DELAY}` seconds...",
                color=discord.Color.blurple(),
            )
            embed.set_footer(
                text="It can take up to 5 attempts for Brawl Stars API to update"
            )
            await message.edit(embed=embed)
            await asyncio.sleep(DELAY)
        else:
            await message.edit(
                embed=discord.Embed(
                    description=f"{NO} Timed out after 5 minutes. Please try again later.",
                    color=discord.Color.red(),
                )
            )
            return
        u_tag(interaction.user.id).update({"tag": tag})
        embed = discord.Embed(
            description=f"{YES} Verification successful. Your Brawl Stars Account is now linked and milestone roles are granted!",
            color=discord.Color.green(),
        )
        stats = await get_stats(tag)
        if stats:
            config = get_config()
            await sync_roles(interaction.user, config, stats)
            keep_stats(interaction.user.id, stats)
            add_progress(embed, config, stats)
        await message.edit(embed=embed)


class IconChangeView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(IconChangeButton())


class UnlinkAccountButton(Button):
    def __init__(self):
        super().__init__(
            emoji=WARN,
            label="Unlink",
            style=discord.ButtonStyle.red,
            custom_id="unlink_account_button",
        )

    async def callback(self, interaction: discord.Interaction):
        if not await in_cafe(interaction):
            return
        await interaction.response.defer()
        u_tag(interaction.user.id).delete()
        await clear_roles(interaction.user, get_config())
        embed = discord.Embed(
            title=f"{YES} Account Unlinked",
            description="Your Brawl Stars account has been successfully unlinked.",
            color=discord.Color.red(),
        )
        embed.set_footer(text="You can relink anytime using the panel.")
        embed.set_thumbnail(url=ICON.format(28000000))
        await interaction.edit_original_response(embed=embed, view=None)


class UnlinkAccountView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(UnlinkAccountButton())


class MilestoneRolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    milestone = app_commands.Group(
        name="milestone", description="Manage Brawl Stars milestone roles"
    )

    @milestone.command(name="embed", description="Post the account linking panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def embed(self, interaction: discord.Interaction):
        if not await in_cafe(interaction):
            return
        embed = discord.Embed(
            description=(
                "# <a:brawlstars:1393743461030694962> Exclusive Self Roles!\n"
                "Link your **Brawl Stars account** with your Discord to **unlock "
                f"exclusive roles** based on your {TROPHY} trophies, {RANKED} Ranked, "
                f"{FAME} Fame and {TRIO} wins.\n\n"
                "<a:SpikeWin:1391625613273727137> **Flex your highest "
                f"in-game achievements** on {LEADERBOARD}!\n"
                f"-# {REPLY_EMOTE} *Use {MINE} to **view** the server milestones.*\n"
                f"-# {REPLY_EMOTE} *Use {PROFILE} to see your Brawl Stars account.*"
            ),
            color=COLOR,
        )
        embed.set_footer(
            text="We verify by checking a temporary icon change, never your password."
        )
        embed.set_image(url=BANNER)
        await interaction.channel.send(embed=embed, view=VerificationEmbedView())
        await interaction.response.send_message(f"{YES} Panel sent.", ephemeral=True)

    @embed.error
    async def embed_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{error}```", ephemeral=True)

    @milestone.command(name="add", description="Add a milestone role")
    @app_commands.describe(
        category="Select a category to add milestone",
        threshold="The number at which the milestone role is given",
        role="The milestone role to give",
        name="A descriptive name of this milestone",
        emoji="An emoji for this milestone",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(category=category_autocomplete)
    async def add(
        self,
        interaction: discord.Interaction,
        category: str,
        threshold: int,
        role: discord.Role,
        name: str,
        emoji: str,
    ):
        if not await in_cafe(interaction):
            return
        if category not in CATEGORIES:
            await interaction.response.send_message(
                f"{NO} Unknown category **{category}**.", ephemeral=True
            )
            return
        config = get_config()
        tier = {
            "threshold": threshold,
            "role_id": str(role.id),
            "name": name,
            "emoji": emoji,
        }
        set_tiers(config, category, get_tiers(config, category) + [tier])
        set_config(config)
        await interaction.response.send_message(
            f"{YES} Added {role.mention} ({emoji} {name}) to **{category}**.",
            ephemeral=True,
        )

    @milestone.command(name="remove", description="Remove a milestone by name")
    @app_commands.describe(
        category="Select a category of the milestone",
        name="The descriptive name of the milestone to be removed",
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(category=category_autocomplete)
    async def remove(self, interaction: discord.Interaction, category: str, name: str):
        if not await in_cafe(interaction):
            return
        config = get_config()
        tiers = get_tiers(config, category)
        kept = [tier for tier in tiers if tier["name"] != name]
        if len(kept) == len(tiers):
            await interaction.response.send_message(
                f"{NO} No milestone named {name} in **{category}**.", ephemeral=True
            )
            return
        set_tiers(config, category, kept)
        set_config(config)
        await interaction.response.send_message(
            f"{YES} Removed {name} from **{category}**.", ephemeral=True
        )

    @milestone.command(name="list", description="List milestone roles in a category")
    @app_commands.describe(category="Select a milestone category to view")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(category=category_autocomplete)
    async def list(self, interaction: discord.Interaction, category: str):
        if not await in_cafe(interaction):
            return
        tiers = get_tiers(get_config(), category)
        if not tiers:
            await interaction.response.send_message(
                f"No milestones in {category}.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "\n".join(
                f"<@&{tier['role_id']}>: `{tier['threshold']}` ({tier['emoji']} {tier['name']})"
                for tier in tiers
            ),
            ephemeral=True,
        )

    @milestone.command(name="mine", description="Show your milestone progress")
    async def mine(self, interaction: discord.Interaction):
        if not await in_cafe(interaction):
            return
        await interaction.response.defer(thinking=True)
        tag = linked(interaction.user.id)
        if not tag:
            await interaction.followup.send(NOT_LINKED)
            return
        stats = await get_stats(tag)
        if not stats:
            await interaction.followup.send(FAILED)
            return
        await interaction.followup.send(
            file=await milestone_card(interaction.user, tag, stats, "MILESTONE ROLES")
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MilestoneRolesCog(bot))

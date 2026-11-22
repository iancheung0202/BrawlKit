import datetime
import re
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View
from firebase_admin import db

from brawl.Utility.style import NO, YES

COLOR = "#5865F2"
NAME = r"[\w-]+"
STATUSES = {
    "pending": ("🟡", 0xFEE75C),
    "accepted": ("🟢", 0x57F287),
    "rejected": ("🔴", 0xED4245),
    "blacklisted": ("⚫", 0x000000),
}
INVITES = "https://discord.com/api/v9/invites/{}"
FALLBACK_ICON = "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTEkPA5_-j6SudIbSZh-ExIs1eSeuCYIIRthjHfg0P2dbwUH2E&s"
THREADS_IMAGE = "https://media.discordapp.net/attachments/1106727534479032341/1366102857366896781/thread_instructions.png?ex=680fb9ee&is=680e686e&hm=4a80c4dda380d4b3e5ef7781576a9be6981e909a0179780e50dc605b1a4570c1&="
NOT_ENABLED = f"{NO} Partnership system not enabled!"
NO_GROUP = f"{NO} Group not found!"


def mention(command: str) -> str:
    return f"</partner {command}:1390765119272648836>"


def ref(name: str, guild_id: int):
    return db.reference(f"Partner/{name}/{guild_id}")


def now() -> float:
    return datetime.datetime.now().timestamp()


def to_color(text: str) -> int:
    try:
        return int(text.lstrip("#"), 16)
    except (AttributeError, ValueError):
        return int(COLOR.lstrip("#"), 16)


def yes_no(value: bool) -> str:
    return f"{YES} Yes" if value else f"{NO} No"


def link(partner: dict) -> str:
    if partner["invite"].isdigit():
        return f"https://discord.com/oauth2/authorize?client_id={partner['invite']}"
    return f"https://discord.gg/{partner['invite']}"


def section_embed(data: dict, title: str, name: str) -> discord.Embed:
    embed = discord.Embed(
        title=data.get("title"),
        description=data.get("description"),
        color=to_color(data.get("color")),
    )
    if not embed.title and not embed.description:
        embed.title = title
        embed.description = (
            f"Use {mention('edit-panel')} and select `{name}` to edit this embed!"
        )
    embed.set_thumbnail(url=data.get("thumbnail"))
    embed.set_image(url=data.get("image"))
    return embed


def group_embeds(name: str, group: dict, partners: list) -> list:
    chunks = []
    for partner in sorted(partners, key=lambda partner: partner["name"].lower()):
        line = f"{group.get('prefix', '')} [{partner['name']}]({link(partner)}) {group.get('suffix', '')}"
        letter = partner["name"][0].upper()
        if chunks and len("\n".join(chunks[-1]["lines"] + [line])) <= 1024:
            chunks[-1]["lines"].append(line)
            chunks[-1]["end"] = letter
        else:
            chunks.append({"start": letter, "end": letter, "lines": [line]})
    if chunks:
        chunks[0]["start"], chunks[-1]["end"] = "A", "Z"
    embeds = []
    for index, chunk in enumerate(chunks):
        if index % 25 == 0:
            embeds.append(
                discord.Embed(
                    title=group.get("title", name), color=to_color(group.get("color"))
                )
            )
            embeds[-1].set_thumbnail(url=group.get("thumbnail"))
        embeds[-1].add_field(
            name=f"{chunk['start']} - {chunk['end']}",
            value="\n".join(chunk["lines"]),
            inline=False,
        )
    return embeds


def panel_embeds(guild_id: int) -> list:
    sections = (ref("config", guild_id).get() or {}).get("embed", {})
    partners = (ref("partners", guild_id).get() or {}).values()
    embeds = [
        section_embed(sections.get("header", {}), "Server Partner List", "Header")
    ]
    for name, group in (ref("categories", guild_id).get() or {}).items():
        members = [partner for partner in partners if partner.get("category") == name]
        embeds += group_embeds(name, group, members)
    footer = section_embed(sections.get("footer", {}), "Instructions", "Footer")
    footer.set_footer(text="⚡ Panel automatically updated • Powered by BrawlKit")
    return embeds + [footer]


async def update_panel(bot: commands.Bot, guild_id: int) -> str:
    panel = ref("panels", guild_id).get()
    if not panel:
        return f"{NO} No panel to update. Use {mention('send-panel')} to send one."
    try:
        channel = bot.get_channel(panel["channel_id"])
        message = await channel.fetch_message(panel["message_id"])
        await message.edit(embeds=panel_embeds(guild_id))
    except (AttributeError, discord.HTTPException) as error:
        return f"{NO} Failed to update panel: {error}"
    return f"{YES} Panel updated!"


async def log(interaction: discord.Interaction, action: str, details: dict, url=None):
    config = ref("config", interaction.guild.id).get() or {}
    channel = interaction.guild.get_channel(config.get("log_channel", 0))
    if not channel:
        return
    embed = discord.Embed(
        title=action,
        color=to_color(COLOR),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_author(
        name=str(interaction.user), icon_url=interaction.user.display_avatar.url
    )
    for name, value in details.items():
        embed.add_field(name=name, value=str(value), inline=False)
    view = View()
    if url:
        view.add_item(
            Button(label="Go to thread", style=discord.ButtonStyle.link, url=url)
        )
    await channel.send(embed=embed, view=view)


async def get_invite(invite_link: str):
    code = invite_link.strip().rstrip("/").split("/")[-1]
    params = {"with_counts": "true", "with_expiration": "true"}
    async with aiohttp.ClientSession() as session:
        async with session.get(INVITES.format(code), params=params) as response:
            data = await response.json() if response.status == 200 else {}
    return code, data if data.get("guild") else None


async def find_thread(channel: discord.TextChannel, server_id: str, bot_id: int):
    threads = channel.threads + [thread async for thread in channel.archived_threads()]
    for thread in threads:
        try:
            messages = [m async for m in thread.history(limit=2, oldest_first=True)]
        except discord.HTTPException:
            continue
        for message in messages:
            if message.author.id != bot_id or not message.embeds:
                continue
            for field in message.embeds[0].fields:
                if field.name == "Server ID" and field.value == server_id:
                    return thread
    return None


async def open_thread(interaction: discord.Interaction, invite_link: str, staff: bool):
    config = ref("config", interaction.guild.id).get()
    if not config:
        return NOT_ENABLED
    code, invite = await get_invite(invite_link)
    if not invite:
        return f"{NO} Invalid invite link!"
    server = invite["guild"]
    if not staff and ref("Blacklist", interaction.guild.id).child(server["id"]).get():
        return f"{NO} This server is blacklisted! If you believe this is a mistake, contact a server staff and ask them to unblacklist your server!"
    channel = interaction.guild.get_channel(config["request_channel"])
    if not channel:
        return f"{NO} The request channel no longer exists. Ask staff to run {mention('setup')} again."
    existing = await find_thread(channel, server["id"], interaction.client.user.id)
    if existing:
        return f"{NO} A partnership thread for this server already exists: {existing.mention}"
    thread = await channel.create_thread(
        name=f"🟡 {server['name']}", type=discord.ChannelType.private_thread
    )
    role = "Staff" if staff else "Requester"
    members = invite.get("approximate_member_count", "Unknown")
    permanent = yes_no(invite.get("expires_at") is None)
    embed = discord.Embed(
        title=(
            "Partnership Thread (initiated by Staff)"
            if staff
            else "New Partnership Request"
        ),
        description=f"-# - Staff can use {mention('status')} to update the thread and {mention('add-partner')} to add partner to the panel.\n-# - Everyone here can use {mention('invite')} to invite other server reps/staff to this thread.",
        color=STATUSES["pending"][1],
    )
    embed.add_field(name="Server ID", value=server["id"])
    embed.add_field(name="Server Name", value=server["name"])
    embed.add_field(name="Members", value=members)
    embed.add_field(name="Permanent Server Invite", value=permanent)
    embed.add_field(name=f"{role} ID", value=interaction.user.id)
    embed.add_field(name=f"{role} Mention", value=interaction.user.mention)
    embed.set_footer(text="Status: 🟡 Pending")
    if server.get("icon"):
        embed.set_thumbnail(
            url=f"https://cdn.discordapp.com/icons/{server['id']}/{server['icon']}.png"
        )
    else:
        embed.set_thumbnail(url=FALLBACK_ICON)
    manager = config.get("partner_manager_role_id")
    ping = f"<@&{manager}> " if manager and not staff else ""
    await thread.send(f"{ping}{invite_link}", embed=embed)
    await log(
        interaction,
        (
            f"Staff Partnership Thread Creation ({server['name']})"
            if staff
            else f"New Partnership Request ({server['name']})"
        ),
        {
            "Server ID": server["id"],
            "Server Name": server["name"],
            "Invite Link": f"https://discord.gg/{code}",
            "Permanent Invite": permanent,
            "Members": members,
        },
        thread.jump_url,
    )
    if staff:
        return f"{YES} Thread created: {thread.mention}. Use {mention('invite')} to invite server representatives to the thread!"
    await thread.add_user(interaction.user)
    ref("Cooldown", interaction.guild.id).child(str(interaction.user.id)).set(now())
    return f"{YES} Request created in {thread.mention}"


async def group_autocomplete(interaction: discord.Interaction, current: str):
    groups = ref("categories", interaction.guild.id).get() or {}
    return [
        app_commands.Choice(name=name, value=name)
        for name in groups
        if current.lower() in name.lower()
    ][:25]


class RequestModal(Modal, title="Partnership Request"):
    invite_link = TextInput(
        label="Your Server's Permanent Invite Link",
        placeholder="Other details will be fetched automatically.",
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = ref("config", interaction.guild.id).get() or {}
        cooldown = ref("Cooldown", interaction.guild.id)
        last = cooldown.child(str(interaction.user.id)).get() or 0
        wait = int(config.get("user_cooldown", 0) - (now() - last))
        if wait > 0:
            await interaction.followup.send(
                f"{NO} You're on cooldown! Try again in {wait // 3600}h {wait % 3600 // 60}m",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            await open_thread(interaction, self.invite_link.value, staff=False),
            ephemeral=True,
        )


class RequestButton(Button):
    def __init__(self):
        super().__init__(
            label="Request Partnership",
            style=discord.ButtonStyle.blurple,
            custom_id="partner_request",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RequestModal())


class RequestView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RequestButton())


class PanelModal(Modal):
    heading = TextInput(
        label="Title", required=False, placeholder="Enter an embed title"
    )
    description = TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        required=False,
        placeholder="Enter an embed description",
    )
    color = TextInput(
        label="Color (hex code)", required=False, placeholder="e.g. #0f0f0f"
    )
    thumbnail = TextInput(
        label="Thumbnail URL",
        required=False,
        placeholder="Enter an link for thumbnail image",
    )
    image = TextInput(
        label="Image URL", required=False, placeholder="Enter an link for large image"
    )

    def __init__(self, section: str, data: dict):
        super().__init__(title=f"Edit {section.capitalize()} Embed")
        self.section = section
        self.heading.default = data.get("title")
        self.description.default = data.get("description")
        self.color.default = data.get("color", COLOR)
        self.thumbnail.default = data.get("thumbnail")
        self.image.default = data.get("image")

    async def on_submit(self, interaction: discord.Interaction):
        updates = {
            "title": self.heading.value.strip() or None,
            "description": self.description.value.strip() or None,
            "color": self.color.value.strip() or COLOR,
            "thumbnail": self.thumbnail.value.strip() or None,
            "image": self.image.value.strip() or None,
        }
        section = ref("config", interaction.guild.id).child(f"embed/{self.section}")
        saved = section.get() or {}
        changes = {
            key: value for key, value in updates.items() if value != saved.get(key)
        }
        if not changes:
            await interaction.response.send_message(
                f"{NO} No changes detected!", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        section.update(changes)
        await interaction.followup.send(
            await update_panel(interaction.client, interaction.guild.id),
            ephemeral=True,
        )
        await log(interaction, f"Panel Edited ({self.section.capitalize()})", changes)


class GroupModal(Modal, title="Edit Partner Group"):
    name = TextInput(
        label="Unique Group Name", placeholder="Letters, numbers, underscores, hyphens"
    )
    heading = TextInput(label="Display Title", required=False)
    color = TextInput(label="Color (hex)", required=False)
    affixes = TextInput(
        label="Prefix, Suffix (separated by a comma)",
        placeholder="Example: -, >",
        required=False,
    )
    thumbnail = TextInput(label="Thumbnail URL", required=False)

    def __init__(self, name: str, group: dict):
        super().__init__()
        self.old = name
        self.name.default = name
        self.heading.default = group.get("title")
        self.color.default = group.get("color", COLOR)
        self.affixes.default = (
            f"{group.get('prefix', '-')}, {group.get('suffix', '')}".strip(", ")
        )
        self.thumbnail.default = group.get("thumbnail")

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name.value.strip()
        groups = ref("categories", interaction.guild.id)
        saved = groups.get() or {}
        taken = {other.lower() for other in saved if other != self.old}
        if not re.fullmatch(NAME, name):
            error = f"{NO} Invalid group name! Only letters, numbers, underscores, and hyphens allowed."
        elif name.lower() in taken:
            error = f"{NO} Group name already exists!"
        elif self.old not in saved:
            error = NO_GROUP
        else:
            error = None
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        prefix, _, suffix = self.affixes.value.partition(",")
        updates = {
            "title": self.heading.value.strip() or name,
            "color": self.color.value.strip() or COLOR,
            "prefix": prefix.strip(),
            "suffix": suffix.strip(),
            "thumbnail": self.thumbnail.value.strip() or None,
        }
        if name != self.old:
            groups.child(self.old).delete()
            partners = ref("partners", interaction.guild.id)
            for key, partner in (partners.get() or {}).items():
                if partner.get("category") == self.old:
                    partners.child(key).update({"category": name})
        groups.child(name).update({**saved[self.old], **updates})
        status = await update_panel(interaction.client, interaction.guild.id)
        await interaction.followup.send(
            f"{YES} Group updated! \n{status}", ephemeral=True
        )
        await log(
            interaction,
            "Group Edited",
            {"Original Name": self.old, "New Name": name, **updates},
        )


class Partner(commands.GroupCog, name="partner"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        if interaction.response.is_done():
            await interaction.followup.send(f"```{error}```", ephemeral=True)
        else:
            await interaction.response.send_message(f"```{error}```", ephemeral=True)

    @app_commands.command(name="status", description="Update partnership status")
    @app_commands.describe(status="New status", reason="Reason for status change")
    @app_commands.choices(
        status=[
            app_commands.Choice(name="🟡 Pending", value="pending"),
            app_commands.Choice(name="🟢 Accepted", value="accepted"),
            app_commands.Choice(name="🔴 Rejected", value="rejected"),
            app_commands.Choice(name="⚫ Blacklisted", value="blacklisted"),
        ]
    )
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def status(
        self,
        interaction: discord.Interaction,
        status: str,
        reason: str = "No reason provided",
    ):
        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message(
                f"{NO} This command must be used in a partnership thread!",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        emoji, color = STATUSES[status]
        name = thread.name.lstrip("".join(e for e, _ in STATUSES.values())).strip()
        await thread.edit(name=f"{emoji} {name}")
        async for message in thread.history(limit=2, oldest_first=True):
            if message.author.id != interaction.client.user.id or not message.embeds:
                continue
            embed = message.embeds[0]
            embed.color = color
            embed.set_footer(
                text=f"Status: {emoji} {status.capitalize()} | Reason: {reason}"
            )
            await message.edit(embed=embed)
        await log(interaction, f"Partner Status Updated {emoji}", {"Server Name": name})
        await interaction.followup.send(
            f"{YES} Status updated to {emoji} {status}!", ephemeral=True
        )

    @app_commands.command(
        name="invite",
        description="Invite server representatives to the partnership thread",
    )
    @app_commands.describe(user="User to invite")
    async def invite(self, interaction: discord.Interaction, user: discord.User):
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                f"{NO} This command can only be used in partnership threads!",
                ephemeral=True,
            )
            return
        try:
            await interaction.channel.add_user(user)
        except discord.HTTPException:
            await interaction.response.send_message(
                f"{NO} Sorry, something went wrong!", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"{YES} {user.mention} has been added to the thread!", ephemeral=True
        )

    @app_commands.command(
        name="create",
        description="Manually create a partnership thread (bypasses blacklist)",
    )
    @app_commands.describe(invite_link="Permanent invite link for the server")
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def create(self, interaction: discord.Interaction, invite_link: str):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            await open_thread(interaction, invite_link, staff=True), ephemeral=True
        )

    @app_commands.command(
        name="blacklist", description="Blacklist a server from partnerships"
    )
    @app_commands.describe(
        invite_link="The invite link of server to blacklist (Leave blank to view blacklist)"
    )
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def blacklist(
        self, interaction: discord.Interaction, invite_link: Optional[str] = None
    ):
        blacklist = ref("Blacklist", interaction.guild.id)
        if not invite_link:
            servers = blacklist.get() or {}
            if not servers:
                await interaction.response.send_message(
                    "No servers are blacklisted!", ephemeral=True
                )
                return
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Blacklisted Server ID",
                    description="\n".join(f"- `{server}`" for server in servers),
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )
            return
        _, invite = await get_invite(invite_link)
        if not invite:
            await interaction.response.send_message(
                f"{NO} Invalid invite link!", ephemeral=True
            )
            return
        blacklist.child(invite["guild"]["id"]).set(True)
        await interaction.response.send_message(
            f"{YES} Server {invite['guild']['id']} blacklisted!", ephemeral=True
        )

    @app_commands.command(
        name="unblacklist", description="Remove a server from blacklist"
    )
    @app_commands.describe(guild_id="Server ID to unblacklist")
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def unblacklist(self, interaction: discord.Interaction, guild_id: str):
        server = ref("Blacklist", interaction.guild.id).child(guild_id)
        if not server.get():
            await interaction.response.send_message(
                f"{NO} Server not in blacklist!", ephemeral=True
            )
            return
        server.delete()
        await interaction.response.send_message(
            f"{YES} Server {guild_id} unblacklisted!", ephemeral=True
        )

    @app_commands.command(name="edit-panel", description="Edit panel embeds")
    @app_commands.describe(section="Section to edit")
    @app_commands.choices(
        section=[
            app_commands.Choice(name="Header", value="header"),
            app_commands.Choice(name="Footer", value="footer"),
        ]
    )
    @app_commands.checks.has_permissions(
        manage_webhooks=True, manage_channels=True, manage_messages=True
    )
    async def edit_panel(self, interaction: discord.Interaction, section: str):
        data = ref("config", interaction.guild.id).child(f"embed/{section}").get()
        await interaction.response.send_modal(PanelModal(section, data or {}))

    @app_commands.command(name="disable", description="Disable partnership system")
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def disable(self, interaction: discord.Interaction):
        if not ref("config", interaction.guild.id).get():
            await interaction.response.send_message(NOT_ENABLED, ephemeral=True)
            return
        for name in ("config", "panels", "categories", "partners"):
            ref(name, interaction.guild.id).delete()
        await interaction.response.send_message(
            f"{YES} Partnership system disabled! All configurations removed.",
            ephemeral=True,
        )

    @app_commands.command(name="send-panel", description="Send the partnership panel")
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def send_panel(self, interaction: discord.Interaction):
        config = ref("config", interaction.guild.id).get()
        if not config:
            await interaction.response.send_message(NOT_ENABLED, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        channel = interaction.guild.get_channel(config["panel_channel"])
        embeds = panel_embeds(interaction.guild.id)
        message = await channel.send(embeds=embeds, view=RequestView())
        ref("panels", interaction.guild.id).set(
            {"message_id": message.id, "channel_id": channel.id}
        )
        await log(
            interaction,
            "Panel Sent",
            {
                "Channel": channel.mention,
                "Message ID": message.id,
                "Embed Count": len(embeds),
            },
        )
        await interaction.followup.send(
            f"{YES} [Partnership panel sent]({message.jump_url})! *All other panels sent previously will no longer automatically update.*",
            ephemeral=True,
        )

    @app_commands.command(
        name="add-group",
        description="Create new partner group with separate panel embed",
    )
    @app_commands.describe(
        name="Unique group name (no spaces)",
        title="Display title (default: the group name)",
        color="Embed color in hex code (default: #5865F2)",
        prefix="Line prefix (default: bullet point)",
        suffix="Line suffix (default: None)",
        thumbnail="Thumbnail URL (optional)",
    )
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def add_group(
        self,
        interaction: discord.Interaction,
        name: str,
        title: Optional[str] = None,
        color: Optional[str] = COLOR,
        prefix: Optional[str] = "-",
        suffix: Optional[str] = "",
        thumbnail: Optional[str] = None,
    ):
        groups = ref("categories", interaction.guild.id)
        if not re.fullmatch(NAME, name):
            error = f"{NO} Group name can only contain letters, numbers, underscores and hyphens!"
        elif name.lower() in {other.lower() for other in groups.get() or {}}:
            error = f"{NO} Group already exists!"
        else:
            error = None
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        groups.child(name).set(
            {
                "title": title or name,
                "color": color,
                "prefix": prefix,
                "suffix": suffix,
                "thumbnail": thumbnail,
                "created_at": now(),
            }
        )
        await interaction.response.send_message(
            f"{YES} Group '{name}' created! To delete a group, use {mention('remove-group')}.",
            ephemeral=True,
        )
        await log(
            interaction,
            "Group Created",
            {
                "Group Name": name,
                "Title": title or name,
                "Color": color,
                "Prefix": prefix,
                "Suffix": suffix or "None",
                "Thumbnail": thumbnail or "None",
            },
        )

    @app_commands.command(
        name="edit-group", description="Edit an existing partner group"
    )
    @app_commands.describe(group="Group to edit")
    @app_commands.autocomplete(group=group_autocomplete)
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def edit_group(self, interaction: discord.Interaction, group: str):
        groups = ref("categories", interaction.guild.id).get() or {}
        if group not in groups:
            await interaction.response.send_message(NO_GROUP, ephemeral=True)
            return
        await interaction.response.send_modal(GroupModal(group, groups[group]))

    @app_commands.command(
        name="remove-group", description="⚠️ Remove a group and ALL its partners"
    )
    @app_commands.describe(name="Group name to remove")
    @app_commands.autocomplete(name=group_autocomplete)
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def remove_group(self, interaction: discord.Interaction, name: str):
        groups = ref("categories", interaction.guild.id)
        if name not in (groups.get() or {}):
            await interaction.response.send_message(NO_GROUP, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        partners = ref("partners", interaction.guild.id)
        removed = [
            key
            for key, partner in (partners.get() or {}).items()
            if partner.get("category") == name
        ]
        for key in removed:
            partners.child(key).delete()
        groups.child(name).delete()
        await update_panel(interaction.client, interaction.guild.id)
        await log(
            interaction,
            "Group Removed",
            {"Group Name": name, "Partners Deleted": len(removed)},
        )
        await interaction.followup.send(
            f"{YES} Group '{name}' and its {len(removed)} partner(s) were permanently deleted!",
            ephemeral=True,
        )

    @app_commands.command(name="setup", description="Set up partnership system")
    @app_commands.describe(
        log_channel="Channel for partnership logs",
        partner_role="Role to grant server partners",
        request_channel="Channel to create partnership threads under",
        panel_channel="Channel to send the partnership panel",
        partner_manager_role="Staff role to ping for new partnership requests (default: None)",
        user_cooldown="Cooldown between user requests (format: 3d12h45m; default: 0)",
    )
    @app_commands.checks.has_permissions(manage_webhooks=True, manage_channels=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        log_channel: discord.TextChannel,
        partner_role: discord.Role,
        request_channel: discord.TextChannel,
        panel_channel: discord.TextChannel,
        partner_manager_role: discord.Role = None,
        user_cooldown: str = "0m",
    ):
        match = re.fullmatch(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?", user_cooldown)
        if not match:
            await interaction.response.send_message(
                "⚠️ Invalid cooldown format. Use something like `3d12h45m`, `5h`, or `30m`.",
                ephemeral=True,
            )
            return
        days, hours, minutes = (int(amount or 0) for amount in match.groups())
        units = ((days, "day"), (hours, "hour"), (minutes, "minute"))
        cooldown = ", ".join(
            f"{amount} {unit}{'s' if amount != 1 else ''}"
            for amount, unit in units
            if amount
        )
        ref("config", interaction.guild.id).update(
            {
                "log_channel": log_channel.id,
                "partner_role": partner_role.id,
                "request_channel": request_channel.id,
                "panel_channel": panel_channel.id,
                "user_cooldown": days * 86400 + hours * 3600 + minutes * 60,
                "partner_manager_role_id": (
                    str(partner_manager_role.id) if partner_manager_role else ""
                ),
                "enabled": True,
            }
        )
        embed = discord.Embed(
            title=f"{YES} Partnership System Setup Complete!",
            description=(
                "Here are something you can do next to make everything work:\n"
                f"- Check out {panel_channel.mention} and {request_channel.mention} and follow the instructions there.\n"
                f'- Use {mention("add-group")} to group partners (e.g., "Hangouts", "Brawl", "Clash_Royale", etc).\n'
                "  - **Name**: A short ID is required (no spaces, like `Brawl_Stars`).\n"
                '  - **Title**: The display name of the group (e.g., "🎮 Brawl Stars Servers").\n'
                "  - **Prefix/Suffix**: Customize how server links appear on the panel with your favorite symbols.\n"
                "  - Partners will only show up on the panel if they're in a group!\n"
                f"- Try {mention('add-partner')} and {mention('remove-partner')} to test add/remove partners.\n"
                f"- Use {mention('create')} to manually create a partnership thread as a staff\n\n"
                "**⚙️ Your Configured Settings** "
            ),
            color=discord.Color.green(),
        )
        embed.add_field(name="Log Channel", value=log_channel.mention)
        embed.add_field(name="Request Channel", value=request_channel.mention)
        embed.add_field(name="Panel Channel", value=panel_channel.mention)
        embed.add_field(name="Partner Role", value=partner_role.mention)
        embed.add_field(
            name="Partner Manager Role *(pinged for new requests)*",
            value=partner_manager_role.mention if partner_manager_role else "None",
        )
        embed.add_field(name="User Cooldown", value=cooldown or "None")
        await interaction.response.send_message(embed=embed)
        try:
            panel = await panel_channel.send(
                embeds=panel_embeds(interaction.guild.id), view=RequestView()
            )
            ref("panels", interaction.guild.id).set(
                {"message_id": panel.id, "channel_id": panel_channel.id}
            )
            await log_channel.send(
                embed=discord.Embed(
                    description="📝 This channel will be used for logging all partnership-related actions.",
                    color=to_color(COLOR),
                )
            )
            guide = discord.Embed(
                title="Partnership Request Instructions", color=to_color(COLOR)
            )
            guide.add_field(
                name="For Server Representatives",
                value=f"1. Click `Request Partnership` **[here]({panel.jump_url})** in {panel_channel.mention}\n2. Check existing threads using:\n  - **Threads <:thread_icon:1366092363822268598> button** at channel top\n  - **Channel Sidebar** on desktop (hover → 'See All')",
                inline=False,
            )
            guide.add_field(
                name="For Staff Only",
                value=f"- Manage partnership requests in threads. Use the methods above to access all the threads.\n- Use {mention('create')} to manually create a partnership thread.",
                inline=False,
            )
            guide.set_image(url=THREADS_IMAGE)
            guide.set_footer(text="You may delete/replace this message if you wish to.")
            await request_channel.send(embed=guide)
        except discord.HTTPException as error:
            await interaction.followup.send(
                f"⚠️ Partially completed setup: {type(error).__name__} - {error}",
                ephemeral=True,
            )

    @app_commands.command(
        name="mass-add-partner",
        description="Mass add partner servers from formatted text",
    )
    @app_commands.describe(
        group="Group that servers belong to",
        content="Formatted partner list (each line: [Server Name](invite_link))",
    )
    @app_commands.autocomplete(group=group_autocomplete)
    @app_commands.checks.has_permissions(
        manage_webhooks=True, manage_channels=True, manage_messages=True
    )
    async def mass_add(
        self, interaction: discord.Interaction, group: str, content: str
    ):
        await interaction.response.defer(ephemeral=True)
        if group not in (ref("categories", interaction.guild.id).get() or {}):
            await interaction.followup.send(
                f"{NO} Invalid group! Create groups first using {mention('add-group')}.",
                ephemeral=True,
            )
            return
        added = 0
        errors = []
        lines = [line.strip() for line in content.splitlines()]
        for number, line in enumerate(lines, 1):
            match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", line)
            if not line:
                continue
            if not match:
                errors.append(f"Line {number}: Invalid format")
                continue
            ref("partners", interaction.guild.id).push().set(
                {
                    "name": match.group(1),
                    "invite": match.group(2).rstrip("/").split("/")[-1],
                    "member_count": 0,
                    "staff_id": interaction.user.id,
                    "timestamp": now(),
                    "category": group,
                }
            )
            added += 1
        status = await update_panel(interaction.client, interaction.guild.id)
        reply = f"{YES} Added {added} partners to group `{group}`!\n{status}"
        if errors:
            reply += "\n\n**Errors:**\n" + "\n".join(errors[:5])
        if len(errors) > 5:
            reply += f"\n...and {len(errors) - 5} more errors"
        await interaction.followup.send(reply, ephemeral=True)
        await log(
            interaction,
            "Mass Partner Add",
            {"Group": group, "Added Count": added, "Error Count": len(errors)},
        )

    @app_commands.command(name="add-partner", description="Add a partner server")
    @app_commands.describe(
        name="Server name",
        invite_link="Server's permanent invite link (please include 'https://')",
        group="Group that server belongs (use /partner add-group to create a group)",
        server_rep="The server's representative to get the partner role",
    )
    @app_commands.autocomplete(group=group_autocomplete)
    @app_commands.checks.has_permissions(
        manage_webhooks=True, manage_channels=True, manage_messages=True
    )
    async def add_partner(
        self,
        interaction: discord.Interaction,
        name: str,
        invite_link: str,
        group: str,
        server_rep: discord.Member = None,
    ):
        await interaction.response.defer(ephemeral=True)
        config = ref("config", interaction.guild.id).get() or {}
        role = interaction.guild.get_role(int(config.get("partner_role", 0)))
        bot = invite_link.isdigit()
        code, invite = (invite_link, {}) if bot else await get_invite(invite_link)
        if group not in (ref("categories", interaction.guild.id).get() or {}):
            error = (
                f"{NO} Invalid group! Create groups first using {mention('add-group')}."
            )
        elif invite is None:
            error = f"{NO} Invalid invite link!"
        elif invite.get("expires_at"):
            error = f"{NO} Invite link is not permanent."
        elif server_rep and not role:
            error = f"{NO} Invalid partner role. Double check to see if the role has been deleted."
        else:
            error = None
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return
        if server_rep:
            await server_rep.add_roles(role)
        members = "N/A" if bot else invite.get("approximate_member_count", 0)
        ref("partners", interaction.guild.id).push().set(
            {
                "name": name,
                "invite": code,
                "member_count": members,
                "staff_id": interaction.user.id,
                "timestamp": now(),
                "category": group,
            }
        )
        await update_panel(interaction.client, interaction.guild.id)
        await log(
            interaction,
            "Bot Partner Added" if bot else "Partner Added",
            {
                "Server Name": name,
                "Invite Code": code,
                "Category": group,
                "Member Count": members,
            },
        )
        await interaction.followup.send(
            f"{YES} {'Bot partner' if bot else 'Partner server'} added!",
            ephemeral=True,
        )

    @app_commands.command(name="remove-partner", description="Remove a partner server")
    @app_commands.describe(
        server_name="Server name to remove", invite="Invite link to remove"
    )
    @app_commands.checks.has_permissions(
        manage_webhooks=True, manage_channels=True, manage_messages=True
    )
    async def remove_partner(
        self,
        interaction: discord.Interaction,
        server_name: Optional[str] = None,
        invite: Optional[str] = None,
    ):
        if not server_name and not invite:
            await interaction.response.send_message(
                f"{NO} You must provide either server name or invite link!",
                ephemeral=True,
            )
            return
        partners = ref("partners", interaction.guild.id)
        for key, partner in (partners.get() or {}).items():
            if server_name and partner["name"].lower() != server_name.lower():
                continue
            if invite and partner["invite"] not in invite:
                continue
            break
        else:
            await interaction.response.send_message(
                f"{NO} Partner server not found!", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        partners.child(key).delete()
        await update_panel(interaction.client, interaction.guild.id)
        await log(
            interaction,
            "Partner Removed",
            {
                "Partner ID": key,
                "Server Name": partner["name"],
                "Invite Code": partner["invite"],
            },
        )
        await interaction.followup.send(
            f"{YES} Partner server removed!", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Partner(bot))

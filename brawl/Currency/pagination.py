import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Select, View
from firebase_admin import db

from brawl.Currency.boardcard import PER_PAGE, draw_board
from brawl.Currency.card import faces, render
from brawl.Currency.config import TABLE_SEATS
from brawl.Currency.db import U_ROOT, g_invites_monthly, g_tables, g_user_tables
from brawl.Currency.helper import MAIN_GUILD_ID, NO_EMOTE, get_current_month_key
from brawl.Currency.home import background
from brawl.Currency.panel import notice

# Leaderboard: (title, icon, what one row is)
# title, icon, what is counted, icon before the value, icon before the note
BOARDS = {
    "Beans": ("Most Beans", "kit/bean", "member", "kit/bean", None),
    "Tokens": ("Most Tokens", "kit/token", "member", "kit/token", None),
    "Invites": (
        "Most invites this month",
        "kit/icon_inbox",
        "member",
        "kit/icon_inbox",
        None,
    ),
    "Tables": ("Top tables this week", "kit/icon_trophy", "table", "kit/bean", None),
    "Streaks": (
        "Longest daily streaks",
        "items/streak_insurance",
        "member",
        None,
        None,
    ),
    "Brews": ("Most brews", "brewing", "member", "brewing", None),
    "Levels": ("Highest levels", "kit/icon_xp", "member", None, "kit/icon_xp"),
}


def ranks(member):
    return member is not None and not member.bot


class BasePaginationView(View):
    def __init__(self, pages=None, initial_author=None, timeout=60):
        super().__init__(timeout=timeout)
        self.initial_author = initial_author
        self.page = 0
        self.pages = pages or []
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.initial_author != interaction.user:
            await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} You are not the author of this command.", "bad"
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, Button) and child.style == discord.ButtonStyle.link:
                continue
            child.disabled = True
            if isinstance(child, Select):
                child.options = [
                    discord.SelectOption(
                        label="Disabled due to timeout",
                        value="X",
                        emoji="⛔",
                        default=True,
                    )
                ]
        try:
            if self.message:
                await self.message.edit(view=self)
        except (discord.NotFound, AttributeError):
            pass
        self.stop()

    async def turn(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    def update_buttons(self):
        if len(self.pages) <= 1:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id in [
                    "first_page",
                    "prev_page",
                    "next_page",
                    "last_page",
                ]:
                    child.disabled = True
        else:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    if child.custom_id == "first_page":
                        child.disabled = self.page == 0
                    elif child.custom_id == "prev_page":
                        child.disabled = self.page == 0
                    elif child.custom_id == "next_page":
                        child.disabled = self.page >= len(self.pages) - 1
                    elif child.custom_id == "last_page":
                        child.disabled = self.page >= len(self.pages) - 1

    @discord.ui.button(
        emoji="<:fastbackward:1351972112696479824>",
        style=discord.ButtonStyle.grey,
        custom_id="first_page",
        row=1,
    )
    async def first_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page = 0
        self.update_buttons()
        await self.turn(interaction)

    @discord.ui.button(
        emoji="<:backarrow:1351972111010369618>",
        style=discord.ButtonStyle.grey,
        custom_id="prev_page",
        row=1,
    )
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.page > 0:
            self.page -= 1
        self.update_buttons()
        await self.turn(interaction)

    @discord.ui.button(
        emoji="<:rightarrow:1351972116819480616>",
        style=discord.ButtonStyle.grey,
        custom_id="next_page",
        row=1,
    )
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.page < len(self.pages) - 1:
            self.page += 1
        self.update_buttons()
        await self.turn(interaction)

    @discord.ui.button(
        emoji="<:fastforward:1351972114433048719>",
        style=discord.ButtonStyle.grey,
        custom_id="last_page",
        row=1,
    )
    async def last_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page = len(self.pages) - 1
        self.update_buttons()
        await self.turn(interaction)


class JumpToPageModal(discord.ui.Modal, title="Jump to Page"):
    def __init__(self, view, max_page):
        super().__init__()
        self.view_ref = view
        self.max_page = max_page

        self.page_input = discord.ui.TextInput(
            label="Page Number",
            placeholder=f"Enter a page number (1-{max_page})",
            default=str(view.page + 1),
            min_length=1,
            max_length=len(str(max_page)),
        )
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page_num = int(self.page_input.value)
            if 1 <= page_num <= self.max_page:
                await self.view_ref.show_page(interaction, page_num - 1)
            else:
                await interaction.response.send_message(
                    embed=notice(
                        f"Please enter a valid page number between 1 and {self.max_page}."
                    ),
                    ephemeral=True,
                )
        except ValueError:
            await interaction.response.send_message(
                embed=notice("Please enter a valid number."), ephemeral=True
            )


class LeaderboardView(BasePaginationView):
    """Draws a page only when someone turns to it."""

    def __init__(self, interaction, board, entries):
        pages = range((len(entries) - 1) // PER_PAGE + 1)
        super().__init__(pages=pages, initial_author=interaction.user, timeout=120)
        self.board, self.entries = board, entries
        self.total_pages = len(pages)
        self.update_buttons()

    async def file(self, interaction):
        start = self.page * PER_PAGE
        page = self.entries[start : start + PER_PAGE]
        members = [
            interaction.guild.get_member(entry[0]) if entry[1] is None else None
            for entry in page
        ]
        avatars = await faces(members)
        rows = []
        for rank, entry in enumerate(page, start + 1):
            member_id, name, value, note = entry
            member, avatar = members[rank - start - 1], avatars[rank - start - 1]
            if name is None:
                name = member.display_name if member else "Member who left"
            else:
                avatar = None
            rows.append(
                (rank, name, value, note, member_id == interaction.user.id, avatar)
            )
        board = {**self.board, "rows": rows, "page": self.page + 1}
        return await render(draw_board, board, name="leaderboard")

    async def show_page(self, interaction, page_idx):
        self.page = page_idx
        self.update_buttons()
        files = [await self.file(interaction)]
        if interaction.response.is_done():
            await interaction.edit_original_response(attachments=files, view=self)
        else:
            await interaction.response.edit_message(attachments=files, view=self)

    @discord.ui.button(
        emoji="<:fastbackward:1351972112696479824>",
        style=discord.ButtonStyle.grey,
        custom_id="first_page",
        row=2,
    )
    async def first_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.show_page(interaction, 0)

    @discord.ui.button(
        emoji="<:backarrow:1351972111010369618>",
        style=discord.ButtonStyle.grey,
        custom_id="prev_page",
        row=2,
    )
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.page > 0:
            await self.show_page(interaction, self.page - 1)

    @discord.ui.button(
        label="Jump", style=discord.ButtonStyle.blurple, custom_id="jump_page", row=2
    )
    async def jump_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(JumpToPageModal(self, self.total_pages))

    @discord.ui.button(
        emoji="<:rightarrow:1351972116819480616>",
        style=discord.ButtonStyle.grey,
        custom_id="next_page",
        row=2,
    )
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.page < self.total_pages - 1:
            await self.show_page(interaction, self.page + 1)

    @discord.ui.button(
        emoji="<:fastforward:1351972114433048719>",
        style=discord.ButtonStyle.grey,
        custom_id="last_page",
        row=2,
    )
    async def last_page_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.show_page(interaction, self.total_pages - 1)


class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def economy(self):
        return self.bot.get_cog("CurrencySystem")

    @app_commands.command(
        name="leaderboard",
        description="See who is on top: Beans, Tokens, levels, tables and more",
    )
    @app_commands.choices(
        currency=[
            app_commands.Choice(name="Beans", value="Beans"),
            app_commands.Choice(name="Tokens", value="Tokens"),
            app_commands.Choice(name="Invites this month", value="Invites"),
            app_commands.Choice(name="Tables this week", value="Tables"),
            app_commands.Choice(name="Daily streaks", value="Streaks"),
            app_commands.Choice(name="Brews", value="Brews"),
            app_commands.Choice(name="Levels", value="Levels"),
        ]
    )
    @app_commands.checks.cooldown(rate=1, per=10.0)
    @app_commands.describe(currency="Which leaderboard to view")
    async def leaderboard(self, interaction: discord.Interaction, currency: str):
        await interaction.response.defer(thinking=True)
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.followup.send(
                embed=notice(
                    f"{NO_EMOTE} You do not have permission to use this command.", "bad"
                ),
                ephemeral=True,
            )

        guild = interaction.guild
        users = {
            int(user_id): user
            for user_id, user in (
                (db.reference(U_ROOT).get() or {})
                if currency in ("Beans", "Tokens", "Streaks", "Brews")
                else {}
            ).items()
            if user_id.isdigit()
        }

        def ranked(amount):
            """(member, amount) for everyone above zero, highest first."""
            found = [(user_id, amount(user)) for user_id, user in users.items()]
            return sorted((row for row in found if row[1] > 0), key=lambda row: -row[1])

        if currency == "Tables":
            tables = [
                table
                for table in (g_tables(guild.id).get() or {}).values()
                if table.get("formalized")
            ]
            tables.sort(
                key=lambda table: (
                    -table.get("weekly_beans", 0),
                    -len(table.get("members", [])),
                )
            )
            entries = [
                (
                    None,
                    table["name"],
                    f"{table.get('weekly_beans', 0):,}",
                    f"{len(table.get('members', []))} / {TABLE_SEATS} seats",
                )
                for table in tables
            ]
            mine = (g_user_tables(guild.id, interaction.user.id).get() or "").lower()
            yours = next(
                (
                    rank
                    for rank, table in enumerate(tables, 1)
                    if table["name"].lower() == mine
                ),
                None,
            )
        elif currency == "Invites":
            month = g_invites_monthly(guild.id, get_current_month_key()).get() or {}
            invites = sorted(month.items(), key=lambda row: -row[1].get("valid", 0))
            entries = [
                (
                    int(user_id),
                    None,
                    f"{row.get('valid', 0)}",
                    f"{row.get('total', 0)} joined, {row.get('left', 0)} left",
                )
                for user_id, row in invites
            ]
        elif currency == "Levels":
            leveling_cog = self.bot.get_cog("Leveling")
            if not leveling_cog or not leveling_cog.pool:
                return await interaction.followup.send(
                    embed=notice(
                        f"{NO_EMOTE} Levels are unavailable right now.", "bad"
                    ),
                    ephemeral=True,
                )
            async with leveling_cog.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, xp, level FROM levels WHERE guild = $1 ORDER BY xp DESC LIMIT 2000",
                    str(guild.id),
                )
            entries = [
                (int(row["id"]), None, f"Level {row['level']}", f"{row['xp']:,}")
                for row in rows
            ]
        elif currency == "Streaks":
            entries = [
                (user_id, None, f"{days:,} day{'s' * (days != 1)}", None)
                for user_id, days in ranked(
                    lambda user: user.get("progress", {})
                    .get("daily_checkin_streaks", {})
                    .get("current_streak", 0)
                )
            ]
        elif currency == "Brews":
            entries = [
                (user_id, None, f"{brews:,}", None)
                for user_id, brews in ranked(
                    lambda user: user.get("inventory", {})
                    .get("brews", {})
                    .get("stats", {})
                    .get("total_brews", 0)
                )
            ]
        else:
            entries = [
                (user_id, None, f"{amount:,}", None)
                for user_id, amount in ranked(
                    lambda user: user.get("balance", {}).get(currency, 0)
                )
            ]

        if not guild.chunked:
            await guild.chunk()
        # Members who left keep their data but hold no place on a board.
        entries = [
            entry
            for entry in entries
            if entry[0] is None or ranks(guild.get_member(entry[0]))
        ]
        if not entries:
            return await interaction.followup.send(
                embed=notice(f"{NO_EMOTE} Nobody is on this leaderboard yet.", "bad"),
                ephemeral=True,
            )
        if currency != "Tables":
            yours = next(
                (
                    rank
                    for rank, entry in enumerate(entries, 1)
                    if entry[0] == interaction.user.id
                ),
                None,
            )
        title, icon, unit, value_icon, note_icon = BOARDS[currency]
        count = len(entries)
        view = LeaderboardView(
            interaction,
            {
                "background": background(interaction.user.id),
                "title": title,
                "icon": icon,
                "value_icon": value_icon,
                "note_icon": note_icon,
                "yours": yours,
                "pages": (count - 1) // PER_PAGE + 1,
                "total": f"{count:,} {unit}{'s' * (count != 1)}",
            },
            entries,
        )
        view.message = await interaction.followup.send(
            file=await view.file(interaction), view=view
        )

    @leaderboard.error
    async def leaderboard_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        await interaction.response.send_message(
            embed=notice(f"```{str(error)}```"), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))

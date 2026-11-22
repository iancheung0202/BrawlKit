import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Select, View
from firebase_admin import db

from brawl.Currency.db import (
    U_ROOT,
    g_invites_monthly,
    g_tables,
)
from brawl.Currency.helper import (
    BEAN_EMOTE,
    LB_EMOTE,
    MAIN_GUILD_ID,
    NO_EMOTE,
    TOKEN_EMOTE,
    get_current_month_key,
)


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
                f"{NO_EMOTE} You are not the author of this command.", ephemeral=True
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
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

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
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

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
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

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
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)


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
                    f"Please enter a valid page number between 1 and {self.max_page}.",
                    ephemeral=True,
                )
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number.", ephemeral=True
            )


class LeaderboardView(BasePaginationView):
    def __init__(self, interaction, pages):
        super().__init__(pages=pages, initial_author=interaction.user, timeout=120)
        self.interaction = interaction
        self.total_pages = len(pages)
        self.page = 0
        self.update_buttons()

    async def show_page(self, interaction, page_idx):
        self.page = page_idx
        self.update_buttons()
        embed = self.pages[page_idx]
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

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
        description="View the top users by Beans, Tokens, or Invites",
    )
    @app_commands.choices(
        currency=[
            app_commands.Choice(name="🫘 Starr Beans", value="Beans"),
            app_commands.Choice(name="🌟 Starr Tokens", value="Tokens"),
            app_commands.Choice(name="🫂 Monthly Server Invites", value="Invites"),
            app_commands.Choice(name="🍽️ Weekly Table Beans", value="Tables"),
            app_commands.Choice(name="🔥 Daily Streaks", value="Streaks"),
            app_commands.Choice(name="☕ Coffee Brews", value="Brews"),
            app_commands.Choice(name="📊 XP Levels", value="Levels"),
        ]
    )
    @app_commands.checks.cooldown(rate=1, per=10.0)
    @app_commands.describe(currency="Which leaderboard to view")
    async def leaderboard(self, interaction: discord.Interaction, currency: str):
        await interaction.response.defer(thinking=True)
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.followup.send(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )

        data = []
        formatter = None
        title = ""

        async def get_name(guild, uid):
            if uid == 0:
                return "Unknown"
            member = guild.get_member(uid)
            return member.mention if member else f"<@{uid}>"

        if currency == "Tables":
            all_tables = g_tables(interaction.guild.id).get() or {}
            formalized_tables = {
                name: data
                for name, data in all_tables.items()
                if data.get("formalized", False)
            }

            if not formalized_tables:
                return await interaction.followup.send(
                    f"{NO_EMOTE} No officially recognized tables yet!", ephemeral=True
                )

            data = sorted(
                formalized_tables.items(),
                key=lambda x: (
                    x[1].get("weekly_beans", 0),
                    len(x[1].get("members", [])),
                ),
                reverse=True,
            )
            title = f"Top Tables"

            async def table_formatter(rank, item, guild):
                name, tdata = item
                return (
                    f"**{rank}. {tdata.get('emoji', '')} {tdata.get('name', name)}**\n"
                    f"-# <:reply:1036792837821435976> {BEAN_EMOTE} **`{tdata.get('weekly_beans', 0):,}` Beans**\n"
                    f"-# <:reply:1036792837821435976> `{len(tdata.get('members', []))}/10` people seated\n"
                    f"-# <:reply:1036792837821435976> **Host:** <@{tdata.get('host')}>"
                )

            formatter = table_formatter

        elif currency == "Streaks":
            ref = db.reference(U_ROOT)
            all_users = ref.get() or {}

            for uid_str, user_data in all_users.items():
                if uid_str and uid_str.isdigit():
                    progress = user_data.get("progress", {})
                    sdata = progress.get("daily_checkin_streaks", {})
                    streak = sdata.get("current_streak", 0)
                    if streak > 0:
                        data.append((int(uid_str), streak))

            data.sort(key=lambda x: x[1], reverse=True)
            title = "Top Daily Streaks"

            async def streak_formatter(rank, item, guild):
                uid, streak = item
                name = await get_name(guild, uid)
                return (
                    f"{rank}. {name} - **`{streak}`** day{'s' if streak != 1 else ''}"
                )

            formatter = streak_formatter

        elif currency == "Brews":
            ref = db.reference(U_ROOT)
            all_users = ref.get() or {}

            for uid_str, user_data in all_users.items():
                if uid_str and uid_str.isdigit():
                    inventory = user_data.get("inventory", {})
                    bdata = inventory.get("brews", {})
                    stats = bdata.get("stats", {})
                    total_brews = stats.get("total_brews", 0)
                    if total_brews > 0:
                        data.append((int(uid_str), total_brews))

            data.sort(key=lambda x: x[1], reverse=True)
            title = "Top Brewers"

            async def brew_formatter(rank, item, guild):
                uid, brews = item
                name = await get_name(guild, uid)
                return (
                    f"{rank}. {name} - **`{brews:,}`** brew{'s' if brews != 1 else ''}"
                )

            formatter = brew_formatter

        elif currency == "Invites":
            current_month = get_current_month_key()
            ref = g_invites_monthly(interaction.guild.id, current_month)
            all_data = ref.get() or {}

            if not all_data:
                return await interaction.followup.send(
                    f"{NO_EMOTE} No invite data available yet", ephemeral=True
                )

            inv_data = []
            for uid_str, idata in all_data.items():
                inv_data.append((uid_str, idata))

            data = sorted(inv_data, key=lambda x: x[1].get("valid", 0), reverse=True)
            title = "Top Monthly Inviters"

            async def invite_formatter(rank, item, guild):
                uid_str, idata = item
                name = await get_name(guild, int(uid_str))
                valid = idata.get("valid", 0)
                total = idata.get("total", 0)
                left = idata.get("left", 0)
                return f"{rank}. {name} - **`{valid}` invite{'s' if valid > 1 else ''}** (`{total}` total, `{left}` left)"

            formatter = invite_formatter

        elif currency == "Levels":
            leveling_cog = self.bot.get_cog("Leveling")
            if not leveling_cog or not leveling_cog.pool:
                return await interaction.followup.send(
                    f"{NO_EMOTE} Leveling system is currently unavailable.",
                    ephemeral=True,
                )

            async with leveling_cog.pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, xp, level FROM levels WHERE guild = $1 ORDER BY xp DESC LIMIT 2000",
                    str(interaction.guild.id),
                )

            data = rows
            title = "Top Level XP"

            async def level_formatter(rank, item, guild):
                uid = int(item["id"])
                name = await get_name(guild, uid)
                level = item["level"]
                xp = item["xp"]
                return f"{rank}. {name} - **Level {level}** (`{xp:,}` XP)"

            formatter = level_formatter

        else:  # Beans or Tokens
            ref = db.reference(U_ROOT)
            all_users = ref.get() or {}

            target_field = currency

            for uid_str, user_data in all_users.items():
                if uid_str and uid_str.isdigit():
                    bdata = user_data.get("balance", {})
                    amount = bdata.get(target_field, 0)
                    data.append((int(uid_str), amount))

            data.sort(key=lambda x: x[1], reverse=True)
            emoji = BEAN_EMOTE if currency == "Beans" else TOKEN_EMOTE
            title = f"Top Starr {currency} Holders {emoji}"

            async def balance_formatter(rank, item, guild):
                uid, amt = item
                name = await get_name(guild, uid)
                return f"{rank}. {name} - {emoji} `{amt:,}` Starr {currency}"

            formatter = balance_formatter

        if not data:
            return await interaction.followup.send(
                f"{NO_EMOTE} No data available for this leaderboard.", ephemeral=True
            )

        pages = []
        per_page = 10
        total_pages = (len(data) - 1) // per_page + 1

        user_rank = "N/A"
        try:
            if currency == "Levels":
                rnk = next(
                    (
                        i
                        for i, x in enumerate(data)
                        if int(x["id"]) == interaction.user.id
                    ),
                    None,
                )
            elif currency == "Invites":
                rnk = next(
                    (i for i, x in enumerate(data) if int(x[0]) == interaction.user.id),
                    None,
                )
            elif currency == "Tables":
                rnk = None
            else:
                rnk = next(
                    (
                        i
                        for i, x in enumerate(data)
                        if hasattr(x, "__getitem__") and x[0] == interaction.user.id
                    ),
                    None,
                )

            if rnk is not None:
                user_rank = f"#{rnk + 1}"
        except Exception:
            pass

        for page_num in range(total_pages):
            start = page_num * per_page
            end = start + per_page
            current_data = data[start:end]

            description = ""
            for i, item in enumerate(current_data, start + 1):
                try:
                    line = await formatter(i, item, interaction.guild)
                    description += f"{line}\n"
                except Exception as e:
                    print(f"Error formatting leaderboard item: {e}")
                    continue

            embed = discord.Embed(
                title=f"{LB_EMOTE} {title}", description=description, color=0xF1C40F
            )
            footer_text = f"Page {page_num + 1}/{total_pages} • Total: {len(data)}"
            if user_rank != "N/A":
                footer_text += f" • Your Rank: {user_rank}"

            embed.set_footer(text=footer_text)
            pages.append(embed)

        view = LeaderboardView(interaction, pages)
        view.message = await interaction.followup.send(embed=pages[0], view=view)

    @leaderboard.error
    async def leaderboard_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))

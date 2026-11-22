import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency import quests as daily_order
from brawl.Currency.card import BACKGROUND, render
from brawl.Currency.config import BACKGROUNDS, LADDER
from brawl.Currency.db import (
    u_background,
    u_customization,
    u_daily_checkin_streaks,
    u_mega_boxes,
    u_pin_message,
    u_star_drops,
)
from brawl.Currency.factions import table_card
from brawl.Currency.helper import (
    EFFECT_EMOTE,
    INVITES_EMOTE,
    MAIN_GUILD_ID,
    NO_EMOTE,
    OVERVIEW_EMOTE,
    SERVER_STORE,
    STAMP_EMOTE,
    STORE_ITEMS,
    TABLE_EMOTE,
    YES_EMOTE,
)
from brawl.Currency.home import background, draw_home
from brawl.Currency.invitecard import INVITE_HELP, draw_invites, invited_by, summary
from brawl.Currency.itemcard import draw_inventory
from brawl.Currency.ladder import locked, unlocked
from brawl.Currency.levels import get_level
from brawl.Currency.panel import notice
from brawl.Currency.quests import order_tasks, update_quest
from brawl.Currency.shopcard import clean
from brawl.Currency.stampcard import stamps

HOME_STATIONS = {"table_info": "tables"}
PAGES = ("overview", "stampcard", "effect_info", "balance_invites", "table_info")


def progress(name, task, done):
    return (
        name,
        "Done" if done else f"{task['current']:,} / {task['goal']:,}",
        done,
        1 if done else task["current"] / task["goal"],
    )


class BalanceInfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.message = None

    async def on_timeout(self) -> None:
        for child in self.children:
            if (
                isinstance(child, discord.ui.Button)
                and child.style == discord.ButtonStyle.link
            ):
                continue
            child.disabled = True
            if isinstance(child, discord.ui.Select):
                child.options = [
                    discord.SelectOption(
                        label="Disabled due to timeout",
                        value="X",
                        emoji="⛔",
                        default=True,
                    )
                ]
        try:
            if hasattr(self, "message") and self.message:
                await self.message.edit(view=self)
        except (discord.NotFound, AttributeError, discord.HTTPException):
            pass

    def _remove_selects(self):
        to_remove = []
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                to_remove.append(child)
            elif getattr(child, "url", None) == INVITE_HELP:
                to_remove.append(child)
            elif getattr(child, "custom_id", "") == "bsort_select":
                to_remove.append(child)
        for child in to_remove:
            self.remove_item(child)

    def mark(self, current):
        """The button of the page on screen is the blurple one."""
        for child in self.children:
            if getattr(child, "custom_id", None) in PAGES:
                child.style = (
                    discord.ButtonStyle.blurple
                    if child is current
                    else discord.ButtonStyle.grey
                )

    @discord.ui.button(
        style=discord.ButtonStyle.blurple,
        emoji=OVERVIEW_EMOTE,
        custom_id="overview",
        label="Overview",
    )
    async def overview(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = int(
            interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
        )
        if interaction.user.id != user_id:
            return await interaction.response.send_message(
                embed=notice("This is not your command."), ephemeral=True
            )
        self._remove_selects()
        self.mark(button)
        home = interaction.client.get_cog("Balance")
        await interaction.response.edit_message(
            attachments=[await home.home_card(interaction.user, interaction.guild)],
            embed=None,
            view=self,
        )

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji=STAMP_EMOTE,
        custom_id="stampcard",
        label="Stamp Card",
    )
    async def stampcard_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = int(
            interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
        )
        if interaction.user.id != user_id:
            return await interaction.response.send_message(
                embed=notice("This is not your command."), ephemeral=True
            )
        stamp_cog = interaction.client.get_cog("StampCard")
        if not stamp_cog:
            return await interaction.response.send_message(
                embed=notice("Stamp Card system unavailable."), ephemeral=True
            )
        self._remove_selects()
        self.mark(button)
        await interaction.response.edit_message(
            attachments=[await stamp_cog.card(interaction.user, interaction.guild)],
            embed=None,
            view=self,
        )

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        custom_id="effect_info",
        emoji=EFFECT_EMOTE,
        label="Inventory",
    )
    async def effect_info(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = int(
            interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
        )
        if interaction.user.id != user_id:
            return await interaction.response.send_message(
                embed=notice("This is not your command. You cannot use this button."),
                ephemeral=True,
            )

        economy = interaction.client.get_cog("CurrencySystem")
        active = await economy.effect_manager.get_user_active_effects(user_id)
        member = {
            "background": background(user_id),
            "held": {
                "star_drops": u_star_drops(user_id).get(),
                "mega_boxes": u_mega_boxes(user_id).get(),
                "pins": (u_pin_message(user_id).get() or {}).get("count"),
                "credits": (u_customization(user_id).get() or {}).get("credits"),
            },
            "effects": [
                {
                    "item": item,
                    "name": STORE_ITEMS[item]["name"],
                    "expires_at": data.get("expires_at", 0),
                }
                for item, data in active.items()
                if item in STORE_ITEMS
                and not (
                    item == "streak_insurance" and data.get("uses_remaining", 0) <= 0
                )
            ],
        }
        self._remove_selects()
        self.mark(button)
        await interaction.response.edit_message(
            attachments=[
                await render(draw_inventory, member, name=f"balance_{user_id}")
            ],
            embed=None,
            view=self,
        )

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji=INVITES_EMOTE,
        custom_id="balance_invites",
        label="Invites",
    )
    async def balance_invites(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = int(
            interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
        )
        if interaction.user.id != user_id:
            return await interaction.response.send_message(
                embed=notice("This is not your command. You cannot use this button."),
                ephemeral=True,
            )

        months = sorted(invited_by(interaction.guild.id, user_id), reverse=True)[:25]
        self._remove_selects()
        self.mark(button)
        if months:
            from brawl.Currency.invitetracker import MonthSelect

            select = MonthSelect(interaction.user, months)
            select.row = 2
            self.add_item(select)
        else:
            self.add_item(
                discord.ui.Button(label="How to invite", url=INVITE_HELP, row=1)
            )
        await interaction.response.edit_message(
            attachments=[
                await render(
                    draw_invites,
                    summary(interaction.guild.id, user_id),
                    name=f"balance_{user_id}",
                )
            ],
            embed=None,
            view=self,
        )

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji=TABLE_EMOTE,
        custom_id="table_info",
        label="Table",
    )
    async def table_info(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            user_id = int(
                interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
            )
        except (IndexError, ValueError):
            user_id = interaction.user.id
        if interaction.user.id != user_id:
            return await interaction.response.send_message(
                embed=notice("This is not your command."), ephemeral=True
            )
        table_cog = interaction.client.get_cog("table")
        table = table_cog and await table_cog.get_user_table(
            user_id, interaction.guild.id
        )
        if not table:
            return await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} You're not seated at a table. Join one with `/table seat` or start one with `/table reserve`.",
                    "bad",
                ),
                ephemeral=True,
            )
        self._remove_selects()
        self.mark(button)
        await interaction.response.edit_message(
            attachments=[
                await table_card(table, interaction, name=f"balance_{user_id}")
            ],
            embed=None,
            view=self,
        )


class ConfirmBackground(discord.ui.View):
    """The preview's Confirm button: only pressing it saves the background and spends the credit."""

    def __init__(self, cog, background, allowed):
        super().__init__(timeout=300)
        self.cog, self.background = cog, background
        self.confirm.disabled = not allowed

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button):
        user_id, name = interaction.user.id, self.background.name
        self.stop()
        if self.background.value == BACKGROUND:
            u_background(user_id).delete()
            return await interaction.response.edit_message(
                content=None,
                embed=notice(
                    f"{YES_EMOTE} Your home card is back on the default **{name}** background.",
                    "good",
                ),
                view=None,
            )
        ref = u_customization(user_id)
        credits = (ref.get() or {}).get("credits", 0)
        if credits < 1:
            return await interaction.response.edit_message(
                content=None,
                embed=notice(
                    f"{NO_EMOTE} You need 1 Customization Credit. "
                    "Get one with </buy:1393376242501157010>.",
                    "bad",
                ),
                view=None,
            )
        ref.update({"credits": credits - 1})
        u_background(user_id).set(self.background.value)
        await interaction.response.edit_message(
            content=None,
            embed=notice(
                f"{YES_EMOTE} Your home card now uses the **{name}** background. "
                f"Credits left: `{credits - 1}`.",
                "good",
            ),
            view=None,
        )


class Balance(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def economy(self):
        return self.bot.get_cog("CurrencySystem")

    async def member(self, user, guild):
        await update_quest(user.id, guild.id, {}, self.bot, refresh_only=True)
        beans, tokens = await self.economy.get_balance(user.id)
        xp = 0
        leveling = self.bot.get_cog("Leveling")
        if leveling and leveling.pool:
            xp = await leveling.pool.fetchval(
                "SELECT xp FROM levels WHERE id = $1 AND guild = $2",
                str(user.id),
                str(guild.id),
            )
        level, xp, xp_needed = get_level(xp or 0)
        try:
            avatar = await user.display_avatar.replace(size=128).read()
        except Exception:
            avatar = b""
        return {
            "name": user.display_name,
            "avatar": avatar,
            "level": level,
            "xp": xp,
            "xp_needed": xp_needed,
            "beans": beans,
            "tokens": tokens,
            "tasks": [
                progress(name, task, done)
                for _, name, task, done in order_tasks(user.id)
            ],
            "store": clean(getattr(guild.get_channel(SERVER_STORE), "name", "store")),
            "brew": await self.economy.get_active_brew(user.id),
            "brewing": await unlocked(self.bot, user.id, guild.id, "brewing"),
            "stamps": stamps(user.id),
            "streak": (u_daily_checkin_streaks(user.id).get() or {}).get(
                "current_streak", 0
            ),
            "background": background(user.id),
        }

    async def home_card(self, user, guild, background=None):
        member = await self.member(user, guild)
        member["background"] = background or member["background"]
        return await render(draw_home, member, name=f"balance_{user.id}")

    @app_commands.command(
        name="balance",
        description="Open your cafe home: level, Beans, Tokens, order and Stamp Card",
    )
    async def balance(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                embed=notice(f"{NO_EMOTE} Not available here.", "bad"), ephemeral=True
            )
        await interaction.response.defer(thinking=True)
        view = BalanceInfoView()
        for button in view.children:
            station = HOME_STATIONS.get(button.custom_id)
            if station and not await unlocked(
                self.bot, interaction.user.id, interaction.guild.id, station
            ):
                button.disabled = True
                button.label = f"{button.label} (Level {LADDER[station][0]})"
        if not daily_order.clocked_in(interaction.user.id):
            view.add_item(
                discord.ui.Button(
                    emoji="🗓️",
                    label="Go clock in",
                    url=f"https://discord.com/channels/{interaction.guild.id}/{SERVER_STORE}",
                    row=1,
                )
            )
        view.message = await interaction.followup.send(
            file=await self.home_card(interaction.user, interaction.guild), view=view
        )

    @balance.error
    async def balance_error(self, interaction: discord.Interaction, error: Exception):
        print(f"Error in balance: {error}")

    @app_commands.command(
        name="customize",
        description="Pick the background of your home card (uses 1 Customization Credit)",
    )
    @app_commands.describe(background="The background to use")
    @app_commands.choices(
        background=[
            app_commands.Choice(name=name, value=key)
            for key, name in BACKGROUNDS.items()
        ]
    )
    @app_commands.checks.cooldown(rate=1, per=30.0)
    async def customize(
        self, interaction: discord.Interaction, background: app_commands.Choice[str]
    ):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                embed=notice(f"{NO_EMOTE} Not available here.", "bad"), ephemeral=True
            )
        if await locked(interaction, "style"):
            return
        user_id = interaction.user.id
        free = background.value == BACKGROUND
        credits = (u_customization(user_id).get() or {}).get("credits", 0)
        await interaction.response.defer(ephemeral=True, thinking=True)
        if free:
            note = "This is the default background, so it is free."
        elif credits < 1:
            note = (
                "You need 1 Customization Credit to use it. "
                "Get one with </buy:1393376242501157010>."
            )
        else:
            note = f"Confirm uses 1 Customization Credit. You have `{credits}`."
        await interaction.followup.send(
            embed=notice(
                f"This is your home card with the {background.name} background. {note}"
            ),
            file=await self.home_card(
                interaction.user, interaction.guild, background.value
            ),
            view=ConfirmBackground(self, background, free or credits >= 1),
            ephemeral=True,
        )

    @customize.error
    async def customize_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            embed=notice(f"{NO_EMOTE} Something went wrong: {error}", "bad"),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Balance(bot))

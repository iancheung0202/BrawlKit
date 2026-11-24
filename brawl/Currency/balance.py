import time

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency import boss, heat
from brawl.Currency import quests as daily_order
from brawl.Currency.bag import held
from brawl.Currency.balancecard import (
    draw_chat,
    draw_community,
    draw_counter,
    draw_header,
    draw_inventory,
    draw_stamps,
)
from brawl.Currency.card import BACKGROUND, render, roster
from brawl.Currency.chat import chat_limit, chat_today
from brawl.Currency.config import BACKGROUNDS
from brawl.Currency.db import (
    u_background,
    u_customization,
    u_daily_chat_earnings,
    u_mega_boxes,
    u_pin_message,
    u_star_drops,
)
from brawl.Currency.helper import (
    CALENDAR_EMOTE,
    EFFECT_EMOTE,
    MAIN_GUILD_ID,
    NO_EMOTE,
    OVERVIEW_EMOTE,
    SERVER_STORE,
    STORE_ITEMS,
    TABLE_EMOTE,
    YES_EMOTE,
)
from brawl.Currency.home import background
from brawl.Currency.invitecard import INVITE_HELP, invited_by, summary
from brawl.Currency.ladder import locked, unlocked
from brawl.Currency.levels import get_level
from brawl.Currency.panel import notice
from brawl.Currency.quests import get_next_daily_reset, order_tasks, update_quest
from brawl.Currency.shopcard import clean
from brawl.Currency.stampcard import stamps
from brawl.Currency.tables import seated
from brawl.TeamFinder.reputationSystem import paid_today, rep_of
from brawl.Utility.topic import approved_by

# Each page of /balance: its place, the button's label and its emoji.
PAGES = (
    ("COUNTER", "Counter", OVERVIEW_EMOTE),
    ("CHAT", "Chat", "\N{SPEECH BALLOON}"),
    ("INVENTORY", "Inventory", EFFECT_EMOTE),
    ("COMMUNITY", "Community", TABLE_EMOTE),
)


def progress(name, task, done):
    return (
        name,
        "Done" if done else f"{task['current']:,} / {task['goal']:,}",
        done,
        1 if done else task["current"] / task["goal"],
    )


class BalanceView(discord.ui.LayoutView):
    """One page of /balance: its cards in a container, then a button per page."""

    def __init__(self, cog, user, place, files, extras=()):
        super().__init__(timeout=180)
        self.cog, self.user, self.message = cog, user, None
        container = discord.ui.Container(
            *(
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(f"attachment://{file.filename}")
                )
                for file in files
            )
        )
        row = discord.ui.ActionRow()
        for name, label, emoji in PAGES:
            button = discord.ui.Button(
                style=(
                    discord.ButtonStyle.blurple
                    if name == place
                    else discord.ButtonStyle.grey
                ),
                emoji=emoji,
                label=label,
                custom_id=f"balance_{name.lower()}",
            )
            button.callback = self.open(name)
            row.add_item(button)
        container.add_item(row)
        for extra in extras:
            container.add_item(discord.ui.ActionRow(extra))
        self.add_item(container)

    def open(self, place):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user.id:
                return await interaction.response.send_message(
                    embed=notice("This is not your command."), ephemeral=True
                )
            await interaction.response.defer()
            view, files = await self.cog.page(self.user, interaction.guild, place)
            view.message = self.message
            self.stop()
            await interaction.edit_original_response(view=view, attachments=files)

        return callback

    async def on_timeout(self) -> None:
        for child in self.walk_children():
            if isinstance(child, discord.ui.Select) or (
                isinstance(child, discord.ui.Button) and not child.url
            ):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except discord.HTTPException:
            pass


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
        """What every page's header shows, and the Counter under it."""
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
        return {
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
            "background": background(user.id),
        }

    async def chat(self, user, guild):
        effects = await self.economy.effect_manager.get_user_active_effects(user.id)
        drops, resets = heat.drops(user.id)
        cup = {
            "heat": self.economy.thermometer_heat,
            "drops": drops,
            "resets": resets,
            "beans": heat.beans_today(user.id),
        }
        frozen = heat.freeze(guild.id)
        if frozen:
            by = (await roster(guild, [frozen[0]]))[0]
            minutes = max(1, round((frozen[1]["expires_at"] - time.time()) / 60))
            cup["frozen"] = (by.display_name if by else "someone", minutes)
        saved = (u_daily_chat_earnings(user.id).get() or {}).get("reset_time", 0)
        return {
            "chat": (chat_today(user.id), chat_limit(user, effects)),
            "chat_resets": saved if saved > time.time() else get_next_daily_reset(),
            "cup": cup,
            "boss": boss.visits(user.id, guild.id),
            "boss_locked": not await unlocked(self.bot, user.id, guild.id, "boss"),
        }

    async def inventory(self, user):
        active = await self.economy.effect_manager.get_user_active_effects(user.id)
        return {
            "held": {
                "star_drops": u_star_drops(user.id).get(),
                "mega_boxes": u_mega_boxes(user.id).get(),
                "pins": (u_pin_message(user.id).get() or {}).get("count"),
                "credits": (u_customization(user.id).get() or {}).get("credits"),
            },
            "bag": held(user.id),
            "effects": [
                {"item": item, "expires_at": data.get("expires_at", 0)}
                for item, data in active.items()
                if item in STORE_ITEMS
                and not (
                    item == "streak_insurance" and data.get("uses_remaining", 0) <= 0
                )
            ],
        }

    async def community(self, user, guild):
        tables = self.bot.get_cog("table")
        table = tables and await tables.get_user_table(user.id, guild.id)
        return {
            "table": await seated(table, guild, user.id) if table else None,
            "invites": summary(guild.id, user.id),
            "rep": rep_of(user.id),
            "rep_paid": paid_today(user.id),
            "topics": approved_by(user.id),
        }

    async def page(self, user, guild, place):
        """The view and files of one page, drawn now."""
        member = await self.member(user, guild)
        extras = []
        if place == "COUNTER":
            member["scene"] = member["background"]
            member.update(await self.bot.get_cog("StampCard").summary(user, guild))
            cards = [(draw_counter, member), (draw_stamps, member)]
            if not daily_order.clocked_in(user.id):
                extras.append(
                    discord.ui.Button(
                        emoji=CALENDAR_EMOTE,
                        label="Go clock in",
                        url=f"https://discord.com/channels/{guild.id}/{SERVER_STORE}",
                    )
                )
        elif place == "CHAT":
            cards = [(draw_chat, await self.chat(user, guild))]
        elif place == "INVENTORY":
            cards = [(draw_inventory, await self.inventory(user))]
        else:
            cards = [(draw_community, await self.community(user, guild))]
            months = sorted(invited_by(guild.id, user.id), reverse=True)[:25]
            if months:
                from brawl.Currency.invitetracker import MonthSelect

                extras.append(MonthSelect(user, months))
            else:
                extras.append(discord.ui.Button(label="How to invite", url=INVITE_HELP))
        files = [
            await render(draw, *args, name=f"balance_{user.id}_{spot}")
            for spot, (draw, *args) in enumerate([(draw_header, place, member), *cards])
        ]
        return BalanceView(self, user, place, files, extras), files

    async def home_card(self, user, guild, background=None):
        """The Counter on a background, to preview one before it is bought."""
        member = await self.member(user, guild)
        member["background"] = background or member["background"]
        return await render(draw_counter, member, name=f"balance_{user.id}")

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
        view, files = await self.page(interaction.user, interaction.guild, "COUNTER")
        view.message = await interaction.followup.send(view=view, files=files)

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

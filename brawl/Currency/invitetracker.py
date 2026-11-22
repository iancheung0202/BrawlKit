import asyncio
import json
import os
import time

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency.card import render
from brawl.Currency.config import TUTORIAL_BEANS
from brawl.Currency.db import (
    g_invites_member_data,
    g_invites_monthly,
    g_member_history,
    u_recent_join,
    u_welcome_cooldown,
)
from brawl.Currency.helper import (
    BEAN_EMOTE,
    GENERAL_CHAT,
    INVITE_LOG,
    MAX_BUTTON_WELCOMES,
    NO_EMOTE,
    WELCOME_BUTTON_REWARD,
    YES_EMOTE,
    get_current_month_key,
)
from brawl.Currency.invitecard import draw_invitees, invited_by, invitees, month_name
from brawl.Currency.tutorial import TutorialManager, hint, shift


class WelcomeView(discord.ui.View):
    def __init__(self, member, bot):
        super().__init__(timeout=600)  # 5 mins
        self.member = member
        self.bot = bot
        self.welcomed_by = set()

    @discord.ui.button(
        label="Clock In",
        style=discord.ButtonStyle.blurple,
        emoji="🗓️",
        custom_id="clock_in",
    )
    async def clock_in(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.bot.get_cog("Daily").process_daily(interaction)

    @discord.ui.button(
        label="Welcome!",
        style=discord.ButtonStyle.green,
        emoji="<:pandaHappy:855019705836240916>",
    )
    async def welcome_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id == self.member.id:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description="💚 You can't welcome yourself! 😅 Thanks for joining our server though!",
                    color=discord.Color.pink(),
                ),
                ephemeral=True,
            )
        if interaction.user.id in self.welcomed_by:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"💚 You have already welcomed {self.member.mention}!",
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )
        cooldown_ref = u_welcome_cooldown(interaction.user.id)
        last_welcome = cooldown_ref.get() or 0
        current_time = time.time()

        if current_time - last_welcome < 300:
            expire_time = int(current_time + (300 - (current_time - last_welcome)))
            return await interaction.response.send_message(
                f"⏰ You have already welcomed another new member not long ago. Try again <t:{expire_time}:R>",
                ephemeral=True,
            )
        self.welcomed_by.add(interaction.user.id)
        cooldown_ref.set(current_time)
        if len(self.welcomed_by) <= MAX_BUTTON_WELCOMES:
            currency_cog = self.bot.get_cog("CurrencySystem")
            if currency_cog:
                await currency_cog.add_beans(
                    interaction.user.id, WELCOME_BUTTON_REWARD, skip_quest_check=True
                )
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"🎉 Thanks for welcoming {self.member.mention}! You earned <:StarrBean:1393442086279315456> **{WELCOME_BUTTON_REWARD} Beans**",
                        color=discord.Color.green(),
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"{YES_EMOTE} Thanks for welcoming {self.member.mention}!",
                        color=discord.Color.green(),
                    ),
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"💚 Thanks for welcoming {self.member.mention}! (Reward limit reached for this new member)",
                    color=discord.Color.yellow(),
                ),
                ephemeral=True,
            )
        button.label = f"Welcomed by {len(self.welcomed_by)} member{'s' if len(self.welcomed_by) != 1 else ''}"
        if len(self.welcomed_by) >= MAX_BUTTON_WELCOMES:
            button.disabled = True
            button.style = discord.ButtonStyle.gray

        await interaction.message.edit(view=self)

    async def on_timeout(self):
        for item in self.children:
            if item.custom_id != "clock_in":
                item.disabled = True
                if len(self.welcomed_by) > 0:
                    item.label = f"Welcomed by {len(self.welcomed_by)} member{'s' if len(self.welcomed_by) != 1 else ''}"
                else:
                    item.label = "Welcome period ended"
                item.style = discord.ButtonStyle.gray


class InviteTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_cache = {}
        self.tracked_guild_id = 791534106919305226
        self.cache_lock = asyncio.Lock()
        self.bot.loop.create_task(self.startup_refresh())
        self.member_history_file = "brawl/Currency/member_history.json"
        self.member_history = self.load_member_history()
        os.makedirs(os.path.dirname(self.member_history_file), exist_ok=True)

    def load_member_history(self):
        try:
            if os.path.exists(self.member_history_file):
                with open(self.member_history_file, "r") as f:
                    return set(json.load(f))
            return set()
        except (json.JSONDecodeError, FileNotFoundError):
            return set()

    def save_member_history(self):
        with open(self.member_history_file, "w") as f:
            json.dump(list(self.member_history), f)

    async def startup_refresh(self):
        await self.bot.wait_until_ready()
        guild = await self.bot.fetch_guild(self.tracked_guild_id)
        if not guild:
            return
        try:
            invites = await guild.invites()
            async with self.cache_lock:
                self.invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
        except discord.Forbidden:
            print(f"Missing permissions to fetch invites in {guild.name}")

    @commands.Cog.listener()
    async def on_ready(self):
        guild = await self.bot.fetch_guild(self.tracked_guild_id)
        if not guild:
            return
        self.member_history.update(member.id for member in guild.members)
        self.save_member_history()

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if invite.guild.id != self.tracked_guild_id:
            return
        async with self.cache_lock:
            if invite.guild.id not in self.invite_cache:
                self.invite_cache[invite.guild.id] = {}
            self.invite_cache[invite.guild.id][invite.code] = getattr(invite, "uses", 0)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild.id != self.tracked_guild_id:
            return
        async with self.cache_lock:
            if (
                invite.guild.id in self.invite_cache
                and invite.code in self.invite_cache[invite.guild.id]
            ):
                del self.invite_cache[invite.guild.id][invite.code]

    async def log_invite_action(self, message: str):
        if channel := self.bot.get_channel(INVITE_LOG):
            await channel.send(message)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.guild.id != self.tracked_guild_id:
            return

        guild = member.guild
        member_id = str(member.id)
        current_month = get_current_month_key()

        if member.bot:
            g_invites_member_data(guild.id, member_id).set(
                {"inviter": None, "code": "oauth", "join_month": current_month}
            )
            await self.log_invite_action(f"{member.mention} joined via OAuth.")
            return
        try:
            vanity_code = (await guild.vanity_invite()).code
        except (discord.Forbidden, AttributeError):
            vanity_code = None
        async with self.cache_lock:
            try:
                current_invites = await guild.invites()
            except discord.Forbidden:
                current_invites = []
            cached = self.invite_cache.get(guild.id, {})
            new_cache = {}
            increased_invites = []
            for inv in current_invites:
                new_cache[inv.code] = inv.uses
                if inv.uses > cached.get(inv.code, 0):
                    increased_invites.append((inv, inv.uses - cached.get(inv.code, 0)))
            self.invite_cache[guild.id] = new_cache
            used_invite = (
                increased_invites[0][0]
                if len(increased_invites) == 1 and increased_invites[0][1] == 1
                else None
            )
        is_new = member.id not in self.member_history
        if is_new:
            self.member_history.add(member.id)
            self.save_member_history()
            guide = await TutorialManager(self.bot).start(member)

        if used_invite and used_invite.inviter:
            inviter_id = str(used_invite.inviter.id)
            monthly_ref = g_invites_monthly(guild.id, current_month, inviter_id)
            monthly_data = monthly_ref.get() or {"total": 0, "left": 0, "valid": 0}
            monthly_data["total"] += 1
            monthly_data["valid"] += 1
            monthly_ref.set(monthly_data)
            g_invites_member_data(guild.id, member_id).set(
                {
                    "inviter": inviter_id,
                    "code": used_invite.code,
                    "join_month": current_month,
                    "is_new": is_new,
                    "brew_done": False,
                    "sell_done": False,
                }
            )

            await self.log_invite_action(
                f"{member.mention} has been invited by {used_invite.inviter.display_name} ({used_invite.inviter.id}) and now has `{monthly_data['valid']}` valid monthly invites."
            )
        else:
            code = "vanity" if vanity_code else "unknown"
            g_invites_member_data(guild.id, member_id).set(
                {
                    "inviter": None,
                    "code": code,
                    "join_month": current_month,
                    "is_new": is_new,
                    "brew_done": False,
                    "sell_done": False,
                }
            )
            msg = (
                f"{member.mention} joined using a vanity invite."
                if vanity_code
                else f"{member.name} joined, but the invite could not be determined."
            )
            await self.log_invite_action(msg)
        ref_history = g_member_history(guild.id, member_id)
        history = ref_history.get() or {"first_join": current_month}
        history["last_join"] = current_month
        ref_history.set(history)
        u_recent_join(member.id).set(time.time())
        welcome_channel = self.bot.get_channel(GENERAL_CHAT)
        if welcome_channel:
            if is_new:
                await welcome_channel.send(
                    f"### {member.mention} just joined <:pandaHappy:855019705836240916> ~ please give them a warm welcome! <:PumpkinLove:1391457782061990099>\n"
                    f"Welcome, {member.mention}! Here are {BEAN_EMOTE} **{TUTORIAL_BEANS}** to start.\n"
                    f"-# {hint(guide)}",
                    view=WelcomeView(member, self.bot),
                    file=await shift(guide, member.id),
                )
            else:
                await welcome_channel.send(
                    f"### {member.mention} is back! <:pandaHappy:855019705836240916> ~ welcome back to the server!"
                )

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.guild.id != self.tracked_guild_id:
            return
        member_id = str(member.id)
        ref_mapping = g_invites_member_data(member.guild.id, member_id)
        mapping_data = ref_mapping.get()
        if (
            mapping_data
            and (inviter_id := mapping_data.get("inviter"))
            and (join_month := mapping_data.get("join_month"))
        ):
            monthly_ref = g_invites_monthly(member.guild.id, join_month, inviter_id)
            if monthly_data := monthly_ref.get():
                monthly_data["left"] += 1
                monthly_data["valid"] = max(monthly_data["valid"] - 1, 0)
                monthly_ref.set(monthly_data)
                await self.log_invite_action(
                    f"{member.name} left the server (Invited by <@{inviter_id}> in `{join_month}`, now has `{monthly_data['valid']}` valid invites)."
                )
        else:
            await self.log_invite_action(
                f"{member.name} left the server. They joined using the vanity invite."
            )
        ref_mapping.delete()

    @app_commands.command(
        name="addinvites", description="Add invites to a user (Admin only)"
    )
    @app_commands.describe(
        user="User to add invites to", amount="Number of invites to add"
    )
    @app_commands.default_permissions(administrator=True)
    async def add_invites(
        self, interaction: discord.Interaction, user: discord.User, amount: int
    ):
        if interaction.guild.id != self.tracked_guild_id:
            return await interaction.response.send_message(
                "🚫 You can't use this here.", ephemeral=True
            )
        if amount <= 0:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Amount must be positive.", ephemeral=True
            )
        current_month = get_current_month_key()
        ref = g_invites_monthly(interaction.guild.id, current_month, user.id)
        data = ref.get() or {"total": 0, "left": 0, "valid": 0}
        data["total"] += amount
        data["valid"] += amount
        ref.set(data)
        await interaction.response.send_message(
            f"{YES_EMOTE} Added **{amount}** invites to {user.mention} for {current_month}",
            ephemeral=True,
        )


class InviteeProgressView(discord.ui.View):
    def __init__(self, bot, inviter, months):
        super().__init__(timeout=300)
        self.bot = bot
        self.inviter = inviter
        self.months = months
        self.add_item(MonthSelect(inviter, months))


class MonthSelect(discord.ui.Select):
    def __init__(self, inviter, months):
        self.inviter = inviter
        options = [
            discord.SelectOption(label=month_name(month), value=month)
            for month in months
        ]
        super().__init__(placeholder="See who you invited", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.inviter:
            return await interaction.response.send_message(
                "This is not your command.", ephemeral=True
            )
        economy = interaction.client.get_cog("CurrencySystem")
        if not economy:
            return await interaction.response.send_message(
                "The Cafe is closed right now. Try again in a minute.", ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        month = self.values[0]
        people = invited_by(interaction.guild.id, self.inviter.id).get(month)
        if not people:
            return await interaction.followup.send(
                f"You invited no one in {month_name(month)}.", ephemeral=True
            )
        card = await invitees(
            economy, interaction.guild, self.inviter.id, month, people
        )
        await interaction.followup.send(
            file=await render(draw_invitees, card, name="invites"), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(InviteTracker(bot))

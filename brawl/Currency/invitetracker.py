import discord
import asyncio
import json
import os 
import time

from discord import app_commands
from discord.ext import commands
from firebase_admin import db
from datetime import datetime, timezone

from brawl.Currency.tutorial import TutorialManager
from brawl.Currency.helper import GENERAL_CHAT, INVITE_LOG, BEAN_EMOTE, get_current_month_key, WELCOME_BUTTON_REWARD, MAX_BUTTON_WELCOMES
from brawl.Currency.db import (
    u_welcome_cooldown, g_invites_monthly, g_invites_member_data, 
    g_member_history, u_recent_join
)

class WelcomeView(discord.ui.View):
    def __init__(self, member, bot):
        super().__init__(timeout=600) # 5 mins
        self.member = member
        self.bot = bot
        self.welcomed_by = set()
    
    @discord.ui.button(label="Welcome!", style=discord.ButtonStyle.green, emoji="<:pandaHappy:855019705836240916>")
    async def welcome_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.member.id:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description="💚 You can't welcome yourself! 😅 Thanks for joining our server though!",
                    color=discord.Color.pink()
                ),
                ephemeral=True
            )
        if interaction.user.id in self.welcomed_by:
            return await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"💚 You have already welcomed {self.member.mention}!",
                    color=discord.Color.red()
                ),
                ephemeral=True
            )
        cooldown_ref = u_welcome_cooldown(interaction.user.id)
        last_welcome = cooldown_ref.get() or 0
        current_time = time.time()
        
        if current_time - last_welcome < 300:
            expire_time = int(current_time + (300 - (current_time - last_welcome)))
            return await interaction.response.send_message(
                f"⏰ You have already welcomed another new member not long ago. Try again <t:{expire_time}:R>", 
                ephemeral=True
            )
        self.welcomed_by.add(interaction.user.id)
        cooldown_ref.set(current_time)
        if len(self.welcomed_by) <= MAX_BUTTON_WELCOMES:
            currency_cog = self.bot.get_cog("CurrencySystem")
            if currency_cog:
                await currency_cog.add_beans(interaction.user.id, WELCOME_BUTTON_REWARD, skip_quest_check=True)
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"🎉 Thanks for welcoming {self.member.mention}! You earned <:StarrBean:1393442086279315456> **{WELCOME_BUTTON_REWARD} Beans**",
                        color=discord.Color.green()
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        description=f"✅ Thanks for welcoming {self.member.mention}!",
                        color=discord.Color.green()
                    ),
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"💚 Thanks for welcoming {self.member.mention}! (Reward limit reached for this new member)",
                    color=discord.Color.yellow()
                ),
                ephemeral=True
            )
        button.label = f"Welcomed by {len(self.welcomed_by)} member{'s' if len(self.welcomed_by) != 1 else ''}"
        if len(self.welcomed_by) >= MAX_BUTTON_WELCOMES:
            button.disabled = True
            button.style = discord.ButtonStyle.gray
        
        await interaction.message.edit(view=self)
    
    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
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
                with open(self.member_history_file, 'r') as f:
                    return set(json.load(f))
            return set()
        except (json.JSONDecodeError, FileNotFoundError):
            return set()

    def save_member_history(self):
        with open(self.member_history_file, 'w') as f:
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
            self.invite_cache[invite.guild.id][invite.code] = getattr(invite, 'uses', 0)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild.id != self.tracked_guild_id:
            return
        async with self.cache_lock:
            if invite.guild.id in self.invite_cache and invite.code in self.invite_cache[invite.guild.id]:
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
            g_invites_member_data(guild.id, member_id).set({
                "inviter": None, "code": "oauth", "join_month": current_month
            })
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
            used_invite = increased_invites[0][0] if len(increased_invites) == 1 and increased_invites[0][1] == 1 else None
        is_new = member.id not in self.member_history
        if is_new:
            self.member_history.add(member.id)
            self.save_member_history()
            await TutorialManager(self.bot).start(member)

        if used_invite and used_invite.inviter:
            inviter_id = str(used_invite.inviter.id)
            monthly_ref = g_invites_monthly(guild.id, current_month, inviter_id)
            monthly_data = monthly_ref.get() or {"total": 0, "left": 0, "valid": 0}
            monthly_data["total"] += 1
            monthly_data["valid"] += 1
            monthly_ref.set(monthly_data)
            g_invites_member_data(guild.id, member_id).set({
                "inviter": inviter_id, "code": used_invite.code, "join_month": current_month,
                "is_new": is_new, "brew_done": False, "sell_done": False
            })

            await self.log_invite_action(
                f"{member.mention} has been invited by {used_invite.inviter.display_name} ({used_invite.inviter.id}) and now has `{monthly_data['valid']}` valid monthly invites."
            )
        else:
            code = "vanity" if vanity_code else "unknown"
            g_invites_member_data(guild.id, member_id).set({
                "inviter": None, "code": code, "join_month": current_month,
                "is_new": is_new, "brew_done": False, "sell_done": False
            })
            msg = f"{member.mention} joined using a vanity invite." if vanity_code else f"{member.name} joined, but the invite could not be determined."
            await self.log_invite_action(msg)
        ref_history = g_member_history(guild.id, member_id)
        history = ref_history.get() or {"first_join": current_month}
        history["last_join"] = current_month
        ref_history.set(history)
        u_recent_join(member.id).set(time.time())
        welcome_channel = self.bot.get_channel(GENERAL_CHAT)
        if welcome_channel:
            if is_new:
                msg = (f"Welcome to the server, {member.mention}! 🎉\n"
                       f"You've just received {BEAN_EMOTE} **500** as a welcome bonus to get started!\n\n"
                       f"**Step 1:** Go to <#1391361575641677956> and claim your extra daily {BEAN_EMOTE} `500`.\n"
                       f"Once you have {BEAN_EMOTE} `1000`, I'll guide you to the next step!")
                await welcome_channel.send(
                    f"### {member.mention} just joined <:pandaHappy:855019705836240916> ~ please give them a warm welcome! <:PumpkinLove:1391457782061990099>",
                    view=WelcomeView(member, self.bot),
                    embed=discord.Embed(title="Let me guide you through the server!", description=msg, color=discord.Color.purple())
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
        if mapping_data and (inviter_id := mapping_data.get("inviter")) and (join_month := mapping_data.get("join_month")):
            monthly_ref = g_invites_monthly(member.guild.id, join_month, inviter_id)
            if monthly_data := monthly_ref.get():
                monthly_data["left"] += 1
                monthly_data["valid"] = max(monthly_data["valid"] - 1, 0)
                monthly_ref.set(monthly_data)
                await self.log_invite_action(f"{member.name} left the server (Invited by <@{inviter_id}> in `{join_month}`, now has `{monthly_data['valid']}` valid invites).")
        else:
            await self.log_invite_action(f"{member.name} left the server. They joined using the vanity invite.")
        ref_mapping.delete()

    @app_commands.command(name="addinvites", description="Add invites to a user (Admin only)")
    @app_commands.describe(user="User to add invites to", amount="Number of invites to add")
    @app_commands.default_permissions(administrator=True)
    async def add_invites(self, interaction: discord.Interaction, user: discord.User, amount: int):
        if interaction.guild.id != self.tracked_guild_id:
            return await interaction.response.send_message("🚫 You can't use this here.", ephemeral=True)
        if amount <= 0:
            return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
        current_month = get_current_month_key()
        ref = g_invites_monthly(interaction.guild.id, current_month, user.id)
        data = ref.get() or {"total": 0, "left": 0, "valid": 0}
        data["total"] += amount
        data["valid"] += amount
        ref.set(data)
        await interaction.response.send_message(f"✅ Added **{amount}** invites to {user.mention} for {current_month}", ephemeral=True)

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
        options = [discord.SelectOption(label=f"{self._month_name(int(m.split('-')[1]))} {m.split('-')[0]}", value=m) for m in months]
        super().__init__(placeholder="Select month to view invitees", options=options)

    def _month_name(self, month_num):
        months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        return months[month_num - 1] if 1 <= month_num <= 12 else f"Month {month_num}"

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.inviter:
            return await interaction.response.send_message("<:No:855023143743651860> You are not the author of the command.", ephemeral=True)
        selected_month = self.values[0]
        year, month_num = selected_month.split('-')
        month_display = f"{self._month_name(int(month_num))} {year}"
        currency_cog = interaction.client.get_cog("CurrencySystem")
        if not currency_cog:
            return await interaction.response.send_message("Currency system not available!", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ref = g_invites_member_data(interaction.guild.id)
        all_data = ref.get() or {}
        invitees = [m for m, d in all_data.items() if d.get('inviter') == str(self.inviter.id) and d.get('join_month') == selected_month]
        if not invitees:
            return await interaction.followup.send(f"No invitees found for {month_display}", ephemeral=True)
        embed = discord.Embed(
            title=f"{self.inviter.display_name}'s Past Invites ({month_display})",
            description=f"Showing `{len(invitees)}` valid invitees. If the member has the emojis ⚠️ (account age < 14 days) or 🔁 (rejoins) next to their name, they are ineligible for referral milestones.\n\n",
            color=discord.Color.purple()
        )
        
        for member_id in invitees:
            try:
                member = await interaction.guild.fetch_member(int(member_id))
            except Exception:
                member = None
            display = member.mention if member else f"<@{member_id}> (Left)"
            if member and (datetime.now(timezone.utc) - member.created_at).days < 14:
                display += " ⚠️"
            if not (g_invites_member_data(interaction.guild.id, member_id).get() or {}).get("is_new"):
                display += " 🔁"
            beans, tokens = await currency_cog.get_balance(int(member_id))
            active_brew = await currency_cog.get_active_brew(int(member_id))
            if active_brew:
                current_time = time.time()
                roast_name = active_brew['roast_type'].capitalize()
                insured_status = "🛡️ " if active_brew.get('insured', False) else ""
                brew_status = f"{insured_status}`{roast_name}` (Ready <t:{int(active_brew['end_time'])}:R>)" if current_time < active_brew['end_time'] else f"{insured_status}`{roast_name}` (Ready to sell! <a:tick:817884554361569280>)"
            else:
                brew_status = " No active brew"
            embed.description += f"- {display}\n> <:StarrBean:1393442086279315456> `{beans}` Beans\n> <:StarrToken:1393442089894940846> `{tokens}` Tokens\n> ☕ {brew_status}\n"
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
async def setup(bot):
    await bot.add_cog(InviteTracker(bot))
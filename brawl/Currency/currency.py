import asyncio
import random
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency import heat, wallet
from brawl.Currency.boss import start_inspection
from brawl.Currency.card import render, roster
from brawl.Currency.chat import ChatRewardSystem
from brawl.Currency.config import (
    REFERRAL_BRIDGE_BEANS,
    REFERRAL_MASTER_SELLS,
    REFERRAL_TRAINEE_BEANS,
)
from brawl.Currency.db import (
    g_boss_inspection,
    g_invites_member_data,
    g_member_history,
    g_referral_milestones,
    g_sell_alarm,
    g_thermometer,
    sync_sell_alarm,
    sync_shop_effects,
    u_balance,
    u_brews,
    u_mega_boxes,
    u_star_drops,
)
from brawl.Currency.effects import EffectManager
from brawl.Currency.helper import (
    BEAN_EMOTE,
    BOT_COMMANDS,
    BRIDGE_ROLE_ID,
    INVITE_LOG,
    MAIN_CHAT_CHANNELS,
    MAIN_GUILD_ID,
    MASTER_ROLE_ID,
    NO_EMOTE,
    ROAST_TYPES,
    TOKEN_EMOTE,
    TRAINEE_ROLE_ID,
    get_current_month_key,
)
from brawl.Currency.home import background
from brawl.Currency.rewardcard import draw_ready
from brawl.Currency.stationcard import draw_thermometer
from brawl.Currency.tutorial import TutorialManager


class CurrencySystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chat_system = ChatRewardSystem(self.bot)
        self.effect_manager = EffectManager(self.bot)
        self.tutorial_manager = TutorialManager(self.bot)
        self.bot.loop.create_task(self.monthly_referral_reset())
        heat_ref = g_thermometer(MAIN_GUILD_ID).get()
        self.thermometer_heat = heat_ref.get("heat", 0) if heat_ref else 0
        self.thermometer_decay_task = self.bot.loop.create_task(
            self.thermometer_decay_loop()
        )
        self.thermo_bean_update_task = self.bot.loop.create_task(
            self.thermo_bean_update_loop()
        )
        self.effect_cleanup_task = self.bot.loop.create_task(self.effect_cleanup_loop())
        self.sell_alarm_task = self.bot.loop.create_task(self.sell_alarm_check_loop())
        self.boss_inspection_task = self.bot.loop.create_task(
            self.boss_inspection_loop()
        )

    async def thermo_bean_update_loop(self):
        """Process cached thermo beans every minute to reduce database writes"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(60)

            async with self.chat_system.thermo_bean_lock:
                cache = self.chat_system.thermo_bean_cache
                self.chat_system.thermo_bean_cache = {}

            for user_id, beans in cache.items():
                await self.add_beans(user_id, beans)

    async def effect_cleanup_loop(self):
        """Clean up expired effects every minute"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self.effect_manager.cleanup_expired_effects()
            except Exception as e:
                print(f"Error cleaning up effects: {e}")
            await asyncio.sleep(60)

    async def thermometer_decay_loop(self):
        """Decay thermometer heat by 5% every minute"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(60)

            frozen = heat.freeze(MAIN_GUILD_ID)
            if frozen:
                if frozen[1].get("frozen_heat") is None:
                    sync_shop_effects(
                        frozen[0],
                        "freeze_thermometer",
                        "update",
                        {"frozen_heat": self.thermometer_heat},
                        MAIN_GUILD_ID,
                    )
                continue

            current_heat = self.thermometer_heat
            if current_heat > 0:
                if current_heat > 100:
                    new_heat = max(0, current_heat - 20)
                elif current_heat > 75:
                    new_heat = max(0, current_heat - 10)
                elif current_heat > 50:
                    new_heat = max(0, current_heat - 5)
                else:
                    new_heat = max(0, current_heat - 2)
                self.thermometer_heat = new_heat
                g_thermometer(MAIN_GUILD_ID).set({"heat": new_heat})

    async def monthly_referral_reset(self):
        """Reset referral system on 1st of each month"""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            now = datetime.now(timezone.utc)
            if now.day == 1 and now.hour == 0:
                guild = self.bot.get_guild(MAIN_GUILD_ID)
                if not guild:
                    await asyncio.sleep(3600)
                    continue

                for role_id in [TRAINEE_ROLE_ID, BRIDGE_ROLE_ID, MASTER_ROLE_ID]:
                    role = guild.get_role(role_id)
                    if role:
                        for member in role.members:
                            await member.remove_roles(role)

                current_month = get_current_month_key()
                g_referral_milestones(guild.id, current_month).delete()

                channel = self.bot.get_channel(INVITE_LOG)
                if channel:
                    await channel.send(
                        f"🔄 **Monthly Referral Reset**\n"
                        f"All Barista roles removed\n"
                        f"Milestone data cleared for {current_month}"
                    )

                await asyncio.sleep(82800)
            else:
                await asyncio.sleep(3600)

    async def sell_alarm_check_loop(self):
        """Check every 5 minutes for brews ready to sell and send DM notifications"""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                await asyncio.sleep(300)

                alarm_ref = g_sell_alarm(MAIN_GUILD_ID)
                all_alarms = alarm_ref.get() or {}
                current_time = time.time()

                for user_id_str, alarm_data in all_alarms.items():
                    user_id = int(user_id_str)

                    if alarm_data.get("notified", False):
                        continue

                    end_time = alarm_data.get("end_time", 0)
                    if current_time >= end_time:
                        active_effects = (
                            await self.effect_manager.get_user_active_effects(user_id)
                        )
                        if "sell_alarm" not in active_effects:
                            sync_sell_alarm(user_id, "delete", guild_id=MAIN_GUILD_ID)
                            continue

                        try:
                            user = await self.bot.fetch_user(user_id)
                            if user:
                                guild = self.bot.get_guild(MAIN_GUILD_ID)
                                bot_channel = (
                                    guild.get_channel(BOT_COMMANDS) if guild else None
                                )

                                ready = {
                                    "roast": alarm_data.get("roast_type", "light"),
                                    "background": background(user_id),
                                }

                                view = discord.ui.View()
                                if bot_channel:
                                    button = discord.ui.Button(
                                        label="Go to Bot Channel",
                                        style=discord.ButtonStyle.link,
                                        url=f"https://discord.com/channels/{guild.id}/{bot_channel.id}",
                                    )
                                    view.add_item(button)

                                await user.send(
                                    f"-# **Next:** use </sell:1396588612790784071> in {bot_channel.mention if bot_channel else 'the bot channel'}. This reminder is from your Sell Alarm.",
                                    file=await render(draw_ready, ready, name="ready"),
                                    **({"view": view} if bot_channel else {}),
                                )
                                sync_sell_alarm(
                                    user_id, "update", {"notified": True}, MAIN_GUILD_ID
                                )

                        except discord.Forbidden:
                            sync_sell_alarm(
                                user_id, "update", {"notified": True}, MAIN_GUILD_ID
                            )
                        except Exception as e:
                            print(f"Error sending sell alarm DM to user {user_id}: {e}")

            except Exception as e:
                print(f"Error in sell_alarm_check_loop: {e}")
                await asyncio.sleep(60)

    async def boss_inspection_loop(self):
        """Drop Boss Inspection 1-3 times a day in random chat channels (UTC time)"""
        await self.bot.wait_until_ready()

        await asyncio.sleep(10)

        while not self.bot.is_closed():
            try:
                current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                ref = g_boss_inspection(MAIN_GUILD_ID)
                inspection_data = ref.get() or {}

                if not inspection_data:
                    drops_today = random.randint(1, 3)
                    inspection_data = {
                        "total_drops": drops_today,
                        "completed_drops": 0,
                        "last_drop_time": 0,
                    }
                    ref.set(inspection_data)
                    print(
                        f"Boss Inspection: New day initialized with {drops_today} drops planned"
                    )

                if inspection_data["completed_drops"] >= inspection_data["total_drops"]:
                    now = datetime.now(timezone.utc)
                    next_midnight = (now + timedelta(days=1)).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    seconds_until_midnight = (next_midnight - now).total_seconds()

                    print(
                        f"Boss Inspection: All drops complete for today. Sleeping until midnight ({seconds_until_midnight/3600:.2f} hours)"
                    )
                    await asyncio.sleep(seconds_until_midnight + 60)
                    continue

                min_wait = 30 * 60
                max_wait = 8 * 3600
                wait_time = random.uniform(min_wait, max_wait)

                now = datetime.now(timezone.utc)
                next_midnight = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                seconds_until_midnight = (next_midnight - now).total_seconds()

                if wait_time >= seconds_until_midnight:
                    print(
                        f"Boss Inspection: Not enough time for another drop today. Waiting until midnight."
                    )
                    await asyncio.sleep(seconds_until_midnight + 60)
                    continue

                print(
                    f"Boss Inspection: Waiting {wait_time/3600:.2f} hours until next drop"
                )
                await asyncio.sleep(wait_time)

                if self.bot.is_closed():
                    break

                new_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if new_date != current_date:
                    print("Boss Inspection: Day changed during sleep, restarting loop")
                    continue

                if not MAIN_CHAT_CHANNELS:
                    print("Warning: Boss Inspection channels not configured!")
                    await asyncio.sleep(3600)
                    continue

                channel_id = random.choice(MAIN_CHAT_CHANNELS)
                channel = self.bot.get_channel(channel_id)

                if not channel:
                    print(
                        f"Warning: Could not find channel {channel_id} for Boss Inspection"
                    )
                    await asyncio.sleep(3600)
                    continue

                await start_inspection(self, channel)

                inspection_data["completed_drops"] += 1
                inspection_data["last_drop_time"] = time.time()
                ref.set(inspection_data)
                print(
                    f"Boss Inspection dropped in {channel.name} (drop {inspection_data['completed_drops']}/{inspection_data['total_drops']})"
                )
            except Exception as e:
                print(f"Error in boss_inspection_loop: {e}")
                await asyncio.sleep(3600)

    def _get_balance_ref(self, user_id: int):
        return u_balance(user_id)

    async def add_beans(
        self,
        user_id: int,
        amount: int,
        skip_quest_check: bool = False,
        reason: str = "other",
    ):
        new_beans, _ = await wallet.change(user_id, beans=amount, reason=reason)

        if skip_quest_check:
            return new_beans

        table_cog = self.bot.get_cog("table")
        if table_cog:
            table_data = await table_cog.get_user_table(user_id, MAIN_GUILD_ID)
            if table_data and table_data.get("formalized", False):
                table_ref = table_cog._get_table_ref(
                    MAIN_GUILD_ID, table_data["name"].lower()
                )
                current_beans = table_data.get("weekly_beans", 0)
                new_total_beans = current_beans + amount
                user_contributions = table_data.get("user_contributions", {})
                user_current_contribution = user_contributions.get(str(user_id), 0)
                user_contributions[str(user_id)] = user_current_contribution + amount

                table_ref.update(
                    {
                        "weekly_beans": new_total_beans,
                        "user_contributions": user_contributions,
                    }
                )
                try:
                    quest_result = await table_cog.check_and_reward_quest(
                        MAIN_GUILD_ID, table_data["name"].lower(), new_total_beans
                    )
                except Exception as e:
                    print(f"Error checking quest: {e}")
        return new_beans

    async def add_tokens(self, user_id: int, amount: int, reason: str = "other"):
        _, new_tokens = await wallet.change(user_id, tokens=amount, reason=reason)
        return new_tokens

    async def get_balance(self, user_id: int):
        return wallet.balance(user_id)

    async def update_balance(self, user_id: int, beans: int = None, tokens: int = None):
        """Update user's Beans and/or Tokens balance."""
        ref = self._get_balance_ref(user_id)
        data = ref.get() or {}
        if beans is not None:
            data["Beans"] = beans
        if tokens is not None:
            data["Tokens"] = tokens
        ref.set(data)

    def _get_brew_ref(self, user_id: int):
        return u_brews(user_id)

    async def get_active_brew(self, user_id: int):
        ref = self._get_brew_ref(user_id)
        data = ref.get()
        return data.get("active_brew") if data else None

    async def set_active_brew(self, user_id: int, brew_data: dict):
        ref = self._get_brew_ref(user_id)
        data = ref.get() or {}
        data["active_brew"] = brew_data
        ref.set(data)

    async def remove_active_brew(self, user_id: int):
        ref = self._get_brew_ref(user_id)
        data = ref.get() or {}
        if "active_brew" in data:
            del data["active_brew"]
            ref.set(data)
            return True
        return False

    async def update_brew_stats(self, user_id: int, stats: dict):
        ref = self._get_brew_ref(user_id)
        data = ref.get() or {}
        data["stats"] = stats
        ref.set(data)

    async def get_brew_stats(self, user_id: int):
        ref = self._get_brew_ref(user_id)
        data = ref.get()
        return data.get("stats") if data else None

    async def record_brew_history(self, user_id: int, history_data: dict):
        ref = self._get_brew_ref(user_id)
        data = ref.get() or {}
        history = data.get("history", [])
        history.append(history_data)
        data["history"] = history[-10:]  # Keep last 10 brews to avoid unbounded growth
        ref.set(data)

    async def update_brew_stats_on_brew(self, user_id: int, roast_type: str):
        stats = await self.get_brew_stats(user_id) or {
            "total_brews": 0,
            "total_tokens": 0,
            "light": 0,
            "medium": 0,
            "dark": 0,
            "golden": 0,
            "most_brewed": "none",
            "last_brew": None,
        }

        stats["total_brews"] += 1
        stats[roast_type] = stats.get(roast_type, 0) + 1
        roasts = ["light", "medium", "dark", "golden"]
        roast_counts = {r: stats.get(r, 0) for r in roasts}
        max_roast = max(roast_counts, key=roast_counts.get)
        stats["most_brewed"] = max_roast
        await self.update_brew_stats(user_id, stats)
        return stats

    async def update_brew_stats_on_sell(
        self,
        user_id: int,
        tokens: int,
        roast_type: str,
        perfect: bool,
        insured: bool,
        saved_burn: bool,
    ):
        stats = await self.get_brew_stats(user_id) or {
            "total_brews": 0,
            "total_tokens": 0,
            "light": 0,
            "medium": 0,
            "dark": 0,
            "golden": 0,
            "most_brewed": "none",
            "last_brew": None,
        }

        stats["total_tokens"] += tokens
        stats["last_brew"] = {
            "roast_type": roast_type,
            "tokens": tokens,
            "perfect": perfect,
            "insured": insured,
            "saved_burn": saved_burn,
            "time": time.time(),
        }

        await self.update_brew_stats(user_id, stats)
        return stats

    async def process_invitee_welcome_bonus(self, interaction, event_type, invitee):
        """Process welcome bonus for an invitee and notify inviter"""
        guild = interaction.guild
        ref_mapping = g_invites_member_data(guild.id, invitee.id)
        mapping = ref_mapping.get() or {}

        if not mapping.get("inviter") or not mapping.get("is_new"):
            return None

        inviter_id = int(mapping["inviter"])
        try:
            inviter = await guild.fetch_member(inviter_id)
        except (discord.NotFound, discord.HTTPException):
            return None
        if not inviter:
            return None

        account_age = (datetime.now(timezone.utc) - invitee.created_at).days
        if account_age < 14:
            return None

        current_month = get_current_month_key()
        ref_history = g_member_history(guild.id, invitee.id)
        history = ref_history.get()
        if (
            history
            and history.get("first_join")
            and history["first_join"] < current_month
        ):
            return None

        bonus_key = f"{event_type}_done"
        if mapping.get(bonus_key, False):
            return None

        mapping[bonus_key] = True
        ref_mapping.set(mapping)

        if event_type == "brew":
            beans_earned = 150
            message_invitee = f"🎉 **Welcome bonus!** You earned a bonus {BEAN_EMOTE} **{beans_earned} Beans** for your first brew!"
            message_inviter = f"☕ Your invitee {invitee.mention} **brewed** their first coffee and earned a welcome bonus!"
            await self.log_referral_milestone(
                f"{inviter.mention}'s (inviter) invitee {invitee.mention} **brewed** their first coffee and earned a welcome bonus!",
                "Brew Welcome Bonus",
            )
        else:
            beans_earned = 500
            message_invitee = f"🎉 **Welcome bonus!** You earned a bonus {BEAN_EMOTE} **{beans_earned} Beans** for your first sale!"
            message_inviter = f"☕ Your invitee {invitee.mention} **sold** their first coffee and earned a welcome bonus!"
            await self.log_referral_milestone(
                f"{inviter.mention}'s (inviter) invitee {invitee.mention} **sold** their first coffee and earned a welcome bonus!",
                "Sell Welcome Bonus",
            )

        await self.add_beans(invitee.id, beans_earned)

        try:
            await inviter.send(
                embed=discord.Embed(description=message_inviter, color=0x808080)
            )
        except (discord.Forbidden, discord.HTTPException):
            pass
        return message_invitee

    async def process_referral_milestone(self, interaction, milestone_type, invitee):
        """Process referral milestones (inviter only)"""
        guild = interaction.guild
        current_month = get_current_month_key()

        ref_mapping = g_invites_member_data(guild.id, invitee.id)
        mapping = ref_mapping.get() or {}

        if not mapping.get("inviter") or not mapping.get("is_new"):
            return None, None

        inviter_id = int(mapping["inviter"])
        try:
            inviter = await guild.fetch_member(inviter_id)
        except (discord.NotFound, discord.HTTPException):
            return None, None
        if not inviter:
            return None, None

        account_age = (datetime.now(timezone.utc) - invitee.created_at).days
        if account_age < 14:
            return None, None

        ref_history = g_member_history(interaction.guild.id, invitee.id)
        history = ref_history.get()
        if (
            history
            and history.get("first_join")
            and history["first_join"] < current_month
        ):
            return None, None

        ref_milestone = g_referral_milestones(guild.id, current_month, inviter_id)
        milestone = ref_milestone.get() or {
            "trainee_done": False,
            "bridge_done": False,
            "master_done": False,
            "sells": 0,
        }

        reward_message = ""
        role_granted = None
        log_entry = None

        if milestone_type == "trainee" and not milestone["trainee_done"]:
            milestone["trainee_done"] = True
            mapping["brew_done"] = True
            role_granted = TRAINEE_ROLE_ID
            await self.add_beans(inviter_id, REFERRAL_TRAINEE_BEANS)
            reward_message = f"🎉 Your invitee {invitee.mention} brewed their first coffee! You **earned {BEAN_EMOTE} `300` Beans** and unlocked the `Trainee Barista` role!"
            log_entry = f"🎯 **Milestone Reached:** <@&{TRAINEE_ROLE_ID}>\n🎁 **Reward:** `+300` Beans to {inviter.mention} (inviter)\n👤 **Invitee:** {invitee.mention}"

        elif (
            milestone_type == "bridge"
            and not milestone["bridge_done"]
            and milestone["trainee_done"]
        ):
            milestone["bridge_done"] = True
            mapping["sell_done"] = True
            role_granted = BRIDGE_ROLE_ID
            await self.add_beans(inviter_id, REFERRAL_BRIDGE_BEANS)
            reward_message = f"🎉 Your invitee {invitee.mention} sold their first coffee! You **earned {BEAN_EMOTE} `3,000` Beans** and unlocked the `Bridge Barista` role!"
            log_entry = f"🎯 **Milestone Reached:** <@&{BRIDGE_ROLE_ID}>\n🎁 **Reward:** `+3000` Beans to {inviter.mention} (inviter)\n👤 **Invitee:** {invitee.mention}"

        elif milestone_type == "sell":
            milestone["sells"] = milestone.get("sells", 0) + 1
            if (
                milestone["sells"] >= REFERRAL_MASTER_SELLS
                and not milestone["master_done"]
            ):
                milestone["master_done"] = True
                role_granted = MASTER_ROLE_ID
                reward_message = f"🏆 Your invitee(s) have successfully sold a total of 3 coffees! You unlocked the `Master Barista` role and will now **earn {TOKEN_EMOTE} `+50%` Tokens per non-burnt brew** until the end of this month."
                log_entry = f"🎯 **Milestone Reached:** <@&{MASTER_ROLE_ID}>\n🎁 **Reward:** `+`1 Token per future brew for {inviter.mention} (inviter)\n👤 **Invitee:** {invitee.mention}"

        color = discord.Color.blurple()
        if role_granted:
            role = guild.get_role(role_granted)
            if role:
                await inviter.add_roles(role)
                color = role.color

        ref_milestone.set(milestone)
        ref_mapping.set(mapping)

        if reward_message:
            try:
                await inviter.send(
                    embed=discord.Embed(description=reward_message, color=color)
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

        return log_entry, inviter

    async def log_referral_milestone(self, log_entry, title_override=None):
        """Log milestone to referral channel"""
        channel = self.bot.get_channel(INVITE_LOG)
        if channel and log_entry:
            embed = discord.Embed(
                title=title_override if title_override else "New Referral Milestone!",
                description=log_entry,
                color=discord.Color.gold(),
            )
            embed.set_footer(
                text=f"🕒 Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
            )
            await channel.send(embed=embed)

    @app_commands.command(
        name="thermometer",
        description="See how hot the chat is and what each message earns",
    )
    async def thermometer(self, interaction: discord.Interaction):
        cup = {
            "background": background(interaction.user.id),
            "heat": self.thermometer_heat,
            "drops": heat.drops_today(interaction.user.id),
        }
        frozen = heat.freeze(interaction.guild.id)
        if frozen:
            member = (await roster(interaction.guild, [frozen[0]]))[0]
            minutes = max(1, round((frozen[1]["expires_at"] - time.time()) / 60))
            cup["frozen"] = (member.display_name if member else "someone", minutes)
        await interaction.response.send_message(
            file=await render(draw_thermometer, cup, name="thermometer")
        )

    @thermometer.error
    async def thermometer_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    @app_commands.command(
        name="add",
        description="Add Beans, Tokens, Star Drops or Mega Boxes to a user (Admin only)",
    )
    @app_commands.describe(
        user="Target user", currency="Currency or Item to add", amount="Amount to add"
    )
    @app_commands.choices(
        currency=[
            app_commands.Choice(name="🫘 Starr Beans", value="Beans"),
            app_commands.Choice(name="🌟 Starr Tokens", value="Tokens"),
            app_commands.Choice(name="⭐ Star Drops", value="StarDrops"),
            app_commands.Choice(name="📦 Mega Boxes", value="MegaBoxes"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def add(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        currency: str,
        amount: int,
    ):
        if (
            not interaction.user.guild_permissions.administrator
            or interaction.guild.id != MAIN_GUILD_ID
        ):
            return await interaction.response.send_message(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )

        if amount <= 0:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Amount must be positive.", ephemeral=True
            )

        if currency == "Tokens":
            new_amount = await self.add_tokens(user.id, amount)
        elif currency == "StarDrops":
            ref = u_star_drops(user.id)
            current = ref.get() or 0
            new_amount = current + amount
            ref.set(new_amount)
            currency = "Star Drops"
        elif currency == "MegaBoxes":
            ref = u_mega_boxes(user.id)
            current = ref.get() or 0
            new_amount = current + amount
            ref.set(new_amount)
            currency = "Mega Boxes"
        else:
            new_amount = await self.add_beans(user.id, amount)

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"Added `{amount:,}` {currency} to {user.mention}. \n-# **New balance:** `{new_amount:,}` {currency}.",
                color=discord.Color.green(),
            )
        )

    @add.error
    async def add_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)


async def setup(bot):
    await bot.add_cog(CurrencySystem(bot))

import asyncio
import random
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency import heat, wallet
from brawl.Currency.boss import plan, start_inspection
from brawl.Currency.card import BACKGROUND, render, roster
from brawl.Currency.chat import ChatRewardSystem
from brawl.Currency.config import (
    BOSS_LATE_SECONDS,
    REFERRAL_ACCOUNT_DAYS,
    REFERRAL_BRIDGE_STAMPS,
    REFERRAL_MASTER_SELLS,
    REFERRAL_TRAINEE_STAMPS,
    THERMOMETER_COOLING,
    THERMOMETER_NEWS_SECONDS,
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
    u_brews,
    u_mega_boxes,
    u_star_drops,
)
from brawl.Currency.effects import EffectManager
from brawl.Currency.guide import guide
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
    STAMP_EMOTE,
    TOKEN_EMOTE,
    TRAINEE_ROLE_ID,
    get_current_month_key,
)
from brawl.Currency.panel import notice
from brawl.Currency.quests import get_next_daily_reset
from brawl.Currency.rewardcard import draw_ready
from brawl.Currency.stationcard import draw_heat, draw_thermometer
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
        self.heat_channel = None
        self.heat_told = {}
        self.heat_notice = None
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
                await self.add_beans(user_id, beans, reason="thermometer")
                heat.count_beans(user_id, beans, get_next_daily_reset())
                self.chat_system.extra(user_id, beans)

    async def set_heat(self, heat_now, channel=None):
        """Moves the thermometer, and tells the chat when that changes its level.

        channel is where the message that heated it was sent. A drop is told
        there too, in the last drop notice when nobody has written since.
        """
        before = heat.level_of(min(self.thermometer_heat, 100))
        self.thermometer_heat = heat_now
        g_thermometer(MAIN_GUILD_ID).update({"heat": heat_now})
        self.heat_channel = channel or self.heat_channel
        now = heat.level_of(min(heat_now, 100))
        if now is before:
            return
        channel = self.heat_channel or self.bot.get_channel(MAIN_CHAT_CHANNELS[0])
        rose = now[0] > before[0]
        notice, self.heat_notice = self.heat_notice, None
        try:
            card = await render(
                draw_heat,
                {"level": now, "rose": rose},
                name="thermometer",
            )
            told, self.heat_told[now[1]] = self.heat_told.get(now[1], 0), time.time()
            if not rose and notice and channel.last_message_id == notice.id:
                self.heat_notice = await notice.edit(attachments=[card])
                return
            if time.time() - told < THERMOMETER_NEWS_SECONDS:
                self.heat_told[now[1]] = told
                return
            sent = await channel.send(
                file=card,
                view=guide("stations", "Use /thermometer to view the heat"),
            )
            self.heat_notice = None if rose else sent
        except Exception as e:
            print(f"Failed to post the thermometer level: {e}")

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
                lost = next(
                    lost for above, lost in THERMOMETER_COOLING if current_heat > above
                )
                await self.set_heat(max(0, current_heat - lost))

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
                                    "background": BACKGROUND,
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
                                    file=await render(draw_ready, ready, name="ready"),
                                    view=guide("brewing", view=view),
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
        """Sends the boss into a random chat channel at each of the day's planned times."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)

        while not self.bot.is_closed():
            try:
                now = datetime.now(timezone.utc)
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                ref = g_boss_inspection(MAIN_GUILD_ID)
                day = ref.get() or {}
                if "times" not in day:
                    day = {"times": plan(int(midnight.timestamp())), "done": 0}
                    ref.set(day)
                    print(f"Boss Inspection: planned {len(day['times'])} visits")

                # A visit missed while the bot was off is skipped, not sent late.
                while (
                    day["done"] < len(day["times"])
                    and day["times"][day["done"]] < time.time() - BOSS_LATE_SECONDS
                ):
                    day["done"] += 1
                if day["done"] >= len(day["times"]):
                    ref.update({"done": day["done"]})
                    tomorrow = midnight + timedelta(days=1)
                    await asyncio.sleep((tomorrow - now).total_seconds() + 60)
                    continue

                wait = day["times"][day["done"]] - time.time()
                print(f"Boss Inspection: next visit in {wait / 3600:.2f} hours")
                await asyncio.sleep(max(wait, 0))
                if self.bot.is_closed():
                    break

                channel = self.bot.get_channel(random.choice(MAIN_CHAT_CHANNELS))
                # Counted before it is sent, so a failed visit is never retried in a loop.
                ref.update({"done": day["done"] + 1})
                await start_inspection(self, channel, day["done"])
                print(
                    f"Boss Inspection dropped in {channel.name} "
                    f"(visit {day['done'] + 1}/{len(day['times'])})"
                )
            except Exception as e:
                print(f"Error in boss_inspection_loop: {e}")
                await asyncio.sleep(600)

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
        if account_age < REFERRAL_ACCOUNT_DAYS:
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
            from brawl.Currency.stampcard import add as add_stamps

            boxes = add_stamps(inviter_id, REFERRAL_TRAINEE_STAMPS, source="invites")
            extra = f" and `x{boxes}` Mega Boxes" if boxes else ""
            reward_message = f"🎉 Your invitee {invitee.mention} brewed their first coffee! You **earned {STAMP_EMOTE} `{REFERRAL_TRAINEE_STAMPS}` Stamp{extra}** and unlocked the `Trainee Barista` role!"
            log_entry = f"🎯 **Milestone Reached:** <@&{TRAINEE_ROLE_ID}>\n🎁 **Reward:** `+{REFERRAL_TRAINEE_STAMPS}` Stamp{extra} to {inviter.mention} (inviter)\n👤 **Invitee:** {invitee.mention}"

        elif (
            milestone_type == "bridge"
            and not milestone["bridge_done"]
            and milestone["trainee_done"]
        ):
            milestone["bridge_done"] = True
            mapping["sell_done"] = True
            role_granted = BRIDGE_ROLE_ID
            from brawl.Currency.stampcard import add as add_stamps

            boxes = add_stamps(inviter_id, REFERRAL_BRIDGE_STAMPS, source="invites")
            extra = f" and `x{boxes}` Mega Boxes" if boxes else ""
            reward_message = f"🎉 Your invitee {invitee.mention} sold their first coffee! You **earned {STAMP_EMOTE} `{REFERRAL_BRIDGE_STAMPS}` Stamp{extra}** and unlocked the `Bridge Barista` role!"
            log_entry = f"🎯 **Milestone Reached:** <@&{BRIDGE_ROLE_ID}>\n🎁 **Reward:** `+{REFERRAL_BRIDGE_STAMPS}` Stamp{extra} to {inviter.mention} (inviter)\n👤 **Invitee:** {invitee.mention}"

        elif milestone_type == "sell":
            milestone["sells"] = milestone.get("sells", 0) + 1
            if (
                milestone["sells"] >= REFERRAL_MASTER_SELLS
                and not milestone["master_done"]
            ):
                milestone["master_done"] = True
                role_granted = MASTER_ROLE_ID
                reward_message = f"🏆 Your invitees sold {REFERRAL_MASTER_SELLS} coffees! You unlocked the `Master Barista` role and now **earn {TOKEN_EMOTE} `+50%` Tokens on every sell this month**."
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
        drops, resets = heat.drops(interaction.user.id)
        cup = {
            "background": BACKGROUND,
            "heat": self.thermometer_heat,
            "drops": drops,
            "resets": resets,
            "beans": heat.beans_today(interaction.user.id),
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
        await interaction.response.send_message(
            embed=notice(f"```{str(error)}```"), ephemeral=True
        )

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
                embed=notice(
                    f"{NO_EMOTE} You do not have permission to use this command.", "bad"
                ),
                ephemeral=True,
            )

        if amount <= 0:
            return await interaction.response.send_message(
                embed=notice(f"{NO_EMOTE} Amount must be positive.", "bad"),
                ephemeral=True,
            )

        if currency == "Tokens":
            new_amount = await self.add_tokens(user.id, amount, reason="staff")
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
            new_amount = await self.add_beans(user.id, amount, reason="staff")

        await interaction.response.send_message(
            embed=discord.Embed(
                description=f"Added `{amount:,}` {currency} to {user.mention}. \n-# **New balance:** `{new_amount:,}` {currency}.",
                color=discord.Color.green(),
            )
        )

    @add.error
    async def add_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            embed=notice(f"```{str(error)}```"), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(CurrencySystem(bot))

import asyncio
import random
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher

import discord

from brawl.Currency.db import (
    g_shop_effects,
    g_thermometer,
    u_daily_chat_earnings,
)
from brawl.Currency.helper import (
    BEAN_EMOTE,
    EFFECT_EMOTE,
    MAIN_CHAT_CHANNELS,
    NO_EMOTE,
    TOKEN_EMOTE,
    ULTRA_TIER_ROLE_ID,
    YES_EMOTE,
)
from brawl.Currency.quests import update_quest


class ChatRewardSystem:
    def __init__(self, bot):
        self.bot = bot
        self.user_cooldowns = {}
        self.message_counts = {}
        self.thermo_bean_cache = {}
        self.daily_thresholds = {}
        self.last_messages = {}
        self.first_message_times = {}
        self.earnings_cache = {}
        self.thermo_bean_lock = asyncio.Lock()

    def is_effortful_message(self, message: str, user_id: int) -> tuple[bool, str]:
        content = message.strip()

        if len(content) < 5:
            return False, f"{NO_EMOTE} Too short (< 5 characters)"

        total_chars = len(content)
        non_alnum_chars = len(re.findall(r"[^\w\s]", content))
        if total_chars > 0 and (non_alnum_chars / total_chars) > 0.6:
            return False, f"{NO_EMOTE} Too many symbols/non-alphanumeric characters"

        emoji_match = re.sub(
            r"<a?:\w+:\d+>|[\u2600-\u27BF\u2190-\u21FF\u2300-\u23FF]", "", content
        )
        if len(emoji_match.strip()) == 0:
            return False, f"{NO_EMOTE} Only emojis or custom emojis"

        words = content.lower().split()
        if len(set(words)) <= 2 and len(words) > 5:
            return False, f"{NO_EMOTE} Too repetitive (e.g., 'lol lol lol')"

        if re.search(r"(.)\1{4,}", content):
            return False, f"{NO_EMOTE} Excessive repeated characters (e.g., 'nooooo')"

        if content.startswith("="):
            return False, f"{NO_EMOTE} Carl-bot command detected"

        last_msg = self.last_messages.get(user_id)
        if last_msg:
            similarity = SequenceMatcher(
                None, last_msg.strip().lower(), content.lower()
            ).ratio()
            if similarity > 0.9:
                return False, f"{NO_EMOTE} Too similar to previous message"

        if re.search(r"(https?:\/\/|www\.|discord\.gg\/|^\/\w+)", content.lower()):
            return False, f"{NO_EMOTE} Looks like spam or a link"

        if re.fullmatch(r"(\s*<a?:\w+:\d+>\s*){1,4}", content):
            return False, f"{NO_EMOTE} Only emojis or emoji + fillers"

        return True, f"{YES_EMOTE} Effortful message"

    async def process_message(self, message, cog):
        if message.author.bot:
            return

        user_id = message.author.id
        current_time = time.time()

        if user_id not in self.user_cooldowns:
            self.user_cooldowns[user_id] = 0
            self.message_counts[user_id] = 0
            self.last_messages[user_id] = ""
            self.daily_thresholds[user_id] = random.randint(9, 11)

        if user_id in self.earnings_cache:
            earnings_data = self.earnings_cache[user_id]
        else:
            ref = u_daily_chat_earnings(user_id)
            data = ref.get() or {"earnings": 0, "reset_time": 0}
            earnings_data = data
            self.earnings_cache[user_id] = earnings_data

        reset_time = earnings_data.get("reset_time", 0)
        if current_time > reset_time:
            earnings_data["earnings"] = 0
            earnings_data["reset_time"] = current_time + 86400
            self.earnings_cache[user_id] = earnings_data

        today_earnings = earnings_data["earnings"]

        if current_time - self.user_cooldowns[user_id] < 5:
            return

        effortful, reason = self.is_effortful_message(message.content, user_id)
        if not effortful:
            return

        self.user_cooldowns[user_id] = current_time
        self.message_counts[user_id] += 1
        self.last_messages[user_id] = message.content.strip()

        MAX_DAILY_CHAT_BEAN_LIMIT = 1000
        booster_role = message.guild.premium_subscriber_role
        if booster_role in message.author.roles:
            MAX_DAILY_CHAT_BEAN_LIMIT = 1500

        ultra_role = message.guild.get_role(ULTRA_TIER_ROLE_ID)
        if ultra_role and ultra_role in message.author.roles:
            MAX_DAILY_CHAT_BEAN_LIMIT = 5000

        if datetime.now(timezone.utc).weekday() >= 5:
            MAX_DAILY_CHAT_BEAN_LIMIT *= 2

        active_effects = await cog.effect_manager.get_user_active_effects(user_id)
        chat_boost_active = "chat_boost" in active_effects
        if chat_boost_active:
            MAX_DAILY_CHAT_BEAN_LIMIT *= 3

        if message.channel.id in MAIN_CHAT_CHANNELS:
            freeze_ref = g_shop_effects(message.guild.id)
            all_effects = freeze_ref.get() or {}
            current_time = time.time()

            frozen = False
            for user_id_check, user_effects in all_effects.items():
                freeze_data = user_effects.get("freeze_thermometer", {})
                if freeze_data.get("active", False) and current_time < freeze_data.get(
                    "expires_at", 0
                ):
                    frozen = True
                    break

            if not frozen:
                heat_add = random.randint(1, 2)
                cog.thermometer_heat = min(130, cog.thermometer_heat + heat_add)
                g_thermometer(message.guild.id).update({"heat": cog.thermometer_heat})

        display_heat = min(cog.thermometer_heat, 100)

        if display_heat >= 100:
            thermo_beans = 6
        elif display_heat >= 75:
            thermo_beans = 4
        elif display_heat >= 50:
            thermo_beans = 2
        else:
            thermo_beans = 0

        if thermo_beans > 0:
            async with self.thermo_bean_lock:
                self.thermo_bean_cache[user_id] = (
                    self.thermo_bean_cache.get(user_id, 0) + thermo_beans
                )

        bonus_tokens = 0
        bonus_message = None
        roll = random.random()
        if display_heat >= 100:
            if roll < 0.005:
                bonus_tokens = 5
                bonus_message = "🎉 **JACKPOT!** You hit the 0.5% jackpot!"
            elif roll < 0.02:
                bonus_tokens = random.choice([1, 1, 2])
        elif display_heat >= 75:
            if roll < 0.01:
                bonus_tokens = 1

        if bonus_tokens > 0:
            can_receive, current_count, reset_time = (
                await cog.check_and_update_token_reward_limit(user_id)
            )
            if not can_receive:
                bonus_tokens = 0
                bonus_message = None

        embed = None
        if bonus_tokens > 0:
            await cog.add_tokens(user_id, bonus_tokens)
            _, tokens_balance = await cog.get_balance(user_id)

            embed = discord.Embed(
                title="☕ Chat Thermometer Bonus!",
                color=0xFFD700,
                description=f"You received {TOKEN_EMOTE} **{bonus_tokens} Tokens**!",
            )
            if bonus_message:
                embed.description += f"\n{bonus_message}"

            current_time = time.time()
            remaining = int(reset_time - current_time)
            if remaining > 0:
                hours, remainder = divmod(remaining, 3600)
                minutes, _ = divmod(remainder, 60)
                formatted = f"in {hours}h {minutes}m"
            else:
                formatted = "soon"
            embed.set_footer(
                text=f"Token rewards today: {current_count}/3 (resets {formatted})"
            )

            embed.add_field(
                name="Thermometer Level",
                value=f"{display_heat}% - {'Boiling 🔥' if display_heat >= 100 else 'Hot 🌡️' if display_heat >= 75 else 'Warm ☕'}",
                inline=True,
            )
            embed.add_field(
                name="New Token Balance",
                value=f"{TOKEN_EMOTE} `{tokens_balance}`",
                inline=True,
            )

            stamp_cog = self.bot.get_cog("StampCard")
            if stamp_cog:
                await stamp_cog.update_progress(user_id, "thermometer_bonuses", 1)

        daily_threshold = self.daily_thresholds[user_id]
        beans_earned = 0
        new_earnings = today_earnings
        reward_triggered = False

        if self.message_counts[user_id] >= daily_threshold:
            self.message_counts[user_id] = 0
            self.daily_thresholds[user_id] = random.randint(9, 11)

            if today_earnings < MAX_DAILY_CHAT_BEAN_LIMIT:
                active_effects = await cog.effect_manager.get_user_active_effects(
                    user_id
                )

                min_beans = 100 if "chat_bean_boost" not in active_effects else 150
                max_beans = 201 if "chat_bean_boost" not in active_effects else 301
                beans_earned = random.randint(min_beans, max_beans)

                if chat_boost_active:
                    beans_earned *= 3

                ultra_role = message.guild.get_role(ULTRA_TIER_ROLE_ID)
                if ultra_role and ultra_role in message.author.roles:
                    beans_earned *= 3

                if today_earnings + beans_earned > MAX_DAILY_CHAT_BEAN_LIMIT:
                    beans_earned = MAX_DAILY_CHAT_BEAN_LIMIT - today_earnings

                new_earnings = today_earnings + beans_earned
                earnings_data["earnings"] = new_earnings
                u_daily_chat_earnings(user_id).set(earnings_data)
                self.earnings_cache[user_id] = earnings_data

                await cog.add_beans(user_id, beans_earned)
                await update_quest(
                    user_id, message.guild.id, {"chat_earnings": beans_earned}, self.bot
                )
                reward_triggered = True
                reset_time = earnings_data["reset_time"]

        try:
            if reward_triggered:
                emoji = "<:Like:793027164731605033>"
                table_cog = self.bot.get_cog("table")
                if table_cog:
                    table_data = await table_cog.get_user_table(
                        user_id, message.guild.id
                    )
                    if table_data and table_data.get("formalized", False):
                        emoji = table_data["emoji"]
                await message.channel.send(
                    f"{emoji} {message.author.mention} earned {BEAN_EMOTE} **{beans_earned} Beans** "
                    f"for chatting actively! *(Daily Cap: `{new_earnings}/{MAX_DAILY_CHAT_BEAN_LIMIT}`)* {EFFECT_EMOTE if chat_boost_active else ''} \n"
                    f"> -# <a:clock:1382887924273774754> Resets <t:{int(reset_time)}:R>. "
                    "Use </balance:1393376242501157005> to check your progress!",
                    embed=embed,
                )
            elif embed is not None:
                await message.channel.send(message.author.mention, embed=embed)
        except Exception as e:
            print(f"Failed to send bean reward message: {e}")


async def setup(bot):
    pass

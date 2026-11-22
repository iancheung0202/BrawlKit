import asyncio
import random
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher

from brawl.Currency import heat
from brawl.Currency.card import render
from brawl.Currency.db import g_thermometer, u_daily_chat_earnings
from brawl.Currency.helper import (
    BEAN_EMOTE,
    EFFECT_EMOTE,
    MAIN_CHAT_CHANNELS,
    NO_EMOTE,
    ULTRA_TIER_ROLE_ID,
    YES_EMOTE,
)
from brawl.Currency.home import background
from brawl.Currency.ladder import unlocked
from brawl.Currency.panel import notice
from brawl.Currency.quests import get_next_daily_reset, update_quest
from brawl.Currency.stationcard import draw_token_drop


def chat_limit(member, effects):
    """How many Beans this member can earn from chat today."""
    limit = 1000
    if member.guild.premium_subscriber_role in member.roles:
        limit = 1500
    ultra = member.guild.get_role(ULTRA_TIER_ROLE_ID)
    if ultra and ultra in member.roles:
        limit = 5000
    if datetime.now(timezone.utc).weekday() >= 5:
        limit *= 2
    if "chat_boost" in effects:
        limit *= 3
    return limit


def chat_today(user_id):
    """The Beans this member has earned from chat since the daily reset."""
    data = u_daily_chat_earnings(user_id).get() or {}
    return data.get("earnings", 0) if time.time() <= data.get("reset_time", 0) else 0


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
            earnings_data["reset_time"] = get_next_daily_reset()
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

        active_effects = await cog.effect_manager.get_user_active_effects(user_id)
        chat_boost_active = "chat_boost" in active_effects
        MAX_DAILY_CHAT_BEAN_LIMIT = chat_limit(message.author, active_effects)

        if message.channel.id in MAIN_CHAT_CHANNELS and not heat.freeze(
            message.guild.id
        ):
            cog.thermometer_heat = min(130, cog.thermometer_heat + random.randint(1, 2))
            g_thermometer(message.guild.id).update({"heat": cog.thermometer_heat})

        level = heat.level_of(min(cog.thermometer_heat, 100))
        if level[2]:
            async with self.thermo_bean_lock:
                self.thermo_bean_cache[user_id] = (
                    self.thermo_bean_cache.get(user_id, 0) + level[2]
                )

        drop = None
        bonus_tokens, jackpot = heat.roll_tokens(level)
        if bonus_tokens and await unlocked(
            self.bot, user_id, message.guild.id, "thermometer"
        ):
            count = heat.take_drop(user_id)
            if count:
                await cog.add_tokens(user_id, bonus_tokens)
                drop = await render(
                    draw_token_drop,
                    {
                        "background": background(user_id),
                        "amount": bonus_tokens,
                        "jackpot": jackpot,
                        "level": level[1],
                        "count": count,
                        "tokens": (await cog.get_balance(user_id))[1],
                    },
                    name="tokens",
                )

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
                order = await update_quest(
                    user_id,
                    message.guild.id,
                    {},
                    self.bot,
                    chat=(new_earnings, MAX_DAILY_CHAT_BEAN_LIMIT),
                )
                reward_triggered = True
                reset_time = earnings_data["reset_time"]
            else:
                # Already at the limit: the order may still be waiting on it.
                done = await update_quest(
                    user_id,
                    message.guild.id,
                    {},
                    self.bot,
                    chat=(today_earnings, MAX_DAILY_CHAT_BEAN_LIMIT),
                )
                if done:
                    await message.channel.send(embed=notice("\n".join(done)))

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
                earned = notice(
                    f"{emoji} {message.author.mention} earned {BEAN_EMOTE} `{beans_earned}` Beans "
                    f"for chatting {EFFECT_EMOTE if chat_boost_active else ''}\n"
                    f"Today: `{new_earnings}/{MAX_DAILY_CHAT_BEAN_LIMIT}`, resets <t:{int(reset_time)}:R>"
                    + "".join(f"\n{line}" for line in order)
                )
                if drop:
                    earned.set_image(url=f"attachment://{drop.filename}")
                await message.channel.send(embed=earned, file=drop)
            elif drop:
                await message.channel.send(message.author.mention, file=drop)
        except Exception as e:
            print(f"Failed to send bean reward message: {e}")


async def setup(bot):
    pass

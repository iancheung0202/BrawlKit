import discord
import datetime
import time
import random

from firebase_admin import db
from discord.ext import commands
from brawl.Currency.db import u_quests

QUEST_GOAL_PRESETS = {
    "chat_earnings": {
        "daily": [500, 750, 1000],
        "weekly": [3000, 4000, 5000],
        "monthly": [15000, 17500, 20000]
    },
    "brew_start": {
        "daily": [1],
        "weekly": [3, 4],
        "monthly": [12, 15, 17]
    },
    "brew_sells": {
        "daily": [1],
        "weekly": [3, 4],
        "monthly": [12, 15, 17]
    },
    "shop_purchases": {
        "daily": [1],
        "weekly": [3, 5],
        "monthly": [8, 10, 12]
    },
    "daily_checkins": {
        "daily": [1],
        "weekly": [4, 5, 6],
        "monthly": [20, 22, 24]
    }
}

QUEST_DESCRIPTIONS = {
    "chat_earnings": "Earn Beans from chat",
    "brew_start": "Start coffee brews",
    "brew_sells": "Sell coffee brews",
    "shop_purchases": "Purchase items from shop",
    "daily_checkins": "Claim daily check-in rewards"
}

QUEST_TYPES = list(QUEST_DESCRIPTIONS.keys())

QUEST_BEAN_REWARDS = {
    "daily": 250,
    "weekly": 500,
    "monthly": 1500
}

QUEST_BONUS_BEANS = {
    "daily": 500,
    "weekly": 1000,
    "monthly": 4500
}

def get_next_daily_reset():
    now = datetime.datetime.now(datetime.timezone.utc)
    next_day = now + datetime.timedelta(days=1)
    return int(next_day.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

def get_next_weekly_reset():
    now = datetime.datetime.now(datetime.timezone.utc)
    days_until_sunday = (6 - now.weekday()) % 7
    if days_until_sunday == 0:
        days_until_sunday = 7
    next_sunday = now + datetime.timedelta(days=days_until_sunday)
    return int(next_sunday.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

def get_next_monthly_reset():
    now = datetime.datetime.now(datetime.timezone.utc)
    if now.month == 12:
        next_month = now.replace(year=now.year+1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month+1, day=1)
    return int(next_month.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

def generate_quests(duration: str) -> dict:
    """Generate randomized quests for a given duration"""
    num_quests = 2 if duration == "daily" else 3
    available_types = [q for q in QUEST_TYPES if duration in QUEST_GOAL_PRESETS.get(q, {})]
    selected = random.sample(available_types, min(num_quests, len(available_types)))
    quests = {}
    for q in selected:
        goal = random.choice(QUEST_GOAL_PRESETS[q][duration])
        quests[q] = {"current": 0, "goal": goal}
    return quests

async def update_quest(user_id: int, guild_id: int, quest_dict: dict, bot: commands.Bot, refresh_only: bool = False) -> list:
    """
    Update quest progress and award beans for completions
    
    Args:
        user_id: User ID
        guild_id: Guild ID
        quest_dict: Dict of quest types and amounts (e.g., {"chat_earnings": 500})
        bot: Discord bot instance
        refresh_only: If True, only refresh expired quests without updating progress
    
    Returns:
        List of completion messages for user feedback
    """
    ref = u_quests(user_id)
    quest_data = ref.get() or {}
    now = time.time()
    total_beans = 0
    messages = []
    
    # Import here to avoid circular imports
    from brawl.Currency.currency import CurrencySystem
    currency_cog = bot.get_cog("CurrencySystem")
    
    for duration in ["daily", "weekly", "monthly"]:
        dur_data = quest_data.get(duration, {})
        end_time = dur_data.get("end_time", 0)
        
        # Refresh expired quests
        if now >= end_time:
            if duration == "daily":
                new_end = get_next_daily_reset()
            elif duration == "weekly":
                new_end = get_next_weekly_reset()
            else:
                new_end = get_next_monthly_reset()
                
            dur_data = {
                "quests": generate_quests(duration),
                "end_time": new_end,
                "completed": {}
            }
            quest_data[duration] = dur_data
            ref.child(duration).set(dur_data)
        
        # Update quest progress
        if not refresh_only:
            quests = dur_data.get("quests", {})
            completed = dur_data.get("completed", {})
            updated = False
            all_completed = True

            for q_type, amount in quest_dict.items():
                if q_type in quests and q_type not in completed:
                    quests[q_type]["current"] += amount
                    updated = True
                    after = quests[q_type]["current"]

                    # Check if quest is completed
                    if after >= quests[q_type]["goal"]:
                        completed[q_type] = True
                        bean_reward = QUEST_BEAN_REWARDS[duration]
                        total_beans += bean_reward
                        messages.append(
                            f"<:yes:1036811164891480194> **{QUEST_DESCRIPTIONS[q_type]}** ({duration}): "
                            f"`{quests[q_type]['goal']}` ‎ <:fastforward:1351972114433048719> ‎ `+{bean_reward}` Beans"
                        )

                        stamp_cog = bot.get_cog("StampCard")
                        if stamp_cog:
                            # Notify that one quest (any tier) was finished
                            await stamp_cog.add_quest_completion(user_id)

            # Check if all quests completed for bonus
            if len(quests) > 0:
                for q in quests:
                    if q not in completed:
                        all_completed = False
                        break

                if all_completed and "bonus_awarded" not in dur_data:
                    bonus = QUEST_BONUS_BEANS[duration]
                    total_beans += bonus
                    dur_data["bonus_awarded"] = True
                    messages.append(
                        f"<a:tada:1227425729654820885> **Completed all {duration} quests** ‎ <:fastforward:1351972114433048719> ‎ `+{bonus}` Beans"
                    )
                    updated = True

                    stamp_cog = bot.get_cog("StampCard")
                    if stamp_cog:
                        await stamp_cog.add_quest_completion(user_id)

            if updated:
                dur_data["quests"] = quests
                dur_data["completed"] = completed
                ref.child(duration).set(dur_data)

    # Award beans if any quests completed
    if total_beans > 0 and currency_cog:
        await currency_cog.add_beans(user_id, total_beans, skip_quest_check=True)
    
    return messages

async def setup(bot: commands.Bot) -> None:
    pass

import datetime
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency import events
from brawl.Currency.card import render
from brawl.Currency.config import (
    ORDER_CHAT_BEANS,
    ORDER_FILLER,
    ORDER_LABELS,
    ORDER_STATION_TASKS,
    ORDER_TASK_LEVELS,
    QUEST_BEAN_REWARDS,
    QUEST_BONUS_BEANS,
)
from brawl.Currency.db import u_daily_checkin_streaks, u_quests
from brawl.Currency.helper import (
    BEAN_EMOTE,
    MAIN_GUILD_ID,
    NO_EMOTE,
    STAMP_EMOTE,
    YES_EMOTE,
)
from brawl.Currency.home import background
from brawl.Currency.ladder import level_of
from brawl.Currency.panel import notice
from brawl.Currency.rewardcard import draw_order

QUEST_TYPES = list(ORDER_LABELS)


class Progress(list):
    """The lines a finished task prints, with the Beans and Stamp they came with."""

    beans = 0
    stamp = False


ARROW = "<:fastforward:1351972114433048719>"


def midnight(day):
    return int(day.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def get_next_daily_reset():
    now = datetime.datetime.now(datetime.timezone.utc)
    return midnight(now + datetime.timedelta(days=1))


def generate_order(level):
    unlocked = [task for task, need in ORDER_TASK_LEVELS.items() if level >= need]
    tasks = random.sample(unlocked, min(ORDER_STATION_TASKS, len(unlocked)))
    if len(tasks) < ORDER_STATION_TASKS:
        tasks.append(ORDER_FILLER)
    order = {task: {"current": 0, "goal": 1} for task in tasks}
    order["chat_earnings"] = {"current": 0, "goal": ORDER_CHAT_BEANS}
    return order


def generate_quests(duration, level=0):
    return generate_order(level)


def label(task, goal):
    return ORDER_LABELS[task].format(goal=goal)


def clocked_in(user_id):
    last = (u_daily_checkin_streaks(user_id).get() or {}).get("last_claim", 0)
    return int(last // 86400) == int(time.time() // 86400)


def order_tasks(user_id):
    """Today's Order. A member takes it by clocking in, so it is empty before that."""
    if not clocked_in(user_id):
        return []
    daily = u_quests(user_id).child("daily").get() or {}
    if time.time() >= daily.get("end_time", 0):
        return []
    quests = daily.get("quests", {})
    done = daily.get("completed", {})
    return [
        (task, label(task, quests[task]["goal"]), quests[task], task in done)
        for task in ORDER_LABELS
        if task in quests
    ]


def order_lines(user_id):
    return [
        (
            f"{YES_EMOTE} ~~{name}~~"
            if done
            else f"▫️ {name} `{data['current']:,}/{data['goal']:,}`"
        )
        for _, name, data, done in order_tasks(user_id)
    ]


async def update_quest(
    user_id, guild_id, quest_dict, bot, refresh_only=False, chat=None
):
    """Moves Today's Order forward and pays for what got finished.

    chat is (Beans earned from chat today, the member's daily chat limit): the chat
    task follows both, so its goal is always the limit this member has right now.
    """
    ref = u_quests(user_id).child("daily")
    data = ref.get() or {}
    if time.time() >= data.get("end_time", 0):
        data = {
            "quests": generate_quests("daily", await level_of(bot, user_id, guild_id)),
            "end_time": get_next_daily_reset(),
            "completed": {},
        }
        ref.set(data)
    if refresh_only or not clocked_in(user_id):
        return []

    quests = data.get("quests", {})
    completed = data.get("completed", {})
    each, bonus = QUEST_BEAN_REWARDS["daily"], QUEST_BONUS_BEANS["daily"]
    beans = 0
    messages = Progress()
    updated = False
    moves = dict(quest_dict)
    if chat and "chat_earnings" in quests and "chat_earnings" not in completed:
        earned, limit = chat
        quests["chat_earnings"] = {"current": min(earned, limit), "goal": limit}
        moves["chat_earnings"] = 0
    for quest, amount in moves.items():
        if quest not in quests or quest in completed:
            continue
        quests[quest]["current"] += amount
        updated = True
        if quests[quest]["current"] < quests[quest]["goal"]:
            continue
        completed[quest] = True
        beans += each
        messages.append(
            f"{YES_EMOTE} **{label(quest, quests[quest]['goal'])}** ‎ {ARROW} ‎ "
            f"{BEAN_EMOTE} `+{each}`"
        )
    if not updated:
        return []

    if len(completed) == len(quests) and "bonus_awarded" not in data:
        data["bonus_awarded"] = True
        beans += bonus
        messages.stamp = True
        await events.emit("order", user_id)
        messages.append(
            f"<a:tada:1227425729654820885> **Order complete!** ‎ {ARROW} ‎ "
            f"{STAMP_EMOTE} **1 Stamp** and {BEAN_EMOTE} `+{bonus}`"
        )
    data["quests"] = quests
    data["completed"] = completed
    ref.set(data)

    currency = bot.get_cog("CurrencySystem")
    if beans and currency:
        await currency.add_beans(user_id, beans, skip_quest_check=True, reason="quest")
    messages.beans = beans
    return messages


async def wildcard(user_id, guild_id, bot):
    await update_quest(user_id, guild_id, {}, bot, refresh_only=True)
    for task, _, data, done in order_tasks(user_id):
        if not done and task != "chat_earnings":
            return await update_quest(
                user_id, guild_id, {task: data["goal"] - data["current"]}, bot
            )
    return []


def standing(user_id):
    """Today's Order as the rows a card draws."""
    return [
        (
            name,
            "Done" if done else f"{task['current']:,} / {task['goal']:,}",
            done,
            1 if done else task["current"] / task["goal"],
        )
        for _, name, task, done in order_tasks(user_id)
    ]


async def order_card(user_id, messages):
    progress = {
        "tasks": standing(user_id),
        "beans": getattr(messages, "beans", 0),
        "stamp": getattr(messages, "stamp", False),
        "background": background(user_id),
    }
    return await render(draw_order, progress, name="order")


async def report(interaction, messages):
    """After a station reply: Today's Order, if the reply moved it."""
    if messages:
        await interaction.followup.send(
            file=await order_card(interaction.user.id, messages), ephemeral=True
        )


class QuestAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def economy(self):
        return self.bot.get_cog("CurrencySystem")

    @app_commands.command(
        name="update-quest", description="Update a user's quest progress (Admin only)"
    )
    @app_commands.describe(
        user="Target user",
        quest="Quest type to update",
        amount="Amount to add to the quest",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def update_quest_cmd(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        quest: str,
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

        if quest not in QUEST_TYPES:
            return await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} Invalid quest type. Valid types are: {', '.join(QUEST_TYPES)}",
                    "bad",
                ),
                ephemeral=True,
            )

        # Call update_quest to properly track the quest completion
        messages = await update_quest(
            user.id, interaction.guild.id, {quest: amount}, self.bot
        )

        result = (
            "\n".join(messages)
            if messages
            else f"Updated {user.mention}'s **{quest}** quest by `{amount}`."
        )

        await interaction.response.send_message(
            embed=discord.Embed(description=result, color=discord.Color.green())
        )

    @update_quest_cmd.autocomplete("quest")
    async def quest_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            # Get user ID from interaction data
            user_id = None
            if interaction.data and "options" in interaction.data:
                for option in interaction.data["options"]:
                    if option.get("name") == "user":
                        user_id = int(option.get("value", 0))
                        break

            if not user_id:
                return []

            ref = u_quests(user_id)
            quest_data = ref.get() or {}

            quest_types_available = set(quest_data.get("daily", {}).get("quests", {}))
            current_lower = current.lower()

            options = []
            for quest_type in sorted(quest_types_available):
                if current_lower in quest_type.lower():
                    options.append(
                        app_commands.Choice(name=quest_type, value=quest_type)
                    )

            return options[:25]  # Discord limits to 25 choices
        except Exception:
            return []

    @update_quest_cmd.error
    async def update_quest_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        await interaction.response.send_message(
            embed=notice(f"```{str(error)}```"), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(QuestAdmin(bot))

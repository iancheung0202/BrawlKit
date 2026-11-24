"""Counts what every system pays and takes, by week, so each can be compared."""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency import events
from brawl.Currency.db import g_ledger
from brawl.Currency.helper import MAIN_GUILD_ID

# Every source an earning or a spend is tagged with, and its name in the report.
SOURCES = {
    "chat": "Chat",
    "thermometer": "Thermometer",
    "clock_in": "Clock in",
    "order": "Today's Order",
    "level_up": "Level up",
    "brew": "Brewing",
    "shop": "Shop",
    "drop": "Star Drops and Mega Boxes",
    "boss": "Boss inspection",
    "table_goal": "Table weekly goal",
    "table_winner": "Top table",
    "invites": "Invites",
    "games": "Games",
    "welcome": "Welcome button",
    "topic": "Topics",
    "rep": "Team finder rep",
    "tutorial": "First shift",
    "pass": "Pass redeemed",
    "staff": "Staff",
    "other": "Untagged",
}
AMOUNTS = ("beans", "tokens", "stamps", "beans_spent", "tokens_spent")
SAVE_SECONDS = 300

waiting = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
members = defaultdict(lambda: defaultdict(set))


def week_key(now=None):
    """The Monday (UTC) that began this week."""
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")


def note(source, user_id, beans=0, tokens=0, stamps=0):
    """Counts one use of a system. Kept in memory until the next save."""
    source = source if source in SOURCES else "other"
    week = week_key()
    row = waiting[week][source]
    row["uses"] += 1
    for name, amount in (("beans", beans), ("tokens", tokens), ("stamps", stamps)):
        if amount > 0:
            row[name] += amount
        elif amount < 0:
            row[f"{name}_spent"] -= amount
    members[week][source].add(str(user_id))


async def on_wallet(user_id, beans=0, tokens=0, reason="other"):
    note(reason, user_id, beans=beans, tokens=tokens)


def save():
    """Adds what was counted since the last save to the saved weeks."""
    for week in list(waiting):
        rows, people = waiting.pop(week), members.pop(week, {})
        ref = g_ledger(MAIN_GUILD_ID).child(week)
        saved = ref.get() or {}
        for source, row in rows.items():
            old = saved.setdefault(source, {})
            for name, amount in row.items():
                old[name] = old.get(name, 0) + amount
            old["members"] = {
                **old.get("members", {}),
                **dict.fromkeys(people.get(source, ()), True),
            }
        ref.set(saved)


def report(week):
    """The saved week as lines of text, busiest system first."""
    saved = g_ledger(MAIN_GUILD_ID).child(week).get() or {}
    if not saved:
        return f"Week of {week}: nothing counted."
    everyone = {user for row in saved.values() for user in row.get("members", {})}
    lines = [
        f"Week of {week}: {len(everyone)} members used the cafe.",
        "",
        f"{'System':<26}{'Members':>8}{'Uses':>8}{'Beans':>10}{'Tokens':>8}"
        f"{'Stamps':>8}{'Beans out':>11}{'Tokens out':>11}",
    ]
    order = sorted(saved, key=lambda source: -len(saved[source].get("members", {})))
    for source in order:
        row = saved[source]
        lines.append(
            f"{SOURCES.get(source, source):<26}{len(row.get('members', {})):>8}"
            f"{row.get('uses', 0):>8}"
            + "".join(
                f"{row.get(name, 0):>{width},}"
                for name, width in zip(AMOUNTS, (10, 8, 8, 11, 11))
            )
        )
    unused = [name for source, name in SOURCES.items() if source not in saved]
    if unused:
        lines += ["", "Not used: " + ", ".join(unused)]
    return "\n".join(lines)


def pages(text, size=1900):
    page = ""
    for line in text.split("\n"):
        if len(page) + len(line) + 1 > size:
            yield page
            page = ""
        page += line + "\n"
    if page:
        yield page


class Ledger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        events.listen("wallet", on_wallet)
        self.task = bot.loop.create_task(self.loop())

    def cog_unload(self):
        self.task.cancel()

    async def owner(self):
        app = await self.bot.application_info()
        owner = app.team.owner if app.team else app.owner
        return self.bot.get_user(owner.id) or await self.bot.fetch_user(owner.id)

    async def loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(SAVE_SECONDS)
            try:
                save()
                await self.send_last_week()
            except Exception as e:
                print(f"Failed to save the ledger: {e}")

    async def send_last_week(self):
        """Sends the owner each finished week once."""
        sent = g_ledger(MAIN_GUILD_ID).child("sent")
        last = week_key(datetime.now(timezone.utc) - timedelta(days=7))
        if sent.get() == last or not g_ledger(MAIN_GUILD_ID).child(last).get():
            return
        sent.set(last)
        owner = await self.owner()
        for page in pages(report(last)):
            await owner.send(f"```\n{page}```")

    @app_commands.command(
        name="economy", description="What each cafe system paid this week (Admin only)"
    )
    @app_commands.describe(weeks_ago="0 is this week, 1 is last week")
    @app_commands.default_permissions(administrator=True)
    async def economy(self, interaction: discord.Interaction, weeks_ago: int = 0):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Admins only.", ephemeral=True
            )
        save()
        week = week_key(datetime.now(timezone.utc) - timedelta(days=7 * weeks_ago))
        texts = list(pages(report(week)))
        await interaction.response.send_message(f"```\n{texts[0]}```", ephemeral=True)
        for text in texts[1:]:
            await interaction.followup.send(f"```\n{text}```", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Ledger(bot))

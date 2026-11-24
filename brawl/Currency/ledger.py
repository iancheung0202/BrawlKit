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
WIDTHS = (10, 8, 8, 11, 11)
SORTS = {
    "Most members": "members",
    "Most uses": "uses",
    "Most Beans paid": "beans",
    "Most Tokens paid": "tokens",
    "Most Stamps paid": "stamps",
    "Most Beans taken": "beans_spent",
    "Most Tokens taken": "tokens_spent",
}
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


def line(name, members, row):
    return f"{name:<26}{members:>8,}{row.get('uses', 0):>8,}" + "".join(
        f"{row.get(name, 0):>{width},}" for name, width in zip(AMOUNTS, WIDTHS)
    )


def grid(saved, sort="members"):
    """The week as lines of fixed-width text, ending with the whole cafe."""
    people = {source: len(row.get("members", {})) for source, row in saved.items()}
    order = sorted(
        saved,
        key=lambda source: -{**saved[source], "members": people[source]}.get(sort, 0),
    )
    everyone = {user for row in saved.values() for user in row.get("members", {})}
    whole = {
        name: sum(row.get(name, 0) for row in saved.values())
        for name in ("uses", *AMOUNTS)
    }
    head = (
        f"{'System':<26}{'Members':>8}{'Uses':>8}{'Beans':>10}{'Tokens':>8}"
        f"{'Stamps':>8}{'Beans out':>11}{'Tokens out':>11}"
    )
    return [
        head,
        *(
            line(SOURCES.get(source, source), people[source], saved[source])
            for source in order
        ),
        "-" * len(head),
        line("Whole cafe", len(everyone), whole),
    ]


class Sort(discord.ui.Select):
    def __init__(self, chosen):
        super().__init__(
            options=[
                discord.SelectOption(label=label, default=label == chosen)
                for label in SORTS
            ]
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.sort = self.values[0]
        await self.view.turn(interaction)


class EconomyView(discord.ui.LayoutView):
    """One week of the ledger as a table, with a sort menu and week buttons."""

    def __init__(self, weeks_ago=0, turns=True):
        super().__init__(timeout=600)
        self.weeks_ago, self.turns, self.sort = weeks_ago, turns, next(iter(SORTS))
        self.lay_out()

    async def turn(self, interaction):
        save()
        self.lay_out()
        await interaction.response.edit_message(view=self)

    def turner(self, label, weeks_ago):
        button = discord.ui.Button(
            label=label, style=discord.ButtonStyle.grey, disabled=weeks_ago < 0
        )

        async def go(interaction: discord.Interaction):
            self.weeks_ago = weeks_ago
            await self.turn(interaction)

        button.callback = go
        return button

    def lay_out(self):
        self.clear_items()
        week = week_key(datetime.now(timezone.utc) - timedelta(weeks=self.weeks_ago))
        saved = g_ledger(MAIN_GUILD_ID).child(week).get() or {}
        day = datetime.strptime(week, "%Y-%m-%d")
        ui = discord.ui
        box = ui.Container(
            ui.TextDisplay(f"## Cafe economy\n-# Week of {day:%B} {day.day}")
        )
        if saved:
            table = "\n".join(grid(saved, SORTS[self.sort]))
            box.add_item(ui.TextDisplay(f"```\n{table}```"))
        else:
            box.add_item(ui.TextDisplay("Nothing was counted this week."))
        unused = [name for source, name in SOURCES.items() if source not in saved]
        if unused and saved:
            box.add_item(ui.TextDisplay("-# Not used: " + ", ".join(unused)))
        if self.turns:
            box.add_item(ui.Separator())
            box.add_item(ui.ActionRow(Sort(self.sort)))
            box.add_item(
                ui.ActionRow(
                    self.turner("Earlier week", self.weeks_ago + 1),
                    self.turner("Later week", self.weeks_ago - 1),
                )
            )
        self.add_item(box)


class Ledger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        events.listen("wallet", on_wallet)
        self.task = bot.loop.create_task(self.loop())

    def cog_unload(self):
        self.task.cancel()
        save()

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
        await owner.send(view=EconomyView(1, turns=False))

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
        await interaction.response.send_message(
            view=EconomyView(max(weeks_ago, 0)), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Ledger(bot))

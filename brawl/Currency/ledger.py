"""Counts what every system pays and takes, by week, so each can be compared."""

import asyncio
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency import events
from brawl.Currency.db import g_ledger
from brawl.Currency.helper import MAIN_GUILD_ID, STORE_ITEMS

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
COLUMNS = ("bought", "dropped", "used")
ITEM_SORTS = {f"Sort by {column}": column for column in COLUMNS}
ITEM_ROWS = 25
OLDER, NEWER = "<:backarrow:1351972111010369618>", "<:rightarrow:1351972116819480616>"
SORTS = {
    "Sort by members": "members",
    "Sort by uses": "uses",
    "Sort by Beans": "beans",
    "Sort by Tokens": "tokens",
    "Sort by Stamps": "stamps",
    "Sort by Beans out": "beans_spent",
    "Sort by Tokens out": "tokens_spent",
}
SAVE_SECONDS = 300

waiting = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
members = defaultdict(lambda: defaultdict(set))
items = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))


def g_items(week):
    return g_ledger(MAIN_GUILD_ID).child("items").child(week)


def week_start(now=None):
    """The Sunday 00:00 UTC that began the week, the same week the tables use."""
    now = now or datetime.now(timezone.utc)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=(now.weekday() + 1) % 7)


def week_key(now=None):
    """The Sunday that began this week."""
    return week_start(now).strftime("%Y-%m-%d")


def until_next_week(early=timedelta(0)):
    """Seconds until this week ends, or until `early` before that."""
    left = week_start() + timedelta(days=7) - early - datetime.now(timezone.utc)
    return left.total_seconds() % (7 * 86400)


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


def item(name, bought=0, dropped=0, used=0):
    """Counts an item bought, dropped or used. Kept in memory until the next save."""
    row = items[week_key()][re.sub(r"[.$#\[\]/]", " ", str(name))]
    for column, amount in zip(COLUMNS, (bought, dropped, used)):
        row[column] += amount


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
    for week in list(items):
        ref = g_items(week)
        saved = ref.get() or {}
        for name, row in items.pop(week).items():
            old = saved.setdefault(name, {})
            for column, amount in row.items():
                old[column] = old.get(column, 0) + amount
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


def ago(weeks):
    return ("This week", "Last week")[weeks] if weeks < 2 else f"{weeks} weeks ago"


def stock(saved, sort="bought"):
    """The week's items as lines of fixed-width text, busiest first."""
    rows = sorted(saved.items(), key=lambda item: -item[1].get(sort, 0))
    lines = [f"{'Item':<26}{'Bought':>8}{'Dropped':>9}{'Used':>8}"] + [
        f"{STORE_ITEMS.get(name, {}).get('name', name)[:25]:<26}"
        f"{row.get('bought', 0):>8,}{row.get('dropped', 0):>9,}{row.get('used', 0):>8,}"
        for name, row in rows[:ITEM_ROWS]
    ]
    more = len(rows) - ITEM_ROWS
    return lines + [f"and {more} more"] * (more > 0)


class Sort(discord.ui.Select):
    """A menu that sorts one of the two tables."""

    def __init__(self, field, options, chosen):
        self.field = field
        super().__init__(
            options=[
                discord.SelectOption(label=label, default=label == chosen)
                for label in options
            ]
        )

    async def callback(self, interaction: discord.Interaction):
        setattr(self.view, self.field, self.values[0])
        await self.view.turn(interaction)


class EconomyView(discord.ui.LayoutView):
    """One week of the ledger as two tables, each with a sort menu, and week arrows."""

    def __init__(self, weeks_ago=0, turns=True):
        super().__init__(timeout=600)
        self.weeks_ago, self.turns = weeks_ago, turns
        self.sort, self.item_sort = next(iter(SORTS)), next(iter(ITEM_SORTS))
        self.lay_out()

    async def turn(self, interaction):
        save()
        self.lay_out()
        await interaction.response.edit_message(view=self)

    def turner(self, emoji, weeks_ago):
        button = discord.ui.Button(
            emoji=emoji, style=discord.ButtonStyle.grey, disabled=weeks_ago < 0
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
        quiet = [
            name
            for source, name in SOURCES.items()
            if source not in saved and source != "other"
        ]
        if quiet and saved:
            box.add_item(ui.TextDisplay("-# No activity: " + ", ".join(quiet)))
        if self.turns:
            box.add_item(ui.ActionRow(Sort("sort", SORTS, self.sort)))
        box.add_item(ui.Separator())
        bought = g_items(week).get() or {}
        if bought:
            table = "\n".join(stock(bought, ITEM_SORTS[self.item_sort]))
            box.add_item(ui.TextDisplay(f"```\n{table}```"))
        else:
            box.add_item(ui.TextDisplay("No items were bought, dropped or used."))
        if self.turns:
            box.add_item(ui.ActionRow(Sort("item_sort", ITEM_SORTS, self.item_sort)))
            box.add_item(
                ui.ActionRow(
                    self.turner(OLDER, self.weeks_ago + 1),
                    discord.ui.Button(label=ago(self.weeks_ago), disabled=True),
                    self.turner(NEWER, self.weeks_ago - 1),
                )
            )
        self.add_item(box)


class Ledger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        events.listen("wallet", on_wallet)
        events.listen("top_table_paid", self.on_top_table_paid)
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
            await asyncio.sleep(min(SAVE_SECONDS, until_next_week() + 1))
            try:
                save()
                await self.send_last_week()
            except Exception as e:
                print(f"Failed to save the ledger: {e}")

    async def on_top_table_paid(self, _, week):
        g_ledger(MAIN_GUILD_ID).child("paid").set(week)

    async def send_last_week(self):
        """Sends the owner each finished week once, after its top table was paid."""
        book = g_ledger(MAIN_GUILD_ID)
        sent = book.child("sent")
        last = week_key(datetime.now(timezone.utc) - timedelta(days=7))
        paid = book.child("paid").get() == last
        if sent.get() == last or not paid or not book.child(last).get():
            return
        sent.set(last)
        owner = await self.owner()
        await owner.send(view=EconomyView(1, turns=False))

    @app_commands.command(
        name="economy", description="What each cafe system paid this week (Admin only)"
    )
    @app_commands.default_permissions(administrator=True)
    async def economy(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "Admins only.", ephemeral=True
            )
        save()
        await interaction.response.send_message(view=EconomyView(), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Ledger(bot))

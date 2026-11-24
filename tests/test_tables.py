import asyncio
from unittest.mock import AsyncMock

from brawl.Currency import tablecard
from brawl.Currency.config import (
    TABLE_QUEST_TYPES,
    TABLE_SEATS,
    TABLE_WINNER_STAMPS,
    TABLE_WINNER_TOKENS,
)
from brawl.Currency.db import g_tables, g_user_tables, u_balance, u_veteran
from brawl.Currency.helper import MAIN_GUILD_ID
from tests.conftest import text

HOST = 1


def run(cafe, user, command, *args):
    interaction = cafe.interaction(user)
    interaction.guild.id = MAIN_GUILD_ID
    interaction.guild.get_member.return_value.display_name = f"member {user}"
    cog = cafe.cogs["TableSystem"]
    cog.bot.get_user.return_value.send = AsyncMock()
    u_veteran(user).set(True)
    asyncio.run(getattr(cog, command).callback(cog, interaction, *args))
    return interaction


def reserve(cafe):
    return run(cafe, HOST, "table_reserve", "Roasters", "We brew", "#E67E22", "🔥")


def sent(interaction):
    return interaction.response.send_message.call_args


def test_reserving_a_table_shows_its_card(cafe):
    reply = sent(reserve(cafe))
    assert reply.kwargs["file"].filename == "table.jpg"
    assert g_user_tables(MAIN_GUILD_ID, HOST).get() == "roasters"
    assert g_tables(MAIN_GUILD_ID, "roasters").get()["host"] == HOST


def test_a_table_is_recognized_at_five_and_full_at_ten(cafe):
    reserve(cafe)
    for user in range(2, TABLE_SEATS + 1):
        reply = sent(run(cafe, user, "table_seat", "Roasters"))
        assert reply.kwargs["file"].filename == "table.jpg"
        recognized = g_tables(MAIN_GUILD_ID, "roasters").get().get("formalized", False)
        assert recognized == (user >= 5)
    late = sent(run(cafe, 99, "table_seat", "Roasters"))
    assert "full" in text(late)
    assert g_user_tables(MAIN_GUILD_ID, 99).get() is None


def test_my_table_is_a_card(cafe):
    reserve(cafe)
    interaction = run(cafe, HOST, "table_mine")
    assert interaction.followup.send.call_args.kwargs["file"].filename == "table.jpg"


def test_a_kicked_member_cannot_come_straight_back(cafe):
    reserve(cafe)
    run(cafe, 2, "table_seat", "Roasters")
    kicked = AsyncMock(id=2)
    run(cafe, HOST, "table_kick", kicked)
    assert g_user_tables(MAIN_GUILD_ID, 2).get() is None
    assert "kicked" in text(sent(run(cafe, 2, "table_seat", "Roasters")))


def test_a_kick_with_no_user_clears_only_members_who_left(cafe, monkeypatch):
    import discord

    reserve(cafe)
    for user in (2, 3):
        run(cafe, user, "table_seat", "Roasters")
    gone = discord.NotFound(AsyncMock(status=404), "gone")
    interaction = cafe.interaction(HOST)
    interaction.guild.get_member = lambda user: user != 3
    interaction.guild.fetch_member = AsyncMock(side_effect=gone)
    cog = cafe.cogs["TableSystem"]
    asyncio.run(cog.table_kick.callback(cog, interaction))
    assert "Cleared 1 seat" in text(sent(interaction))
    assert g_tables(MAIN_GUILD_ID, "roasters").get()["members"] == [HOST, 2]
    assert g_user_tables(MAIN_GUILD_ID, 3).get() is None
    asyncio.run(cog.table_kick.callback(cog, interaction))
    assert "still in the server" in text(sent(interaction))
    assert "kicked" not in text(sent(run(cafe, 3, "table_seat", "Roasters")))


def test_the_host_leaving_hands_over_or_closes(cafe):
    reserve(cafe)
    run(cafe, 2, "table_seat", "Roasters")
    run(cafe, HOST, "table_leave")
    assert g_tables(MAIN_GUILD_ID, "roasters").get()["host"] == 2
    run(cafe, 2, "table_leave")
    assert g_tables(MAIN_GUILD_ID, "roasters").get() is None


def test_the_quest_pays_every_member_once_per_step(cafe):
    reserve(cafe)
    for user in range(2, 6):
        run(cafe, user, "table_seat", "Roasters")
    cog = cafe.cogs["TableSystem"]
    cog.bot.fetch_user = AsyncMock()
    quest = TABLE_QUEST_TYPES["bean_collector"]
    target, reward = quest["targets"][0], quest["rewards"][0]
    assert asyncio.run(cog.check_and_reward_quest(MAIN_GUILD_ID, "roasters", 5)) is None
    paid = asyncio.run(cog.check_and_reward_quest(MAIN_GUILD_ID, "roasters", target))
    assert paid["reward"] == reward and paid["members_count"] == 5
    asyncio.run(cog.check_and_reward_quest(MAIN_GUILD_ID, "roasters", target + 1))
    assert u_balance(3).get()["Beans"] == reward
    dm = cog.bot.fetch_user.return_value.send.call_args
    assert dm.kwargs["file"].filename == "table.png"


def test_cards_draw_for_every_size_of_table():
    for seats in (1, 4, 5, 10):
        for tier in (0, 3, 5):
            assert tablecard.draw_table(
                {
                    "background": "gym",
                    "name": "A very long table name that goes on and on",
                    "motto": "motto " * 30,
                    "color": "#fa0",
                    "weekly_beans": 23_456,
                    "tier": tier,
                    "members": [
                        ("name " * 9, 12_345, n == 0, n == 1, b"") for n in range(seats)
                    ],
                }
            )
    assert (TABLE_WINNER_TOKENS, TABLE_WINNER_STAMPS) == (5, 1)


def test_members_the_bot_has_not_loaded_are_asked_for():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from brawl.Currency.card import roster

    loaded = {1: "Ann"}
    guild = MagicMock()
    guild.get_member = loaded.get

    async def query(user_ids, cache):
        loaded.update({user: f"member {user}" for user in user_ids if user != 3})

    guild.query_members = AsyncMock(side_effect=query)
    assert asyncio.run(roster(guild, [1, "2", 3])) == ["Ann", "member 2", None]
    guild.query_members.assert_awaited_once_with(user_ids=[2, 3], cache=True)


def test_a_missed_sunday_still_resets_the_week(cafe):
    import asyncio
    import time
    from datetime import datetime, timezone

    from brawl.Currency import tables
    from brawl.Currency.db import g_table_reset, g_tables
    from brawl.Currency.helper import MAIN_GUILD_ID

    wednesday = datetime(2026, 11, 25, 15, 30, tzinfo=timezone.utc)
    assert tables.week_start(wednesday) == datetime(2026, 11, 22, tzinfo=timezone.utc)
    sunday = datetime(2026, 11, 22, 0, 0, tzinfo=timezone.utc)
    assert tables.week_start(sunday) == sunday

    cog = cafe.cogs["TableSystem"]
    cog.bot.get_channel = lambda _: None
    g_tables(MAIN_GUILD_ID, "owls").set(
        {
            "name": "Owls",
            "emoji": "o",
            "color": "#ffffff",
            "formalized": True,
            "members": [7],
            "weekly_beans": 900,
            "user_contributions": {"1": 900},
            "quest": {"start_time": 1, "current_tier": 5, "progress": 900},
        }
    )
    assert cog.reset_due()
    g_table_reset(MAIN_GUILD_ID).set(time.time())
    asyncio.run(cog.reset_week())
    table = g_tables(MAIN_GUILD_ID, "owls").get()
    assert table["weekly_beans"] == 0 and table["quest"]["current_tier"] == 0
    from brawl.Currency import stampcard

    assert u_balance(7).get()["Tokens"] == TABLE_WINNER_TOKENS
    assert stampcard.stamps(7) == TABLE_WINNER_STAMPS
    assert not cog.reset_due()

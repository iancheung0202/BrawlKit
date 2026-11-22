import asyncio
from unittest.mock import AsyncMock

from brawl.Currency import tablecard
from brawl.Currency.config import TABLE_QUEST_TYPES, TABLE_SEATS, TABLE_WINNER_TOKENS
from brawl.Currency.db import g_tables, g_user_tables, u_balance, u_veteran
from brawl.Currency.helper import MAIN_GUILD_ID

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
    assert "full" in late[0][0]
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
    assert "kicked" in sent(run(cafe, 2, "table_seat", "Roasters"))[0][0]


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
    assert dm.kwargs["file"].filename == "table.jpg"


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
    assert TABLE_WINNER_TOKENS == 3


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

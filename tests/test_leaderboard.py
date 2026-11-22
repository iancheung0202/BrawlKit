import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from brawl.Currency import boardcard
from brawl.Currency.db import g_tables, g_user_tables, u_balance
from brawl.Currency.helper import MAIN_GUILD_ID
from brawl.Currency.pagination import BOARDS
from tests.conftest import text

ME = 7


def board(cafe, currency):
    interaction = cafe.interaction(ME)
    interaction.guild.id = MAIN_GUILD_ID
    interaction.guild.get_member.return_value.display_name = "Sam"
    interaction.guild.get_member.return_value.bot = False
    cog = cafe.cogs["Leaderboard"]
    asyncio.run(cog.leaderboard.callback(cog, interaction, currency))
    return interaction.followup.send.call_args


def test_every_board_has_art():
    for _, icon, _, value_icon, note_icon in BOARDS.values():
        for extra in filter(None, (value_icon, note_icon)):
            assert boardcard.Card(64, 64).icon(extra, 0, 0, 32) is None
        assert boardcard.Card(64, 64).icon(icon, 0, 0, 32) is None


def test_beans_board_ranks_highest_first_and_finds_you(cafe):
    for user in range(1, 26):
        u_balance(user).set({"Beans": user * 10, "Tokens": 0})
    sent = board(cafe, "Beans")
    view = sent.kwargs["view"]
    assert sent.kwargs["file"].filename == "leaderboard.jpg"
    assert view.entries[0][:3] == (25, None, "250")
    assert view.board["yours"] == 19 and view.total_pages == 3
    assert view.board["total"] == "25 members"


def test_turning_the_page_redraws_the_card(cafe):
    for user in range(1, 26):
        u_balance(user).set({"Beans": user, "Tokens": 0})
    view = board(cafe, "Beans").kwargs["view"]
    interaction = cafe.interaction(ME)
    interaction.response.is_done.return_value = False
    asyncio.run(view.show_page(interaction, 2))
    edit = interaction.response.edit_message.call_args.kwargs
    assert edit["attachments"][0].filename == "leaderboard.jpg" and view.page == 2


def test_an_empty_board_says_so(cafe):
    assert "Nobody" in text(board(cafe, "Tokens"))


def test_tables_board_ranks_recognized_tables_and_finds_yours(cafe):
    for name, beans, formal in (
        ("Owls", 50, True),
        ("Cats", 90, True),
        ("New", 99, False),
    ):
        g_tables(MAIN_GUILD_ID, name.lower()).set(
            {"name": name, "weekly_beans": beans, "formalized": formal, "members": [1]}
        )
    g_user_tables(MAIN_GUILD_ID, ME).set("owls")
    view = board(cafe, "Tables").kwargs["view"]
    assert [entry[1] for entry in view.entries] == ["Cats", "Owls"]
    assert view.board["yours"] == 2 and view.board["total"] == "2 tables"


@pytest.mark.parametrize("rows", [1, 10])
def test_the_card_draws_short_and_full_pages(rows):
    assert boardcard.draw_board(
        {
            "background": "gym",
            "title": "Most invites this month",
            "value_icon": "kit/icon_inbox",
            "note_icon": None,
            "icon": "kit/icon_inbox",
            "yours": 1234,
            "page": 1,
            "pages": 200,
            "total": "2,000 members",
            "rows": [
                (
                    n,
                    "a very long display name " * 3,
                    "1,234,567 invites",
                    "9 joined",
                    n == 2,
                    b"",
                )
                for n in range(1, rows + 1)
            ],
        }
    )


def test_members_who_left_and_bots_hold_no_rank(cafe):
    for user in range(1, 11):
        u_balance(user).set({"Beans": user * 10, "Tokens": 0})
    interaction = cafe.interaction(ME)
    interaction.guild.get_member = lambda user: (
        None if user > ME else MagicMock(bot=user == 3)
    )
    cog = cafe.cogs["Leaderboard"]
    asyncio.run(cog.leaderboard.callback(cog, interaction, "Beans"))
    view = interaction.followup.send.call_args.kwargs["view"]
    assert [entry[0] for entry in view.entries] == [7, 6, 5, 4, 2, 1]
    assert view.board["yours"] == 1
    assert view.board["total"] == "6 members"


def test_board_loads_the_member_list_once_when_it_is_missing(cafe):
    u_balance(ME).set({"Beans": 10, "Tokens": 0})
    interaction = cafe.interaction(ME)
    interaction.guild.chunked = False
    interaction.guild.chunk = AsyncMock()
    interaction.guild.get_member.return_value.bot = False
    cog = cafe.cogs["Leaderboard"]
    asyncio.run(cog.leaderboard.callback(cog, interaction, "Beans"))
    interaction.guild.chunk.assert_awaited_once()


def test_stamps_board_counts_new_and_converted_cards(cafe):
    from brawl.Currency.db import u_stamp_card

    u_stamp_card(1).set({"count": 4})
    u_stamp_card(2).set({"stamps": {"daily_checkins": 30, "brew_sells": 30}})
    u_stamp_card(3).set({"stamps": {"boss_inspections": 1}})
    view = board(cafe, "Stamps").kwargs["view"]
    assert [entry[:3] for entry in view.entries] == [(2, None, "10"), (1, None, "4")]


def test_in_game_boards_rank_linked_members_by_their_saved_stats(cafe):
    from brawl.Currency.db import u_tag
    from brawl.Utility.profile import keep_stats

    for user, trophies in ((1, 500), (2, 90000), (ME, 20000)):
        u_tag(user).set({"tag": f"#A{user}"})
        keep_stats(user, {"trophies": trophies, "famePoints": 0})
    view = board(cafe, "Trophies").kwargs["view"]
    assert [entry[:3] for entry in view.entries] == [
        (2, None, "90,000"),
        (ME, None, "20,000"),
        (1, None, "500"),
    ]
    assert view.board["yours"] == 2
    assert "Nobody" in text(board(cafe, "Fame"))

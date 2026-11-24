import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from brawl.Currency import ledger, wallet
from brawl.Currency.config import REP_PAID_DAILY, REP_TOKENS
from brawl.TeamFinder import reputationSystem as reputation
from brawl.TeamFinder import teamFind
from tests.conftest import text

HOST, HELPER, OTHER = 1, 2, 3
MESSAGE = 77


@pytest.fixture
def finder(cafe):
    card = AsyncMock(return_value="card")
    with patch.object(teamFind, "request_card", card):
        cafe.ref(teamFind.REQUESTS).child(str(MESSAGE)).set(
            {
                "host": HOST,
                "tag": "#ABC",
                "code": "XABC123",
                "seats": 2,
                "open": True,
                "at": 0,
            }
        )
        yield cafe


def member(user_id):
    found = MagicMock(id=user_id, display_name=f"member {user_id}")
    found.mention = f"<@{user_id}>"
    found.add_roles = AsyncMock()
    return found


def press(cafe, name, user_id, admin=False):
    interaction = cafe.interaction(user_id)
    interaction.guild.fetch_channel = AsyncMock()
    interaction.guild.get_member = member
    interaction.user.guild_permissions.administrator = admin
    interaction.message.id = MESSAGE
    interaction.message.content = f"<@{HOST}> is looking for teammates"
    interaction.message.edit = AsyncMock()
    interaction.message.guild = interaction.guild

    async def run():
        await getattr(teamFind.RequestView(), name).callback(interaction)

    asyncio.run(run())
    return interaction


def claims(cafe):
    return (teamFind.get_request(MESSAGE) or {}).get("claims", [])


def test_claims_fill_the_team(finder):
    press(finder, "claim", HELPER)
    assert claims(finder) == [HELPER]
    edit = press(finder, "claim", OTHER).edit_original_response.call_args.kwargs
    assert claims(finder) == [HELPER, OTHER]
    assert edit["attachments"] == ["card"] and edit["view"].claim.disabled
    assert edit["view"].children[-1].url == teamFind.INVITE.format("XABC123")


def test_claim_is_refused_for_host_repeat_and_full_team(finder):
    finder.ref(teamFind.REQUESTS).child(f"{MESSAGE}/seats").set(1)
    assert "own" in text(press(finder, "claim", HOST).response.send_message.call_args)
    press(finder, "claim", HELPER)
    again = press(finder, "claim", HELPER).response.send_message.call_args
    assert "already" in text(again)
    assert "full" in text(press(finder, "claim", OTHER).response.send_message.call_args)
    assert claims(finder) == [HELPER]


def test_only_host_or_admin_can_close(finder):
    refused = press(finder, "close", OTHER)
    assert "not your" in text(refused.response.send_message.call_args)
    assert teamFind.get_request(MESSAGE)
    closed = press(finder, "close", OTHER, admin=True)
    assert closed.message.edit.call_args.kwargs["content"] == teamFind.closed_text(HOST)
    assert not teamFind.get_request(MESSAGE)


def test_host_ticks_who_played_and_they_get_rep_and_a_token(finder):
    press(finder, "claim", HELPER)
    press(finder, "claim", OTHER)
    asked = press(finder, "close", HOST)
    view = asked.response.send_message.call_args.kwargs["view"]
    assert [option.value for option in view.menu.options] == ["2", "3"]
    assert teamFind.get_request(MESSAGE)
    view.played = [HELPER]
    asked.response.reset_mock()
    asyncio.run(view.close.callback(asked))
    assert not teamFind.get_request(MESSAGE)
    assert reputation.get_totals() == {HELPER: 1}
    assert wallet.balance(HELPER)[1] == REP_TOKENS and wallet.balance(OTHER)[1] == 0
    sent = asked.guild.fetch_channel.return_value.send.call_args[0][0]
    assert f"<@{HELPER}>" in sent and f"<@{OTHER}>" not in sent


def test_rep_is_once_a_day_per_host_and_tokens_stop_at_the_cap(cafe):
    helper = member(HELPER)
    assert asyncio.run(reputation.thank(helper, HOST)) == (REP_TOKENS, [])
    assert asyncio.run(reputation.thank(helper, HOST)) is None
    for host in range(10, 10 + REP_PAID_DAILY):
        asyncio.run(reputation.thank(helper, host))
    assert reputation.rep_of(HELPER) == REP_PAID_DAILY + 1
    assert wallet.balance(HELPER)[1] == REP_TOKENS * REP_PAID_DAILY
    assert ledger.waiting[ledger.week_key()]["rep"]["uses"] >= 1


def test_rep_unlocks_the_reward_role(cafe):
    cafe.ref(reputation.ROLES).set({"5": 2, "6": 50})
    helper = member(HELPER)
    assert asyncio.run(reputation.add_rep(helper, 1)) == []
    assert asyncio.run(reputation.add_rep(helper, 1)) == [helper.guild.get_role(5)]
    helper.add_roles.assert_awaited_once()
    assert asyncio.run(reputation.add_rep(helper, -9)) == []
    assert reputation.rep_of(HELPER) == 0


def test_requests_close_by_themselves_after_a_day(finder):
    cog = teamFind.TeamFind.__new__(teamFind.TeamFind)
    cog.bot = MagicMock()
    message = cog.bot.get_channel.return_value.fetch_message = AsyncMock()
    message.return_value.edit, message.return_value.id = AsyncMock(), MESSAGE
    finder.ref(teamFind.REQUESTS).child("78").set({"host": HOST, "at": 9**12})
    asyncio.run(teamFind.TeamFind.expire.coro(cog))
    assert not teamFind.get_request(MESSAGE) and teamFind.get_request(78)
    assert message.return_value.edit.call_args.kwargs[
        "content"
    ] == teamFind.closed_text(HOST)


def test_team_finder_is_cafe_only(cafe):
    interaction = cafe.interaction()
    interaction.guild.id = 5
    asyncio.run(teamFind.RegionButton("NA").callback(interaction))
    assert "Not available" in text(interaction.response.send_message.call_args)


def test_request_card_draws():
    from brawl.Currency.card import BACKGROUND
    from brawl.Utility.playercard import draw_request

    player = {"name": "Sam", "color": (255, 255, 255), "tag": "#ABC", "icon": b""}
    sheet = {
        "player": player,
        "label": "NA TEAM",
        "background": BACKGROUND,
        "mode": "Brawl Ball",
        "mode_art": b"",
        "kind": "Ranked",
        "trophies": 1234,
        "ranked": (5, 1000),
        "league_art": b"",
        "seats": 2,
        "faces": [b""],
        "open": True,
    }
    assert draw_request(sheet).getbuffer().nbytes > 1000


def test_game_mode_is_only_asked_for_trophies():
    async def run():
        view = teamFind.StartView("NA", {48000005: "Brawl Ball"}, "#ABC", None)
        assert view.mode_menu in view.children
        asked = MagicMock(response=AsyncMock())
        view.kind_menu._values = ["Ranked"]
        await view.kind_menu.callback(asked)
        assert view.mode_menu not in view.children
        await view.go.callback(asked)
        return asked.response.send_modal.call_args[0][0].pick

    assert asyncio.run(run()) == {"kind": "Ranked", "seats": 2}

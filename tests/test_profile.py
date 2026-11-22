import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from brawl.Currency.helper import MAIN_GUILD_ID
from brawl.Milestone import milestone
from brawl.Utility import api, playercard, profile
from tests.conftest import text

TAG = "#ME"
PLAYER = {"name": "Sam", "color": (255, 255, 255), "tag": TAG, "icon": b""}
STATS = {
    "name": "Sam",
    "icon": {"id": 1},
    "trophies": 6000,
    "ranked": 8,
    "highestRanked": 22,
    "fameTierName": "METEORIC FAME II",
    "brawlers": [
        {"id": 1, "name": "SHELLY", "power": 9, "trophies": 300},
        {"id": 2, "name": "COLT", "power": 11, "trophies": 1200},
    ],
}


def battle(result="victory", **extra):
    teams = [
        [{"tag": "#A", "brawler": {"id": 1}}],
        [{"tag": TAG, "brawler": {"id": 2}}],
    ]
    return {
        "battleTime": "20260101T100000.000Z",
        "event": {"mode": "brawlBall", "modeId": 5, "map": "Triple Dribble"},
        "battle": {"type": "ranked", "result": result, "teams": teams, **extra},
    }


def test_ranked_steps_and_fame_read_as_names():
    assert [playercard.league(rank) for rank in (0, 1, 8, 21, 22)] == [
        "Bronze I",
        "Bronze I",
        "Gold II",
        "Masters III",
        "Pro",
    ]
    assert playercard.fame_name(STATS) == "Meteoric II"
    assert playercard.fame_name({}) == "No Fame"
    assert playercard.fame_icon(STATS) == "game/fame_meteoric"


def test_a_battle_puts_the_player_side_first_and_names_how_it_ended():
    mine, others = playercard.sides(battle()["battle"], TAG)
    assert mine[0]["tag"] == TAG and others[0]["tag"] == "#A"
    assert playercard.outcome(battle("defeat")["battle"])[0] == "Loss"
    showdown = {"rank": 2, "players": [{"tag": TAG, "brawler": {"id": 2}}] * 10}
    assert playercard.outcome(showdown)[0] == "#2"
    assert playercard.sides(showdown, TAG)[1] == []
    assert playercard.spaced("brawlBall") == "Brawl Ball"
    now = datetime(2026, 1, 1, 13, 0)
    assert playercard.ago("20260101T100000.000Z", now) == "3h ago"


def test_brawlers_sort_by_the_chosen_order():
    names = lambda sort: [
        brawler["name"] for brawler in profile.sorted_brawlers(STATS["brawlers"], sort)
    ]
    assert names("default") == ["SHELLY", "COLT"]
    assert names("trophy_high") == names("alpha_asc") == ["COLT", "SHELLY"]


def test_every_player_card_draws_without_its_art():
    page = {"player": PLAYER, "background": "gym", "page": 1, "pages": 1, "art": {}}
    drawn = [
        playercard.draw_profile(
            {**page, "stats": STATS, "brawlers": 1},
        ),
        playercard.draw_brawlers(
            {**page, "brawlers": STATS["brawlers"], "sort": "A to Z", "total": "2"}
        ),
        playercard.draw_battles(
            {**page, "battles": [battle(), battle("defeat", trophyChange=-8)]}
        ),
        playercard.draw_milestones(
            {
                **page,
                "label": "ROLES UPDATED",
                "rows": [
                    {
                        "icon": "game/trophies",
                        "name": "Trophies",
                        "value": 6000,
                        "role": "5K",
                        "color": (255, 0, 0),
                        "goals": [1000, 5000, 9000],
                    }
                ],
            }
        ),
    ]
    assert all(card.getvalue().startswith(b"\xff\xd8") for card in drawn)


def test_the_brawler_total_comes_from_the_live_list(monkeypatch):
    listed = AsyncMock(return_value={"data": [{}] * 120})
    monkeypatch.setattr(api, "fetch", listed)
    monkeypatch.setitem(api.released, "at", 0)
    assert asyncio.run(api.brawler_count()) == 120
    assert asyncio.run(api.brawler_count()) == 120 and listed.await_count == 1
    monkeypatch.setitem(api.released, "at", 0)
    listed.return_value = None
    assert asyncio.run(api.brawler_count()) == 120


def test_milestone_roles_only_work_in_the_cafe(cafe):
    interaction = cafe.interaction(7)
    interaction.guild.id = 5
    asyncio.run(milestone.UpdateRolesButton().callback(interaction))
    assert "Not available here" in text(interaction.response.send_message.call_args)
    cog = milestone.MilestoneRolesCog(MagicMock())
    asyncio.run(cog.add.callback(cog, interaction, "trophy", 5, MagicMock(), "a", "b"))
    assert milestone.get_config() == {}
    interaction.guild.id = MAIN_GUILD_ID
    role = MagicMock(id=9)
    asyncio.run(cog.add.callback(cog, interaction, "trophy", 5, role, "a", "b"))
    assert milestone.get_config()["trophy"][0]["role_id"] == "9"


def test_update_roles_gives_the_role_saves_stats_and_sends_a_card(cafe, monkeypatch):
    from brawl.Currency.db import u_tag

    stats = {**STATS, "trophies": 6000}
    monkeypatch.setattr(milestone, "get_stats", AsyncMock(return_value=stats))
    monkeypatch.setattr(api, "image", AsyncMock(return_value=b""))
    milestone.set_config(
        {"trophy": [{"threshold": 5000, "role_id": "9", "name": "5K", "emoji": "x"}]}
    )
    u_tag(7).set({"tag": "me"})
    interaction = cafe.interaction(7)
    interaction.guild.id = MAIN_GUILD_ID
    role = MagicMock()
    role.name, role.color.value = "5K Trophies", 0
    interaction.user.guild.get_role.return_value = role
    interaction.user.roles = []
    interaction.user.add_roles = AsyncMock()
    asyncio.run(milestone.UpdateRolesButton().callback(interaction))
    interaction.user.add_roles.assert_awaited_once_with(role)
    assert interaction.followup.send.call_args.kwargs["file"].filename == (
        "milestones.jpg"
    )
    assert u_tag(7).get()["stats"]["trophies"] == 6000


def test_profile_shows_a_linked_account_and_turns_to_its_brawlers(cafe, monkeypatch):
    from brawl.Currency.db import u_tag

    monkeypatch.setattr(api, "get_stats", AsyncMock(return_value=STATS))
    monkeypatch.setattr(api, "get_battles", AsyncMock(return_value=[battle()] * 7))
    monkeypatch.setattr(api, "brawler_count", AsyncMock(return_value=112))
    monkeypatch.setattr(api, "image", AsyncMock(return_value=b""))
    interaction = cafe.interaction(7)
    cog = profile.Profile(MagicMock())
    asyncio.run(cog.profile.callback(cog, interaction))
    assert "not linked" in text(interaction.response.send_message.call_args)
    u_tag(7).set({"tag": "me"})
    asyncio.run(cog.profile.callback(cog, interaction))
    sent = interaction.followup.send.call_args.kwargs
    view = sent["view"]
    assert sent["file"].filename == "profile.jpg"
    assert u_tag(7).get()["stats"]["trophies"] == 6000
    asyncio.run(view.show(interaction, "battles", 1))
    edit = interaction.edit_original_response.call_args.kwargs
    assert edit["attachments"][0].filename == "battles.jpg" and view.pages() == 2
    assert view.next_button.disabled and not view.prev_button.disabled

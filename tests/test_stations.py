import asyncio
from unittest.mock import AsyncMock, MagicMock

from brawl.Currency import boss, heat, stationcard
from brawl.Currency.config import (
    BOSS_ODDS,
    THERMOMETER_DAILY_TOKEN_DROPS,
    THERMOMETER_LEVELS,
)
from brawl.Currency.db import g_shop_effects, u_mega_boxes, u_star_drops
from brawl.Currency.helper import MAIN_GUILD_ID
from tests.conftest import text

USER = 1


def inspection(cafe):
    channel = MagicMock(send=AsyncMock())
    view = asyncio.run(boss.start_inspection(cafe.cogs["CurrencySystem"], channel))
    return view, channel


def act(cafe, view, user=USER):
    interaction = cafe.interaction(user)
    interaction.user.display_name = f"member {user}"
    asyncio.run(view.children[0].callback(interaction))
    return interaction


def test_boss_odds_add_up():
    assert abs(sum(odds for _, odds in BOSS_ODDS) - 1) < 1e-9


def test_the_boss_arrives_as_a_card_with_three_buttons(cafe):
    view, channel = inspection(cafe)
    assert channel.send.call_args.kwargs["file"].filename == "boss.jpg"
    assert len(view.children) == 3


def test_each_outcome_pays_what_the_card_says(cafe, monkeypatch):
    for user, (outcome, boxes, drops) in enumerate(
        [("mega_box", 1, None), ("star_drop", None, 1), ("nothing", None, None)], 10
    ):
        monkeypatch.setattr(boss, "roll", lambda: outcome)
        view, _ = inspection(cafe)
        sent = act(cafe, view, user).response.send_message.call_args
        assert sent.kwargs["file"].filename == "boss.png" and sent.kwargs["ephemeral"]
        assert u_mega_boxes(user).get() == boxes
        assert u_star_drops(user).get() == drops


def test_one_move_per_member(cafe, monkeypatch):
    monkeypatch.setattr(boss, "roll", lambda: "mega_box")
    view, _ = inspection(cafe)
    act(cafe, view)
    again = act(cafe, view)
    assert "already" in text(again.response.send_message.call_args)
    assert u_mega_boxes(USER).get() == 1


def test_results_replace_the_card_once_and_close_it(cafe, monkeypatch):
    monkeypatch.setattr(boss, "roll", lambda: "star_drop")
    view, _ = inspection(cafe)
    view.message = MagicMock(edit=AsyncMock())
    act(cafe, view)
    asyncio.run(view.on_timeout())
    asyncio.run(view.end_inspection())
    view.message.edit.assert_awaited_once()
    assert view.message.edit.call_args.kwargs["view"] is None
    late = act(cafe, view, 2)
    assert "left" in text(late.response.send_message.call_args)
    assert u_star_drops(2).get() is None


def test_results_card_draws_empty_and_crowded():
    for count in (0, 1, 30):
        people = [(f"member {n}", BOSS_ODDS[n % 3][0]) for n in range(count)]
        assert stationcard.draw_boss_results({"background": "gym", "people": people})


def test_thermometer_levels_run_hot_to_cold():
    starts = [level[0] for level in THERMOMETER_LEVELS]
    assert starts == sorted(starts, reverse=True) and starts[-1] == 0
    assert heat.level_of(100)[1] == "Boiling" and heat.level_of(74)[1] == "Warm"


def test_token_rolls_follow_the_config(monkeypatch):
    boiling, hot, warm = THERMOMETER_LEVELS[:3]
    assert [level[2] for level in (boiling, hot, warm)] == [10, 5, 2]
    monkeypatch.setattr(heat.random, "random", lambda: 0.0004)
    assert heat.roll_tokens(boiling) == (5, True)
    assert heat.roll_tokens(hot) == (1, False)
    assert heat.roll_tokens(warm) == (1, False)
    for roll, tokens in ((0.001, 3), (0.002, 2), (0.004, 1), (0.018, 1), (0.019, 0)):
        monkeypatch.setattr(heat.random, "random", lambda: roll)
        assert heat.roll_tokens(boiling) == (tokens, False)
    monkeypatch.setattr(heat.random, "random", lambda: 0.006)
    assert heat.roll_tokens(hot) == (1, False)
    assert heat.roll_tokens(warm) == (0, False)


def test_token_drops_stop_at_the_daily_limit(cafe, monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(heat.time, "time", lambda: clock[0])
    counts = [heat.take_drop(USER) for _ in range(THERMOMETER_DAILY_TOKEN_DROPS + 1)]
    assert counts == [*range(1, THERMOMETER_DAILY_TOKEN_DROPS + 1), 0]
    clock[0] += heat.DAY
    assert heat.drops_today(USER) == 0 and heat.take_drop(USER) == 1


def test_thermometer_command_sends_a_card_and_names_who_froze_it(cafe):
    cog = cafe.cogs["CurrencySystem"]
    cog.thermometer_heat = 80
    g_shop_effects(MAIN_GUILD_ID).set(
        {"7": {"freeze_thermometer": {"active": True, "expires_at": 9e12}}}
    )
    assert heat.freeze(MAIN_GUILD_ID)[0] == 7
    interaction = cafe.interaction(USER)
    interaction.guild.get_member.return_value.display_name = "Sam"
    asyncio.run(cog.thermometer.callback(cog, interaction))
    sent = interaction.response.send_message.call_args.kwargs
    assert sent["file"].filename == "thermometer.jpg"


def test_a_hot_chat_drops_tokens_as_a_card(cafe, monkeypatch):
    from brawl.Currency import chat
    from brawl.Currency.db import u_balance

    cog = cafe.cogs["CurrencySystem"]
    cog.thermometer_heat = 120
    monkeypatch.setattr(heat, "roll_tokens", lambda level: (5, True))
    message = MagicMock(content="this is a perfectly normal message")
    message.author.id = USER
    message.author.bot = False
    message.author.roles = []
    message.guild.id = MAIN_GUILD_ID
    message.guild.premium_subscriber_role = None
    message.guild.get_role.return_value = None
    message.channel.send = AsyncMock()
    asyncio.run(cog.chat_system.process_message(message, cog))
    assert u_balance(USER).get()["Tokens"] == 5
    sent = message.channel.send.call_args_list
    assert [call.kwargs["file"].filename for call in sent] == ["tokens.png"]
    assert chat


def test_the_boss_visits_twice_in_each_half_of_the_day():
    from brawl.Currency.config import BOSS_VISITS

    hour = 3600
    for _ in range(500):
        times = boss.plan(0)
        assert len(times) == BOSS_VISITS == 4
        assert all(0 <= moment < 12 * hour for moment in times[:2])
        assert all(12 * hour <= moment < 24 * hour for moment in times[2:])
        gaps = [after - before for before, after in zip(times, times[1:])]
        assert all(gap >= hour - 1 for gap in gaps)
        assert all(gap <= 8 * hour for gap in (gaps[0], gaps[2]))


def test_thermometer_beans_count_until_the_daily_reset(cafe, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(heat.time, "time", lambda: clock[0])
    heat.count_beans(USER, 10, 2000)
    heat.count_beans(USER, 5, 2000)
    assert heat.beans_today(USER) == 15
    clock[0] = 2001
    assert heat.beans_today(USER) == 0


def test_a_level_change_is_posted_and_a_dead_chat_keeps_one_notice(cafe):
    cog = cafe.cogs["CurrencySystem"]
    channel = MagicMock(send=AsyncMock(), last_message_id=None)
    cog.thermometer_heat, cog.heat_told, cog.heat_notice = 74, {}, None
    asyncio.run(cog.set_heat(74.5, channel))
    channel.send.assert_not_awaited()
    asyncio.run(cog.set_heat(76, channel))
    assert channel.send.await_count == 1 and cog.heat_notice is None
    # It cools with the chat quiet: one new post, then that post is edited.
    notice = channel.send.return_value = MagicMock(id=5)
    notice.edit = AsyncMock(return_value=notice)
    asyncio.run(cog.set_heat(60))
    assert channel.send.await_count == 2 and cog.heat_notice is notice
    channel.last_message_id = 5
    asyncio.run(cog.set_heat(10))
    assert channel.send.await_count == 2 and notice.edit.await_count == 1
    # Someone wrote after the notice, then it rose and fell again within minutes.
    channel.last_message_id = 6
    asyncio.run(cog.set_heat(60, channel))
    asyncio.run(cog.set_heat(10))
    assert channel.send.await_count == 2


def test_the_ended_inspection_keeps_the_role_ping(cafe):
    view, channel = inspection(cafe)
    asyncio.run(view.end_inspection())
    assert "<@&" in view.message.edit.await_args.kwargs["content"]

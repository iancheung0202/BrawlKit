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
        assert sent.kwargs["file"].filename == "boss.jpg" and sent.kwargs["ephemeral"]
        assert u_mega_boxes(user).get() == boxes
        assert u_star_drops(user).get() == drops


def test_one_move_per_member(cafe, monkeypatch):
    monkeypatch.setattr(boss, "roll", lambda: "mega_box")
    view, _ = inspection(cafe)
    act(cafe, view)
    again = act(cafe, view)
    assert "already" in again.response.send_message.call_args[0][0]
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
    assert "left" in late.response.send_message.call_args[0][0]
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
    monkeypatch.setattr(heat.random, "random", lambda: 0.001)
    assert heat.roll_tokens(boiling) == (5, True)
    assert heat.roll_tokens(hot) == (1, False)
    assert heat.roll_tokens(warm) == (0, False)
    monkeypatch.setattr(heat.random, "random", lambda: 0.019)
    assert heat.roll_tokens(boiling)[0] in (1, 2)
    assert heat.roll_tokens(hot) == (0, False)
    monkeypatch.setattr(heat.random, "random", lambda: 0.02)
    assert heat.roll_tokens(boiling) == (0, False)


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
    assert message.channel.send.call_args.kwargs["file"].filename == "tokens.jpg"
    assert chat

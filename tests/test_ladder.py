import asyncio
import importlib
import inspect
import pkgutil
from unittest.mock import AsyncMock, MagicMock

import pytest

import brawl.Currency
from brawl.Currency import ladder, quests, tutorial
from brawl.Currency.config import LADDER, ROAST_TYPES, TUTORIAL_TOKENS
from brawl.Currency.db import u_balance, u_brews, u_quests, u_tutorial, u_veteran
from brawl.Currency.helper import MAIN_GUILD_ID

USER = 1


def level(cafe, value):
    cafe.cogs["Leveling"] = MagicMock(level_of=AsyncMock(return_value=value), pool=None)


def run(cafe, cog, command, *args):
    interaction = cafe.interaction()
    target = cafe.cogs[cog]
    asyncio.run(getattr(target, command).callback(target, interaction, *args))
    return interaction


def said(interaction):
    call = interaction.response.send_message.call_args
    return call[0][0] if call and call[0] else ""


def test_ladder_has_one_station_per_level():
    levels = [need for need, _, _ in LADDER.values()]
    assert levels == sorted(set(levels))


def test_a_locked_station_names_its_level(cafe):
    level(cafe, 0)
    u_balance(USER).set({"Beans": 5000})
    interaction = run(cafe, "Brewing", "brew", MagicMock(value="light"))
    assert "**Brewing** unlocks at **Level 1**" in said(interaction)
    assert u_balance(USER).get()["Beans"] == 5000


def test_the_station_opens_at_its_level(cafe):
    level(cafe, 1)
    u_balance(USER).set({"Beans": 5000})
    run(cafe, "Brewing", "brew", MagicMock(value="light"))
    assert u_balance(USER).get()["Beans"] == 5000 - ROAST_TYPES["light"]["cost"]


def test_games_stay_locked_below_their_level(cafe):
    level(cafe, 14)
    u_balance(USER).set({"Beans": 5000})
    interaction = run(cafe, "Gambling", "coinflip", 100)
    assert "**Games** unlocks at **Level 15**" in said(interaction)
    assert u_balance(USER).get()["Beans"] == 5000


def test_veterans_keep_every_station(cafe):
    level(cafe, 0)
    u_veteran(USER).set(True)
    for station in LADDER:
        assert asyncio.run(ladder.unlocked(cafe.bot, USER, MAIN_GUILD_ID, station))


def test_weekly_quests_wait_for_their_level(cafe, monkeypatch):
    monkeypatch.setattr(
        quests, "generate_quests", lambda *_: {"brew_start": {"current": 0, "goal": 9}}
    )
    level(cafe, 2)
    asyncio.run(quests.update_quest(USER, MAIN_GUILD_ID, {"brew_start": 1}, cafe.bot))
    assert u_quests(USER).child("weekly/quests/brew_start/current").get() == 0
    level(cafe, 3)
    asyncio.run(quests.update_quest(USER, MAIN_GUILD_ID, {"brew_start": 1}, cafe.bot))
    assert u_quests(USER).child("weekly/quests/brew_start/current").get() == 1


def test_level_up_teaches_only_the_new_stations():
    assert ladder.lessons(0, 1) == [
        f"🔓 **You unlocked Brewing**\n{LADDER['brewing'][2]}"
    ]
    assert len(ladder.lessons(1, 3)) == 2
    assert ladder.lessons(5, 6) == []


def test_tutorial_is_clock_in_brew_sell(cafe):
    manager = cafe.cogs["CurrencySystem"].tutorial_manager
    member = MagicMock(id=USER)
    assert "Step 1 of 3" in asyncio.run(manager.start(member)).description
    assert u_balance(USER).get()["Beans"] == 500
    assert asyncio.run(manager.advance(USER, "brew")) is None
    assert asyncio.run(manager.advance(USER, "clock_in")) is not None
    assert asyncio.run(manager.advance(USER, "brew")) is not None
    done = asyncio.run(manager.advance(USER, "sell"))
    assert done.title == "First shift complete!"
    assert u_balance(USER).get()["Tokens"] == TUTORIAL_TOKENS
    assert u_tutorial(USER).get() == tutorial.DONE
    assert asyncio.run(manager.advance(USER, "sell")) is None


def test_members_midway_through_the_old_tutorial_finish_by_selling(cafe):
    u_tutorial(USER).set(5)
    assert tutorial.step_of(USER) == tutorial.SELL_STEP
    u_tutorial(USER).set(6)
    assert tutorial.step_of(USER) is None


def test_selling_a_first_brew_ends_the_tutorial(cafe):
    u_tutorial(USER).set(tutorial.SELL_STEP)
    u_brews(USER).child("active_brew").set(
        {
            "roast_type": "light",
            "end_time": 1,
            "insured": True,
            "batch_id": "x",
            "start_time": 0,
        }
    )
    interaction = run(cafe, "Brewing", "sell")
    embeds = [
        call.kwargs.get("embed") for call in interaction.followup.send.call_args_list
    ]
    assert any(embed and embed.title == "First shift complete!" for embed in embeds)


GATES = [
    ("Gacha", "stardrop", (), 3, "Star Drops"),
    ("Gacha", "megabox", (), 24, "Mega Boxes"),
    ("Shop", "shop", (), 1, "Shop"),
    ("Shop", "buy", ("Nitro",), 1, "Shop"),
    ("Shop", "pin", ("link",), 34, "Customize and Pin"),
    ("Gambling", "blackjack", (100,), 14, "Games"),
    ("TableSystem", "table_seat", ("table",), 9, "Tables"),
    ("TableSystem", "table_reserve", (), 9, "Tables"),
]


@pytest.mark.parametrize("cog, command, args, below, name", GATES)
def test_every_station_command_is_gated(cafe, cog, command, args, below, name):
    level(cafe, below)
    interaction = cafe.interaction()
    target = cafe.cogs[cog]
    callback = getattr(target, command).callback
    spare = len(inspect.signature(callback).parameters) - 2 - len(args)
    asyncio.run(callback(target, interaction, *args, *[None] * spare))
    assert f"**{name}** unlocks at **Level {below + 1}**" in said(interaction)


def test_every_currency_module_can_be_loaded():
    for module in pkgutil.iter_modules(brawl.Currency.__path__):
        loaded = importlib.import_module(f"brawl.Currency.{module.name}")
        assert inspect.iscoroutinefunction(loaded.setup), module.name

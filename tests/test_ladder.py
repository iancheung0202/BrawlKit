import asyncio
import importlib
import inspect
import pkgutil
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

import brawl.Currency
from brawl.Currency import ladder, quests, tutorial
from brawl.Currency.config import LADDER, ROAST_TYPES, TUTORIAL_BEANS, TUTORIAL_TOKENS
from brawl.Currency.db import (
    u_balance,
    u_brews,
    u_daily_checkin_streaks,
    u_quests,
    u_tutorial,
    u_veteran,
)
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


def test_level_up_teaches_only_the_new_stations():
    assert ladder.lessons(0, 1) == [
        f"🔓 **You unlocked Brewing**\n{LADDER['brewing'][2]}"
    ]
    assert len(ladder.lessons(1, 4)) == 2
    assert ladder.lessons(5, 6) == []


def test_tutorial_is_brew_sell_clock_in(cafe):
    manager = cafe.cogs["CurrencySystem"].tutorial_manager
    member = MagicMock(id=USER)
    assert asyncio.run(manager.start(member)) == tutorial.BREW_STEP
    assert not u_balance(USER).get()
    assert asyncio.run(manager.advance(USER, "sell")) is None
    assert asyncio.run(manager.advance(USER, "clock_in")) is None
    assert asyncio.run(manager.advance(USER, "brew")) == tutorial.SELL_STEP
    assert asyncio.run(manager.advance(USER, "sell")) == tutorial.CLOCK_IN
    assert asyncio.run(manager.advance(USER, "clock_in")) == tutorial.FINISHED
    assert u_balance(USER).get() == {"Beans": TUTORIAL_BEANS, "Tokens": TUTORIAL_TOKENS}
    assert u_tutorial(USER).get() == tutorial.DONE
    assert asyncio.run(manager.advance(USER, "clock_in")) is None


def test_steps_saved_by_older_tutorials_still_fit(cafe):
    u_tutorial(USER).set(1)
    assert tutorial.step_of(USER) == tutorial.BREW_STEP
    u_tutorial(USER).set(5)
    assert tutorial.step_of(USER) == tutorial.CLOCK_IN
    u_tutorial(USER).set(6)
    assert tutorial.step_of(USER) is None


def test_selling_ends_the_tutorial_for_a_member_who_already_clocked_in(cafe):
    u_tutorial(USER).set(tutorial.SELL_STEP)
    u_daily_checkin_streaks(USER).set({"last_claim": time.time()})
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
    assert "First shift done" in interaction.followup.send.call_args_list[0].args[0]
    assert u_tutorial(USER).get() == tutorial.DONE


def test_a_new_member_brews_before_level_one_without_picking_a_roast(cafe):
    u_tutorial(USER).set(tutorial.BREW_STEP)
    interaction = run(cafe, "Brewing", "brew")
    assert "Step 2 of 3" in interaction.followup.send.call_args_list[0].args[0]
    assert u_brews(USER).child("active_brew").get()["insured"]


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

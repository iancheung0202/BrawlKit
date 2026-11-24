import asyncio
from unittest.mock import AsyncMock

from brawl.Currency import bag, gacha
from brawl.Currency.db import u_balance, u_shop_cooldowns, u_shop_effects
from brawl.Currency.helper import MAIN_GUILD_ID
from tests.conftest import text

USER = 1


def buy(cafe, item):
    u_balance(USER).set({"Beans": 9000, "Tokens": 50})
    interaction = cafe.interaction(USER)
    asyncio.run(cafe.cogs["Shop"]._process_effect_purchase(interaction, USER, item))
    return interaction.edit_original_response.call_args.kwargs


def press(cafe, callback):
    interaction = cafe.interaction(USER)
    asyncio.run(callback(interaction))
    return interaction


def test_a_bought_timed_item_waits_in_the_bag(cafe):
    reply = buy(cafe, "chat_boost")
    assert bag.held(USER) == ["chat_boost"]
    assert not u_shop_effects(USER, "chat_boost").get()
    assert u_shop_cooldowns(USER, "chat_boost").get()
    assert isinstance(reply["view"], bag.UseNow)


def test_an_item_already_held_cannot_be_bought_again(cafe):
    buy(cafe, "chat_boost")
    u_shop_cooldowns(USER, "chat_boost").delete()
    reply = buy(cafe, "chat_boost")
    assert "already hold" in text(reply)
    assert u_balance(USER).get() == {"Beans": 9000, "Tokens": 50}


def test_an_instant_item_still_acts_when_bought(cafe):
    cafe.cogs["CurrencySystem"].thermometer_heat = 10
    reply = buy(cafe, "thermometer_boost")
    assert reply["view"].children[1].label == "Use /thermometer to view the heat"
    assert bag.held(USER) == []
    assert cafe.cogs["CurrencySystem"].thermometer_heat == 40


def test_use_now_starts_the_item_once(cafe):
    view = buy(cafe, "chat_boost")["view"]
    first = press(cafe, lambda i: view.use_now.callback(i))
    assert first.response.edit_message.call_args.kwargs["attachments"][0].filename == (
        "started.png"
    )
    assert u_shop_effects(USER, "chat_boost").get()["active"]
    assert bag.held(USER) == []
    again = press(cafe, lambda i: view.use_now.callback(i))
    assert "no Espresso Shot" in text(again.response.send_message.call_args)


def test_a_held_item_waits_while_the_same_effect_runs(cafe):
    bag.keep(USER, "chat_boost")
    asyncio.run(bag.start(cafe.bot, USER, MAIN_GUILD_ID, "chat_boost"))
    bag.keep(USER, "chat_boost")
    assert "still running" in bag.blocked(USER, MAIN_GUILD_ID, "chat_boost")


def test_the_freezer_holds_the_heat_only_when_used(cafe):
    cafe.cogs["CurrencySystem"].thermometer_heat = 87
    buy(cafe, "freeze_thermometer")
    from brawl.Currency import heat

    assert heat.freeze(MAIN_GUILD_ID) is None
    cog = cafe.cogs["Bag"]
    opened = press(cafe, lambda i: cog.use.callback(cog, i))
    sent = opened.response.send_message.call_args.kwargs
    select = sent["view"].children[0]
    assert sent["ephemeral"] and sent["file"].filename == "bag.jpg"
    assert select.options[0].description == "Thermometer is at 87"
    select._values = ["freeze_thermometer"]
    press(cafe, select.callback)
    assert heat.freeze(MAIN_GUILD_ID)[0] == USER
    bag.keep(2, "freeze_thermometer")
    assert "already frozen" in bag.blocked(2, MAIN_GUILD_ID, "freeze_thermometer")


def test_an_empty_bag_says_where_items_come_from(cafe):
    cog = cafe.cogs["Bag"]
    opened = press(cafe, lambda i: cog.use.callback(cog, i))
    assert "bag is empty" in text(opened.response.send_message.call_args)


def test_a_dropped_item_goes_to_the_bag_and_is_not_dropped_twice(cafe, monkeypatch):
    monkeypatch.setattr(gacha, "pay", AsyncMock(return_value={"kind": "tokens"}))
    got = set()
    for _ in bag.TIMED:
        reward = asyncio.run(gacha.give_effect(USER, MAIN_GUILD_ID))
        assert reward["note"] == "Start it with /use"
        got.add(reward["item"])
    assert got == set(bag.TIMED) == set(bag.held(USER))
    assert not u_shop_effects(USER).get()
    spare = asyncio.run(gacha.give_effect(USER, MAIN_GUILD_ID))
    assert spare["note"] == "in place of an effect item"

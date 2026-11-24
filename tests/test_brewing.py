import asyncio
from unittest.mock import MagicMock

from discord import app_commands

from brawl.Currency import quests
from brawl.Currency.helper import ROAST_TYPES
from tests.conftest import text

USER = 1
LIGHT = app_commands.Choice(name="Light Roast", value="light")

SELL = "Use /sell when it is ready"


def user(cafe, path):
    return cafe.ref(f"Cafe Economy/{USER}/{path}")


def brew(cafe):
    cog = cafe.cogs["Brewing"]
    sent = cafe.interaction(USER)
    asyncio.run(cog.brew.callback(cog, sent, LIGHT))
    return sent


def pressing(cafe, sent, who=USER):
    press = cafe.interaction(who)
    press.message.embeds = []
    press.message.content = ""
    press.message.attachments = [MagicMock(filename=sent["file"].filename)]
    return press


def test_only_the_brewer_can_insure(cafe):
    user(cafe, "balance").set({"Beans": 5000})
    sent = brew(cafe).followup.send.call_args.kwargs
    press = pressing(cafe, sent, who=USER + 1)
    asyncio.run(sent["view"].children[0].callback(press))
    assert "not your brew" in text(press.response.send_message.call_args)
    assert user(cafe, "inventory/brews/active_brew/insured").get() is False


def sell(cafe):
    cog = cafe.cogs["Brewing"]
    sent = cafe.interaction(USER)
    asyncio.run(cog.sell.callback(cog, sent))
    return sent


def test_brew_costs_beans_and_starts_a_batch(cafe):
    user(cafe, "balance").set({"Beans": 5000})
    brew(cafe)
    assert user(cafe, "balance/Beans").get() == 5000 - ROAST_TYPES["light"]["cost"]
    batch = user(cafe, "inventory/brews/active_brew").get()
    assert batch["roast_type"] == "light" and not batch["insured"]
    assert batch["end_time"] - batch["start_time"] == ROAST_TYPES["light"]["time"]


def test_brew_needs_enough_beans(cafe):
    user(cafe, "balance").set({"Beans": 10})
    brew(cafe)
    assert user(cafe, "balance/Beans").get() == 10
    assert user(cafe, "inventory/brews/active_brew").get() is None


def test_insurance_button_charges_and_marks_the_batch(cafe):
    user(cafe, "balance").set({"Beans": 5000})
    sent = brew(cafe).followup.send.call_args.kwargs
    view = sent["view"]
    press = pressing(cafe, sent)
    asyncio.run(view.children[0].callback(press))
    after = press.response.edit_message.call_args.kwargs["view"]
    assert after.children[-1].label == SELL
    cost = ROAST_TYPES["light"]["cost"] + ROAST_TYPES["light"]["insurance_cost"]
    assert user(cafe, "balance/Beans").get() == 5000 - cost
    assert user(cafe, "inventory/brews/active_brew/insured").get() is True


def test_insurance_button_ignores_an_older_brew(cafe):
    user(cafe, "balance").set({"Beans": 5000})
    sent = brew(cafe).followup.send.call_args.kwargs
    user(cafe, "inventory/brews/active_brew/batch_id").set("OTHER")
    press = pressing(cafe, sent)
    asyncio.run(sent["view"].children[0].callback(press))
    assert user(cafe, "balance/Beans").get() == 5000 - ROAST_TYPES["light"]["cost"]
    assert user(cafe, "inventory/brews/active_brew/insured").get() is False


def test_sell_waits_until_the_batch_is_ready(cafe):
    user(cafe, "balance").set({"Beans": 5000})
    brew(cafe)
    sell(cafe)
    assert user(cafe, "inventory/brews/active_brew").get() is not None
    assert user(cafe, "balance/Tokens").get() is None


def test_sell_pays_tokens_and_clears_the_batch(cafe):
    user(cafe, "balance").set({"Beans": 5000})
    brew(cafe)
    user(cafe, "inventory/brews/active_brew/end_time").set(1)
    sent = sell(cafe)
    assert user(cafe, "inventory/brews/active_brew").get() is None
    tokens = user(cafe, "balance/Tokens").get() or 0
    assert tokens in ROAST_TYPES["light"]["payout"]
    assert user(cafe, "inventory/brews/stats/total_tokens").get() == tokens
    assert sent.followup.send.called


def test_first_brew_completes_the_daily_brew_quest(cafe, monkeypatch):
    monkeypatch.setattr(
        quests,
        "generate_order",
        lambda level=0: {"brew_start": {"current": 0, "goal": 1}},
    )
    user(cafe, "balance").set({"Beans": 5000})
    brew(cafe)
    spent = ROAST_TYPES["light"]["cost"]
    earned = sum(quests.QUEST_BEAN_REWARDS.values()) + sum(
        quests.QUEST_BONUS_BEANS.values()
    )
    assert user(cafe, "balance/Beans").get() == 5000 - spent + earned


def test_the_first_tutorial_brew_is_free_ready_and_insured(cafe):
    from brawl.Currency import tutorial
    from brawl.Currency.db import u_tutorial

    u_tutorial(USER).set(tutorial.BREW_STEP)
    user(cafe, "balance").set({"Beans": 0, "Tokens": 0})
    sent = brew(cafe)
    active = user(cafe, "inventory/brews/active_brew").get()
    assert active["insured"] and active["end_time"] <= active["start_time"]
    assert user(cafe, "balance").get()["Beans"] == 0
    first = sent.followup.send.call_args_list[0].kwargs["view"]
    assert first.children[-1].label == SELL
    assert u_tutorial(USER).get() == tutorial.SELL_STEP

    assert "need" in brew_again(cafe)


def brew_again(cafe):
    user(cafe, "inventory/brews/active_brew").delete()
    return text(brew(cafe).response.send_message.call_args)

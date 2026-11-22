import asyncio

from discord import app_commands

from brawl.Currency import quests
from brawl.Currency.helper import ROAST_TYPES

USER = 1
LIGHT = app_commands.Choice(name="Light Roast", value="light")


def user(cafe, path):
    return cafe.ref(f"Cafe Economy/{USER}/{path}")


def brew(cafe):
    cog = cafe.cogs["Brewing"]
    sent = cafe.interaction(USER)
    asyncio.run(cog.brew.callback(cog, sent, LIGHT))
    return sent


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
    press = cafe.interaction(USER)
    press.message.embeds = [sent["embed"]]
    asyncio.run(view.children[0].callback(press))
    cost = ROAST_TYPES["light"]["cost"] + ROAST_TYPES["light"]["insurance_cost"]
    assert user(cafe, "balance/Beans").get() == 5000 - cost
    assert user(cafe, "inventory/brews/active_brew/insured").get() is True


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
        "generate_quests",
        lambda duration: {"brew_start": {"current": 0, "goal": 1}},
    )
    user(cafe, "balance").set({"Beans": 5000})
    brew(cafe)
    spent = ROAST_TYPES["light"]["cost"]
    earned = sum(quests.QUEST_BEAN_REWARDS.values()) + sum(
        quests.QUEST_BONUS_BEANS.values()
    )
    assert user(cafe, "balance/Beans").get() == 5000 - spent + earned

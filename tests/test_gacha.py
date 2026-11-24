import asyncio

from brawl.Currency import gacha, ledger
from brawl.Currency.config import MEGA_BOX_ITEMS, STAR_DROP_RATES
from brawl.Currency.db import (
    u_balance,
    u_mega_boxes,
    u_mega_boxes_pending,
    u_star_drops,
    u_star_drops_pending,
)
from tests.conftest import text

USER = 1


def open_with(cafe, command):
    interaction = cafe.interaction(USER)
    interaction.user.id = USER
    cog = cafe.cogs["Gacha"]
    asyncio.run(getattr(cog, command).callback(cog, interaction))
    return interaction


def sent(interaction):
    return interaction.response.send_message.call_args


def test_rarity_rates_add_up():
    assert abs(sum(STAR_DROP_RATES["rarity_rates"].values()) - 1) < 1e-9
    assert abs(sum(MEGA_BOX_ITEMS.values()) - 1) < 1e-9


def test_star_drop_needs_one_in_the_inventory(cafe):
    interaction = open_with(cafe, "stardrop")
    assert "no Star Drops" in text(sent(interaction))


def test_star_drop_takes_one_and_pays_after_four_upgrades(cafe, monkeypatch):
    monkeypatch.setattr(gacha.Gacha, "_roll_rarity", lambda self: "rare")
    monkeypatch.setattr(gacha.random, "random", lambda: 1)
    u_star_drops(USER).set(2)
    u_balance(USER).set({"Beans": 0, "Tokens": 0})
    ledger.items.clear()
    interaction = open_with(cafe, "stardrop")
    assert ledger.items[ledger.week_key()]["star_drop"]["used"] == 1
    view = sent(interaction).kwargs["view"]
    assert u_star_drops(USER).get() == 1
    assert u_star_drops_pending(USER).get()["final_rarity"] == "rare"

    press = cafe.interaction(USER)
    press.user.id = USER
    asyncio.run(view.children[1].callback(press))
    assert "4 upgrades" in text(press.followup.send.call_args)
    for _ in range(4):
        asyncio.run(view.children[0].callback(press))
    asyncio.run(view.children[1].callback(press))
    balance = u_balance(USER).get()
    assert balance["Beans"] + balance["Tokens"] > 0
    assert u_star_drops_pending(USER).get() is None or view.is_unlocked
    paid = dict(balance)
    asyncio.run(view.children[1].callback(press))
    assert u_balance(USER).get() == paid
    gacha.StarDropView.active_sessions.clear()


def test_mega_box_takes_one_and_opens_every_item(cafe, monkeypatch):
    ledger.items.clear()
    monkeypatch.setattr(gacha, "roll_items", lambda: 5)
    u_mega_boxes(USER).set(1)
    u_balance(USER).set({"Beans": 0, "Tokens": 0})
    interaction = open_with(cafe, "megabox")
    view = sent(interaction).kwargs["view"]
    assert u_mega_boxes(USER).get() == 0
    assert ledger.items[ledger.week_key()]["mega_box"]["used"] == 1
    assert u_mega_boxes_pending(USER).get()["items_remaining"] == 4
    press = cafe.interaction(USER)
    press.user.id = USER
    for _ in range(5):
        asyncio.run(view.children[0].callback(press))
    assert view.show_summary and len(view.rewards) == 5
    balance = u_balance(USER).get()
    assert balance["Beans"] + balance["Tokens"] > 0
    gacha.MegaBoxView.active_sessions.clear()


def test_drops_and_boxes_are_sent_as_cards(cafe, monkeypatch):
    monkeypatch.setattr(gacha, "roll_items", lambda: 6)
    u_star_drops(USER).set(1)
    u_mega_boxes(USER).set(1)
    for command, name in (("stardrop", "stardrop.jpg"), ("megabox", "megabox.jpg")):
        message = sent(open_with(cafe, command)).kwargs
        assert message["file"].filename == name
    gacha.StarDropView.active_sessions.clear()
    gacha.MegaBoxView.active_sessions.clear()


def test_an_effect_item_keeps_its_own_icon(cafe):
    from brawl.Currency.card import item_icon
    from brawl.Currency.dropcard import picture
    from brawl.Currency.helper import STORE_ITEMS

    reward = asyncio.run(gacha.give_effect(USER, 1))
    assert reward["kind"] == "effect"
    assert picture(reward) == f"items/{reward['item']}"
    missing = [item for item in STORE_ITEMS if item_icon(item) == "items/effect"]
    assert missing == []


def test_a_box_saved_before_the_cards_still_opens():
    assert gacha.reward_of("<:bean:1> `251` Beans") == {
        "kind": "beans",
        "amount": 251,
    }
    old = gacha.reward_of("Effect: `Espresso Shot`")
    assert old["item"] == "chat_boost"


def test_fast_taps_run_one_at_a_time(cafe, monkeypatch):
    monkeypatch.setattr(gacha, "roll_items", lambda: 5)
    u_mega_boxes(USER).set(1)
    u_balance(USER).set({"Beans": 0, "Tokens": 0})
    view = sent(open_with(cafe, "megabox")).kwargs["view"]
    press = cafe.interaction(USER)
    press.user.id = USER
    drawn = []

    async def slow_file():
        shown = len(view.rewards)
        await asyncio.sleep(0.01 / shown)
        drawn.append((shown, len(view.rewards)))

    monkeypatch.setattr(view, "file", slow_file)

    async def spam():
        await asyncio.gather(*(view.children[0].callback(press) for _ in range(8)))

    asyncio.run(spam())
    assert drawn == [(n, n) for n in range(2, 6)]
    assert view.children[0].disabled
    gacha.MegaBoxView.active_sessions.clear()


def test_opening_again_ends_the_old_message(cafe, monkeypatch):
    monkeypatch.setattr(gacha, "roll_items", lambda: 5)
    u_mega_boxes(USER).set(1)
    first = sent(open_with(cafe, "megabox")).kwargs["view"]
    second = sent(open_with(cafe, "megabox")).kwargs["view"]
    assert first.is_finished() and first.children[0].label == "Session ended"
    assert second is not first and len(second.rewards) == 1
    assert u_mega_boxes(USER).get() == 0
    gacha.MegaBoxView.active_sessions.clear()

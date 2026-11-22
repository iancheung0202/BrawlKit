import asyncio
import io
import time
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

from brawl.Currency import home, ladder
from brawl.Currency.card import BACKGROUND
from brawl.Currency.config import BACKGROUNDS
from brawl.Currency.db import (
    u_background,
    u_balance,
    u_brews,
    u_customization,
    u_stamp_card,
)
from brawl.Currency.helper import SERVER_STORE

USER = 1


def member(cafe):
    interaction = cafe.interaction()
    interaction.user.display_name = "sam"
    interaction.user.display_avatar.replace.return_value.read = AsyncMock(
        return_value=b""
    )
    balance = cafe.cogs["Balance"]
    return asyncio.run(balance.member(interaction.user, interaction.guild))


def customize(cafe, key):
    interaction = cafe.interaction()
    interaction.user.display_name = "sam"
    interaction.user.display_avatar.replace.return_value.read = AsyncMock(
        return_value=b""
    )
    choice = type("Choice", (), {"value": key, "name": BACKGROUNDS[key]})
    command = cafe.cogs["Balance"].customize
    asyncio.run(command.callback(cafe.cogs["Balance"], interaction, choice))
    return interaction


def test_every_background_draws_a_card(cafe):
    data = member(cafe)
    for key in BACKGROUNDS:
        image = Image.open(
            io.BytesIO(home.draw_home({**data, "background": key}).read())
        )
        assert image.size == (1800, 1080)


def test_home_shows_the_order_brew_and_stamps(cafe):
    u_balance(USER).set({"Beans": 900, "Tokens": 4})
    u_stamp_card(USER).set({"count": 31})
    u_brews(USER).child("active_brew").set(
        {"roast_type": "light", "end_time": time.time() - 5, "insured": True}
    )
    data = member(cafe)
    assert (data["beans"], data["tokens"], data["stamps"]) == (900, 4, 31)
    assert data["tasks"] and data["brew"]["roast_type"] == "light"
    assert data["background"] == BACKGROUND
    assert home.draw_home(data).read()


def test_next_unlock_walks_the_ladder():
    assert "Brewing unlocks at Level 1" in ladder.next_unlock(0)
    assert "Boss Inspection unlocks at Level 5" in ladder.next_unlock(4)
    assert ladder.next_unlock(99) == "Every station is unlocked"


def test_stamp_goal_moves_to_plus_after_a_full_card():
    assert home.goal(29)[0] == "brawl_pass"
    assert home.goal(30)[0] == "brawl_pass_plus"
    assert home.goal(99)[0] == "brawl_pass_plus"


def test_customize_needs_a_credit(cafe):
    interaction = customize(cafe, "tokyo")
    assert (
        "need 1 Customization Credit"
        in interaction.response.send_message.call_args[0][0]
    )
    assert u_background(USER).get() is None


def test_customize_spends_a_credit_and_saves_the_preset(cafe):
    u_customization(USER).set({"credits": 2})
    customize(cafe, "tokyo")
    assert u_background(USER).get() == "tokyo"
    assert u_customization(USER).get()["credits"] == 1
    assert member(cafe)["background"] == "tokyo"


def test_default_background_is_free(cafe):
    u_customization(USER).set({"credits": 1})
    u_background(USER).set("tokyo")
    customize(cafe, BACKGROUND)
    assert u_background(USER).get() is None
    assert u_customization(USER).get()["credits"] == 1


def test_inventory_is_a_card_of_what_the_member_holds(cafe, monkeypatch):
    from brawl.Currency import balance, itemcard
    from brawl.Currency.db import u_star_drops

    drawn = []
    monkeypatch.setattr(
        balance,
        "draw_inventory",
        lambda member: drawn.append(member) or itemcard.draw_inventory(member),
    )
    u_star_drops(USER).set(3)
    interaction = cafe.interaction(USER)
    interaction.message.attachments = [MagicMock(filename=f"balance_{USER}.jpg")]

    async def press():
        view = balance.BalanceInfoView()
        button = next(b for b in view.children if b.custom_id == "effect_info")
        await button.callback(interaction)

    asyncio.run(press())
    sent = interaction.response.edit_message.call_args.kwargs
    assert sent["embed"] is None
    assert sent["attachments"][0].filename == f"balance_{USER}.jpg"
    assert drawn[0]["held"]["star_drops"] == 3 and drawn[0]["effects"] == []


def test_the_button_of_the_page_on_screen_is_blurple(cafe):
    from brawl.Currency import balance

    interaction = cafe.interaction(USER)
    interaction.user.display_name = "sam"
    interaction.user.display_avatar.replace.return_value.read = AsyncMock(
        return_value=b""
    )
    interaction.message.attachments = [MagicMock(filename=f"balance_{USER}.jpg")]

    async def press():
        view = balance.BalanceInfoView()
        pages = [button.custom_id for button in view.children]
        assert pages == list(balance.PAGES)
        lit = []
        for custom_id in ("effect_info", "overview"):
            button = next(b for b in view.children if b.custom_id == custom_id)
            await button.callback(interaction)
            lit.append(
                [
                    b.custom_id
                    for b in view.children
                    if b.style == discord.ButtonStyle.blurple
                ]
            )
        return lit

    assert asyncio.run(press()) == [["effect_info"], ["overview"]]
    sent = interaction.response.edit_message.call_args.kwargs
    assert sent["attachments"][0].filename == f"balance_{USER}.jpg"


@pytest.mark.before_clock_in
def test_home_points_to_the_store_before_clock_in(cafe):
    data = member(cafe)
    assert data["tasks"] == []
    assert home.draw_home(data).read()
    interaction = cafe.interaction()
    interaction.user.display_name = "sam"
    interaction.user.display_avatar.replace.return_value.read = AsyncMock(
        return_value=b""
    )
    asyncio.run(
        cafe.cogs["Balance"].balance.callback(cafe.cogs["Balance"], interaction)
    )
    view = interaction.followup.send.call_args.kwargs["view"]
    links = [item.url for item in view.children if getattr(item, "url", None)]
    assert links and links[0].endswith(str(SERVER_STORE))
    assert all(item.custom_id != "clock_in" for item in view.children if not item.url)

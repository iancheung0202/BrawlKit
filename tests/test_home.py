import asyncio
import io
import time
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

from brawl.Currency import balancecard, card, ladder
from brawl.Currency.card import BACKGROUND
from brawl.Currency.config import BACKGROUNDS
from brawl.Currency.db import (
    u_background,
    u_balance,
    u_brews,
    u_customization,
    u_stamp_card,
)
from brawl.Currency.helper import MAIN_GUILD_ID, SERVER_STORE
from tests.conftest import text

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


def confirm(interaction):
    view = interaction.followup.send.call_args.kwargs["view"]
    press = MagicMock()
    press.user.id = USER
    press.response.edit_message = AsyncMock()
    if not view.confirm.disabled:
        asyncio.run(view.confirm.callback(press))
    return view, press


def test_every_background_draws_the_counter(cafe):
    data = {**member(cafe), **stamp_card(cafe)}
    for key in BACKGROUNDS:
        data["background"] = key
        image = Image.open(io.BytesIO(balancecard.draw_counter(data).read()))
        assert image.size == (1800, 604)
        assert balancecard.draw_stamps(data).read()


def stamp_card(cafe):
    interaction = cafe.interaction()
    summary = cafe.cogs["StampCard"].summary(interaction.user, interaction.guild)
    return asyncio.run(summary)


def page(cafe, place):
    interaction = cafe.interaction()
    cog = cafe.cogs["Balance"]
    return asyncio.run(cog.page(interaction.user, interaction.guild, place))


def test_counter_shows_the_order_brew_and_stamps(cafe):
    u_balance(USER).set({"Beans": 900, "Tokens": 4})
    u_stamp_card(USER).set({"count": 31})
    u_brews(USER).child("active_brew").set(
        {"roast_type": "light", "end_time": time.time() - 5, "insured": True}
    )
    data = member(cafe)
    assert (data["beans"], data["tokens"], data["stamps"]) == (900, 4, 31)
    assert data["tasks"] and data["brew"]["roast_type"] == "light"
    assert data["background"] == BACKGROUND
    assert balancecard.draw_counter(data).read()
    for place in card.PLACES:
        assert balancecard.draw_header(place, data).read()


def test_next_unlock_walks_the_ladder():
    assert "Brewing unlocks at Level 1" in ladder.next_unlock(0)
    assert "Boss Inspection unlocks at Level 5" in ladder.next_unlock(4)
    assert ladder.next_unlock(99) == "Every station is unlocked"


def test_customize_previews_but_cannot_confirm_without_a_credit(cafe):
    interaction = customize(cafe, "tokyo")
    sent = interaction.followup.send.call_args
    assert "need 1 Customization Credit" in text(sent)
    assert sent.kwargs["file"].filename == f"balance_{USER}.jpg"
    assert confirm(interaction)[0].confirm.disabled
    assert u_background(USER).get() is None


def test_customize_only_spends_the_credit_on_confirm(cafe):
    u_customization(USER).set({"credits": 2})
    interaction = customize(cafe, "tokyo")
    assert u_background(USER).get() is None
    assert u_customization(USER).get()["credits"] == 2
    confirm(interaction)
    assert u_background(USER).get() == "tokyo"
    assert u_customization(USER).get()["credits"] == 1
    assert member(cafe)["background"] == "tokyo"


def test_default_background_is_free(cafe):
    u_customization(USER).set({"credits": 1})
    u_background(USER).set("tokyo")
    confirm(customize(cafe, BACKGROUND))
    assert u_background(USER).get() is None
    assert u_customization(USER).get()["credits"] == 1


def test_every_page_is_its_header_then_its_cards(cafe):
    for place, cards in (
        ("COUNTER", 3),
        ("CHAT", 2),
        ("INVENTORY", 2),
        ("COMMUNITY", 2),
    ):
        view, files = page(cafe, place)
        assert [file.filename for file in files] == [
            f"balance_{USER}_{spot}.jpg" for spot in range(cards)
        ]
        shown = [
            item.media.url
            for gallery in view.walk_children()
            if isinstance(gallery, discord.ui.MediaGallery)
            for item in gallery.items
        ]
        assert shown == [f"attachment://{file.filename}" for file in files]
        lit = [
            button.custom_id
            for button in view.walk_children()
            if getattr(button, "style", None) == discord.ButtonStyle.blurple
        ]
        assert lit == [f"balance_{place.lower()}"]


def test_inventory_shows_what_the_member_holds(cafe):
    from brawl.Currency.db import u_star_drops

    u_star_drops(USER).set(3)
    interaction = cafe.interaction()
    held = asyncio.run(cafe.cogs["Balance"].inventory(interaction.user))
    assert held["held"]["star_drops"] == 3 and held["effects"] == []
    assert balancecard.draw_inventory(held).read()


def test_chat_shows_the_cap_the_cup_and_the_boss(cafe):
    from brawl.Currency import boss
    from brawl.Currency.db import g_boss_inspection

    g_boss_inspection(MAIN_GUILD_ID).set({"times": [1, 2, 3, 4], "done": 2})
    boss.keep(USER, 1, "mega_box")
    interaction = cafe.interaction()
    chat = asyncio.run(cafe.cogs["Balance"].chat(interaction.user, interaction.guild))
    assert chat["boss"] == ["missed", "mega_box", None, None]
    assert chat["chat"][0] == 0 and chat["chat"][1] > 0
    assert balancecard.draw_chat(chat).read()


def test_a_page_button_opens_its_page_for_its_owner_only(cafe):
    view, _ = page(cafe, "COUNTER")
    button = next(
        item
        for item in view.walk_children()
        if getattr(item, "custom_id", None) == "balance_chat"
    )
    stranger = cafe.interaction(2)
    asyncio.run(button.callback(stranger))
    assert "not your command" in text(stranger.response.send_message.call_args)
    owner = cafe.interaction()
    asyncio.run(button.callback(owner))
    sent = owner.edit_original_response.call_args.kwargs
    assert len(sent["attachments"]) == 2
    assert isinstance(sent["view"], discord.ui.LayoutView)


@pytest.mark.before_clock_in
def test_counter_points_to_the_store_before_clock_in(cafe):
    data = member(cafe)
    assert data["tasks"] == []
    assert balancecard.draw_counter(data).read()
    interaction = cafe.interaction()
    asyncio.run(
        cafe.cogs["Balance"].balance.callback(cafe.cogs["Balance"], interaction)
    )
    view = interaction.followup.send.call_args.kwargs["view"]
    links = [item.url for item in view.walk_children() if getattr(item, "url", None)]
    assert links and links[0].endswith(str(SERVER_STORE))

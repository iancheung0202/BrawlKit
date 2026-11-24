import asyncio
import io
import time
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

from brawl.Currency import balancecard, card, ladder
from brawl.Currency.card import BACKGROUND
from brawl.Currency.db import (
    u_balance,
    u_brews,
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


def test_the_counter_draws_on_the_default_background(cafe):
    data = {**member(cafe), **stamp_card(cafe)}
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


def test_every_page_is_its_header_then_its_cards(cafe):
    for place, cards in (
        ("COUNTER", 3),
        ("CHAT", 2),
        ("INVENTORY", 3),
        ("COMMUNITY", 4),
    ):
        view, files = page(cafe, place)
        assert [file.filename for file in files] == [
            f"balance_{USER}_{place.lower()}_{spot}.jpg" for spot in range(cards)
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
    assert balancecard.draw_held(held).read()
    assert balancecard.draw_effects(held).read()


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
    # Only the page on screen answers the timeout.
    view.message = sent["view"].message = AsyncMock()
    asyncio.run(view.on_timeout())
    assert not view.message.edit.called
    asyncio.run(sent["view"].on_timeout())
    assert sent["view"].message.edit.call_args.kwargs == {"view": sent["view"]}


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

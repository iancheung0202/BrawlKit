import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from brawl.Currency.db import g_shops, u_balance
from brawl.Currency.helper import MAIN_GUILD_ID
from brawl.Currency.shop import PurchaseRequest
from tests.conftest import text

USER = 1


def buy(cafe, item, rows, beans=5000, tokens=10):
    u_balance(USER).set({"Beans": beans, "Tokens": tokens})
    g_shops(MAIN_GUILD_ID).set(rows)
    interaction = cafe.interaction(USER)
    request = PurchaseRequest(interaction, item)
    asyncio.run(cafe.cogs["Shop"]._process_purchase(request))
    return interaction.edit_original_response.call_args.kwargs


def test_buy_takes_beans_and_one_stock(cafe):
    reply = buy(cafe, "nitro", [["Nitro", "A month", 3000, "Beans", True, 2]])
    assert reply["attachments"][0].filename == "purchase.png"
    assert "ticket" in text(reply)
    assert u_balance(USER).get() == {"Beans": 2000, "Tokens": 10}
    assert g_shops(MAIN_GUILD_ID).get()[0][5] == 1


def test_buy_takes_tokens_and_leaves_unlimited_stock(cafe):
    buy(cafe, "Nitro", [["Nitro", "A month", 4, "Tokens", True, -1]])
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 6}
    assert g_shops(MAIN_GUILD_ID).get()[0][5] == -1


def test_buy_rejects_a_price_above_the_balance(cafe):
    reply = buy(cafe, "Nitro", [["Nitro", "A month", 9000, "Beans", True, 2]])
    assert "do not have enough" in text(reply)
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 10}
    assert g_shops(MAIN_GUILD_ID).get()[0][5] == 2


def test_buy_rejects_an_item_out_of_stock(cafe):
    reply = buy(cafe, "Nitro", [["Nitro", "A month", 3000, "Beans", True, 0]])
    assert "out of stock" in text(reply)
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 10}


def test_buy_rejects_an_unknown_item(cafe):
    reply = buy(cafe, "Boat", [["Nitro", "A month", 3000, "Beans", True, 2]])
    assert "no item called `Boat`" in text(reply)
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 10}


def test_effect_item_stays_locked_below_its_level(cafe):
    cafe.cogs["Leveling"] = MagicMock(level_of=AsyncMock(return_value=5))
    u_balance(USER).set({"Beans": 5000, "Tokens": 10})
    interaction = cafe.interaction(USER)
    asyncio.run(
        cafe.cogs["Shop"]._process_effect_purchase(interaction, USER, "double_daily")
    )
    reply = interaction.edit_original_response.call_args.kwargs
    assert "Level 9" in text(reply)
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 10}


def open_shop(cafe, rows, admin=False, level=50):
    from brawl.Currency import shop

    cafe.cogs["Leveling"] = MagicMock(level_of=AsyncMock(return_value=level))
    g_shops(MAIN_GUILD_ID).set(rows)
    u_balance(USER).set({"Beans": 700, "Tokens": 2})
    interaction = cafe.interaction(USER)
    interaction.user.guild_permissions.administrator = admin
    cog = cafe.cogs["Shop"]
    asyncio.run(cog.shop.callback(cog, interaction))
    return interaction.followup.send.call_args.kwargs, shop


def find(view, custom_id):
    return next(
        item
        for item in view.walk_children()
        if getattr(item, "custom_id", None) == custom_id
    )


def rows(view):
    """Each item row on screen: (its text, its price button)."""
    return [
        (section.children[0].content, section.accessory)
        for section in view.walk_children()
        if isinstance(section, discord.ui.Section)
    ]


def test_shop_opens_with_the_wallet_and_a_row_for_each_item(cafe):
    sent, shop = open_shop(cafe, [["Nitro", "A month", 3000, "Beans", True, 2]])
    view = sent["view"]
    assert sent["file"].filename == "shop.jpg" and "embed" not in sent
    assert type(view) is shop.ShopView
    assert view.wallet["beans"] == 700 and view.wallet["tokens"] == 2
    names = [item["name"] for page in view.pages for item in page]
    assert "Nitro" in names and "Star Drop" in names
    assert all(len(page) <= 6 for page in view.pages)
    assert len(rows(view)) == len(view.pages[0])
    assert view.total_children_count <= 40
    with pytest.raises(StopIteration):
        find(view, "addreward")


def test_shop_marks_what_the_member_has_not_unlocked(cafe):
    sent, _ = open_shop(cafe, [], level=3)
    view = sent["view"]
    assert {"effects", "boxes", "style"} <= view.wallet["locked"]
    assert "drops" not in view.wallet["locked"]
    view.filter = "Effect items"
    view.lay_out()
    assert any(
        "Unlocks at Level 9" in text and button.disabled for text, button in rows(view)
    )


def test_shop_filter_and_page_buttons_relay_the_rows(cafe):
    sent, shop = open_shop(cafe, [["Nitro", "A month", 4, "Tokens", True, 0]], True)
    view = sent["view"]
    assert find(view, "addreward") and find(view, "editstock")
    press = cafe.interaction(USER)

    async def choose():
        select = find(view, "filterselection")
        select._values = ["Token items"]
        await select.callback(press)
        await find(view, "next_page").callback(press)

    asyncio.run(choose())
    assert view.filter == "Token items" and view.page == 1
    assert all(item["currency"] == "tokens" for page in view.pages for item in page)
    assert press.response.edit_message.call_args.kwargs == {"view": view}
    assert find(view, "filterselection").options[2].default


def test_shop_uploads_only_the_emojis_the_bot_is_missing(cafe):
    from brawl.Currency import shop

    have = MagicMock()
    have.name = "Shop_star_drop"
    have.__str__ = lambda self: "<:Shop_star_drop:1>"
    cafe.bot.fetch_application_emojis = AsyncMock(return_value=[have])
    made = AsyncMock(side_effect=lambda name, image: f"<:{name}:2>")
    cafe.bot.create_application_emoji = made
    asyncio.run(shop.stock_emotes(cafe.bot))
    names = [call.kwargs["name"] for call in made.call_args_list]
    assert "Shop_star_drop" not in names and "Shop_icon_role" in names
    assert shop.EMOTES["items/star_drop"] == "<:Shop_star_drop:1>"
    assert shop.EMOTES["items/mega_box"] == "<:Shop_mega_box:2>"
    assert all(call.kwargs["image"][:4] == b"\x89PNG" for call in made.call_args_list)
    shop.EMOTES.clear()


def test_every_shop_item_has_an_icon_and_a_short_description():
    from brawl.Currency.card import item_icon
    from brawl.Currency.helper import STORE_ITEMS

    for item, data in STORE_ITEMS.items():
        assert item_icon(item) == f"items/{item}"
        assert len(data["description"]) <= 70 and data["description"].endswith(".")


def test_buying_an_effect_item_shows_a_card_with_what_to_do_next(cafe):
    from brawl.Currency.shopcard import after

    cafe.cogs["Leveling"] = MagicMock(level_of=AsyncMock(return_value=50))
    u_balance(USER).set({"Beans": 5000, "Tokens": 10})
    interaction = cafe.interaction(USER)
    asyncio.run(
        cafe.cogs["Shop"]._process_effect_purchase(interaction, USER, "star_drop")
    )
    reply = interaction.edit_original_response.call_args.kwargs
    assert reply["attachments"][0].filename == "purchase.png"
    assert after("double_daily") == "Active for 7 days."
    assert after("instant_brew") == "It took effect right away."


def on_page(view, name):
    """Lays out the page an item is on and returns its row: (text, price button)."""
    for view.page in range(len(view.pages)):
        view.lay_out()
        for text, button in rows(view):
            if f" {name}" in text.splitlines()[0]:
                return text, button


def test_only_what_the_member_can_buy_has_a_live_button(cafe):
    sent, _ = open_shop(
        cafe,
        [
            ["Cheap", "x", 100, "Beans", True, -1],
            ["Dear", "x", 9000, "Beans", True, -1],
            ["Gone", "x", 1, "Beans", True, 0],
        ],
    )
    view = sent["view"]
    text, button = on_page(view, "Cheap")
    assert not button.disabled and button.style == discord.ButtonStyle.green
    assert button.label == "100" and "-#" not in text
    text, button = on_page(view, "Dear")
    assert button.disabled and button.style == discord.ButtonStyle.grey
    assert "You need 8,300 more Beans" in text
    text, button = on_page(view, "Gone")
    assert button.disabled and "Sold out" in text and "You need" not in text


def test_admin_row_sits_under_the_controls(cafe):
    sent, _ = open_shop(cafe, [], admin=True)
    order = [
        getattr(item, "custom_id", None)
        for item in sent["view"].walk_children()
        if getattr(item, "custom_id", None)
    ]
    assert order[-7:] == [
        "last_page",
        "sortselection",
        "filterselection",
        "addreward",
        "removereward",
        "editcost",
        "editstock",
    ]
    assert sent["view"].total_children_count <= 40
    member, _ = open_shop(cafe, [])
    with pytest.raises(StopIteration):
        find(member["view"], "addreward")


def test_pressing_a_price_button_buys_like_the_buy_command(cafe):
    sent, shop = open_shop(cafe, [["Cheap", "x", 100, "Beans", True, 3]])
    view = sent["view"]
    press = cafe.interaction(USER)
    _, button = on_page(view, "Cheap")
    asyncio.run(button.callback(press))
    assert "Processing" in text(press.response.send_message.call_args)
    assert press.edit_original_response.call_args.kwargs["attachments"][0].filename == (
        "purchase.png"
    )
    assert u_balance(USER).get()["Beans"] == 600
    assert g_shops(MAIN_GUILD_ID).get()[0][5] == 2
    assert view.wallet["beans"] == 600
    edit = view.origin.edit_original_response.call_args.kwargs
    assert edit["attachments"][0].filename == "shop.jpg" and edit["view"] is view


def test_an_item_in_the_bag_is_marked_and_cannot_be_bought(cafe):
    from brawl.Currency import bag

    bag.keep(USER, "sell_alarm")
    sent, _ = open_shop(cafe, [])
    view = sent["view"]
    assert view.wallet["held"] == {"sell_alarm"}
    text, button = on_page(view, "Sell Alarm")
    assert "In your bag, start it with /use" in text and button.disabled
    assert [component["type"] for component in view.to_components()] == [17]


def queued(cafe, item, process=None):
    """Runs one purchase through the queue, as /buy and the shop menu do."""
    from brawl.Currency import shop

    interaction = cafe.interaction(USER)
    interaction.response.send_message = AsyncMock()
    interaction.client.get_cog = cafe.cogs.get
    if process:
        cafe.cogs["Shop"]._process_purchase = process

    async def run():
        request = await shop.order(interaction, item)
        await asyncio.wait_for(request.done.wait(), 5)

    asyncio.run(run())
    return interaction.edit_original_response.call_args.kwargs


def test_a_typed_name_that_matches_nothing_points_to_the_shop_menu(cafe):
    g_shops(MAIN_GUILD_ID).set([["Nitro", "A month", 3000, "Beans", True, 2]])
    reply = text(queued(cafe, "stardrop"))
    assert "no item called `stardrop`" in reply and "</shop:" in reply


def test_a_stuck_or_broken_purchase_ends_its_waiting_note(cafe, monkeypatch):
    from brawl.Currency import shop

    async def stuck(request):
        await asyncio.sleep(9)

    async def broken(request):
        raise KeyError("x")

    monkeypatch.setattr(shop, "PURCHASE_SECONDS", 0.05)
    for process in (stuck, broken):
        assert "did not go through" in text(queued(cafe, "Nitro", process))


def test_only_the_member_who_opened_the_shop_can_press_its_buttons(cafe):
    sent, _ = open_shop(cafe, [["Cheap", "x", 100, "Beans", True, 3]])
    other = cafe.interaction(USER + 1)
    assert not asyncio.run(sent["view"].interaction_check(other))
    assert "not the author" in text(other.response.send_message.call_args)
    assert asyncio.run(sent["view"].interaction_check(cafe.interaction(USER)))

import asyncio
from unittest.mock import AsyncMock, MagicMock

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
    assert "not found" in text(reply)
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 10}


def test_effect_item_stays_locked_below_its_level(cafe):
    cafe.cogs["Leveling"] = MagicMock(level_of=AsyncMock(return_value=5))
    u_balance(USER).set({"Beans": 5000, "Tokens": 10})
    interaction = cafe.interaction(USER)
    asyncio.run(
        cafe.cogs["Shop"]._process_effect_purchase(interaction, USER, "double_daily")
    )
    reply = interaction.edit_original_response.call_args.kwargs
    assert "Level 20" in text(reply)
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


def test_shop_opens_as_a_card_with_the_members_balance(cafe):
    sent, shop = open_shop(cafe, [["Nitro", "A month", 3000, "Beans", True, 2]])
    view = sent["view"]
    assert sent["file"].filename == "shop.jpg" and "embed" not in sent
    assert type(view) is shop.ShopView
    assert view.wallet["beans"] == 700 and view.wallet["tokens"] == 2
    names = [item["name"] for page in view.pages for item in page]
    assert "Nitro" in names and "Star Drop" in names
    assert all(len(page) <= 6 for page in view.pages)


def test_shop_marks_what_the_member_has_not_unlocked(cafe):
    sent, _ = open_shop(cafe, [], level=5)
    assert {"effects", "boxes", "style"} <= sent["view"].wallet["locked"]
    assert "drops" not in sent["view"].wallet["locked"]


def test_shop_filter_and_page_buttons_redraw_the_card(cafe):
    sent, shop = open_shop(cafe, [["Nitro", "A month", 4, "Tokens", True, 0]], True)
    view = sent["view"]
    assert type(view) is shop.Panel
    press = cafe.interaction(USER)

    async def choose():
        select = next(c for c in view.children if c.custom_id == "filterselection")
        select._values = ["Token items"]
        await select.callback(press)
        await view.next_button.callback(press)

    asyncio.run(choose())
    assert view.filter == "Token items" and view.page == 1
    assert all(item["currency"] == "tokens" for page in view.pages for item in page)
    edit = press.response.edit_message.call_args.kwargs
    assert edit["attachments"][0].filename == "shop.jpg"


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


def options(view):
    return [option.label for option in view.buy.options]


def test_buy_menu_lists_only_what_the_member_can_buy_on_the_page(cafe):
    rows = [
        ["Cheap", "x", 100, "Beans", True, -1],
        ["Dear", "x", 9000, "Beans", True, -1],
        ["Gone", "x", 1, "Beans", True, 0],
    ]
    sent, _ = open_shop(cafe, rows)
    view = sent["view"]
    assert view.buy.row == 0 and not view.buy.disabled
    page = {item["name"] for item in view.pages[0]}
    assert "Cheap" in options(view) and set(options(view)) <= page
    assert not {"Dear", "Gone"} & set(options(view))
    assert all(
        view.wallet[item["currency"]] >= item["cost"]
        for item in view.pages[0]
        if item["name"] in options(view)
    )


def test_buy_menu_is_off_when_nothing_on_the_page_can_be_bought(cafe):
    sent, _ = open_shop(cafe, [], level=50)
    view = sent["view"]
    view.wallet["beans"] = view.wallet["tokens"] = 0
    view.lay_out()
    assert view.buy.disabled and view.buy.placeholder == "Nothing to buy on this page"


def test_admin_rows_sit_under_the_buy_menu(cafe):
    sent, shop = open_shop(cafe, [], admin=True)
    rows = {child.custom_id: child.row for child in sent["view"].children}
    assert rows["buyselection"] == 0 and rows["addreward"] == 1
    assert rows["next_page"] == 2 and rows["filterselection"] == 4
    member, _ = open_shop(cafe, [])
    rows = {child.custom_id: child.row for child in member["view"].children}
    assert rows["buyselection"] == 0 and rows["next_page"] == 1
    assert rows["filterselection"] == 3


def test_picking_from_the_menu_buys_like_the_buy_command(cafe):
    sent, shop = open_shop(cafe, [["Cheap", "x", 100, "Beans", True, 3]])
    view = sent["view"]
    press = cafe.interaction(USER)

    async def pick():
        view.buy._values = ["Cheap"]
        await view.buy.callback(press)

    asyncio.run(pick())
    assert "Processing" in text(press.response.send_message.call_args)
    assert press.edit_original_response.call_args.kwargs["attachments"][0].filename == (
        "purchase.png"
    )
    assert u_balance(USER).get()["Beans"] == 600
    assert g_shops(MAIN_GUILD_ID).get()[0][5] == 2
    assert view.wallet["beans"] == 600
    assert view.origin.edit_original_response.call_args.kwargs["view"] is view


def test_an_item_in_the_bag_is_marked_and_left_off_the_buy_menu(cafe):
    from brawl.Currency import bag

    bag.keep(USER, "sell_alarm")
    sent, _ = open_shop(cafe, [])
    view = sent["view"]
    assert view.wallet["held"] == {"sell_alarm"}
    for view.page in range(len(view.pages)):
        view.lay_out()
        assert "Sell Alarm" not in options(view)
    assert [component["type"] for component in view.to_components()] == [1, 1, 1, 1]

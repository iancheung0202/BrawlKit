import asyncio

from brawl.Currency.db import g_shops, u_balance
from brawl.Currency.helper import MAIN_GUILD_ID
from brawl.Currency.shop import PurchaseRequest

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
    assert "Successfully purchased Nitro" in reply["embed"].description
    assert u_balance(USER).get() == {"Beans": 2000, "Tokens": 10}
    assert g_shops(MAIN_GUILD_ID).get()[0][5] == 1


def test_buy_takes_tokens_and_leaves_unlimited_stock(cafe):
    buy(cafe, "Nitro", [["Nitro", "A month", 4, "Tokens", True, -1]])
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 6}
    assert g_shops(MAIN_GUILD_ID).get()[0][5] == -1


def test_buy_rejects_a_price_above_the_balance(cafe):
    reply = buy(cafe, "Nitro", [["Nitro", "A month", 9000, "Beans", True, 2]])
    assert "do not have enough" in reply["content"]
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 10}
    assert g_shops(MAIN_GUILD_ID).get()[0][5] == 2


def test_buy_rejects_an_item_out_of_stock(cafe):
    reply = buy(cafe, "Nitro", [["Nitro", "A month", 3000, "Beans", True, 0]])
    assert "out of stock" in reply["content"]
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 10}


def test_buy_rejects_an_unknown_item(cafe):
    reply = buy(cafe, "Boat", [["Nitro", "A month", 3000, "Beans", True, 2]])
    assert "not found" in reply["content"]
    assert u_balance(USER).get() == {"Beans": 5000, "Tokens": 10}

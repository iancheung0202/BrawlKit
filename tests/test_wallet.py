import asyncio

from brawl.Currency import events, wallet
from brawl.Currency.db import u_balance

USER = 1


def test_change_adds_and_reports_the_new_balance(cafe):
    assert asyncio.run(wallet.change(USER, beans=500, tokens=2)) == (500, 2)
    assert asyncio.run(wallet.change(USER, beans=-100)) == (400, 2)
    assert u_balance(USER).get() == {"Beans": 400, "Tokens": 2}


def test_pay_refuses_when_short_and_leaves_the_balance(cafe):
    asyncio.run(wallet.change(USER, beans=100))
    assert not asyncio.run(wallet.pay(USER, beans=150))
    assert asyncio.run(wallet.pay(USER, beans=60))
    assert wallet.balance(USER) == (40, 0)


def test_change_emits_one_event_with_its_reason(cafe, monkeypatch):
    seen = []

    async def record(user_id, **data):
        seen.append((user_id, data))

    monkeypatch.setattr(events, "handlers", {"wallet": {"record": record}})
    asyncio.run(wallet.change(USER, tokens=3, reason="sell"))
    asyncio.run(wallet.change(USER))
    assert seen == [(USER, {"beans": 0, "tokens": 3, "reason": "sell"})]


def test_a_failing_handler_does_not_stop_the_others(cafe, monkeypatch):
    seen = []

    async def fail(user_id, **data):
        raise ValueError

    async def record(user_id, **data):
        seen.append(user_id)

    monkeypatch.setattr(
        events, "handlers", {"wallet": {"fail": fail, "record": record}}
    )
    asyncio.run(wallet.change(USER, beans=1))
    assert seen == [USER]


def test_cog_helpers_go_through_the_wallet(cafe):
    cog = cafe.cogs["CurrencySystem"]
    assert asyncio.run(cog.add_beans(USER, 300)) == 300
    assert asyncio.run(cog.add_tokens(USER, 4)) == 4
    assert asyncio.run(cog.get_balance(USER)) == (300, 4)

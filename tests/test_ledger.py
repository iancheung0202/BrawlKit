import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from brawl.Currency import events, ledger, stampcard, wallet
from brawl.Currency.db import g_ledger
from brawl.Currency.helper import MAIN_GUILD_ID

USER, OTHER = 1, 2


@pytest.fixture(autouse=True)
def counted(cafe, monkeypatch):
    ledger.waiting.clear()
    ledger.members.clear()
    monkeypatch.setattr(events, "handlers", {"wallet": {"ledger": ledger.on_wallet}})
    yield
    ledger.waiting.clear()
    ledger.members.clear()


def week():
    return g_ledger(MAIN_GUILD_ID).child(ledger.week_key()).get()


def test_a_week_starts_on_monday_utc():
    sunday = datetime(2026, 11, 29, 23, 59, tzinfo=timezone.utc)
    assert ledger.week_key(sunday) == "2026-11-23"
    assert ledger.week_key(datetime(2026, 11, 30, tzinfo=timezone.utc)) == "2026-11-30"


def test_earnings_and_spends_are_counted_by_source():
    asyncio.run(wallet.change(USER, beans=100, reason="chat"))
    asyncio.run(wallet.change(OTHER, beans=50, tokens=1, reason="chat"))
    asyncio.run(wallet.change(USER, beans=-40, reason="shop"))
    stampcard.add(USER, source="order")
    ledger.note("boss", USER)
    ledger.save()
    saved = week()
    assert saved["chat"] == {
        "uses": 2,
        "beans": 150,
        "tokens": 1,
        "members": {"1": True, "2": True},
    }
    assert saved["shop"] == {"uses": 1, "beans_spent": 40, "members": {"1": True}}
    assert saved["order"]["stamps"] == 1
    assert saved["boss"] == {"uses": 1, "members": {"1": True}}


def test_saves_add_up_and_an_unknown_source_is_untagged():
    asyncio.run(wallet.change(USER, beans=5, reason="chat"))
    ledger.save()
    asyncio.run(wallet.change(USER, beans=5, reason="chat"))
    asyncio.run(wallet.change(USER, beans=1, reason="made_up"))
    ledger.save()
    ledger.save()
    saved = week()
    assert saved["chat"]["beans"] == 10 and saved["chat"]["uses"] == 2
    assert saved["other"]["beans"] == 1


def texts(view):
    return [part.content for part in view.walk_children() if hasattr(part, "content")]


def build(*args, **kwargs):
    async def make():
        return ledger.EconomyView(*args, **kwargs)

    return asyncio.run(make())


def test_the_grid_is_aligned_sorted_and_totalled():
    asyncio.run(wallet.change(USER, beans=1200, reason="chat"))
    asyncio.run(wallet.change(OTHER, beans=5, reason="chat"))
    asyncio.run(wallet.change(OTHER, tokens=3, reason="brew"))
    asyncio.run(wallet.change(OTHER, beans=-40, reason="brew"))
    stampcard.add(USER, source="order")
    ledger.save()
    lines = ledger.grid(week())
    assert len({len(line) for line in lines}) == 1
    assert [line.split("  ")[0] for line in lines[1:4]] == [
        "Chat",
        "Brewing",
        "Today's Order",
    ]
    assert lines[-1].split() == [
        "Whole",
        "cafe",
        "2",
        "5",
        "1,205",
        "3",
        "1",
        "40",
        "0",
    ]
    assert ledger.grid(week(), "tokens")[1].startswith("Brewing")


def test_the_economy_view_shows_the_table_and_fits_discord():
    assert "Nothing was counted" in " ".join(texts(build()))
    for source in ledger.SOURCES:
        asyncio.run(wallet.change(USER, beans=1234567, tokens=12345, reason=source))
        asyncio.run(wallet.change(USER, beans=-1234567, tokens=-12345, reason=source))
    ledger.save()
    view, quiet = build(), build(turns=False)
    parts = list(view.walk_children())
    assert len(parts) <= 40 and sum(map(len, texts(view))) <= 4000
    assert any(text.startswith("```\nSystem") for text in texts(view))
    labels = {part.label: part.disabled for part in parts if hasattr(part, "label")}
    assert labels == {"Earlier week": False, "Later week": True}
    assert not any(part.is_dispatchable() for part in quiet.walk_children())
    assert "Not used" not in " ".join(texts(view))
    assert "Nothing was counted" in " ".join(texts(build(1)))


def test_the_ledger_saves_when_it_is_unloaded():
    asyncio.run(wallet.change(USER, beans=5, reason="chat"))
    ledger.Ledger.cog_unload(MagicMock())
    assert week()["chat"]["beans"] == 5


def test_every_tagged_reason_is_a_known_source():
    import pathlib
    import re

    used = set()
    for path in pathlib.Path("brawl").rglob("*.py"):
        used |= set(re.findall(r'(?:reason|source)="(\w+)"', path.read_text()))
    assert used <= set(ledger.SOURCES)


def test_a_finished_week_is_sent_to_the_owner_once(monkeypatch):
    bot = MagicMock()
    cog = ledger.Ledger.__new__(ledger.Ledger)
    cog.bot = bot
    owner = MagicMock(send=AsyncMock())
    cog.owner = AsyncMock(return_value=owner)
    asyncio.run(cog.send_last_week())
    owner.send.assert_not_called()
    last = ledger.week_key(datetime.fromtimestamp(0, timezone.utc))
    monkeypatch.setattr(ledger, "week_key", lambda now=None: last)
    g_ledger(MAIN_GUILD_ID).child(last).set({"chat": {"uses": 1, "beans": 9}})
    asyncio.run(cog.send_last_week())
    asyncio.run(cog.send_last_week())
    assert owner.send.await_count == 1


def test_our_files_start_from_the_copy_other_files_import(monkeypatch):
    import firebase_admin

    monkeypatch.setattr(firebase_admin.credentials, "Certificate", MagicMock())
    monkeypatch.setattr(firebase_admin, "initialize_app", MagicMock())
    import brawlkit

    bot = MagicMock(add_cog=AsyncMock())

    async def load():
        await brawlkit.load(bot, "brawl.Currency.ledger")
        cog = bot.add_cog.call_args.args[0]
        cog.task.cancel()
        return cog

    assert type(asyncio.run(load())) is ledger.Ledger

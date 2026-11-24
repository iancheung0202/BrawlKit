import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from brawl.Currency import events, ledger, stampcard, wallet
from brawl.Currency.db import g_ledger
from brawl.Currency.helper import MAIN_GUILD_ID, STORE_ITEMS

USER, OTHER = 1, 2


@pytest.fixture(autouse=True)
def counted(cafe, monkeypatch):
    ledger.waiting.clear()
    ledger.members.clear()
    ledger.items.clear()
    handlers = defaultdict(dict, wallet={"ledger": ledger.on_wallet})
    monkeypatch.setattr(events, "handlers", handlers)
    yield
    ledger.waiting.clear()
    ledger.members.clear()
    ledger.items.clear()


def week():
    return g_ledger(MAIN_GUILD_ID).child(ledger.week_key()).get()


def test_a_week_starts_on_sunday_utc_like_the_tables():
    saturday = datetime(2026, 11, 28, 23, 59, tzinfo=timezone.utc)
    assert ledger.week_key(saturday) == "2026-11-22"
    assert ledger.week_key(datetime(2026, 11, 29, tzinfo=timezone.utc)) == "2026-11-29"


def test_the_wait_for_the_next_week_is_never_longer_than_a_week():
    week = 7 * 86400
    assert 0 < ledger.until_next_week() <= week
    assert 0 <= ledger.until_next_week(timedelta(minutes=1)) < week


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


def test_items_are_counted_by_week_and_listed_busiest_first():
    ledger.item("mega_box", dropped=2)
    ledger.item("mega_box", bought=10, used=3)
    ledger.item("chat_boost", dropped=1)
    ledger.item("VIP [Gold]/role.", bought=1)
    ledger.save()
    ledger.item("chat_boost", used=1)
    ledger.save()
    saved = ledger.g_items(ledger.week_key()).get()
    assert saved["mega_box"] == {"bought": 10, "dropped": 2, "used": 3}
    assert saved["chat_boost"] == {"bought": 0, "dropped": 1, "used": 1}
    lines = ledger.stock(saved)
    assert len({len(line) for line in lines}) == 1
    assert lines[1].split() == ["Mega", "Box", "10", "2", "3"]
    assert lines[2].startswith("VIP  Gold  role ")
    assert ledger.stock(saved, "used")[2].startswith(STORE_ITEMS["chat_boost"]["name"])
    many = {f"item {number}": {"bought": 1} for number in range(40)}
    assert ledger.stock(many)[-1] == "and 15 more"


def test_the_economy_view_lists_items_under_the_systems():
    asyncio.run(wallet.change(USER, beans=5, reason="chat"))
    ledger.save()
    assert "No items were bought" in " ".join(texts(build()))
    ledger.item("star_drop", used=4)
    ledger.save()
    view = build()
    kinds = [type(part).__name__ for part in view.walk_children()]
    assert kinds.index("Separator") > kinds.index("Sort") and kinds.count("Sort") == 2
    assert kinds[-3:] == ["Button", "Button", "Button"]
    assert any(text.startswith("```\nItem") for text in texts(view))
    assert [type(part).__name__ for part in build(turns=False).walk_children()].count(
        "Separator"
    ) == 1


def test_the_economy_view_shows_the_table_and_fits_discord():
    assert "Nothing was counted" in " ".join(texts(build()))
    for source in ledger.SOURCES:
        asyncio.run(wallet.change(USER, beans=1234567, tokens=12345, reason=source))
        asyncio.run(wallet.change(USER, beans=-1234567, tokens=-12345, reason=source))
    for number in range(40):
        ledger.item(
            f"A reward with a very long name {number}", 1234567, 1234567, 1234567
        )
    ledger.save()
    view, quiet = build(), build(turns=False)
    parts = list(view.walk_children())
    assert len(parts) <= 40 and sum(map(len, texts(view))) <= 4000
    assert any(text.startswith("```\nSystem") for text in texts(view))
    buttons = [part for part in parts if isinstance(part, discord.ui.Button)]
    assert [button.disabled for button in buttons] == [False, True, True]
    assert buttons[1].label == "This week" and ledger.ago(3) == "3 weeks ago"
    last = [part for part in build(1).walk_children() if hasattr(part, "label")]
    assert [(part.label, part.disabled) for part in last][-3:] == [
        (None, False),
        ("Last week", True),
        (None, False),
    ]
    assert not any(part.is_dispatchable() for part in quiet.walk_children())
    assert "No activity" not in " ".join(texts(view))
    g_ledger(MAIN_GUILD_ID).child(ledger.week_key()).child("boss").delete()
    assert "-# No activity: Boss inspection" in texts(build())
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
    owner.send.assert_not_called()
    asyncio.run(cog.on_top_table_paid(0, week=last))
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

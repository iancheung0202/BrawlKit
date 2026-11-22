import asyncio
import time

from brawl.Currency import daily
from brawl.Currency.db import u_balance, u_daily_checkin_streaks
from tests.conftest import text

USER = 1


def claim(cafe, monkeypatch):
    monkeypatch.setattr(daily.random, "random", lambda: 1)
    interaction = cafe.interaction(USER)
    interaction.guild.premium_subscriber_role = None
    asyncio.run(cafe.cogs["Daily"].process_daily(interaction))
    return interaction


def test_first_claim_pays_beans_and_starts_a_streak(cafe, monkeypatch):
    claim(cafe, monkeypatch)
    streak = u_daily_checkin_streaks(USER).get()
    assert u_balance(USER).get()["Beans"] == 500
    assert streak["current_streak"] == 1
    assert streak["total_claims"] == 1


def test_second_claim_the_same_day_is_rejected(cafe, monkeypatch):
    claim(cafe, monkeypatch)
    interaction = claim(cafe, monkeypatch)
    assert "already clocked in" in text(interaction.response.send_message.call_args)
    assert u_balance(USER).get()["Beans"] == 500
    assert u_daily_checkin_streaks(USER).get()["total_claims"] == 1


def test_claim_the_next_day_extends_the_streak(cafe, monkeypatch):
    u_daily_checkin_streaks(USER).set(
        {
            "last_claim": time.time() - 86400,
            "current_streak": 3,
            "all_time_high": 5,
            "total_claims": 9,
        }
    )
    claim(cafe, monkeypatch)
    streak = u_daily_checkin_streaks(USER).get()
    assert streak["current_streak"] == 4
    assert streak["all_time_high"] == 5


def test_claim_after_two_days_resets_the_streak(cafe, monkeypatch):
    u_daily_checkin_streaks(USER).set(
        {
            "last_claim": time.time() - 200000,
            "current_streak": 6,
            "all_time_high": 6,
            "total_claims": 9,
        }
    )
    claim(cafe, monkeypatch)
    assert u_daily_checkin_streaks(USER).get()["current_streak"] == 1


def test_seventh_day_pays_four_times_the_beans_and_tokens(cafe, monkeypatch):
    u_daily_checkin_streaks(USER).set(
        {
            "last_claim": time.time() - 86400,
            "current_streak": 6,
            "all_time_high": 6,
            "total_claims": 6,
        }
    )
    claim(cafe, monkeypatch)
    balance = u_balance(USER).get()
    assert balance["Beans"] == 2000
    assert 2 <= balance["Tokens"] <= 5


def test_only_admins_post_the_store_panel(cafe):
    from unittest.mock import AsyncMock, MagicMock

    def typed(admin):
        message = MagicMock(content="-dailypanel")
        message.author.bot = False
        message.author.guild_permissions.administrator = admin
        message.guild.id = 0
        message.channel.send = AsyncMock()
        message.delete = AsyncMock()
        asyncio.run(cafe.cogs["Daily"].on_message(message))
        return message.channel.send

    assert not typed(False).called
    panel = typed(True)
    text = panel.call_args.kwargs["embed"].description
    assert "Clock In" in text and len(text) < 4096


def test_clocking_in_answers_with_a_card(cafe, monkeypatch):
    sent = claim(cafe, monkeypatch).followup.send.call_args
    assert sent.kwargs["file"].filename == "clock_in.jpg"
    assert "Order" in sent.kwargs["embed"].description
    assert sent.kwargs["embed"].image.url == "attachment://clock_in.jpg"

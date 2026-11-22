import asyncio
import time

from brawl.Currency import daily
from brawl.Currency.db import u_balance, u_daily_checkin_streaks

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
    assert "already claimed" in interaction.response.send_message.call_args.args[0]
    assert u_balance(USER).get()["Beans"] == 500
    assert u_daily_checkin_streaks(USER).get()["total_claims"] == 1


def test_claim_the_next_day_extends_the_streak(cafe, monkeypatch):
    u_daily_checkin_streaks(USER).set(
        {
            "last_claim": time.time() - 90000,
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
            "last_claim": time.time() - 90000,
            "current_streak": 6,
            "all_time_high": 6,
            "total_claims": 6,
        }
    )
    claim(cafe, monkeypatch)
    balance = u_balance(USER).get()
    assert balance["Beans"] == 2000
    assert 2 <= balance["Tokens"] <= 5

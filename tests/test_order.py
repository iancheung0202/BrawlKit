import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from brawl.Currency import quests, stampcard
from brawl.Currency.config import (
    ORDER_CHAT_BEANS,
    QUEST_BEAN_REWARDS,
    QUEST_BONUS_BEANS,
    STAMP_GOALS,
    STAMP_MONTHLY_LIMIT,
)
from brawl.Currency.db import g_stamp_redemptions, u_balance, u_quests, u_stamp_card
from brawl.Currency.helper import MAIN_GUILD_ID, get_current_month_key
from tests.conftest import text

USER = 1


@pytest.fixture
def order(cafe, monkeypatch):
    def generate(duration, level=0):
        if duration == "daily":
            return quests.generate_order(level)
        return {"brew_start": {"current": 0, "goal": 9}}

    monkeypatch.setattr(quests, "generate_quests", generate)
    level(cafe, 0)
    return cafe


def level(cafe, value):
    cafe.cogs["Leveling"] = MagicMock(level_of=AsyncMock(return_value=value))


def do(cafe, **tasks):
    return asyncio.run(quests.update_quest(USER, MAIN_GUILD_ID, tasks, cafe.bot))


def tasks():
    return set(u_quests(USER).child("daily/quests").get())


def test_a_new_member_gets_chat_and_clock_in(order):
    do(order)
    assert tasks() == {"chat_earnings", "daily_checkins"}


def test_level_one_gets_chat_brew_and_sell(order):
    level(order, 1)
    do(order)
    assert tasks() == {"chat_earnings", "brew_start", "brew_sells"}


def test_higher_levels_get_chat_and_two_station_tasks(order):
    level(order, 40)
    do(order)
    assert len(tasks()) == 3
    assert tasks() - {"brew_start", "brew_sells", "shop_purchases"} == {"chat_earnings"}


def test_finishing_the_order_pays_beans_and_one_stamp(order):
    level(order, 1)
    do(order, brew_start=1, brew_sells=1)
    assert stampcard.stamps(USER) == 0
    messages = do(order, chat_earnings=ORDER_CHAT_BEANS)
    assert stampcard.stamps(USER) == 1
    assert "Order complete" in messages[-1]
    earned = 3 * QUEST_BEAN_REWARDS["daily"] + QUEST_BONUS_BEANS["daily"]
    assert u_balance(USER).get()["Beans"] == earned


def test_commands_alone_never_stamp(order):
    level(order, 40)
    for _ in range(20):
        do(order, brew_start=1, brew_sells=1, shop_purchases=1, daily_checkins=1)
    assert stampcard.stamps(USER) == 0


def test_only_one_stamp_per_day(order):
    for _ in range(3):
        do(order, chat_earnings=ORDER_CHAT_BEANS, daily_checkins=1)
        u_quests(USER).child("daily").delete()
    assert stampcard.stamps(USER) == 1


def test_boss_ticks_a_station_task_but_not_chat(order):
    level(order, 1)
    for _ in range(5):
        asyncio.run(quests.wildcard(USER, MAIN_GUILD_ID, order.bot))
    daily = u_quests(USER).child("daily").get()
    assert set(daily["completed"]) == {"brew_start", "brew_sells"}
    assert stampcard.stamps(USER) == 0


def test_old_progress_converts_by_share(cafe):
    u_stamp_card(USER).set(
        {"stamps": {"daily_checkins": 30, "brew_sells": 15, "shop_purchases": 99}}
    )
    assert stampcard.stamps(USER) == round(2.5 / 6 * STAMP_GOALS["brawl_pass"])


def test_price_falls_with_the_streak(cafe):
    from brawl.Currency.db import u_daily_checkin_streaks

    assert stampcard.price(USER, "brawl_pass") == 400
    u_daily_checkin_streaks(USER).set({"current_streak": 55})
    assert stampcard.price(USER, "brawl_pass") == 300
    u_daily_checkin_streaks(USER).set({"current_streak": 500})
    assert stampcard.price(USER, "brawl_pass") == 200


def redeem(cafe, tier="brawl_pass"):
    interaction = cafe.interaction(USER)
    cog = cafe.cogs["StampCard"]
    choice = MagicMock(value=tier)
    choice.name = stampcard.TIERS[tier]
    asyncio.run(cog.redeem.callback(cog, interaction, choice))
    return interaction.response.send_message.call_args


def test_redeem_needs_a_full_card(cafe):
    u_stamp_card(USER).set({"count": 29})
    u_balance(USER).set({"Tokens": 999})
    assert "`30` Stamps" in text(redeem(cafe))
    assert u_balance(USER).get()["Tokens"] == 999


def test_redeem_needs_tokens(cafe):
    u_stamp_card(USER).set({"count": 30})
    u_balance(USER).set({"Tokens": 399})
    assert "costs" in text(redeem(cafe))
    assert u_stamp_card(USER).get()["count"] == 30


def test_redeem_stops_at_the_monthly_limit(cafe):
    u_stamp_card(USER).set({"count": 30})
    u_balance(USER).set({"Tokens": 999})
    g_stamp_redemptions(MAIN_GUILD_ID, get_current_month_key()).set(
        {"count": STAMP_MONTHLY_LIMIT}
    )
    assert "next month" in text(redeem(cafe))
    assert u_balance(USER).get()["Tokens"] == 999
    assert u_stamp_card(USER).get()["count"] == 30


def test_redeem_spends_stamps_and_tokens_and_counts_the_month(cafe):
    u_stamp_card(USER).set({"count": 33})
    u_balance(USER).set({"Tokens": 450})
    assert redeem(cafe).kwargs["file"].filename == "redeemed.png"
    assert u_stamp_card(USER).get()["count"] == 3
    assert u_balance(USER).get()["Tokens"] == 50
    month = g_stamp_redemptions(MAIN_GUILD_ID, get_current_month_key()).get()
    assert month["count"] == 1
    assert month["users"][0]["tier"] == "brawl_pass"


def test_stamp_card_shows_progress_and_prices(order):
    level(order, 1)
    u_stamp_card(USER).set({"count": 31})
    cog = order.cogs["StampCard"]
    user, guild = MagicMock(id=USER), MagicMock(id=MAIN_GUILD_ID)
    summary = asyncio.run(cog.summary(user, guild))
    assert (summary["stamps"], summary["done"], summary["tasks"]) == (31, 0, 3)
    assert summary["prices"] == {"brawl_pass": 400, "brawl_pass_plus": 500}
    assert asyncio.run(cog.card(user, guild)).filename == f"balance_{USER}.jpg"


@pytest.mark.before_clock_in
def test_the_order_waits_for_clock_in(cafe, monkeypatch):
    from brawl.Currency import quests
    from brawl.Currency.db import u_daily_checkin_streaks

    asyncio.run(quests.update_quest(77, 1, {"chat_earnings": 200}, cafe.bot))
    assert quests.order_tasks(77) == []
    u_daily_checkin_streaks(77).set({"last_claim": quests.time.time()})
    tasks = {task: data["current"] for task, _, data, _ in quests.order_tasks(77)}
    assert tasks["chat_earnings"] == 200
    asyncio.run(quests.update_quest(77, 1, {"chat_earnings": 200}, cafe.bot))
    tasks = {task: data["current"] for task, _, data, _ in quests.order_tasks(77)}
    assert tasks["chat_earnings"] == 400


@pytest.mark.before_clock_in
def test_a_brew_before_clock_in_is_ticked_and_paid_on_clock_in(order):
    from brawl.Currency.db import u_daily_checkin_streaks

    level(order, 1)
    assert do(order, brew_start=1) == []
    assert not u_balance(USER).get()
    u_daily_checkin_streaks(USER).set({"last_claim": quests.time.time()})
    done = do(order, daily_checkins=1)
    assert any("Start a brew" in line for line in done)
    assert u_balance(USER).get()["Beans"] == QUEST_BEAN_REWARDS["daily"]


def chat(cafe, earned, limit):
    asyncio.run(
        quests.update_quest(USER, MAIN_GUILD_ID, {}, cafe.bot, chat=(earned, limit))
    )
    return u_quests(USER).child("daily").get()


def test_the_chat_task_is_the_members_own_daily_limit(order):
    daily = chat(order, 600, 1500)
    assert daily["quests"]["chat_earnings"] == {"current": 600, "goal": 1500}
    assert "chat_earnings" not in daily.get("completed", {})
    assert "chat_earnings" in chat(order, 1500, 1500)["completed"]


def test_the_chat_task_follows_a_limit_that_changes_during_the_day(order):
    chat(order, 1200, 3000)
    daily = chat(order, 1200, 1000)
    assert daily["quests"]["chat_earnings"] == {"current": 1000, "goal": 1000}
    assert "chat_earnings" in daily["completed"]


def test_chat_limits_stack_roles_weekends_and_boosts(monkeypatch):
    from datetime import datetime, timezone

    from brawl.Currency import chat as rewards

    booster, ultra = MagicMock(), MagicMock()
    member = MagicMock(roles=[])
    member.guild.premium_subscriber_role = booster
    member.guild.get_role.return_value = ultra
    clock = MagicMock()
    monkeypatch.setattr(rewards, "datetime", clock)
    clock.now.return_value = datetime(2026, 11, 18, tzinfo=timezone.utc)
    assert rewards.chat_limit(member, {}) == 1000
    member.roles = [booster]
    assert rewards.chat_limit(member, {}) == 1500
    member.roles = [booster, ultra]
    assert rewards.chat_limit(member, {"chat_boost": 1}) == 15000
    clock.now.return_value = datetime(2026, 11, 21, tzinfo=timezone.utc)
    assert rewards.chat_limit(member, {}) == 10000

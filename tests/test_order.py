import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from brawl.Currency import balancecard, quests, rewardcard, stampcard
from brawl.Currency.config import (
    ORDER_CHAT_BEANS,
    ORDER_TASK_LEVELS,
    QUEST_BEAN_REWARDS,
    QUEST_BONUS_BEANS,
    STAMP_GOALS,
    STAMP_MONTHLY_LIMIT,
)
from brawl.Currency.db import g_stamp_redemptions, u_balance, u_quests, u_stamp_card
from brawl.Currency.helper import MAIN_GUILD_ID, get_current_month_key
from tests.conftest import text

USER = 1
# The real order; the cafe fixture swaps in a chat-only one.
REAL_ORDER = quests.generate_order


@pytest.fixture
def order(cafe, monkeypatch):
    monkeypatch.setattr(quests, "generate_order", REAL_ORDER)
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
    assert tasks() - set(ORDER_TASK_LEVELS) == {"chat_earnings"}


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


def test_an_inspection_only_finishes_the_boss_task(order, monkeypatch):
    monkeypatch.setattr(quests.random, "sample", lambda pool, count: pool[-count:])
    level(order, 7)
    done = do(order, boss_inspections=1)
    assert set(u_quests(USER).child("daily/completed").get()) == {"boss_inspections"}
    assert done.beans == QUEST_BEAN_REWARDS["daily"]


def test_an_inspection_does_nothing_for_an_order_without_the_boss_task(order):
    level(order, 1)
    assert do(order, boss_inspections=1) == []
    assert not u_quests(USER).child("daily/completed").get()


def test_old_progress_converts_one_stamp_for_six_old_ones(cafe):
    u_stamp_card(USER).set(
        {"stamps": {"daily_checkins": 30, "brew_sells": 15, "shop_purchases": 99}}
    )
    assert stampcard.stamps(USER) == round((30 + 15 + 10) / 6)


def test_price_falls_with_the_streak(cafe):
    from brawl.Currency.db import u_daily_checkin_streaks

    assert stampcard.price(USER, "brawl_pass") == 400
    u_daily_checkin_streaks(USER).set({"current_streak": 1})
    assert stampcard.price(USER, "brawl_pass") == 398
    u_daily_checkin_streaks(USER).set({"current_streak": 50})
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
    assert (summary["stamps"], summary["done"], summary["order"]) == (31, 0, 3)
    assert summary["prices"] == {"brawl_pass": 400, "brawl_pass_plus": 500}
    member = {**summary, "tokens": 500, "background": "gym"}
    assert balancecard.draw_stamps(member).read(2) == b"\xff\xd8"


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


def test_the_order_that_fills_the_card_points_to_redeem(order):
    level(order, 1)
    u_stamp_card(USER).set({"count": STAMP_GOALS["brawl_pass"] - 1})
    messages = do(order, brew_start=1, brew_sells=1, chat_earnings=ORDER_CHAT_BEANS)
    assert messages.redeem == "Brawl Pass"
    assert rewardcard.draw_paid(
        {
            "name": "Sam",
            "avatar": None,
            "beans": 600,
            "stamp": True,
            "redeem": "Brawl Pass",
        }
    )


def test_an_order_short_of_a_pass_does_not_point_to_redeem(order):
    level(order, 1)
    messages = do(order, brew_start=1, brew_sells=1, chat_earnings=ORDER_CHAT_BEANS)
    assert messages.stamp and messages.redeem is None


def test_station_task_levels_match_the_stations_they_need():
    from brawl.Currency.config import LADDER, ORDER_TASK_LEVELS

    assert ORDER_TASK_LEVELS["boss_inspections"] == LADDER["boss"][0]
    assert ORDER_TASK_LEVELS["thermometer_bonuses"] == LADDER["thermometer"][0]


def test_boss_and_thermometer_tasks_need_their_stations(order, monkeypatch):
    monkeypatch.setattr(quests.random, "sample", lambda pool, count: pool[-count:])
    level(order, 4)
    do(order)
    assert not tasks() & {"boss_inspections", "thermometer_bonuses"}
    u_quests(USER).delete()
    level(order, 5)
    do(order)
    assert "boss_inspections" in tasks() and "thermometer_bonuses" not in tasks()
    u_quests(USER).delete()
    level(order, 7)
    do(order)
    assert tasks() == {"chat_earnings", "boss_inspections", "thermometer_bonuses"}


def test_a_veteran_can_get_every_station_task(order, monkeypatch):
    from brawl.Currency.db import u_veteran

    monkeypatch.setattr(quests.random, "sample", lambda pool, count: pool[-count:])
    u_veteran(USER).set(True)
    do(order)
    assert tasks() == {"chat_earnings", "boss_inspections", "thermometer_bonuses"}


def test_a_thermometer_drop_finishes_its_task(order, monkeypatch):
    monkeypatch.setattr(quests.random, "sample", lambda pool, count: pool[-count:])
    level(order, 7)
    done = do(order, thermometer_bonuses=1)
    assert any("thermometer drop" in line for line in done)
    assert do(order, thermometer_bonuses=1) == []


@pytest.mark.before_clock_in
def test_an_order_finished_before_clock_in_pays_in_full_on_clock_in(order):
    from brawl.Currency.db import u_daily_checkin_streaks

    level(order, 1)
    do(order, brew_start=1, brew_sells=1)
    chat(order, 1000, 1000)
    assert not u_balance(USER).get()
    u_daily_checkin_streaks(USER).set({"last_claim": quests.time.time()})
    done = asyncio.run(
        quests.update_quest(
            USER, MAIN_GUILD_ID, {"daily_checkins": 1}, order.bot, chat=(1000, 1000)
        )
    )
    full = 3 * QUEST_BEAN_REWARDS["daily"] + QUEST_BONUS_BEANS["daily"]
    assert done.stamp and done.beans == full
    assert u_balance(USER).get()["Beans"] == full
    assert stampcard.stamps(USER) == 1


def test_the_clock_in_card_grows_to_show_what_the_order_paid():
    from PIL import Image

    shift = {
        "beans": 500,
        "tokens": 0,
        "notes": [],
        "streak": 3,
        "background": None,
        "tasks": [("Start a brew", "Done", True, 1)] * 3,
    }
    plain = Image.open(rewardcard.draw_clock_in(shift)).height
    paid = {"beans": 1000, "stamp": True, "redeem": None}
    assert Image.open(rewardcard.draw_clock_in({**shift, "order": paid})).height > plain


def test_every_fifth_stamp_pays_mega_boxes_up_to_the_top_goal(cafe):
    from brawl.Currency.config import STAMP_BOXES
    from brawl.Currency.db import u_mega_boxes

    assert stampcard.boxes(3, 4) == 0
    assert stampcard.boxes(4, 5) == STAMP_BOXES
    assert stampcard.boxes(44, 45) == STAMP_BOXES
    assert stampcard.boxes(45, 50) == 0
    u_stamp_card(USER).set({"count": 4})
    assert stampcard.add(USER) == STAMP_BOXES
    assert stampcard.add(USER) == 0
    assert stampcard.stamps(USER) == 6
    assert u_mega_boxes(USER).get() == STAMP_BOXES


def test_the_fifth_order_stamp_shows_its_boxes(order):
    from brawl.Currency.config import STAMP_BOXES

    u_stamp_card(USER).set({"count": 4})
    level(order, 1)
    do(order, brew_start=1, brew_sells=1)
    paid = do(order, chat_earnings=ORDER_CHAT_BEANS)
    assert paid.stamp and paid.boxes == STAMP_BOXES
    assert ("items/mega_box", STAMP_BOXES) in rewardcard.earned(
        {"beans": 1, "stamp": True, "boxes": paid.boxes}
    )

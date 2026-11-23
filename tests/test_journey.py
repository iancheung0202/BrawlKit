import asyncio
from unittest.mock import AsyncMock, MagicMock

from brawl.Currency import chat, daily, quests, stampcard
from brawl.Currency.config import STAMP_GOALS, TUTORIAL_BEANS, TUTORIAL_TOKENS
from brawl.Currency.db import (
    g_stamp_redemptions,
    u_balance,
    u_brews,
    u_quests,
    u_stamp_card,
    u_tutorial,
)
from brawl.Currency.helper import MAIN_GUILD_ID, get_current_month_key
from brawl.Currency.tutorial import BREW_STEP, CLOCK_IN, DONE, SELL_STEP
from tests.conftest import text

USER = 1
WORDS = "coffee beans brawl stars showdown trophies ranked gems skins maps".split()


def level(cafe, value):
    cafe.cogs["Leveling"] = MagicMock(level_of=AsyncMock(return_value=value), pool=None)


def press(cafe, cog, command, *args):
    interaction = cafe.interaction(USER)
    interaction.guild.premium_subscriber_role = None
    target = cafe.cogs[cog]
    asyncio.run(getattr(target, command).callback(target, interaction, *args))
    return interaction


def talk(cafe, monkeypatch, count):
    economy = cafe.cogs["CurrencySystem"]
    # Start early in the UTC day, so the chat never runs past the daily reset.
    clock = [chat.time.time() // 86400 * 86400 + 3600]
    monkeypatch.setattr(chat.time, "time", lambda: clock[0])
    for number in range(count):
        clock[0] += 6
        message = MagicMock(content=f"{WORDS[number % 10]} is number {number} today")
        message.author.id = USER
        message.author.bot = False
        message.author.roles = []
        message.guild.id = MAIN_GUILD_ID
        message.guild.premium_subscriber_role = None
        message.guild.get_role.return_value = None
        message.channel.send = AsyncMock()
        asyncio.run(economy.chat_system.process_message(message, economy))


def test_a_new_member_reaches_a_pass(cafe, monkeypatch):
    monkeypatch.setattr(
        quests, "generate_quests", lambda _, level=0: quests.generate_order(level)
    )
    monkeypatch.setattr(daily.random, "random", lambda: 1)
    economy = cafe.cogs["CurrencySystem"]
    level(cafe, 0)

    asyncio.run(economy.tutorial_manager.start(MagicMock(id=USER)))
    assert u_tutorial(USER).get() == BREW_STEP

    press(cafe, "Brewing", "brew", MagicMock(value="light"))
    assert u_tutorial(USER).get() == SELL_STEP
    press(cafe, "Brewing", "sell")
    assert u_tutorial(USER).get() == CLOCK_IN

    locked = press(cafe, "Brewing", "brew", MagicMock(value="light"))
    assert "Level 1" in text(locked.response.send_message.call_args)

    clock_in = cafe.interaction(USER)
    clock_in.guild.premium_subscriber_role = None
    asyncio.run(cafe.cogs["Daily"].process_daily(clock_in))
    assert u_tutorial(USER).get() == DONE
    assert u_balance(USER).get()["Tokens"] >= TUTORIAL_TOKENS
    assert u_balance(USER).get()["Beans"] >= TUTORIAL_BEANS
    assert set(u_quests(USER).child("daily/quests").get()) == {
        "chat_earnings",
        "daily_checkins",
    }
    level(cafe, 1)

    assert stampcard.stamps(USER) == 0
    talk(cafe, monkeypatch, 300)
    assert stampcard.stamps(USER) == 1

    u_stamp_card(USER).update({"count": STAMP_GOALS["brawl_pass"]})
    u_balance(USER).update({"Tokens": 400})
    choice = MagicMock(value="brawl_pass")
    choice.name = "Brawl Pass"
    press(cafe, "StampCard", "redeem", choice)
    assert stampcard.stamps(USER) == 0
    assert u_balance(USER).get()["Tokens"] == 0
    assert g_stamp_redemptions(MAIN_GUILD_ID, get_current_month_key()).get()


def test_a_drop_that_moves_the_order_is_sent_with_the_order_card(cafe, monkeypatch):
    monkeypatch.setattr(
        quests,
        "generate_quests",
        lambda _, level=0: {
            "thermometer_bonuses": {"current": 0, "goal": 1},
            "chat_earnings": {"current": 0, "goal": 1000},
        },
    )
    monkeypatch.setattr(chat.heat, "roll_tokens", lambda level: (5, False))
    monkeypatch.setattr(chat, "unlocked", AsyncMock(return_value=True))
    level(cafe, 7)
    economy = cafe.cogs["CurrencySystem"]
    message = MagicMock(content="coffee is the best thing about today")
    message.author.id = USER
    message.author.bot = False
    message.author.roles = []
    message.guild.id = MAIN_GUILD_ID
    message.guild.premium_subscriber_role = None
    message.guild.get_role.return_value = None
    message.channel.send = AsyncMock()
    asyncio.run(economy.chat_system.process_message(message, economy))
    sent = [call.kwargs for call in message.channel.send.call_args_list]
    # One picture a message, so Discord shows each in full.
    names = [kwargs["file"].filename for kwargs in sent]
    assert names == ["tokens.png", "order.png"]
    assert "thermometer_bonuses" in u_quests(USER).child("daily/completed").get()

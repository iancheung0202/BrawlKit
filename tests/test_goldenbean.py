import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from brawl.Currency import goldenbean, stationcard
from brawl.Currency.config import GOLDEN_BEAN_BEANS, GOLDEN_BEAN_HOLD_SECONDS
from brawl.Currency.db import u_balance
from brawl.Currency.helper import MAIN_CHAT_CHANNELS

A, B, C = 11, 12, 13
MAIN, OTHER = MAIN_CHAT_CHANNELS[0], MAIN_CHAT_CHANNELS[1]


def said(author, number, to=None, channel=MAIN):
    """A message; `to` is the member it replies to."""
    message = MagicMock(id=number, type=discord.MessageType.default, reference=None)
    message.author.id, message.channel.id = author, channel
    message.author.display_name = f"member{author}"
    message.author.display_avatar.replace.return_value.read = AsyncMock(
        return_value=None
    )
    message.channel.send = AsyncMock()
    if to:
        message.type = discord.MessageType.reply
        message.reference = MagicMock(resolved=MagicMock(spec=discord.Message))
        message.reference.resolved.author.id = to
    return message


def bean_of(cafe):
    bean = cafe.cogs["CurrencySystem"].bean
    reactions = []

    async def react(spot, add):
        if spot:
            reactions.append(("add" if add else "remove", spot[1]))

    bean.react = react
    return bean, reactions


def test_the_first_main_chat_message_takes_it(cafe):
    bean, _ = bean_of(cafe)
    assert not bean.offer(said(A, 1, channel=5))
    assert bean.offer(said(A, 2)) and bean.holder == A and bean.mark == (MAIN, 2)


def test_a_reply_to_any_message_of_the_holder_steals_it(cafe):
    bean, reactions = bean_of(cafe)
    bean.offer(said(A, 1))
    asyncio.run(bean.show())
    # The holder writes more, also elsewhere: the reaction stays where it is.
    assert not bean.offer(said(A, 2, channel=OTHER)) and bean.mark == (MAIN, 1)
    assert not bean.offer(said(B, 3)) and not bean.offer(said(A, 4, to=A))
    assert not bean.offer(said(B, 5, to=C)) and bean.holder == A
    assert bean.offer(said(B, 6, to=A, channel=OTHER))
    assert bean.holder == B and bean.mark == (OTHER, 6)
    asyncio.run(bean.show())
    assert reactions == [("add", 1), ("remove", 1), ("add", 6)]


def test_a_burst_of_steals_moves_the_reaction_once(cafe):
    bean, reactions = bean_of(cafe)
    bean.offer(said(A, 1))
    asyncio.run(bean.show())
    for number in range(2, 12):
        thief, victim = (B, A) if number % 2 == 0 else (A, B)
        assert bean.offer(said(thief, number, to=victim))
    asyncio.run(bean.show())
    asyncio.run(bean.show())
    assert reactions == [("add", 1), ("remove", 1), ("add", 11)]


def test_messages_delivered_out_of_order(cafe):
    bean, _ = bean_of(cafe)
    bean.offer(said(A, 1))
    # C's reply to B arrives before the reply that made B the holder.
    assert not bean.offer(said(C, 4, to=B))
    assert bean.offer(said(B, 3, to=A)) and bean.holder == C and bean.took == 4
    # A reply to C sent before C took it arrives late and changes nothing.
    assert not bean.offer(said(A, 2, to=C)) and bean.holder == C
    # A reply written long before its target took the bean does not count later.
    bean.offer(said(B, 5, to=A))
    assert bean.offer(said(A, 6, to=C)) and bean.holder == A


def test_a_deleted_message_or_a_member_leaving(cafe):
    bean, reactions = bean_of(cafe)
    bean.offer(said(A, 1))
    asyncio.run(bean.show())
    bean.deleted({1})
    assert bean.holder == A and bean.mark is None
    bean.offer(said(A, 2))
    asyncio.run(bean.show())
    assert bean.mark == (MAIN, 2) and reactions[-1] == ("add", 2)
    bean.left(B)
    assert bean.holder == A
    bean.left(A)
    asyncio.run(bean.show())
    assert bean.holder is None and reactions[-1] == ("remove", 2)
    assert bean.offer(said(B, 3)) and bean.holder == B


def test_it_survives_a_restart(cafe):
    cog = cafe.cogs["CurrencySystem"]
    bean, _ = bean_of(cafe)
    bean.offer(said(A, 1))
    asyncio.run(bean.show())
    bean.offer(said(B, 2, to=A))
    asyncio.run(bean.show())
    again = goldenbean.GoldenBean(cafe.bot, cog)
    assert (again.holder, again.took, again.mark, again.shown) == (
        B,
        2,
        (MAIN, 2),
        (MAIN, 2),
    )
    assert not again.offer(said(C, 1, to=B)) and again.offer(said(C, 3, to=B))


def test_only_the_holder_at_that_moment_is_paid(cafe, monkeypatch):
    bean, _ = bean_of(cafe)
    asyncio.run(bean.pay())
    bean.offer(said(A, 1))
    bean.offer(said(B, 2, to=A))
    asyncio.run(bean.pay())
    asyncio.run(bean.pay())
    assert u_balance(A).get() is None
    assert u_balance(B).get()["Beans"] == 2 * GOLDEN_BEAN_BEANS
    assert goldenbean.paid_today(B) == 2 * GOLDEN_BEAN_BEANS
    bean.since -= GOLDEN_BEAN_HOLD_SECONDS + 1
    asyncio.run(bean.pay())
    assert goldenbean.paid_today(B) == 2 * GOLDEN_BEAN_BEANS


def test_a_take_is_posted_the_first_time_and_in_a_cold_chat(cafe):
    cog = cafe.cogs["CurrencySystem"]
    bean, _ = bean_of(cafe)
    cog.thermometer_heat = 80
    first = said(A, 1)
    bean.offer(first)
    asyncio.run(bean.tell(first, False))
    assert first.channel.send.await_args.kwargs["file"].filename == "bean.png"
    again = said(A, 3, to=B)
    bean.offer(said(B, 2, to=A))
    bean.offer(again)
    asyncio.run(bean.tell(again, True))
    again.channel.send.assert_not_awaited()
    # Cold chat: posted, the strip before it removed, then quiet for a minute.
    cog.thermometer_heat, bean.told = 10, 0
    old = bean.notice
    asyncio.run(bean.tell(again, True))
    assert again.channel.send.await_count == 1 and old.delete.await_count == 1
    asyncio.run(bean.tell(again, True))
    assert again.channel.send.await_count == 1


def test_a_copied_reaction_is_removed(cafe):
    bean = cafe.cogs["CurrencySystem"].bean
    cafe.bot.user.id = 99
    message = cafe.bot.get_partial_messageable.return_value.get_partial_message
    message.return_value.remove_reaction = AsyncMock()
    fake = MagicMock(user_id=A, channel_id=MAIN, emoji=bean.emoji)
    asyncio.run(bean.fake(fake))
    asyncio.run(bean.fake(MagicMock(user_id=99, channel_id=MAIN, emoji=bean.emoji)))
    asyncio.run(bean.fake(MagicMock(user_id=A, channel_id=MAIN, emoji="x")))
    assert message.return_value.remove_reaction.await_count == 1


def test_cards_draw_with_and_without_a_holder():
    level = stationcard.THERMOMETER_LEVELS[1]
    holder = {"name": "Sam", "avatar": None}
    for bean in (None, holder):
        assert stationcard.draw_heat({"level": level, "rose": True, "bean": bean})
        cup = {"background": "gym", "heat": 80, "drops": 1, "bean": bean}
        assert stationcard.draw_thermometer(cup)
    assert stationcard.draw_stolen({**holder, "stolen": True})

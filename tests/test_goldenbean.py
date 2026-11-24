import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from brawl.Currency import goldenbean
from brawl.Currency.db import u_mega_boxes
from brawl.Currency.helper import MAIN_CHAT_CHANNELS

A, B, C = 11, 12, 13
MAIN, OTHER = MAIN_CHAT_CHANNELS[0], MAIN_CHAT_CHANNELS[1]
DAY = "2026-12-01"


def said(author, number, to=None, channel=MAIN, words="here is a real message"):
    """A message; `to` is the member it replies to."""
    message = MagicMock(id=number, type=discord.MessageType.default, reference=None)
    message.content = f"{words} {number}"
    message.author.id, message.channel.id = author, channel
    message.author.display_name = f"member{author}"
    message.author.display_avatar.replace.return_value.read = AsyncMock(
        return_value=None
    )
    message.channel.send = AsyncMock()
    message.guild = True
    message.author.bot = False
    if to:
        message.type = discord.MessageType.reply
        message.reference = MagicMock(resolved=MagicMock(spec=discord.Message))
        message.reference.resolved.author.id = to
    return message


@pytest.fixture
def clock(monkeypatch):
    at = [1_800_000_000]
    monkeypatch.setattr(goldenbean, "now", lambda: at[0])
    monkeypatch.setattr(goldenbean, "today", lambda: DAY)
    return at


@pytest.fixture
def event(cafe, clock):
    cafe.bot.get_channel.return_value.send = AsyncMock()
    cafe.bot.get_channel.return_value.id = MAIN
    cafe.bot.get_channel.return_value.send.return_value.channel.id = MAIN
    cafe.bot.get_guild.return_value = None
    return start(cafe)


def start(cafe):
    bean = goldenbean.GoldenBean(cafe.bot)
    bean.reactions = []

    async def react(spot, add):
        if spot:
            bean.reactions.append(("add" if add else "remove", spot[1]))

    bean.react = react
    return bean


def posts(cafe):
    return cafe.bot.get_channel.return_value.send


def test_the_first_main_chat_message_takes_it(event):
    assert not event.offer(said(A, 1, channel=5))
    assert not event.offer(said(A, 2, words="k"))
    assert event.offer(said(A, 3)) and event.holder == A and event.mark == (MAIN, 3)


def test_a_reply_to_any_message_of_the_holder_steals_it(event):
    event.offer(said(A, 1))
    asyncio.run(event.show())
    # The holder writes more, also elsewhere: the reaction stays where it is.
    assert not event.offer(said(A, 2, channel=OTHER)) and event.mark == (MAIN, 1)
    assert not event.offer(said(B, 3)) and not event.offer(said(A, 4, to=A))
    assert not event.offer(said(B, 5, to=C)) and event.holder == A
    assert not event.offer(said(B, 6, to=A, words="k"))
    assert event.offer(said(B, 7, to=A, channel=OTHER))
    assert event.holder == B and event.mark == (OTHER, 7)
    asyncio.run(event.show())
    assert event.reactions == [("add", 1), ("remove", 1), ("add", 7)]


def test_a_burst_of_steals_moves_the_reaction_once(event):
    event.offer(said(A, 1))
    asyncio.run(event.show())
    for number in range(2, 12):
        thief, victim = (B, A) if number % 2 == 0 else (A, B)
        assert event.offer(said(thief, number, to=victim))
    asyncio.run(event.show())
    asyncio.run(event.show())
    assert event.reactions == [("add", 1), ("remove", 1), ("add", 11)]


def test_messages_delivered_out_of_order(event):
    event.offer(said(A, 1))
    # C's reply to B arrives before the reply that made B the holder.
    assert not event.offer(said(C, 4, to=B))
    assert event.offer(said(B, 3, to=A)) and event.holder == C and event.took == 4
    # A reply to C sent before C took it arrives late and changes nothing.
    assert not event.offer(said(A, 2, to=C)) and event.holder == C


def test_held_seconds_add_up_and_a_full_minute_is_a_ticket(event, clock):
    event.offer(said(A, 1))
    clock[0] += 40
    event.offer(said(B, 2, to=A))
    clock[0] += 59
    assert (event.tickets(A), event.tickets(B)) == (0, 0)
    event.offer(said(A, 3, to=B))
    clock[0] += 20  # 40 seconds before, 20 now: A's first full minute
    assert (event.tickets(A), event.tickets(B)) == (1, 0)
    event.offer(said(B, 4, to=A))
    clock[0] += 61
    assert (event.tickets(A), event.tickets(B)) == (1, 2)
    assert asyncio.run(event.counted()) == {A: 1, B: 2}


def test_a_low_level_member_holds_it_but_earns_nothing(cafe, event, clock):
    cafe.cogs["Leveling"].level_of.return_value = goldenbean.MIN_LEVEL - 1
    first = said(A, 1)
    event.offer(first)
    asyncio.run(event.tell(first, False))
    clock[0] += 300
    assert asyncio.run(event.counted()) == {} and u_mega_boxes(A).get() is None
    cafe.cogs["Leveling"].level_of.return_value = goldenbean.MIN_LEVEL
    assert asyncio.run(event.counted()) == {A: 5}


def test_a_hold_ends_after_half_an_hour_and_someone_else_picks_it_up(
    cafe, event, clock
):
    event.offer(said(A, 1))
    asyncio.run(event.show())
    clock[0] += goldenbean.HOLD_SECONDS + 1
    asyncio.run(event.minute())
    asyncio.run(event.show())
    assert event.holder is None
    assert event.tickets(A) == goldenbean.HOLD_SECONDS // 60  # and no more
    assert event.reactions[-1] == ("remove", 1)
    asyncio.run(event.minute())
    asyncio.run(event.minute())
    assert posts(cafe).await_count == 1  # the floor strip, once
    assert not event.offer(said(A, 2))  # whoever let it fall cannot pick it up
    taker = said(B, 3)
    assert event.offer(taker)
    asyncio.run(event.tell(taker, False))
    posts(cafe).return_value.delete.assert_awaited_once()  # right above it
    assert event.offer(said(A, 4, to=B))


def test_the_first_take_of_the_day_pays_a_mega_box_and_is_posted(event):
    first = said(A, 1)
    event.offer(first)
    asyncio.run(event.tell(first, False))
    assert u_mega_boxes(A).get() == goldenbean.FIRST_TAKE_BOXES
    assert first.channel.send.await_args.kwargs["file"].filename == "bean.png"
    event.offer(said(B, 2, to=A))
    again = said(A, 3, to=B)
    event.offer(again)
    asyncio.run(event.tell(again, True))
    assert u_mega_boxes(A).get() == goldenbean.FIRST_TAKE_BOXES
    again.channel.send.assert_not_awaited()


def fall(event, clock):
    clock[0] += goldenbean.HOLD_SECONDS + 1
    asyncio.run(event.minute())
    asyncio.run(event.minute())
    return event.strip


def test_a_strip_further_up_the_chat_stays(event, clock):
    event.offer(said(A, 1))
    floor = fall(event, clock)
    asyncio.run(event.on_message(said(C, 2, to=B, words="k")))  # chat goes on
    asyncio.run(event.on_message(said(B, 3)))
    assert event.holder == B and event.strip is not floor
    floor.delete.assert_not_awaited()


def test_a_strip_right_above_the_new_one_goes(event, clock):
    event.offer(said(A, 1))
    floor = fall(event, clock)
    asyncio.run(event.on_message(said(B, 2)))  # only the message that took it
    floor.delete.assert_awaited_once()
    # In another channel the old strip is not above the new one.
    taken = event.strip
    taken.channel.id = MAIN
    fall(event, clock)
    asyncio.run(event.on_message(said(C, 3, channel=OTHER)))
    assert event.holder == C and taken.delete.await_count == 1


def test_news_posts_are_never_taken_down(cafe, event, clock, monkeypatch):
    event.offer(said(A, 1))
    clock[0] += 120
    monkeypatch.setattr(goldenbean, "today", lambda: "2026-12-02")
    asyncio.run(event.minute())
    clock[0] += goldenbean.DAYS * 86400
    asyncio.run(event.minute())
    assert posts(cafe).await_count == 2 and event.strip is None
    posts(cafe).return_value.delete.assert_not_awaited()


def test_it_survives_a_restart(cafe, event, clock):
    event.offer(said(A, 1))
    clock[0] += 90
    event.offer(said(B, 2, to=A))
    asyncio.run(event.show())
    again = start(cafe)
    assert (again.holder, again.took, again.mark, again.shown) == (
        B,
        2,
        (MAIN, 2),
        (MAIN, 2),
    )
    assert again.tickets(A) == 1 and again.starts == event.starts
    assert not again.offer(said(C, 1, to=B)) and again.offer(said(C, 3, to=B))


def test_a_new_day_posts_the_board(cafe, event, monkeypatch):
    event.seconds = {A: 1800, B: 720}
    monkeypatch.setattr(goldenbean, "today", lambda: "2026-12-02")
    asyncio.run(event.minute())
    asyncio.run(event.minute())
    board = [call for call in posts(cafe).await_args_list if "content" not in call[1]]
    assert len(board) == 2  # the board, then the floor strip
    channels = [call.args[0] for call in cafe.bot.get_channel.call_args_list]
    assert channels == [goldenbean.NEWS_CHANNEL, MAIN]


def test_the_draw_picks_one_ticket_and_ends_the_event(cafe, event, clock):
    event.offer(said(A, 1))
    clock[0] += goldenbean.DAYS * 86400
    asyncio.run(event.minute())
    assert event.winner == A and event.holder is None and not event.running
    assert posts(cafe).await_args.kwargs["content"] == f"<@{A}>"
    cafe.bot.get_channel.assert_called_with(goldenbean.NEWS_CHANNEL)
    asyncio.run(event.minute())
    assert posts(cafe).await_count == 1
    assert not event.offer(said(B, 2))
    assert start(cafe).winner == A


def test_nobody_played(cafe, event, clock):
    clock[0] += goldenbean.DAYS * 86400
    asyncio.run(event.minute())
    assert event.winner == 0 and posts(cafe).await_count == 0


def test_a_deleted_message_or_a_member_leaving(event):
    event.offer(said(A, 1))
    asyncio.run(event.show())
    event.deleted({1})
    assert event.holder == A and event.mark is None
    event.offer(said(A, 2))
    asyncio.run(event.show())
    assert event.mark == (MAIN, 2) and event.reactions[-1] == ("add", 2)
    asyncio.run(event.on_member_remove(MagicMock(id=A)))
    asyncio.run(event.show())
    assert event.holder is None and event.reactions[-1] == ("remove", 2)
    assert event.offer(said(B, 3)) and event.holder == B


def test_a_copied_reaction_is_removed(cafe, event):
    cafe.bot.user.id = 99
    message = cafe.bot.get_partial_messageable.return_value.get_partial_message
    message.return_value.remove_reaction = AsyncMock()
    for user, emoji in ((A, event.emoji), (99, event.emoji), (A, "x")):
        payload = MagicMock(user_id=user, channel_id=MAIN, emoji=emoji)
        asyncio.run(event.on_raw_reaction_add(payload))
    assert message.return_value.remove_reaction.await_count == 1


def test_cards_draw():
    take = {"name": "Sam", "avatar": None, "stolen": True, "boxes": 1, "tickets": 4}
    assert goldenbean.draw_taken(take)
    assert goldenbean.draw_taken({**take, "boxes": 0, "stolen": False})
    assert goldenbean.draw_floor(None)
    rows = [("Sam", 40, None), ("Kit", 12, None)]
    assert goldenbean.draw_board({"rows": rows, "players": 2, "ends": "Draw in 3 days"})
    win = {"name": "Sam", "avatar": None, "tickets": 40, "total": 52}
    assert goldenbean.draw_winner(win)

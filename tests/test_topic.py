import asyncio
from unittest.mock import AsyncMock, MagicMock

from brawl.Currency import wallet
from brawl.Currency.config import TOPIC_BEANS
from brawl.Utility import topic
from tests.conftest import text

MEMBER, STAFF, REVIEW = 1, 2, 55


def send_in(cafe, question="Which brawler would run the best cafe?", rested=True):
    if rested:
        cafe.ref(topic.SENT).delete()
    interaction = cafe.interaction(MEMBER)
    interaction.guild.get_channel.return_value.send = AsyncMock(
        return_value=MagicMock(id=REVIEW)
    )

    async def run():
        modal = topic.AddModal()
        modal.text._value = question
        await modal.on_submit(interaction)

    asyncio.run(run())
    return interaction


def staff(cafe):
    interaction = cafe.interaction(STAFF)
    interaction.message.id = REVIEW
    interaction.message.embeds = [MagicMock(description="Topic sent in")]
    interaction.guild.get_member.return_value.send = AsyncMock()
    return interaction


def review(cafe, approved):
    interaction = staff(cafe)

    async def run():
        await topic.ReviewView().settle(interaction, approved)

    asyncio.run(run())
    return interaction.guild.get_member.return_value.send


def edit(cafe, wording):
    interaction = staff(cafe)

    async def run():
        modal = topic.EditModal("old")
        modal.text._value = wording
        await modal.on_submit(interaction)

    asyncio.run(run())
    return interaction


def test_one_suggestion_waits_at_a_time(cafe):
    send_in(cafe)
    refused = send_in(cafe).response.send_message.call_args
    assert "still looking" in text(refused) and len(cafe.ref(topic.PENDING).get()) == 1


def test_approved_topic_pays_and_is_drawn_with_its_author(cafe, monkeypatch):
    send_in(cafe)
    assert wallet.balance(MEMBER)[0] == 0
    review(cafe, True)
    assert (
        wallet.balance(MEMBER)[0] == TOPIC_BEANS and not cafe.ref(topic.PENDING).get()
    )
    monkeypatch.setattr(topic.random, "randrange", lambda count: count - 1)
    embed = topic.topic_embed()
    assert (
        embed.title.startswith("Which brawler") and f"<@{MEMBER}>" in embed.description
    )
    review(cafe, True)
    assert wallet.balance(MEMBER)[0] == TOPIC_BEANS


def test_turned_down_topic_pays_nothing(cafe):
    send_in(cafe)
    review(cafe, False)
    assert wallet.balance(MEMBER)[0] == 0
    assert not cafe.ref(topic.APPROVED).get() and not cafe.ref(topic.PENDING).get()


def test_staff_edit_changes_what_is_approved(cafe, monkeypatch):
    send_in(cafe)
    edited = edit(cafe, "Which brawler makes the best coffee?")
    assert edited.message.embeds[0].title == "Which brawler makes the best coffee?"
    review(cafe, True)
    monkeypatch.setattr(topic.random, "randrange", lambda count: count - 1)
    assert topic.topic_embed().title == "Which brawler makes the best coffee?"


def test_member_is_sent_a_card_either_way_and_closed_dms_are_skipped(cafe, monkeypatch):
    send_in(cafe)
    assert review(cafe, True).call_args.kwargs["file"].filename == "topic.jpg"
    send_in(cafe)
    assert review(cafe, False).call_count == 1
    send_in(cafe)
    closed = topic.discord.HTTPException(MagicMock(status=403), "closed")
    interaction = staff(cafe)
    interaction.guild.get_member.return_value.send = AsyncMock(side_effect=closed)

    async def run():
        await topic.ReviewView().settle(interaction, True)

    asyncio.run(run())
    assert wallet.balance(MEMBER)[0] == 2 * TOPIC_BEANS


def test_member_the_bot_has_not_seen_is_fetched_for_the_card(cafe):
    send_in(cafe)
    interaction = staff(cafe)
    interaction.guild.get_member.return_value = None
    interaction.guild.fetch_member = AsyncMock()

    async def run():
        await topic.ReviewView().settle(interaction, True)

    asyncio.run(run())
    interaction.guild.fetch_member.assert_awaited_once_with(MEMBER)
    assert interaction.guild.fetch_member.return_value.send.call_count == 1


def test_review_shows_how_many_topics_the_member_had_approved(cafe, monkeypatch):
    now = 1_800_000_000

    def key(age):
        stamp, out = int((now - age) * 1000), ""
        for _ in range(8):
            stamp, out = stamp // 64, topic.PUSH[stamp % 64] + out
        return out + "abcdefghijkl"

    monkeypatch.setattr(topic.time, "time", lambda: now)
    for age in (3600, 3 * 86400, 20 * 86400, 90 * 86400):
        cafe.ref(topic.APPROVED).child(key(age)).set({"user": MEMBER, "text": "x"})
    cafe.ref(topic.APPROVED).child(key(60)).set({"user": STAFF, "text": "x"})
    embed = send_in(cafe).guild.get_channel.return_value.send.call_args.kwargs["embed"]
    assert "4 approved topics all-time" in embed.description
    assert [(field.name, field.value) for field in embed.fields] == [
        ("Last 30 days", "`3` approved"),
        ("Last 7 days", "`2` approved"),
        ("Last 24 hours", "`1` approved"),
    ]


def test_one_suggestion_an_hour_whatever_staff_decided(cafe, monkeypatch):
    now = [1_800_000_000]
    monkeypatch.setattr(topic.time, "time", lambda: now[0])
    send_in(cafe)
    review(cafe, False)
    now[0] += topic.COOLDOWN - 5
    refused = send_in(cafe, rested=False).response.send_message.call_args
    assert "one topic an hour" in text(refused) and not cafe.ref(topic.PENDING).get()
    now[0] += 5
    send_in(cafe, rested=False)
    assert len(cafe.ref(topic.PENDING).get()) == 1


def test_review_lists_the_topics_devin_finds_similar(cafe, monkeypatch):
    monkeypatch.setattr(topic.topicmatch, "ready", lambda: True)
    close = [("What's your favorite map to play on?", "Same question")]
    monkeypatch.setattr(topic.topicmatch, "similar", AsyncMock(return_value=close))
    embed = topic.review_embed(MagicMock(id=MEMBER), "Best map?")
    assert embed.fields[-1].value == "-# Checking"
    message = MagicMock()
    message.channel.fetch_message = AsyncMock(return_value=message)
    message.embeds, message.edit = [embed], AsyncMock()
    asyncio.run(topic.check(message, "Best map?"))
    shown = message.edit.call_args.kwargs["embed"].fields[-1].value
    assert shown == "1. What's your favorite map to play on?\n-# Same question"
    asked = topic.topicmatch.similar.call_args.args[1]
    assert asked[: len(topic.ICEBREAKERS)] == topic.ICEBREAKERS
    down = AsyncMock(side_effect=topic.topicmatch.Unavailable("down"))
    monkeypatch.setattr(topic.topicmatch, "similar", down)
    asyncio.run(topic.check(message, "Best map?"))
    assert message.edit.call_args.kwargs["embed"].fields[-1].value == (
        "-# Check unavailable"
    )
    assert topic.close_lines([]) == "-# None found"


def test_the_answer_is_read_from_devins_reply_to_this_question():
    from brawl.Utility import topicmatch

    topics = ["Best map?", "Best brawler?"]
    reply = '{"id": "ab12", "similar": [{"n": 2, "why": "same"}, {"n": 9}]}'
    messages = [
        {"source": "user", "message": reply.replace("2,", "1,")},
        {"source": "devin", "message": '{"id": "old", "similar": [{"n": 1}]}'},
        {"source": "devin", "message": "Here: " + reply},
    ]
    assert topicmatch.answer(messages, "ab12", topics) == [("Best brawler?", "same")]
    assert topicmatch.answer(messages[:2], "ab12", topics) is None
    assert "2. Best brawler?" in topicmatch.question("x", topics, "ab12")

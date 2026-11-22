import asyncio
from unittest.mock import AsyncMock, MagicMock

from brawl.Currency import wallet
from brawl.Currency.config import TOPIC_BEANS
from brawl.Utility import topic
from tests.conftest import text

MEMBER, STAFF, REVIEW = 1, 2, 55


def send_in(cafe, question="Which brawler would run the best cafe?"):
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

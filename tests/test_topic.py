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


def review(cafe, approved):
    interaction = cafe.interaction(STAFF)
    interaction.message.id = REVIEW
    interaction.message.embeds = [MagicMock(description="Topic sent in")]

    async def run():
        await topic.ReviewView().settle(interaction, approved)

    asyncio.run(run())


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

import asyncio
import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

from brawl.Currency import card, how
from brawl.Currency.howcard import PAGES


@pytest.mark.parametrize("topic", PAGES)
def test_every_page_draws_without_cutting_text(topic, monkeypatch):
    cut = []
    fit = card.Card.fit

    def watched(self, text, size, width):
        fitted = fit(self, text, size, width)
        if fitted != text:
            cut.append(text)
        return fitted

    monkeypatch.setattr(card.Card, "fit", watched)
    draw = PAGES[topic][1]
    getattr(draw, "cache_clear", lambda: None)()
    image = Image.open(io.BytesIO(draw()))
    assert image.width == 1800
    assert not cut


def ask(cafe, topic=None):
    cog = how.How(cafe.bot)
    sent = cafe.interaction()
    choice = MagicMock(value=topic) if topic else None
    asyncio.run(cog.how.callback(cog, sent, choice))
    return sent.response.send_message.call_args.kwargs


def test_how_opens_on_the_start_page_in_private(cafe):
    sent = ask(cafe)
    assert sent["file"].filename == "start.jpg"
    assert sent["ephemeral"] is True
    assert "embed" not in sent


def test_how_opens_the_topic_asked_for(cafe):
    assert ask(cafe, "rates")["file"].filename == "rates.jpg"


def test_the_menu_swaps_the_page_in_place(cafe):
    async def pick():
        menu = how.HowView().children[0]
        menu._values = ["brewing"]
        sent = cafe.interaction()
        await menu.callback(sent)
        return sent.response.edit_message.call_args.kwargs

    swapped = asyncio.run(pick())
    assert swapped["attachments"][0].filename == "brewing.jpg"
    assert swapped["view"].children[0].options[4].default

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock

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


def test_how_opens_on_the_start_page_for_everyone_to_see(cafe):
    sent = ask(cafe)
    assert sent["file"].filename == "start.jpg"
    assert "ephemeral" not in sent
    assert "embed" not in sent


def test_how_opens_the_topic_asked_for(cafe):
    assert ask(cafe, "rates")["file"].filename == "rates.jpg"


def test_the_menu_swaps_the_page_in_place(cafe):
    async def pick():
        menu = how.HowView().children[0]
        menu._values = ["brewing"]
        sent = cafe.interaction()
        sent.message.interaction_metadata.user.id = sent.user.id
        await menu.callback(sent)
        return sent.response.edit_message.call_args.kwargs

    swapped = asyncio.run(pick())
    assert swapped["attachments"][0].filename == "brewing.jpg"
    assert swapped["view"].children[0].options[4].default


def test_the_menu_only_works_for_the_member_who_asked(cafe):
    async def pick():
        menu = how.HowView().children[0]
        menu._values = ["brewing"]
        sent = cafe.interaction(2)
        sent.message.interaction_metadata.user.id = 1
        await menu.callback(sent)
        return sent

    sent = asyncio.run(pick())
    sent.response.edit_message.assert_not_called()
    assert sent.response.send_message.call_args.kwargs["ephemeral"] is True


def test_the_level_up_info_button_opens_the_levels_page():
    from brawl.Currency.levels import LevelRewardInfoView

    async def press():
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()
        view = LevelRewardInfoView()
        await view.level_info.callback(interaction)
        return interaction.response.send_message.call_args.kwargs

    sent = asyncio.run(press())
    assert sent["file"].filename == "levels.jpg" and sent["ephemeral"]


def test_the_chat_strip_draws_plain_boosted_and_full():
    from brawl.Currency.rewardcard import draw_chat

    for beans, today, boosted in ((123, 123, False), (603, 6000, True)):
        reward = {
            "name": "A member with a very long display name",
            "avatar": None,
            "beans": beans,
            "boosted": boosted,
            "today": today,
            "limit": 6000,
            "reset": 0,
        }
        assert draw_chat(reward).getvalue().startswith(b"\x89PNG")


def test_the_daily_panel_button_opens_how_privately():
    from brawl.Currency.daily import Daily

    async def press():
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()
        view = Daily.DailyPanelView(MagicMock())
        await view.how.callback(interaction)
        return interaction.response.send_message.call_args.kwargs

    sent = asyncio.run(press())
    assert sent["file"].filename == "start.jpg" and sent["ephemeral"]

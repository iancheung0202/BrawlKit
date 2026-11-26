import asyncio
from unittest.mock import AsyncMock, MagicMock

from brawl.Currency.helper import FREEBIES
from brawl.Utility import freebie
from tests.conftest import text


def post(cafe, link, image=None):
    interaction = cafe.interaction(2)
    channel = interaction.guild.get_channel.return_value
    channel.send = AsyncMock()
    channel.send.return_value.publish = AsyncMock()

    async def run():
        cog = freebie.Freebie(cafe.bot)
        await cog.freebie.callback(
            cog, interaction, "Brawl Stars", "1x Thunder Frogs Box", link, image
        )

    asyncio.run(run())
    return interaction, channel


def test_a_freebie_posts_one_message_with_ping_and_claim_button(cafe):
    interaction, channel = post(cafe, "https://link.brawlstars.com/voucher/abc")
    channel_id, role = FREEBIES["Brawl Stars"]
    interaction.guild.get_channel.assert_called_with(channel_id)
    sent = channel.send.call_args.kwargs
    assert sent["content"] == f"<@&{role}>" and channel.send.await_count == 1
    assert sent["embed"].title == "1x Thunder Frogs Box"
    button, code = sent["view"].children
    assert button.label == "Claim" and button.url.endswith("/voucher/abc")
    assert code.label == "Show QR Code" and code.custom_id == "freebie_qr"
    channel.send.return_value.publish.assert_awaited_once()
    assert "Posted" in text(interaction.followup.send.call_args)


def test_a_freebie_shows_its_picture(cafe):
    image = MagicMock(filename="box.png", to_file=AsyncMock(return_value="file"))
    _, channel = post(cafe, "https://store.supercell.com/brawlstars", image)
    sent = channel.send.call_args.kwargs
    assert sent["files"] == ["file"]
    assert sent["embed"].image.url == "attachment://box.png"


def test_a_bad_link_is_refused(cafe):
    interaction, channel = post(cafe, "link.brawlstars.com/voucher/abc")
    assert not channel.send.called
    assert "https://" in text(interaction.response.send_message.call_args)


def press(cafe, links):
    interaction = cafe.interaction(3)
    row = MagicMock(children=[MagicMock(url=link) for link in links])
    interaction.message.components = [row]

    async def run():
        await freebie.ClaimView().show.callback(interaction)

    asyncio.run(run())
    return interaction.response.send_message.call_args.kwargs


def test_the_qr_code_is_made_from_the_claim_link_and_shown_privately(cafe):
    link = "https://link.brawlstars.com/voucher/abc"
    shown = press(cafe, [link, None])
    assert shown["ephemeral"] and shown["file"].filename == "qr.png"
    assert shown["file"].fp.read() == freebie.code(link)
    assert freebie.code(link)[:4] == b"\x89PNG"
    assert freebie.code(link) != freebie.code(link + "d")


def test_a_post_without_a_link_gives_no_qr_code(cafe):
    shown = press(cafe, [None])
    assert shown["ephemeral"] and "file" not in shown

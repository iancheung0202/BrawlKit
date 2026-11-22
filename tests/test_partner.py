import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from brawl.Partnership import partnershipSystem as partner
from tests.conftest import Ref

GUILD = 7


def database(data=None):
    tree = {}
    Ref(tree, "Partner").set(data or {})
    return patch.object(partner.db, "reference", lambda path: Ref(tree, path))


def interaction():
    interaction = MagicMock()
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.guild.id = GUILD
    interaction.guild.get_channel.return_value = None
    interaction.client.get_channel.return_value = None
    return interaction


def run(command, *args, **kwargs):
    sent = interaction()
    asyncio.run(command.callback(partner.Partner(None), sent, *args, **kwargs))
    return sent


def servers(*names):
    return [{"name": name, "invite": name.lower()} for name in names]


def test_every_partner_is_listed_in_name_order():
    names = ["zeta", "1up", "Alpha", "mango", "Mint"]
    embed = partner.group_embeds("games", {"prefix": "-"}, servers(*names))[0]
    assert embed.title == "games"
    assert embed.fields[0].name == "A - Z"
    assert embed.fields[0].value.split("\n") == [
        "- [1up](https://discord.gg/1up) ",
        "- [Alpha](https://discord.gg/alpha) ",
        "- [mango](https://discord.gg/mango) ",
        "- [Mint](https://discord.gg/mint) ",
        "- [zeta](https://discord.gg/zeta) ",
    ]


def test_long_groups_split_into_fields_without_losing_partners():
    names = [f"{letter}{number:03}" for letter in "ABM" for number in range(40)]
    embeds = partner.group_embeds("games", {}, servers(*names))
    fields = [field for embed in embeds for field in embed.fields]
    assert all(len(field.value) <= 1024 for field in fields)
    assert sum(field.value.count("\n") + 1 for field in fields) == len(names)
    assert fields[0].name.startswith("A - ") and fields[-1].name.endswith(" - Z")


def test_bot_partners_link_to_the_authorize_page():
    assert partner.link({"invite": "123"}).endswith("authorize?client_id=123")


def test_bad_colors_fall_back_to_blurple():
    assert partner.to_color("#ff0000") == 0xFF0000
    assert partner.to_color("red") == 0x5865F2
    assert partner.to_color(None) == 0x5865F2


def test_panel_has_header_groups_and_footer():
    data = {
        "config": {GUILD: {"embed": {"header": {"title": "Our partners"}}}},
        "categories": {GUILD: {"games": {"title": "Games"}, "empty": {"title": "E"}}},
        "partners": {
            GUILD: {"a": {"name": "Alpha", "invite": "x", "category": "games"}}
        },
    }
    with database(data):
        embeds = partner.panel_embeds(GUILD)
    assert [embed.title for embed in embeds] == [
        "Our partners",
        "Games",
        "Instructions",
    ]


def test_groups_are_added_once():
    with database():
        first = run(partner.Partner.add_group, "Games", title="🎮 Games")
        assert "created" in first.response.send_message.call_args[0][0]
        second = run(partner.Partner.add_group, "games")
        assert "already exists" in second.response.send_message.call_args[0][0]
        bad = run(partner.Partner.add_group, "two words")
        assert "can only contain" in bad.response.send_message.call_args[0][0]
        assert partner.ref("categories", GUILD).get()["Games"]["title"] == "🎮 Games"


def test_partner_is_removed_by_name_or_invite():
    data = {
        "partners": {
            GUILD: {
                "a": {"name": "Alpha", "invite": "aaa", "category": "games"},
                "b": {"name": "Beta", "invite": "bbb", "category": "games"},
            }
        }
    }
    with database(data):
        missing = run(partner.Partner.remove_partner, server_name="Alpha", invite="bbb")
        assert "not found" in missing.response.send_message.call_args[0][0]
        run(partner.Partner.remove_partner, invite="https://discord.gg/bbb")
        run(partner.Partner.remove_partner, server_name="alpha")
        assert partner.ref("partners", GUILD).get() is None


def test_renaming_a_group_moves_its_partners():
    data = {
        "categories": {GUILD: {"old": {"title": "Old", "created_at": 5}}},
        "partners": {GUILD: {"a": {"name": "Alpha", "invite": "x", "category": "old"}}},
    }
    with database(data):

        async def submit():
            modal = partner.GroupModal("old", {"title": "Old"})
            modal.name._value = "new"
            modal.heading._value = ""
            modal.color._value = ""
            modal.affixes._value = "•, !"
            modal.thumbnail._value = ""
            await modal.on_submit(interaction())

        asyncio.run(submit())
        assert partner.ref("categories", GUILD).get() == {
            "new": {
                "title": "new",
                "created_at": 5,
                "color": partner.COLOR,
                "prefix": "•",
                "suffix": "!",
            }
        }
        assert partner.ref("partners", GUILD).get()["a"]["category"] == "new"


def test_request_respects_cooldown_and_blacklist():
    invite = {"guild": {"id": "55", "name": "Them", "icon": None}}
    data = {
        "config": {GUILD: {"request_channel": 1, "user_cooldown": 3600}},
        "Blacklist": {GUILD: {"55": True}},
    }
    with database(data), patch.object(
        partner, "get_invite", AsyncMock(return_value=("code", invite))
    ):

        async def submit(sent):
            modal = partner.RequestModal()
            modal.invite_link._value = "https://discord.gg/code"
            await modal.on_submit(sent)

        sent = interaction()
        sent.user.id = 9
        asyncio.run(submit(sent))
        assert "blacklisted" in sent.followup.send.call_args[0][0]
        partner.ref("Cooldown", GUILD).child("9").set(partner.now() - 90)
        asyncio.run(submit(sent))
        assert "cooldown! Try again in 0h 58m" in sent.followup.send.call_args[0][0]


def test_thread_is_opened_once_per_server():
    invite = {"guild": {"id": "55", "name": "Them", "icon": "abc"}, "expires_at": None}
    config = {"request_channel": 1, "partner_manager_role_id": "77"}
    sent = interaction()
    sent.user.id, sent.user.mention = 9, "<@9>"
    channel = MagicMock()
    channel.threads = []
    channel.create_thread = AsyncMock()
    thread = channel.create_thread.return_value
    thread.mention, thread.jump_url = "<#3>", "https://discord.com/channels/7/3"

    async def archived():
        return
        yield

    channel.archived_threads = archived
    sent.guild.get_channel.side_effect = lambda id: channel if id == 1 else None
    with database({"config": {GUILD: config}}), patch.object(
        partner, "get_invite", AsyncMock(return_value=("code", invite))
    ):
        reply = asyncio.run(partner.open_thread(sent, "discord.gg/code", staff=False))
        assert reply == f"{partner.YES} Request created in <#3>"
        assert partner.ref("Cooldown", GUILD).child("9").get() > 0
    assert channel.create_thread.call_args.kwargs["name"] == "🟡 Them"
    content = thread.send.call_args[0][0]
    embed = thread.send.call_args.kwargs["embed"]
    assert content == "<@&77> discord.gg/code"
    assert [field.name for field in embed.fields][-2:] == [
        "Requester ID",
        "Requester Mention",
    ]
    thread.add_user.assert_awaited_once_with(sent.user)
    message = MagicMock()
    message.author.id = sent.client.user.id
    message.embeds = [embed]

    async def history(**kwargs):
        yield message

    thread.history = history
    channel.threads = [thread]
    with database({"config": {GUILD: config}}), patch.object(
        partner, "get_invite", AsyncMock(return_value=("code", invite))
    ):
        reply = asyncio.run(partner.open_thread(sent, "discord.gg/code", staff=True))
    assert "already exists: <#3>" in reply

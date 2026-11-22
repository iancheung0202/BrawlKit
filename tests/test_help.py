import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord

from brawl.Help.help import (
    PAGES,
    STAFF,
    HelpPanel,
    PageSelect,
    entries,
    mention,
    page_embeds,
)

SUB = discord.AppCommandOptionType.subcommand
TEXT = discord.AppCommandOptionType.string


def command(name, id, *options):
    return SimpleNamespace(
        name=name, id=id, description=f"About {name}", options=list(options)
    )


def option(name, type=SUB):
    return SimpleNamespace(name=name, type=type, description=f"About {name}")


FOUND = {
    "brew": command("brew", 1, option("roast", TEXT)),
    "table": command("table", 2, option("seat"), option("leave")),
    "add": command("add", 3),
    "ticket": command("ticket", 4, option("settings"), option("button")),
}


def test_mention_links_known_commands_and_names_unknown_ones():
    assert mention(FOUND, "table seat") == "</table seat:2>"
    assert mention(FOUND, "sell") == "`/sell`"


def test_entries_list_a_command_a_whole_group_or_one_subcommand():
    assert entries(FOUND, ["brew"]).startswith("</brew:1>\n")
    assert "roast" not in entries(FOUND, ["brew"])
    assert entries(FOUND, ["table"]).count("</table") == 2
    assert entries(FOUND, ["table seat"]).count("</table") == 1
    assert entries(FOUND, ["sell"]) == ""


def test_staff_group_shows_for_admins_only():
    member = [embed.title for embed in page_embeds(FOUND, "Cafe", False)]
    admin = [embed.title for embed in page_embeds(FOUND, "Cafe", True)]
    assert STAFF not in member
    assert STAFF in admin


def test_intro_links_its_setup_command_and_empty_groups_are_skipped():
    intro, commands = page_embeds(FOUND, "Tickets", False)
    assert "</ticket settings:4>" in intro.description
    assert "</ticket button:4>" in commands.description
    assert len(page_embeds(FOUND, "Welcomer", False)) == 1


def test_every_command_is_listed_once():
    names = [
        name
        for _, _, groups in PAGES.values()
        for group in groups.values()
        for name in group
    ]
    assert len(names) == len(set(names))
    assert len(PAGES) <= 25


def test_panel_opens_a_page_for_its_author_only():
    async def run():
        author = MagicMock()
        author.guild_permissions.administrator = False
        view = HelpPanel(FOUND, author)
        select = next(item for item in view.children if isinstance(item, PageSelect))
        press = MagicMock(user=author, response=AsyncMock())
        with patch.object(PageSelect, "values", PropertyMock(return_value=["Cafe"])):
            await select.callback(press)
        stranger = MagicMock(response=AsyncMock())
        return view, press, await view.interaction_check(stranger), stranger

    view, press, allowed, stranger = asyncio.run(run())
    embeds = press.response.edit_message.call_args.kwargs["embeds"]
    assert [embed.title for embed in embeds] == ["☕ Cafe", "Earn", "Play"]
    assert allowed is False
    assert "not the author" in stranger.response.send_message.call_args.args[0]
    assert len(view.children) == 5

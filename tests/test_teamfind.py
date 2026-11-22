import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from brawl.TeamFinder import reputationSystem as reputation
from brawl.TeamFinder import teamFind

REQUESTER, HELPER, OTHER = 1, 2, 3


def request(players):
    embed = discord.Embed(
        description=f"### Asia Team Request {teamFind.needed(players)}\n-# rules"
    )
    embed.add_field(name="Team Code", value="> XABC123")
    return embed


def press(name, user_id, embed, admin=False):
    interaction = MagicMock()
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.guild.fetch_channel = AsyncMock()
    interaction.user.id = user_id
    interaction.user.guild_permissions.administrator = admin
    interaction.message.content = (
        f"**{teamFind.TOOLS} <@{REQUESTER}> is requesting for teammates** - <@&9>"
    )
    interaction.message.embeds = [embed]

    async def run():
        await getattr(teamFind.RequestView(), name).callback(interaction)

    asyncio.run(run())
    return interaction.response


def test_claims_are_listed_and_fill_the_team():
    embed = request(2)
    press("claim", HELPER, embed)
    assert "(1 More Player Needed)" in embed.description
    assert embed.fields[-1].name == "Claimed By `(1/2)`"
    response = press("claim", OTHER, embed)
    assert "(Team Full!)" in embed.description
    assert embed.fields[-1].value == f"- <@{HELPER}>\n- <@{OTHER}>"
    view = response.edit_message.call_args.kwargs["view"]
    assert view.claim.disabled
    assert view.children[-1].url == teamFind.INVITE.format("XABC123")


def test_claim_is_refused_for_requester_repeat_and_full_team():
    embed = request(1)
    assert "yourself" in press("claim", REQUESTER, embed).send_message.call_args[0][0]
    press("claim", HELPER, embed)
    assert "already" in press("claim", HELPER, embed).send_message.call_args[0][0]
    assert "full" in press("claim", OTHER, embed).send_message.call_args[0][0]
    assert len(embed.fields) == 2


def test_only_requester_or_admin_can_close():
    assert press("close", OTHER, request(2)).send_message.called
    for response in (
        press("close", REQUESTER, request(2)),
        press("close", OTHER, request(2), admin=True),
    ):
        content = response.edit_message.call_args.kwargs["content"]
        assert content == f" <@{REQUESTER}> no longer needs teammates. {teamFind.YES}"


def test_rewards_are_empty_until_a_role_is_added():
    assert reputation.get_rewards({"Roles": "None"}) == {}
    assert reputation.get_rewards({"Roles": {"5": 10}}) == {"5": 10}


def test_mentions_and_ids_name_a_user():
    assert reputation.user_id("<@123>") == 123
    assert reputation.user_id("<@!123>") == 123
    assert reputation.user_id("123") == 123
    assert reputation.user_id("someone") is None


def test_giving_rep_unlocks_the_reward_role():
    store = {"Users/2": 8}
    ref = MagicMock()
    ref.get = lambda: store.get("Users/2")
    ref.set = lambda value: store.update({"Users/2": value})
    message = MagicMock()
    message.reply = AsyncMock()
    message.channel.send = AsyncMock()
    member = MagicMock()
    member.name = "helper"
    member.add_roles = AsyncMock()
    message.guild.get_member.return_value = member
    system = {"Max Rep": 5, "Roles": {"5": 10, "6": 50}}
    cog = reputation.ReputationSystem(None)
    with patch.object(reputation.db, "reference", return_value=ref):
        asyncio.run(cog.give(message, ["-giverep", "<@2>", "9"], system))
        assert "more than 5" in message.reply.call_args[0][0]
        asyncio.run(cog.give(message, ["-giverep", "<@2>", "3"], system))
    assert store == {"Users/2": 11}
    member.add_roles.assert_awaited_once_with(message.guild.get_role.return_value)
    assert "(current - `11`)" in message.channel.send.call_args[0][0]

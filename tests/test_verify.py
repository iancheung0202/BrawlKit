import asyncio

import discord

from brawl.Utility import api
from brawl.Verify import verify


class Role:
    def __init__(self, id):
        self.id = id


class Guild:
    def __init__(self, roles):
        self.roles = {role.id: role for role in roles}

    def get_role(self, id):
        return self.roles.get(id)


class Member:
    def __init__(self, guild, roles):
        self.guild, self.roles = guild, list(roles)

    async def add_roles(self, role):
        self.roles.append(role)

    async def remove_roles(self, role):
        self.roles.remove(role)


def tier(threshold, role_id):
    return {
        "threshold": threshold,
        "role_id": str(role_id),
        "name": f"Tier {role_id}",
        "emoji": "⭐",
    }


CONFIG = {
    "trophy": [tier(1000, 1), tier(5000, 2), tier(9000, 3)],
    "wins": {"3v3": [tier(100, 4)]},
}
ROLES = [Role(id) for id in range(1, 5)]


def member_roles(held, stats):
    member = Member(Guild(ROLES), [ROLES[id - 1] for id in held])
    asyncio.run(verify.sync_roles(member, CONFIG, stats))
    return sorted(role.id for role in member.roles)


def test_tag_is_upper_case_with_one_hash():
    assert api.clean_tag(" 9l00jqrgr ") == "#9L00JQRGR"
    assert api.clean_tag("#9L00JQRGR") == "#9L00JQRGR"


def test_wins_tiers_are_nested_under_wins():
    config = {}
    verify.set_tiers(config, "wins_duo", [tier(10, 1)])
    verify.set_tiers(config, "fame", [tier(20, 2)])
    assert config == {"wins": {"duo": [tier(10, 1)]}, "fame": [tier(20, 2)]}
    assert verify.get_tiers(config, "wins_duo") == [tier(10, 1)]
    assert verify.get_tiers(config, "wins_solo") == []


def test_only_the_highest_reached_role_is_kept():
    assert member_roles([1], {"trophies": 6000, "3vs3Victories": 100}) == [2, 4]


def test_roles_stay_when_no_tier_is_reached():
    assert member_roles([1], {"trophies": 500}) == [1]


def test_unlink_removes_every_milestone_role():
    member = Member(Guild(ROLES), ROLES[:2])
    asyncio.run(verify.clear_roles(member, CONFIG))
    assert member.roles == []


def test_summary_shows_the_highest_reached_tier():
    embed = discord.Embed()
    verify.add_progress(embed, CONFIG, {"trophies": 6000})
    assert [field.value for field in embed.fields] == [
        f"> {verify.YES} <@&2>: `6000/5000` (⭐ Tier 2)"
    ]


def test_full_progress_marks_every_tier():
    embed = discord.Embed()
    verify.add_progress(embed, CONFIG, {"trophies": 6000}, full=True)
    marks = [line.split()[1] for line in embed.fields[0].value.split("\n")]
    assert marks == [verify.YES_DIM, verify.YES, verify.NO]
    assert embed.fields[1].value.startswith(f"> {verify.NO} <@&4>: `0/100`")

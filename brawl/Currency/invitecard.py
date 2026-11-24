import asyncio
import calendar
import time
from datetime import datetime, timezone

from brawl.Currency.card import (
    GOLD,
    GREEN,
    GREY,
    MUTED,
    RED,
    WHITE,
    Card,
    faces,
    named,
    roster,
)
from brawl.Currency.config import REFERRAL_MASTER_SELLS, REFERRAL_STEPS
from brawl.Currency.db import (
    g_invites_member_data,
    g_invites_monthly,
    g_referral_milestones,
)
from brawl.Currency.helper import get_current_month_key
from brawl.Currency.home import background

NEW_ACCOUNT_DAYS = 14
INVITE_HELP = "https://support.discord.com/hc/en-us/articles/208866998-Invites-101"


def month_name(key):
    year, month = key.split("-")
    return f"{calendar.month_name[int(month)]} {year}"


def invited_by(guild_id, user_id):
    """Everyone this member invited, by the month they joined."""
    months = {}
    for member_id, data in (g_invites_member_data(guild_id).get() or {}).items():
        if data.get("inviter") == str(user_id):
            months.setdefault(data.get("join_month"), {})[member_id] = data
    months.pop(None, None)
    return months


def days_left():
    """Days until this month's invite rewards start over, today included."""
    now = datetime.now(timezone.utc)
    return calendar.monthrange(now.year, now.month)[1] - now.day + 1


def summary(guild_id, user_id):
    key = get_current_month_key()
    counts = g_invites_monthly(guild_id, key, user_id).get() or {}
    return {
        "background": background(user_id),
        "month": month_name(key),
        "valid": counts.get("valid", 0),
        "total": counts.get("total", 0),
        "left": counts.get("left", 0),
        "done": g_referral_milestones(guild_id, key, user_id).get() or {},
        "days": days_left(),
    }


async def invitees(economy, guild, user_id, key, people):
    """What the invitees card needs for one month of invited members."""
    ids = list(people)[:SHOWN]
    members = await roster(guild, ids)
    avatars = await faces(members)
    balances = await asyncio.gather(
        *(economy.get_balance(int(member_id)) for member_id in ids)
    )
    brews = await asyncio.gather(
        *(economy.get_active_brew(int(member_id)) for member_id in ids)
    )
    now = datetime.now(timezone.utc)
    rows = []
    for member_id, member, avatar, (beans, tokens), brew in zip(
        ids, members, avatars, balances, brews
    ):
        flag = ""
        if not people[member_id].get("is_new"):
            flag = "REJOINED"
        elif member and (now - member.created_at).days < NEW_ACCOUNT_DAYS:
            flag = "NEW ACCOUNT"
        rows.append(
            {
                "avatar": avatar,
                "name": member.display_name if member else "Member who left",
                "here": member is not None,
                "flag": flag,
                "beans": beans,
                "tokens": tokens,
                **brewing(brew),
            }
        )
    rows += [None] * (len(people) - len(ids))
    return {"background": background(user_id), "month": month_name(key), "people": rows}


def brewing(brew):
    if not brew:
        return {"brew": "No brew", "ready": False}
    roast = brew["roast_type"].capitalize()
    left = brew["end_time"] - time.time()
    if left <= 0:
        return {"brew": f"{roast} ready", "ready": True}
    hours, minutes = divmod(int(left // 60) + 1, 60)
    wait = f"{hours}h {minutes}m" if hours else f"{minutes}m"
    return {"brew": f"{roast}, {wait}", "ready": False}


SHOWN = 10


def draw_invitees(month):
    """Who a member invited in one month and how far each has got."""
    people = month["people"]
    shown = [person for person in people if person]
    more = len(people) - len(shown)
    card = Card(640, 132 + len(shown) * 44 + 24 * (more > 0), month["background"])
    card.panel(16, 24, 608, card.height - 40)
    card.tag(32, 12, "INVITES", GOLD)
    card.text(36, 46, month["month"], 26)
    card.text(604, 54, f"{len(people)} invited", 15, MUTED, "ra", 2)
    for row, person in enumerate(shown):
        y = 96 + row * 44
        card.slot(36, y, 568, 38)
        card.avatar(person["avatar"], 44, y + 6, 26, 6)
        flag = person["flag"]
        name = card.fit(named(person["name"]), 16, 196 - card.measure(flag, 11))
        card.text(80, y + 9, name, 16, WHITE if person["here"] else GREY, "la", 2)
        if flag:
            card.text(90 + card.measure(name, 16), y + 13, flag, 11, RED, "la", 2)
        card.icon("kit/bean", 300, y + 8, 22)
        card.text(326, y + 10, f"{person['beans']:,}", 14, WHITE, "la", 2)
        card.icon("kit/token", 394, y + 8, 22)
        card.text(420, y + 10, f"{person['tokens']:,}", 14, WHITE, "la", 2)
        ready = GREEN if person["ready"] else MUTED
        card.text(590, y + 10, person["brew"], 14, ready, "ra", 2)
    if more > 0:
        card.text(36, card.height - 50, f"and {more} more", 14, MUTED, "la", 2)
    return card.jpg()


async def setup(bot):
    pass

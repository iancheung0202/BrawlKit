import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from brawl.Currency import invitecard
from brawl.Currency.config import (
    REFERRAL_BRIDGE_STAMPS,
    REFERRAL_STEPS,
    REFERRAL_TRAINEE_BEANS,
)
from brawl.Currency.db import (
    g_invites_member_data,
    g_invites_monthly,
    g_referral_milestones,
    u_balance,
    u_brews,
)
from brawl.Currency.helper import MAIN_GUILD_ID, get_current_month_key

ME = 1


def invite(member_id, month, new=True):
    g_invites_member_data(MAIN_GUILD_ID, member_id).set(
        {"inviter": str(ME), "join_month": month, "is_new": new}
    )


def test_the_summary_reads_this_months_counts_and_steps(cafe):
    month = get_current_month_key()
    g_invites_monthly(MAIN_GUILD_ID, month, ME).set({"valid": 4, "total": 6, "left": 2})
    g_referral_milestones(MAIN_GUILD_ID, month, ME).set({"trainee_done": True})
    summary = invitecard.summary(MAIN_GUILD_ID, ME)
    assert (summary["valid"], summary["total"], summary["left"]) == (4, 6, 2)
    assert summary["done"] == {"trainee_done": True}
    assert invitecard.draw_invites(summary).read(2) == b"\xff\xd8"


def test_a_member_with_no_invites_still_gets_a_card(cafe):
    assert invitecard.invited_by(MAIN_GUILD_ID, ME) == {}
    summary = invitecard.summary(MAIN_GUILD_ID, ME)
    assert invitecard.draw_invites(summary).read(2) == b"\xff\xd8"


def test_the_card_rewards_are_the_ones_the_bot_pays():
    rewards = {key: reward for key, _, _, _, reward in REFERRAL_STEPS}
    assert rewards["trainee_done"] == f"+{REFERRAL_TRAINEE_BEANS:,}"
    assert rewards["bridge_done"] == f"+{REFERRAL_BRIDGE_STAMPS}"


def test_invitees_are_grouped_by_month_and_flagged(cafe):
    invite(2, "2026-10")
    invite(3, "2026-11")
    invite(4, "2026-11", new=False)
    invite(5, "2026-11")
    g_invites_member_data(MAIN_GUILD_ID, 9).set(
        {"inviter": "77", "join_month": "2026-11"}
    )
    months = invitecard.invited_by(MAIN_GUILD_ID, ME)
    assert sorted(months) == ["2026-10", "2026-11"]
    assert sorted(months["2026-11"]) == ["3", "4", "5"]

    u_balance(3).set({"Beans": 120, "Tokens": 2})
    u_brews(3).set({"active_brew": {"roast_type": "dark", "end_time": time.time() - 5}})
    now = datetime.now(timezone.utc)
    ages = {3: 400, 4: 400}

    def member(member_id):
        if member_id not in ages:
            return None
        found = MagicMock(display_name=f"member {member_id}")
        found.created_at = now - timedelta(days=ages[member_id])
        return found

    guild = MagicMock()
    guild.get_member = member
    card = asyncio.run(
        invitecard.invitees(
            cafe.cogs["CurrencySystem"], guild, ME, "2026-11", months["2026-11"]
        )
    )
    rows = {row["name"]: row for row in card["people"]}
    assert rows["member 3"]["beans"] == 120 and rows["member 3"]["ready"]
    assert rows["member 3"]["brew"] == "Dark ready"
    assert rows["member 4"]["flag"] == "REJOINED"
    assert not rows["Member who left"]["here"]
    assert invitecard.draw_invitees(card).read(2) == b"\xff\xd8"


def test_a_new_account_is_flagged(cafe):
    invite(3, "2026-11")
    guild = MagicMock()
    guild.get_member.return_value.created_at = datetime.now(timezone.utc)
    people = invitecard.invited_by(MAIN_GUILD_ID, ME)["2026-11"]
    card = asyncio.run(
        invitecard.invitees(cafe.cogs["CurrencySystem"], guild, ME, "2026-11", people)
    )
    assert card["people"][0]["flag"] == "NEW ACCOUNT"


def test_a_long_month_shows_ten_and_counts_the_rest(cafe):
    for member_id in range(2, 15):
        invite(member_id, "2026-11")
    guild = MagicMock()
    guild.get_member.return_value = None
    people = invitecard.invited_by(MAIN_GUILD_ID, ME)["2026-11"]
    card = asyncio.run(
        invitecard.invitees(cafe.cogs["CurrencySystem"], guild, ME, "2026-11", people)
    )
    assert len(card["people"]) == 13
    assert sum(person is not None for person in card["people"]) == invitecard.SHOWN
    assert invitecard.draw_invitees(card).read(2) == b"\xff\xd8"


def test_brew_status_is_short():
    assert invitecard.brewing(None) == {"brew": "No brew", "ready": False}
    soon = {"roast_type": "light", "end_time": time.time() + 14 * 60 - 1}
    assert invitecard.brewing(soon) == {"brew": "Light, 14m", "ready": False}


def test_the_invites_button_fits_a_month_picker_on_home(cafe):
    from brawl.Currency import balance

    invite(55, "2026-11")
    interaction = cafe.interaction(ME)
    interaction.message.attachments = [MagicMock(filename=f"balance_{ME}.jpg")]

    async def press():
        view = balance.BalanceInfoView()
        button = next(b for b in view.children if b.custom_id == "balance_invites")
        await button.callback(interaction)
        return view

    view = asyncio.run(press())
    assert interaction.response.edit_message.called
    assert any(type(item).__name__ == "MonthSelect" for item in view.children)

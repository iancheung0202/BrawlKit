import time

from discord import app_commands
from discord.ext import commands

from brawl.Currency import events, ledger, wallet
from brawl.Currency.card import BACKGROUND, render
from brawl.Currency.config import (
    LEGACY_STAMP_GOALS,
    STAMP_BOX_EVERY,
    STAMP_BOXES,
    STAMP_GOALS,
    STAMP_MONTHLY_LIMIT,
    STAMP_PRICE_RANGES,
    STAMP_PRICE_STREAK,
)
from brawl.Currency.db import (
    g_stamp_redemptions,
    u_daily_checkin_streaks,
    u_mega_boxes,
    u_stamp_card,
)
from brawl.Currency.guide import guide
from brawl.Currency.helper import (
    MAIN_GUILD_ID,
    NO_EMOTE,
    STAMP_EMOTE,
    TOKEN_EMOTE,
    get_current_date_key,
    get_current_month_key,
)
from brawl.Currency.panel import framed, notice
from brawl.Currency.quests import order_tasks, update_quest
from brawl.Currency.rewardcard import draw_redeemed

TIERS = {"brawl_pass": "Brawl Pass", "brawl_pass_plus": "Brawl Pass Plus"}


def stamps(user_id):
    return count(u_stamp_card(user_id).get() or {})


def count(card):
    """The Stamps on a card, new or converted from the old six objectives."""
    if "count" in card:
        return card["count"]
    old = card.get("stamps", {})
    # Every stamp on the old card counts the same, up to its objective's goal.
    kept = sum(min(old.get(task, 0), goal) for task, goal in LEGACY_STAMP_GOALS.items())
    return round(kept / len(LEGACY_STAMP_GOALS))


def boxes(before, after):
    """Mega Boxes for every fifth Stamp passed on the way from before to after."""
    top = max(STAMP_GOALS.values())
    steps = min(after, top) // STAMP_BOX_EVERY - min(before, top) // STAMP_BOX_EVERY
    return max(steps, 0) * STAMP_BOXES


def add(user_id, amount=1, day=None, source="other"):
    """Adds Stamps to a card and pays its Mega Boxes. Returns the boxes paid."""
    have = stamps(user_id)
    u_stamp_card(user_id).update(
        {"count": have + amount, **({"last_stamp": day} if day else {})}
    )
    ledger.note(source, user_id, stamps=amount)
    paid = boxes(have, have + amount)
    if paid:
        u_mega_boxes(user_id).set((u_mega_boxes(user_id).get() or 0) + paid)
        ledger.item("mega_box", dropped=paid)
    return paid


def streak(user_id):
    return (u_daily_checkin_streaks(user_id).get() or {}).get("current_streak", 0)


def price(user_id, tier):
    low, high = STAMP_PRICE_RANGES[tier]
    start, lowest = STAMP_PRICE_STREAK
    span = lowest - start
    return int(high - min(max(streak(user_id) - start, 0), span) / span * (high - low))


def redeemed(guild_id):
    return (g_stamp_redemptions(guild_id, get_current_month_key()).get() or {}).get(
        "count", 0
    )


class StampCard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        events.listen("order", self.stamp)

    async def stamp(self, user_id):
        today = get_current_date_key()
        card = u_stamp_card(user_id)
        if (card.get() or {}).get("last_stamp") == today:
            return
        add(user_id, 1, today, source="order")

    async def summary(self, user, guild):
        await update_quest(user.id, guild.id, {}, self.bot, refresh_only=True)
        tasks = order_tasks(user.id)
        return {
            "stamps": stamps(user.id),
            "redeemed": redeemed(guild.id),
            "streak": streak(user.id),
            "done": sum(done for *_, done in tasks),
            "order": len(tasks),
            "stamped": (u_stamp_card(user.id).get() or {}).get("last_stamp")
            == get_current_date_key(),
            "prices": {tier: price(user.id, tier) for tier in TIERS},
        }

    @app_commands.command(
        name="redeem",
        description="Redeem your Stamp Card for a Brawl Pass or Brawl Pass Plus",
    )
    @app_commands.choices(
        tier=[
            app_commands.Choice(name=name, value=tier) for tier, name in TIERS.items()
        ]
    )
    async def redeem(self, interaction, tier: app_commands.Choice[str]):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                embed=notice(f"{NO_EMOTE} Not available here.", "bad"), ephemeral=True
            )

        user_id = interaction.user.id
        goal = STAMP_GOALS[tier.value]
        count = stamps(user_id)
        if count < goal:
            return await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} **{tier.name}** needs {STAMP_EMOTE} `{goal}` Stamps. You have `{count}`.\n"
                    f"Finish Today's Order to earn {STAMP_EMOTE} 1 Stamp.",
                    "bad",
                ),
                ephemeral=True,
            )

        if redeemed(interaction.guild.id) >= STAMP_MONTHLY_LIMIT:
            return await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} All {STAMP_MONTHLY_LIMIT} passes for this month are redeemed. "
                    "Your Stamps are kept, so try again next month.",
                    "bad",
                ),
                ephemeral=True,
            )

        cost = price(user_id, tier.value)
        if not await wallet.pay(user_id, tokens=cost, reason="pass"):
            _, tokens = wallet.balance(user_id)
            return await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} **{tier.name}** costs {TOKEN_EMOTE} `{cost}`. "
                    f"You have {TOKEN_EMOTE} `{tokens}`.",
                    "bad",
                ),
                ephemeral=True,
            )

        now = int(time.time())
        u_stamp_card(user_id).update({"count": count - goal, "redeemed_at": now})
        ref = g_stamp_redemptions(interaction.guild.id, get_current_month_key())
        month = ref.get() or {}
        ref.set(
            {
                "count": month.get("count", 0) + 1,
                "users": month.get("users", [])
                + [
                    {
                        "user_id": user_id,
                        "timestamp": now,
                        "tier": tier.value,
                        "price": cost,
                    }
                ],
            }
        )

        _, tokens = wallet.balance(user_id)
        sale = {
            "tier": tier.value,
            "name": tier.name,
            "stamps": goal,
            "cost": cost,
            "tokens": tokens,
            "left": count - goal,
            "month": month.get("count", 0) + 1,
            "limit": STAMP_MONTHLY_LIMIT,
            "background": BACKGROUND,
        }
        await interaction.response.send_message(
            **framed(
                await render(draw_redeemed, sale, name="redeemed"),
                "Pass redeemed",
                "Open a ticket in <#1390908939767648328> with a screenshot of this "
                "message and the server owner will deliver your pass.",
                tone="good",
            ),
            view=guide("order", "Use /balance to view your Stamp Card"),
        )

    @redeem.error
    async def redeem_error(self, interaction, error):
        await interaction.response.send_message(
            embed=notice(f"{NO_EMOTE} Something went wrong: {error}", "bad"),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(StampCard(bot))

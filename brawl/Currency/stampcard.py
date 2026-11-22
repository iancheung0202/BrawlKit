import time

from discord import app_commands
from discord.ext import commands

from brawl.Currency import events, wallet
from brawl.Currency.card import render
from brawl.Currency.config import (
    LEGACY_STAMP_GOALS,
    STAMP_GOALS,
    STAMP_MONTHLY_LIMIT,
    STAMP_PRICE_RANGES,
)
from brawl.Currency.db import g_stamp_redemptions, u_daily_checkin_streaks, u_stamp_card
from brawl.Currency.helper import (
    MAIN_GUILD_ID,
    NO_EMOTE,
    STAMP_EMOTE,
    TOKEN_EMOTE,
    get_current_date_key,
    get_current_month_key,
)
from brawl.Currency.home import background, draw_stamp_card
from brawl.Currency.quests import order_tasks, update_quest
from brawl.Currency.rewardcard import draw_redeemed

TIERS = {"brawl_pass": "Brawl Pass", "brawl_pass_plus": "Brawl Pass Plus"}


def stamps(user_id):
    card = u_stamp_card(user_id).get() or {}
    if "count" in card:
        return card["count"]
    old = card.get("stamps", {})
    share = sum(
        min(old.get(task, 0) / goal, 1) for task, goal in LEGACY_STAMP_GOALS.items()
    ) / len(LEGACY_STAMP_GOALS)
    return round(share * STAMP_GOALS["brawl_pass"])


def price(user_id, tier):
    streak = (u_daily_checkin_streaks(user_id).get() or {}).get("current_streak", 0)
    low, high = STAMP_PRICE_RANGES[tier]
    return int(high - min(max(streak - 10, 0), 90) / 90 * (high - low))


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
        card.update({"count": stamps(user_id) + 1, "last_stamp": today})

    async def summary(self, user, guild):
        await update_quest(user.id, guild.id, {}, self.bot, refresh_only=True)
        tasks = order_tasks(user.id)
        return {
            "stamps": stamps(user.id),
            "redeemed": redeemed(guild.id),
            "done": sum(done for *_, done in tasks),
            "tasks": len(tasks),
            "stamped": (u_stamp_card(user.id).get() or {}).get("last_stamp")
            == get_current_date_key(),
            "prices": {tier: price(user.id, tier) for tier in TIERS},
            "background": background(user.id),
        }

    async def card(self, user, guild):
        return await render(
            draw_stamp_card, await self.summary(user, guild), name=f"balance_{user.id}"
        )

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
                f"{NO_EMOTE} Not available here.", ephemeral=True
            )

        user_id = interaction.user.id
        goal = STAMP_GOALS[tier.value]
        count = stamps(user_id)
        if count < goal:
            return await interaction.response.send_message(
                f"{NO_EMOTE} **{tier.name}** needs {STAMP_EMOTE} `{goal}` Stamps. You have `{count}`.\n"
                f"-# Finish Today's Order to earn {STAMP_EMOTE} 1 Stamp.",
                ephemeral=True,
            )

        if redeemed(interaction.guild.id) >= STAMP_MONTHLY_LIMIT:
            return await interaction.response.send_message(
                f"{NO_EMOTE} All {STAMP_MONTHLY_LIMIT} passes for this month are redeemed. "
                "Your Stamps are kept, so try again next month.",
                ephemeral=True,
            )

        cost = price(user_id, tier.value)
        if not await wallet.pay(user_id, tokens=cost, reason="redeem"):
            _, tokens = wallet.balance(user_id)
            return await interaction.response.send_message(
                f"{NO_EMOTE} **{tier.name}** costs {TOKEN_EMOTE} `{cost}`. "
                f"You have {TOKEN_EMOTE} `{tokens}`.",
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
            "background": background(user_id),
        }
        await interaction.response.send_message(
            "-# **Next:** open a ticket in <#1390908939767648328> with a screenshot of this "
            "message and the server owner will deliver your pass.",
            file=await render(draw_redeemed, sale, name="redeemed"),
        )

    @redeem.error
    async def redeem_error(self, interaction, error):
        await interaction.response.send_message(
            f"{NO_EMOTE} Something went wrong: {error}", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(StampCard(bot))

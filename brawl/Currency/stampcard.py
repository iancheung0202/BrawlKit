# stampcard.py
import discord
import time
from discord.ext import commands
from discord import app_commands
from brawl.Currency.db import u_stamp_card, g_stamp_redemptions, u_daily_checkin_streaks
from brawl.Currency.helper import (
    STAMP_OBJECTIVES, STAMP_PRICE_RANGES,
    YES_EMOTE, NO_EMOTE, BEAN_EMOTE, TOKEN_EMOTE, REPLY_EMOTE,
    MAIN_GUILD_ID, get_current_month_key
)

class StampCard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def update_progress(self, user_id: int, action: str, amount: int = 1):
        """Called when a stampable action occurs."""
        data = u_stamp_card(user_id).get()
        all_valid_objectives = set(STAMP_OBJECTIVES["brawl_pass"].keys()) | set(STAMP_OBJECTIVES["brawl_pass_plus"].keys())
        if action not in all_valid_objectives:
            return 

        if not data:
            data = {
                "stamps": {k: 0 for k in STAMP_OBJECTIVES["brawl_pass"].keys()},
                "selected_at": int(time.time())
            }

        stamps = data.get("stamps", {})
        if action not in stamps:
            stamps[action] = 0

        stamps[action] += amount
        data["stamps"] = stamps
        u_stamp_card(user_id).set(data)

    async def add_quest_completion(self, user_id: int):
        """Called from quests.py when any quest is finished."""
        await self.update_progress(user_id, "quests_completed", 1)

    async def get_user_price(self, user_id: int, tier: str) -> int:
        """Compute token price based on daily streak for the given tier."""
        streak_ref = u_daily_checkin_streaks(user_id)
        streak_data = streak_ref.get() or {}
        current_streak = streak_data.get("current_streak", 0)

        min_price, max_price = STAMP_PRICE_RANGES[tier]
        if current_streak >= 100:
            return min_price
        if current_streak <= 10:
            return max_price
        # linear interpolation
        reduction = (current_streak - 10) / 90 * (max_price - min_price)
        return int(max_price - reduction)

    async def get_monthly_redemptions_used(self, guild_id: int) -> int:
        """Return how many redemptions already done this month."""
        month_key = get_current_month_key()
        ref = g_stamp_redemptions(guild_id, month_key)
        data = ref.get() or {"count": 0}
        return data.get("count", 0)

    async def check_eligibility(self, user_id: int, tier: str) -> tuple[bool, list]:
        """Check if user's stamps meet all objectives for the given tier."""
        data = u_stamp_card(user_id).get()
        if not data:
            return False, []
        stamps = data.get("stamps", {})
        required = STAMP_OBJECTIVES[tier]
        missing = []
        for obj, goal in required.items():
            current = stamps.get(obj, 0)
            if current < goal:
                missing.append(f"{obj.replace('_',' ').title()} ({current}/{goal})")
        return len(missing) == 0, missing

    # ------------------------------------------------------------------
    # UI View (simple refresh + back)
    # ------------------------------------------------------------------
    class StampCardView(discord.ui.View):
        def __init__(self, cog, user_id, embed):
            super().__init__(timeout=180)
            self.cog = cog
            self.user_id = user_id
            self.embed = embed

        @discord.ui.button(label="↻ Refresh", style=discord.ButtonStyle.grey)
        async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("Not your stamp card.", ephemeral=True)
            embed, _ = await self.cog.get_stamp_embed(interaction.user, interaction.guild)
            self.embed = embed
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="◀ Back to Balance", style=discord.ButtonStyle.blurple)
        async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("Not your stamp card.", ephemeral=True)
            # Re‑invoke the balance command
            currency_cog = interaction.client.get_cog("CurrencySystem")
            if currency_cog:
                await currency_cog.balance(interaction)
            else:
                await interaction.response.send_message("Balance system unavailable.", ephemeral=True)

    async def get_stamp_embed(self, user: discord.Member, guild: discord.Guild):
        """Build the embed – no interactive elements, only information."""
        data = u_stamp_card(user.id).get()
        stamps = data.get("stamps", {}) if data else {}

        # Define all objectives (same for both tiers, only thresholds differ)
        objectives = list(STAMP_OBJECTIVES["brawl_pass"].keys())
        # Human‑readable names and emojis
        obj_info = {
            "daily_checkins": ("Daily check-ins at <#1391361575641677956>", "<a:streak:1371651844652273694>"),
            "brew_sells": ("Successful </sell:1396588612790784071> of non-burnt brews", "☕"),
            "quests_completed": ("Daily/weekly/monthly quests completed", "<:quest:1490123182345293824>"),
            "shop_purchases": ("</shop:1393376242501157009> purchases with </buy:1393376242501157010>", "<:KitBrawlPassDiamond:1394206796888932393>"),
            "boss_inspections": ("Boss inspections participated in chat", "👔"),
            "thermometer_bonuses": ("</thermometer:1413211262233477272> token bonuses received", ":thermometer:")
        }

        # Build progress table
        lines = []
        for obj in objectives:
            current = stamps.get(obj, 0)
            name, emoji = obj_info[obj]
            # Thresholds for both tiers
            bp_goal = STAMP_OBJECTIVES["brawl_pass"][obj]
            bpp_goal = STAMP_OBJECTIVES["brawl_pass_plus"][obj]

            lines.append(
                f"**{emoji} {name}:** `{current}` \n"
                f"-# {REPLY_EMOTE} *Brawl Pass needs **`{bp_goal}`** • Brawl Pass Plus needs **`{bpp_goal}`***"
            )

        progress_text = "\n".join(lines)

        # Current prices based on user's streak
        price_bp = await self.get_user_price(user.id, "brawl_pass")
        price_bpp = await self.get_user_price(user.id, "brawl_pass_plus")

        # Monthly cap info
        used = await self.get_monthly_redemptions_used(guild.id)

        embed = discord.Embed(
            title="📮 Stamp Card",
            description=(
                f"Complete these tasks to earn free Brawl Passes! There is no catch! Once you meet the requirements, use </redeem:1514483191275192474> to claim it automatically.\n"
                f"### Your Progress\n{progress_text}"
            ),
            color=0xF1C40F
        )
        embed.add_field(
            name="Your Brawl Pass Price",
            value=f"-# {TOKEN_EMOTE} `{price_bp}` Tokens \n-# *(based on your daily streak)*",
            inline=True
        )
        embed.add_field(
            name="Your Brawl Pass Plus Price",
            value=f"-# {TOKEN_EMOTE} `{price_bpp}` Tokens \n-# *(based on your daily streak)*",
            inline=True
        )
        embed.set_footer(text=f"Server-wide redemptions this month: {used}/5")
        return embed, price_bp   # price not used in view

    # ------------------------------------------------------------------
    # /redeem command
    # ------------------------------------------------------------------
    @app_commands.command(name="redeem", description="Redeem your completed Stamp Card for a Brawl Pass or Brawl Pass Plus")
    @app_commands.choices(tier=[
        app_commands.Choice(name="Brawl Pass", value="brawl_pass"),
        app_commands.Choice(name="Brawl Pass Plus", value="brawl_pass_plus")
    ])
    async def redeem(self, interaction: discord.Interaction, tier: app_commands.Choice[str]):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} Not available here.", ephemeral=True)

        user_id = interaction.user.id
        tier_value = tier.value

        # 1. Check eligibility
        eligible, missing = await self.check_eligibility(user_id, tier_value)
        if not eligible:
            missing_list = "\n".join(f"-# - {m}" for m in missing[:5])
            await interaction.response.send_message(
                f"{NO_EMOTE} You haven't completed all stamps for **{tier.name}**.\n"
                f"{missing_list}",
                ephemeral=True
            )
            return

        # 2. Check monthly cap
        used = await self.get_monthly_redemptions_used(interaction.guild.id)
        if used >= 5:
            await interaction.response.send_message(
                f"{NO_EMOTE} The monthly redemption limit (5) has been reached. Try again next month.",
                ephemeral=True
            )
            return

        # 3. Compute price and check tokens
        price = await self.get_user_price(user_id, tier_value)
        currency_cog = interaction.client.get_cog("CurrencySystem")
        if not currency_cog:
            return await interaction.response.send_message("Currency system unavailable.", ephemeral=True)

        beans, tokens = await currency_cog.get_balance(user_id)
        if tokens < price:
            await interaction.response.send_message(
                f"{NO_EMOTE} You need {TOKEN_EMOTE} `{price}` Tokens to redeem **{tier.name}**.\n"
                f"Your balance: {TOKEN_EMOTE} `{tokens}`",
                ephemeral=True
            )
            return

        # 4. Deduct tokens and reset stamps
        new_tokens = tokens - price
        await currency_cog.update_balance(user_id, tokens=new_tokens)

        # Reset stamp card (all stamps to 0)
        u_stamp_card(user_id).set({
            "stamps": {k: 0 for k in STAMP_OBJECTIVES["brawl_pass"].keys()},
            "redeemed_at": int(time.time()),
            "selected_at": int(time.time())
        })

        # 5. Update monthly counter
        month_key = get_current_month_key()
        ref = g_stamp_redemptions(interaction.guild.id, month_key)
        counter_data = ref.get() or {"count": 0, "users": []}
        counter_data["count"] += 1
        counter_data["users"].append({
            "user_id": user_id,
            "timestamp": int(time.time()),
            "tier": tier_value,
            "price": price
        })
        ref.set(counter_data)

        # 6. Success message
        embed = discord.Embed(
            title=f"{YES_EMOTE} Stamp Card Redeemed!",
            description=(
                f"You redeemed **{tier.name}** for {TOKEN_EMOTE} `{price}` Tokens.\n"
                f"-# Your new balance: {TOKEN_EMOTE} `{new_tokens}`\n\n"
                f"-# **Next step:** Please open a ticket in <#1390908939767648328> and provide proof of this redemption. "
                f"Our server owner will deliver your pass."
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="Your stamp card has been reset and can start a new one immediately.")
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @redeem.error
    async def redeem_error(self, interaction: discord.Interaction, error):
        await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(StampCard(bot))
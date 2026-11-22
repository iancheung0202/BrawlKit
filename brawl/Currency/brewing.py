import random
import secrets
import time

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View

from brawl.Currency.db import g_invites_member_data, sync_sell_alarm
from brawl.Currency.helper import (
    BEAN_EMOTE,
    BRIDGE_ROLE_ID,
    EFFECT_EMOTE,
    EMOJIS,
    MAIN_GUILD_ID,
    MASTER_ROLE_ID,
    NO_EMOTE,
    PERFECT_BREW_CHANCE,
    ROAST_TYPES,
    TOKEN_EMOTE,
    TRAINEE_ROLE_ID,
    ULTRA_TIER_ROLE_ID,
    UNLOCK_REQ,
    YES_EMOTE,
)
from brawl.Currency.ladder import locked
from brawl.Currency.panel import COLORS, NEXT, STATIONS, panel
from brawl.Currency.quests import report, update_quest


class Brewing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def economy(self):
        return self.bot.get_cog("CurrencySystem")

    async def insure_brew(self, user_id: int, roast_type: str):
        """Insure an active brew and deduct insurance cost"""
        insurance_cost = ROAST_TYPES[roast_type]["insurance_cost"]
        active_effects = await self.economy.effect_manager.get_user_active_effects(
            user_id
        )
        free_insurance = "free_insurance" in active_effects

        guild = self.bot.get_guild(MAIN_GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            ultra_role = guild.get_role(ULTRA_TIER_ROLE_ID)
            if member and ultra_role and ultra_role in member.roles:
                free_insurance = True

        if not free_insurance:
            beans, tokens = await self.economy.get_balance(user_id)
            if beans < insurance_cost:
                return False

            new_beans = beans - insurance_cost
            await self.economy.update_balance(user_id, beans=new_beans)

        ref = self.economy._get_brew_ref(user_id)
        data = ref.get() or {}
        if "active_brew" in data:
            data["active_brew"]["insured"] = True
            data["active_brew"]["free_insurance"] = free_insurance
            ref.set(data)

            return True
        return False

    def get_min_nonzero_reward(self, roast_type: str) -> int:
        """Get the minimum non-zero reward for a roast type"""
        rewards = ROAST_TYPES[roast_type]["payout"]
        non_zero = [r for r in rewards if r > 0]
        return min(non_zero) if non_zero else 0

    class InsuranceView(View):
        def __init__(self, cog):
            super().__init__(timeout=None)
            self.cog = cog

        async def update_button_for_user(self, user_id):
            active_effects = (
                await self.cog.economy.effect_manager.get_user_active_effects(user_id)
            )
            free_insurance = "free_insurance" in active_effects

            guild = self.cog.bot.get_guild(MAIN_GUILD_ID)
            if guild:
                member = guild.get_member(user_id)
                ultra_role = guild.get_role(ULTRA_TIER_ROLE_ID)
                if member and ultra_role and ultra_role in member.roles:
                    free_insurance = True

            for child in self.children:
                if (
                    hasattr(child, "custom_id")
                    and child.custom_id == "insure_with_beans"
                ):
                    if free_insurance:
                        child.label = "Get FREE Insurance"
                        child.emoji = EFFECT_EMOTE
                        child.style = discord.ButtonStyle.blurple
                elif hasattr(child, "custom_id") and child.custom_id == "no_thanks":
                    self.remove_item(child)

        @discord.ui.button(
            label="Insure with Beans",
            style=discord.ButtonStyle.green,
            emoji="🛡️",
            custom_id="insure_with_beans",
        )
        async def insure_button(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            user_id = interaction.user.id
            if str(user_id) not in interaction.message.embeds[0].description:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} This is not your brew!", ephemeral=True
                )
            active = await self.cog.economy.get_active_brew(user_id)
            shown = [field.value for field in interaction.message.embeds[0].fields]
            if (
                not active
                or active.get("insured")
                or f"`{active['batch_id']}`" not in shown
            ):
                return await interaction.response.send_message(
                    f"{NO_EMOTE} This brew can no longer be insured.", ephemeral=True
                )

            active_effects = (
                await self.cog.economy.effect_manager.get_user_active_effects(user_id)
            )
            free_insurance = "free_insurance" in active_effects

            guild = self.cog.bot.get_guild(MAIN_GUILD_ID)
            if guild:
                member = guild.get_member(user_id)
                ultra_role = guild.get_role(ULTRA_TIER_ROLE_ID)
                if member and ultra_role and ultra_role in member.roles:
                    free_insurance = True

            success = await self.cog.insure_brew(user_id, active["roast_type"])
            if success:
                for child in self.children:
                    child.disabled = True

                embed = interaction.message.embeds[0]
                insurance_text = (
                    f"{EFFECT_EMOTE} **Brew Insured for free!** (Barista's Protection Plan)"
                    if free_insurance
                    else f"{YES_EMOTE} **Brew Insured!**"
                )
                embed.description = embed.description.replace(
                    "🛡️ **Brew Insurance Offer**", insurance_text
                )
                embed.description = embed.description.replace(
                    f"{EFFECT_EMOTE} **FREE Insurance Available!**", insurance_text
                )
                embed.color = discord.Color.green()

                await interaction.response.edit_message(embed=embed, view=None)
            else:
                await interaction.response.send_message(
                    f"{NO_EMOTE} You don't have enough Beans to insure this brew!",
                    ephemeral=True,
                )

        @discord.ui.button(
            label="No Thanks", style=discord.ButtonStyle.grey, custom_id="no_thanks"
        )
        async def decline_button(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            if (
                str(interaction.user.id)
                not in interaction.message.embeds[0].description
            ):
                return await interaction.response.send_message(
                    f"{NO_EMOTE} This is not your brew!", ephemeral=True
                )
            for child in self.children:
                child.disabled = True

            embed = interaction.message.embeds[0]
            embed.description = embed.description.replace(
                "🛡️ **Brew Insurance Offer**", f"{NO_EMOTE} **Not Insured**"
            )

            await interaction.response.edit_message(embed=embed, view=None)

    @app_commands.command(
        name="brew", description="Brew a batch of coffee using your Beans"
    )
    @app_commands.choices(
        roast_type=[
            app_commands.Choice(name="Light Roast", value="light"),
            app_commands.Choice(name="Medium Roast", value="medium"),
            app_commands.Choice(name="Dark Roast", value="dark"),
            app_commands.Choice(name="Golden Roast", value="golden"),
        ]
    )
    @app_commands.checks.cooldown(rate=1, per=10.0)
    @app_commands.describe(
        roast_type="Type of roast (Leave blank to view rewards breakdown)"
    )
    async def brew(
        self,
        interaction: discord.Interaction,
        roast_type: app_commands.Choice[str] = None,
    ):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )
        if await locked(interaction, "brewing"):
            return
        if roast_type is None:
            embed = discord.Embed(
                title="Roast Guide",
                description=(
                    f"Brewing turns {BEAN_EMOTE} Beans into {TOKEN_EMOTE} Tokens. "
                    "One brew at a time.\n"
                    "-# 🛡️ Insurance turns a burnt brew into the lowest payout.\n"
                    f"-# **Next:** {NEXT['brew']}"
                ),
                color=COLORS["info"],
            )

            for key, data in ROAST_TYPES.items():
                emoji = EMOJIS.get(key, "")
                name = f"{emoji} {data['name']}"
                cost = f"{BEAN_EMOTE} `{data['cost']:,}`"
                hours = data["time"] // 3600
                time_str = f"`{hours} hour{'s' if hours != 1 else ''}`"
                insurance_cost = (
                    f"{BEAN_EMOTE} `{data['insurance_cost']:,}`"
                    if data["insurance_cost"] > 0
                    else "Not applicable"
                )

                payout_lines = []
                for reward, weight in zip(data["payout"], data["weights"]):
                    if reward == 0:
                        payout_lines.append(f"> -# `{weight}%` - 💀 Burnt Brew")
                    else:
                        payout_lines.append(
                            f"> -# `{weight}%` - {TOKEN_EMOTE} `{reward}` Token{'s' if reward > 1 else ''}"
                        )

                payout_lines.append(
                    f"-# ✨ **Perfect Brew** (`{PERFECT_BREW_CHANCE}%` chance) for double reward!"
                )
                payout_lines.append(f"-# 🛡️ **Insurance**: {insurance_cost}")

                if key == "golden":
                    payout_lines.insert(
                        0, f"*🔓 Requires `{UNLOCK_REQ}` total brews to unlock*"
                    )
                    payout_lines.append(
                        f"-# 💀 No risk of burnt brew. Guaranteed reward!"
                    )

                value = (
                    f"**Cost:** {cost}\n"
                    f"**Brew Time:** {time_str}\n" + "\n".join(payout_lines)
                )

                embed.add_field(name=name, value=value, inline=True)

            embed.set_footer(text="Higher roasts cost more Beans and pay more Tokens.")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        user_id = interaction.user.id
        roast = roast_type.value

        active_brew = await self.economy.get_active_brew(user_id)
        if active_brew:
            current_time = time.time()
            if current_time < active_brew["end_time"]:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You already have an active brew! You can </sell:1396588612790784071> it <t:{int(active_brew['end_time'])}:R>.",
                    ephemeral=True,
                )
            else:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You have a brew ready to sell! Use </sell:1396588612790784071> first.",
                    ephemeral=True,
                )

        if roast == "golden":
            stats = await self.economy.get_brew_stats(user_id)
            total_brews = stats.get("total_brews", 0) if stats else 0
            if total_brews < UNLOCK_REQ:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You need `{UNLOCK_REQ}` brews to unlock **Golden Roast**. You only have `{total_brews}`.",
                    ephemeral=True,
                )

        cost = ROAST_TYPES[roast]["cost"]
        beans, tokens = await self.economy.get_balance(user_id)
        if beans < cost:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You need {BEAN_EMOTE} `{cost:,}` Beans for a **{ROAST_TYPES[roast]['name']}**. You only have `{beans:,}`.",
                ephemeral=True,
            )

        await interaction.response.defer(thinking=True)

        new_beans = beans - cost
        await self.economy.update_balance(user_id, beans=new_beans)

        current_time = time.time()
        brew_time = ROAST_TYPES[roast]["time"]

        active_effects = await self.economy.effect_manager.get_user_active_effects(
            user_id
        )
        if "half_brew_time" in active_effects:
            brew_time = brew_time // 2

        brew_data = {
            "roast_type": roast,
            "start_time": current_time,
            "end_time": current_time + brew_time,
            "batch_id": secrets.token_hex(4).upper(),
            "insured": False,
        }

        await self.economy.set_active_brew(user_id, brew_data)
        await self.economy.update_brew_stats_on_brew(user_id, roast)
        order = await update_quest(
            user_id, interaction.guild.id, {"brew_start": 1}, self.bot
        )

        guide = await self.economy.tutorial_manager.advance(user_id, "brew")

        if "sell_alarm" in active_effects:
            sync_sell_alarm(
                user_id,
                "set",
                {
                    "roast_type": roast,
                    "end_time": brew_data["end_time"],
                    "batch_id": brew_data["batch_id"],
                    "notified": False,
                },
                interaction.guild.id,
            )

        embed = panel(
            "brew",
            f"{ROAST_TYPES[roast]['name']} started",
            f"{interaction.user.mention}, your coffee is brewing. Ready <t:{int(brew_data['end_time'])}:R>.",
        )

        if "half_brew_time" in active_effects:
            embed.description += "\n<:reply:1036792837821435976> **Turbo Brewing Kit** - 50% faster brewing time! ⚡"

        if roast != "golden" and ROAST_TYPES[roast]["insurance_cost"] > 0:
            insurance_cost = ROAST_TYPES[roast]["insurance_cost"]

            active_effects = await self.economy.effect_manager.get_user_active_effects(
                user_id
            )
            free_insurance = "free_insurance" in active_effects

            ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
            if ultra_role and ultra_role in interaction.user.roles:
                free_insurance = True

            if free_insurance:
                embed.description += (
                    f"\n\n> {EFFECT_EMOTE} **FREE Insurance Available!**\n"
                    f"> -# Your Barista's Protection Plan covers this brew for free!"
                )
            else:
                embed.description += (
                    f"\n\n> 🛡️ **Brew Insurance Offer**\n"
                    f"> -# Protect your brew from burns for {BEAN_EMOTE} `{insurance_cost}` Beans"
                )
            view = self.InsuranceView(self)
            await view.update_button_for_user(user_id)
        else:
            view = None
        embed.description += f"\n-# **Next:** {NEXT['sell']}"

        ref_mapping = g_invites_member_data(interaction.guild.id, interaction.user.id)
        mapping = ref_mapping.get() or {}

        if (
            mapping
            and not mapping.get("brew_done", False)
            and mapping.get("is_new", False)
        ):
            log_entry, inviter = await self.economy.process_referral_milestone(
                interaction, "trainee", interaction.user
            )
            if log_entry:
                await self.economy.log_referral_milestone(log_entry)
                embed.description += f"\n\n<:Information:855023058255478794> **Referral Milestone:** Your inviter {inviter.mention} earned <@&{TRAINEE_ROLE_ID}> too!"

        welcome_bonus_msg = await self.economy.process_invitee_welcome_bonus(
            interaction, "brew", interaction.user
        )
        if welcome_bonus_msg:
            extra_newline = (
                "\n"
                if "<:Information:855023058255478794>" not in embed.description
                else ""
            )
            embed.description += f"\n{extra_newline}{welcome_bonus_msg}"
            new_beans += 150

        embed.add_field(
            name="Cost", value=f"{BEAN_EMOTE} `{cost:,}` Beans", inline=True
        )
        embed.add_field(
            name="Remaining", value=f"{BEAN_EMOTE} `{new_beans:,}` Beans", inline=True
        )
        embed.add_field(name="Brew ID", value=f"`{brew_data['batch_id']}`", inline=True)

        if view is not None:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)
        await report(interaction, order, guide)

    @brew.error
    async def brew_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(
                f"```{str(error)}```", ephemeral=True
            )
        except Exception:
            await interaction.followup.send(f"```{str(error)}```", ephemeral=True)

    @app_commands.command(name="sell", description="Sell your brewed coffee for Tokens")
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def sell(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )
        user_id = interaction.user.id

        active_brew = await self.economy.get_active_brew(user_id)
        if not active_brew:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You don't have an active brew to sell.", ephemeral=True
            )

        current_time = time.time()
        if current_time < active_brew["end_time"]:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Your brew isn't ready yet! You can sell it <t:{int(active_brew['end_time'])}:R>.",
                ephemeral=True,
            )

        await interaction.response.defer(thinking=True)

        roast_type = active_brew["roast_type"]
        payout_info = ROAST_TYPES[roast_type]
        base_payout = random.choices(
            payout_info["payout"], weights=payout_info["weights"]
        )[0]
        insured = active_brew.get("insured", False)
        saved_burn = False

        active_effects = await self.economy.effect_manager.get_user_active_effects(
            user_id
        )

        burnt_to_perfect = False
        if base_payout == 0:
            if "burnt_to_perfect" in active_effects:
                base_payout = max(payout_info["payout"])
                saved_burn = True
                burnt_to_perfect = True
            elif insured:
                base_payout = self.get_min_nonzero_reward(roast_type)
                saved_burn = True

        perfect_chance = PERFECT_BREW_CHANCE
        if "perfect_brew_boost" in active_effects:
            perfect_chance = 25

        perfect = random.random() < (perfect_chance / 100)

        if perfect or burnt_to_perfect:
            tokens = int(base_payout * 2)
        else:
            tokens = base_payout

        master_bonus = False
        if (
            base_payout != 0
            and interaction.guild.get_role(MASTER_ROLE_ID) in interaction.user.roles
        ):
            master_bonus = max(int(base_payout * 0.5), 1)
            tokens += master_bonus

        new_tokens = await self.economy.add_tokens(user_id, tokens)
        order = await update_quest(
            user_id, interaction.guild.id, {"brew_sells": 1}, self.bot
        )

        await self.economy.update_brew_stats_on_sell(
            user_id, tokens, roast_type, perfect, insured, saved_burn
        )
        await self.economy.record_brew_history(
            user_id,
            {
                **active_brew,
                "sold_time": current_time,
                "tokens_earned": tokens,
                "perfect": perfect,
                "insured": insured,
                "saved_burn": saved_burn,
            },
        )

        await self.economy.remove_active_brew(user_id)

        if sync_sell_alarm(user_id, "get"):
            sync_sell_alarm(user_id, "delete", guild_id=interaction.guild.id)

        embed = panel(
            "brew",
            f"{ROAST_TYPES[roast_type]['name']} sold",
            tone="gold" if perfect else "good" if tokens else "bad",
        )

        if tokens == 0:
            embed.description = f"💀 **Burnt Brew!** {interaction.user.mention}, you didn't earn any {TOKEN_EMOTE} Tokens."
            if not insured:
                embed.description += (
                    f"\n-# 🛡️ **Tip:** Insurance would have protected this brew!"
                )
        else:
            embed.description = f"{interaction.user.mention}, you earned {TOKEN_EMOTE} **{tokens} Token{'s' if tokens > 1 else ''}**!"
            if perfect:
                if "perfect_brew_boost" in active_effects:
                    embed.description += f"\n{EFFECT_EMOTE} **Perfect Brew!** (Expert Barista boost - 25% chance)"
                else:
                    embed.description += "\n✨ **Perfect Brew!** (double reward)"
            if saved_burn:
                if "burnt_to_perfect" in active_effects:
                    embed.description += f"\n{EFFECT_EMOTE} **Burnt Brew Revival!** (Burnt brew converted to perfect)"
                else:
                    embed.description += "\n🛡️ **Insurance Saved!** (minimum reward)"
            if master_bonus:
                embed.description += (
                    f"\n☕ **Master Barista Bonus!** ({master_bonus} extra Tokens)"
                )

        embed.description += f"\n-# **Next:** {NEXT['brew']}"
        embed.add_field(
            name="New Token Balance",
            value=f"{TOKEN_EMOTE} `{new_tokens}` Tokens",
            inline=True,
        )
        embed.add_field(
            name="Brew ID", value=f"`{active_brew['batch_id']}`", inline=True
        )
        if insured:
            embed.add_field(name="Insurance Status", value="🛡️ Insured", inline=True)

        if tokens != 0:
            flavor_notes = {
                "light": [
                    "Bright and acidic with floral notes",
                    "Citrusy and tea-like with a crisp finish",
                    "Delicate and aromatic with hints of jasmine",
                    "Fruity and lively with a honey sweetness",
                ],
                "medium": [
                    "Balanced with caramel sweetness",
                    "Smooth and nutty with hints of cocoa",
                    "Well-rounded with brown sugar and spice tones",
                    "Rich and mellow with toffee notes",
                ],
                "dark": [
                    "Bold and smoky with chocolate undertones",
                    "Intense and full-bodied with molasses sweetness",
                    "Dark chocolate and roasted nut flavor",
                    "Earthy and strong with a slightly bitter finish",
                ],
                "golden": [
                    "Exotic and complex with fruity essence",
                    "Vibrant and layered with tropical fruit and spice",
                    "Smooth and buttery with floral aromatics",
                    "Sweet and lush with notes of mango and honey",
                ],
            }

            embed.add_field(
                name="Flavor Profile",
                value=random.choice(flavor_notes[roast_type]),
                inline=False,
            )

            ref_mapping = g_invites_member_data(
                interaction.guild.id, interaction.user.id
            )
            mapping = ref_mapping.get() or {}

            if mapping and mapping.get("inviter") and mapping.get("is_new", False):
                earned_rewards = ""

                if not mapping.get("brew_done", False):
                    log_entry, inviter = await self.economy.process_referral_milestone(
                        interaction, "trainee", interaction.user
                    )
                    if log_entry:
                        earned_rewards = f"Your inviter {inviter.mention} earned <@&{TRAINEE_ROLE_ID}> too!"

                log_entry, inviter = await self.economy.process_referral_milestone(
                    interaction, "bridge", interaction.user
                )
                if log_entry:
                    await self.economy.log_referral_milestone(log_entry)
                    earned_rewards = f"Your inviter {inviter.mention} earned <@&{BRIDGE_ROLE_ID}> too!"

                master_log, inviter = await self.economy.process_referral_milestone(
                    interaction, "sell", interaction.user
                )
                if master_log:
                    await self.economy.log_referral_milestone(master_log)
                    earned_rewards = f"Your inviter {inviter.mention} earned <@&{MASTER_ROLE_ID}> too!"

                if earned_rewards:
                    embed.description += f"\n\n<:Information:855023058255478794> **Referral Milestone::** {earned_rewards}"

            welcome_bonus_msg = await self.economy.process_invitee_welcome_bonus(
                interaction, "sell", interaction.user
            )
            if welcome_bonus_msg:
                extra_newline = (
                    "\n"
                    if "<:Information:855023058255478794>" not in embed.description
                    else ""
                )
                embed.description += f"\n{extra_newline}{welcome_bonus_msg}"

        await interaction.followup.send(embed=embed)
        await report(
            interaction,
            order,
            await self.economy.tutorial_manager.advance(user_id, "sell"),
        )

    @sell.error
    async def sell_error(self, interaction: discord.Interaction, error: Exception):
        try:
            await interaction.response.send_message(
                f"```{str(error)}```", ephemeral=True
            )
        except Exception:
            await interaction.followup.send(f"```{str(error)}```", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Brewing(bot))

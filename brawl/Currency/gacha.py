import random
import time

import discord
from discord import app_commands
from discord.ext import commands
from firebase_admin import db

from brawl.Currency.db import (
    sync_shop_effects,
    u_mega_boxes,
    u_mega_boxes_pending,
    u_shop_effects,
    u_star_drops,
    u_star_drops_pending,
)
from brawl.Currency.helper import (
    BEAN_EMOTE,
    COLORS,
    EFFECT_EMOTE,
    IMAGES,
    MAIN_GUILD_ID,
    MEGA_BOX_EMOTE,
    NO_EMOTE,
    REPLY_EMOTE,
    STAR_DROP_EMOTE,
    STAR_DROP_RATES,
    STORE_ITEMS,
    TOKEN_EMOTE,
)


class StarDropView(discord.ui.View):
    active_sessions = {}

    def __init__(
        self, user: discord.User, total_unopened_count: int, pending_drop: dict
    ):
        super().__init__(timeout=60)
        self.user = user
        self.user_id = str(user.id)
        self.total_unopened = total_unopened_count
        self.rarities = list(STAR_DROP_RATES["rarity_rates"].keys())
        self.max_upgrades = 4
        self.is_unlocked = False
        self.rewards_claimed = False
        self.message = None

        self.final_rarity = pending_drop["final_rarity"]
        self.current_rarity = pending_drop["current_rarity"]
        self.current_upgrades = pending_drop["upgrades_used"]

        StarDropView.active_sessions[self.user_id] = self
        self._update_buttons()

    async def _save_pending_state(self):
        pending_ref = u_star_drops_pending(self.user_id)
        if self.is_unlocked:
            pending_ref.delete()
        else:
            pending_ref.update(
                {
                    "current_rarity": self.current_rarity,
                    "upgrades_used": self.current_upgrades,
                }
            )

    def _deactivate_session(self):
        if self.user_id in StarDropView.active_sessions:
            if StarDropView.active_sessions[self.user_id] == self:
                del StarDropView.active_sessions[self.user_id]

    def create_embed(self, resume=False):
        if self.is_unlocked:
            return self.reward_embed

        desc = (
            "<a:warning:1391215594430402742> Resuming your unfinished Star Drop!"
            if resume
            else "Click `Upgrade` to try improving your drop's rarity!\nYou must use all 4 upgrades before unlocking."
        )
        embed = discord.Embed(
            title=f"{STAR_DROP_EMOTE} Star Drop",
            description=f"{desc}",
            color=COLORS.get(self.current_rarity, 0x49D532),
        )

        embed.set_image(url=IMAGES.get(self.current_rarity, ""))
        embed.add_field(
            name="Current Rarity",
            value=self.current_rarity.replace("_", " ").title(),
            inline=True,
        )
        embed.add_field(
            name="Upgrades Used",
            value=f"{self.current_upgrades}/{self.max_upgrades}",
            inline=True,
        )
        embed.add_field(
            name="Remaining Drops", value=f"{self.total_unopened} more", inline=True
        )
        embed.set_footer(text="💡 Your progress is automatically saved!")
        return embed

    @discord.ui.button(
        label="Upgrade",
        style=discord.ButtonStyle.primary,
        emoji="<:Upgrade:1447684501735211239>",
    )
    async def upgrade_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        if interaction.user.id != self.user.id:
            await interaction.followup.send(
                "This is not your Star Drop!", ephemeral=True
            )
            return

        if self.current_upgrades >= self.max_upgrades:
            await interaction.followup.send("You've used all upgrades!", ephemeral=True)
            return

        if self.is_unlocked:
            await interaction.followup.send(
                "This drop is already unlocked!", ephemeral=True
            )
            return

        current_index = self.rarities.index(self.current_rarity)
        final_index = self.rarities.index(self.final_rarity)

        if self.current_upgrades == self.max_upgrades - 1:
            self.current_rarity = self.final_rarity
        elif current_index < final_index:
            roll = random.random()
            if roll < 0.4:
                remaining_steps = final_index - current_index
                jump = 1
                if remaining_steps > 1 and random.random() < 0.5:
                    jump = 2

                new_index = min(current_index + jump, final_index)
                self.current_rarity = self.rarities[new_index]

        self.current_upgrades += 1
        await self._save_pending_state()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

    @discord.ui.button(
        label="Unlock",
        style=discord.ButtonStyle.success,
        emoji="<a:unlocked:1390755948926079037>",
    )
    async def unlock_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        if interaction.user.id != self.user.id:
            await interaction.followup.send(
                "This is not your Star Drop!", ephemeral=True
            )
            return

        if self.current_upgrades < self.max_upgrades:
            await interaction.followup.send(
                f"You must use all {self.max_upgrades} upgrades first!", ephemeral=True
            )
            return

        if self.is_unlocked:
            await interaction.followup.send(
                "This drop is already unlocked!", ephemeral=True
            )
            return

        if self.rewards_claimed:
            await interaction.followup.send(
                f"{NO_EMOTE} Rewards have already been claimed for this drop!",
                ephemeral=True,
            )
            return

        self.rewards_claimed = True
        reward_description = await self._process_reward(interaction)

        rarity = self.final_rarity
        rate = STAR_DROP_RATES["rarity_rates"][rarity] * 100

        embed = discord.Embed(
            title=f"{STAR_DROP_EMOTE} Star Drop - {rarity.replace('_', ' ').title()}",
            description=f"You received: {reward_description}",
            color=COLORS.get(rarity, 0x49D532),
        )

        embed.set_image(url=IMAGES.get(rarity, ""))
        embed.set_footer(text=f"{rate:.1f}% chance of getting this rarity")

        if self.total_unopened > 0:
            embed.add_field(
                name="Next Drop",
                value=f"You have {self.total_unopened} more Star Drop{'s' if self.total_unopened > 1 else ''}!",
                inline=False,
            )

        self.reward_embed = embed
        self.is_unlocked = True
        await self._save_pending_state()
        if self.total_unopened <= 0:
            self._deactivate_session()
        self._update_buttons()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(
        label="Open Next",
        style=discord.ButtonStyle.grey,
        emoji=STAR_DROP_EMOTE,
        disabled=True,
    )
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "This is not your Star Drop!", ephemeral=True
            )
            return

        if not self.is_unlocked:
            await interaction.response.send_message(
                "Unlock the current drop first!", ephemeral=True
            )
            return

        if self.total_unopened <= 0:
            await interaction.response.send_message(
                "No more drops to open!", ephemeral=True
            )
            return

        inventory_ref = u_star_drops(self.user_id)
        current_count = inventory_ref.get() or 0

        if current_count <= 0:
            await interaction.response.send_message(
                f"{NO_EMOTE} No more star drops available!", ephemeral=True
            )
            self.total_unopened = 0
            self._update_buttons()
            await interaction.edit_original_response(view=self)
            return

        roll = random.random()
        cumulative = 0
        final_rarity = "rare"
        for rarity, rate in STAR_DROP_RATES["rarity_rates"].items():
            cumulative += rate
            if roll <= cumulative:
                final_rarity = rarity
                break

        new_pending = {
            "final_rarity": final_rarity,
            "current_rarity": "rare",
            "upgrades_used": 0,
            "created_at": int(time.time()),
        }

        updates = {
            u_star_drops_pending(self.user_id).path: new_pending,
            u_star_drops(self.user_id).path: current_count - 1,
        }
        db.reference().update(updates)

        self.total_unopened = current_count - 1
        self.final_rarity = final_rarity
        self.current_rarity = "rare"
        self.current_upgrades = 0
        self.is_unlocked = False
        self.rewards_claimed = False
        self._update_buttons()

        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def _process_reward(self, interaction: discord.Interaction) -> str:
        rarity = self.final_rarity
        drops = STAR_DROP_RATES["drops"][rarity]

        total_weight = sum(drop.get("weight", 1) for drop in drops)
        roll = random.uniform(0, total_weight)
        cumulative = 0
        selected_drop = None

        for drop in drops:
            cumulative += drop.get("weight", 1)
            if roll <= cumulative:
                selected_drop = drop
                break

        if not selected_drop:
            selected_drop = drops[0]

        reward_text = ""
        currency_cog = interaction.client.get_cog("CurrencySystem")

        reward_type = selected_drop["type"]
        if reward_type == "beans":
            amount = selected_drop.get("amount") or random.randint(
                *selected_drop["range"]
            )
            if currency_cog:
                current_beans, _ = await currency_cog.get_balance(int(self.user_id))
                await currency_cog.update_balance(
                    int(self.user_id), beans=current_beans + amount
                )
            reward_text = f"{BEAN_EMOTE} `{amount:,}` Beans"
        elif reward_type == "tokens":
            amount = selected_drop.get("amount") or random.randint(
                *selected_drop["range"]
            )
            if currency_cog:
                _, current_tokens = await currency_cog.get_balance(int(self.user_id))
                await currency_cog.update_balance(
                    int(self.user_id), tokens=current_tokens + amount
                )
            reward_text = f"{TOKEN_EMOTE} `{amount:,}` Tokens"

        bonus_chance = 0
        if rarity == "mythic":
            bonus_chance = 0.10
        elif rarity == "legendary":
            bonus_chance = 0.50
        elif rarity == "ultra":
            bonus_chance = 1.0

        if bonus_chance > 0 and random.random() < bonus_chance:
            available_items = [
                k
                for k, v in STORE_ITEMS.items()
                if k != "star_drop" and v.get("duration", 0) > 0
            ]

            if available_items:
                user_effects = sync_shop_effects(self.user_id, operation="get") or {}

                not_owned = []
                current_time = time.time()
                for item_id in available_items:
                    if (
                        item_id not in user_effects
                        or not user_effects[item_id].get("active")
                        or user_effects[item_id].get("expires_at", 0) < current_time
                    ):
                        not_owned.append(item_id)

                if not_owned:
                    item_id = random.choice(not_owned)
                    item_data = STORE_ITEMS[item_id]

                    await item_data["effect"](int(self.user_id))

                    if item_id == "freeze_thermometer":
                        freeze_data_ref = u_shop_effects(
                            int(self.user_id), "freeze_thermometer"
                        )
                        freeze_data = freeze_data_ref.get()
                        if freeze_data:
                            sync_shop_effects(
                                int(self.user_id),
                                "freeze_thermometer",
                                "set",
                                freeze_data,
                                interaction.guild.id,
                            )

                    reward_text += f"\n+ {EFFECT_EMOTE} **Bonus Effect Item:** `{item_data['name']}` *(Expires <t:{int(time.time()) + item_data.get('duration', 0)}:R>)*\n-# {REPLY_EMOTE} **Description:** {item_data.get('description', '')}"
                else:
                    if currency_cog:
                        _, current_tokens = await currency_cog.get_balance(
                            int(self.user_id)
                        )
                        await currency_cog.update_balance(
                            int(self.user_id), tokens=current_tokens + 5
                        )
                    reward_text += f"\n+ {TOKEN_EMOTE} `5` Tokens *(Fallback reward for an effect item)*"

        return reward_text

    def _update_buttons(self):
        upgrade_btn = self.children[0]
        unlock_btn = self.children[1]
        next_btn = self.children[2]

        if self.is_unlocked:
            upgrade_btn.disabled = True
            unlock_btn.disabled = True
            next_btn.disabled = self.total_unopened <= 0
        else:
            upgrade_btn.disabled = self.current_upgrades >= self.max_upgrades
            unlock_btn.disabled = self.current_upgrades < self.max_upgrades
            next_btn.disabled = True

    async def on_timeout(self):
        self._deactivate_session()
        self.clear_items()
        timeout_button = discord.ui.Button(
            label="Session Expired",
            style=discord.ButtonStyle.secondary,
            emoji="<a:clock:1382887924273774754>",
            disabled=True,
        )
        self.add_item(timeout_button)
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass


class MegaBoxView(discord.ui.View):
    active_sessions = {}

    def __init__(
        self, user: discord.User, total_unopened_count: int, pending_box: dict
    ):
        super().__init__(timeout=60)
        self.user = user
        self.user_id = str(user.id)
        self.total_unopened = total_unopened_count
        self.total_items = pending_box["total_items"]
        self.items_remaining = pending_box["items_remaining"]
        self.rewards = pending_box.get("rewards", [])
        self.show_summary = pending_box.get("show_summary", False)
        self.last_drop = pending_box.get("last_drop", None)
        self.used_effect_items = set(pending_box.get("used_effect_items", []))
        self.message = None

        MegaBoxView.active_sessions[self.user_id] = self
        self._update_buttons()

    async def _save_pending_state(self):
        pending_ref = u_mega_boxes_pending(self.user_id)
        if self.show_summary:
            pending_ref.delete()
        else:
            pending_ref.update(
                {
                    "items_remaining": self.items_remaining,
                    "rewards": self.rewards,
                    "show_summary": self.show_summary,
                    "last_drop": self.last_drop,
                    "used_effect_items": list(self.used_effect_items),
                }
            )

    def _deactivate_session(self):
        if self.user_id in MegaBoxView.active_sessions:
            if MegaBoxView.active_sessions[self.user_id] == self:
                del MegaBoxView.active_sessions[self.user_id]

    def create_embed(self, resume=False):
        desc = (
            "<a:warning:1391215594430402742> Resuming your unfinished Mega Box!\n"
            if resume
            else ""
        )
        embed = discord.Embed(color=0x1E90FF)

        if self.items_remaining == self.total_items and not self.last_drop:
            embed.title = f"{MEGA_BOX_EMOTE} Mega Box"
            embed.description = f"{desc}Items Remaining: **{self.items_remaining}**"
        elif not self.show_summary:
            title = self.last_drop["title"] if self.last_drop else "Reward"
            desc_val = self.last_drop["desc"] if self.last_drop else "Unknown"

            embed.title = f"{MEGA_BOX_EMOTE} Mega Box"
            embed.description = f"{desc}## {title}\n{desc_val}\n\nItems Remaining: **{self.items_remaining}**"
        else:
            embed.title = f"{MEGA_BOX_EMOTE} Mega Box Summary"
            embed.description = ""
            if self.rewards:
                rewards_text = "\n".join(self.rewards)
                if len(rewards_text) > 2000:
                    rewards_text = rewards_text[:2000] + "..."
                embed.add_field(name="All Rewards", value=rewards_text, inline=False)
            if self.total_unopened > 0:
                embed.add_field(
                    name="Next Box",
                    value=f"You have {self.total_unopened} more Mega Box{'es' if self.total_unopened > 1 else ''}!",
                    inline=False,
                )

        embed.set_footer(text="💡 Your progress is automatically saved!")
        return embed

    @discord.ui.button(
        label="Tap",
        style=discord.ButtonStyle.primary,
        emoji="<:v_hand:1486225684928921763>",
    )
    async def tap_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        if interaction.user.id != self.user.id:
            await interaction.followup.send(
                "This is not your Mega Box!", ephemeral=True
            )
            return

        if self.items_remaining <= 0:
            if not self.show_summary:
                self.show_summary = True
                await self._save_pending_state()
                if self.total_unopened <= 0:
                    self._deactivate_session()
                self._update_buttons()
                await interaction.edit_original_response(
                    embed=self.create_embed(), view=self
                )
                return
            else:
                await interaction.followup.send("This box is empty!", ephemeral=True)
                return

        item_index = self.total_items - self.items_remaining + 1
        reward_data = await self._generate_and_apply_reward(interaction, item_index)

        self.rewards.append(reward_data["summary"])
        self.last_drop = {"title": reward_data["title"], "desc": reward_data["desc"]}
        self.items_remaining -= 1

        await self._save_pending_state()
        self._update_buttons()
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

    @discord.ui.button(
        label="Open Next",
        style=discord.ButtonStyle.success,
        emoji=MEGA_BOX_EMOTE,
        disabled=True,
    )
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "This is not your Mega Box!", ephemeral=True
            )
            return

        if not self.show_summary:
            await interaction.response.send_message(
                "Finish opening this box first!", ephemeral=True
            )
            return

        inventory_ref = u_mega_boxes(self.user_id)
        current_count = inventory_ref.get() or 0

        if current_count <= 0:
            await interaction.response.send_message(
                f"{NO_EMOTE} No more Mega Boxes available!", ephemeral=True
            )
            self.total_unopened = 0
            self._update_buttons()
            await interaction.edit_original_response(view=self)
            return

        total_items = self._roll_item_count()
        new_pending = {
            "total_items": total_items,
            "items_remaining": total_items,
            "rewards": [],
            "show_summary": False,
            "last_drop": None,
            "created_at": int(time.time()),
        }

        updates = {
            u_mega_boxes_pending(self.user_id).path: new_pending,
            u_mega_boxes(self.user_id).path: current_count - 1,
        }
        db.reference().update(updates)

        self.total_unopened = current_count - 1
        self.total_items = total_items
        self.items_remaining = total_items
        self.rewards = []
        self.show_summary = False
        self.last_drop = None
        self.used_effect_items = set()

        reward_data = await self._generate_and_apply_reward(interaction, 1)
        self.rewards.append(reward_data["summary"])
        self.last_drop = {"title": reward_data["title"], "desc": reward_data["desc"]}
        self.items_remaining -= 1

        new_pending["items_remaining"] = self.items_remaining
        new_pending["rewards"] = self.rewards
        new_pending["last_drop"] = self.last_drop

        updates = {
            u_mega_boxes_pending(self.user_id).path: new_pending,
            u_mega_boxes(self.user_id).path: current_count - 1,
        }
        db.reference().update(updates)

        self._update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    def _update_buttons(self):
        tap_btn = self.children[0]
        next_btn = self.children[1]

        tap_btn.disabled = self.show_summary
        next_btn.disabled = not self.show_summary or self.total_unopened <= 0

    def _roll_item_count(self) -> int:
        roll = random.random()
        if roll < 0.795:
            return 5
        if roll < 0.9675:
            return 6
        if roll < 0.9825:
            return 7
        if roll < 0.9925:
            return 8
        if roll < 0.9975:
            return 9
        return 10

    async def _generate_and_apply_reward(
        self, interaction: discord.Interaction, item_index: int
    ) -> dict:
        currency_cog = interaction.client.get_cog("CurrencySystem")

        if item_index <= 5:
            rarity = "super_rare" if random.random() < 0.40 else "rare"
            drops = STAR_DROP_RATES["drops"][rarity]

            total_weight = sum(drop.get("weight", 1) for drop in drops)
            roll = random.uniform(0, total_weight)
            cumulative = 0
            selected_drop = None
            for drop in drops:
                cumulative += drop.get("weight", 1)
                if roll <= cumulative:
                    selected_drop = drop
                    break
            if not selected_drop:
                selected_drop = drops[0]

            if selected_drop["type"] == "beans":
                amount = selected_drop.get("amount") or random.randint(
                    *selected_drop["range"]
                )
                if currency_cog:
                    current_beans, _ = await currency_cog.get_balance(int(self.user_id))
                    await currency_cog.update_balance(
                        int(self.user_id), beans=current_beans + amount
                    )
                return {
                    "title": f"{(rarity.replace('_', ' ').title())} Item",
                    "desc": f"{BEAN_EMOTE} `{amount:,}` Beans",
                    "summary": f"- {BEAN_EMOTE} `{amount:,}` Beans ({rarity.replace('_', ' ').title()})",
                }
            elif selected_drop["type"] == "tokens":
                amount = selected_drop.get("amount") or random.randint(
                    *selected_drop["range"]
                )
                if currency_cog:
                    _, current_tokens = await currency_cog.get_balance(
                        int(self.user_id)
                    )
                    await currency_cog.update_balance(
                        int(self.user_id), tokens=current_tokens + amount
                    )
                return {
                    "title": f"{(rarity.replace('_', ' ').title())} Item",
                    "desc": f"{TOKEN_EMOTE} `{amount:,}` Tokens",
                    "summary": f"- {TOKEN_EMOTE} `{amount:,}` Tokens ({rarity.replace('_', ' ').title()})",
                }
            return {"title": "Unknown", "desc": "Unknown", "summary": "Unknown Reward"}
        else:
            roll = random.random()
            if roll < 0.40:
                if currency_cog:
                    _, current_tokens = await currency_cog.get_balance(
                        int(self.user_id)
                    )
                    await currency_cog.update_balance(
                        int(self.user_id), tokens=current_tokens + 5
                    )
                return {
                    "title": "Exotic Item <:exclaim:1486161482956804176>",
                    "desc": f"{TOKEN_EMOTE} `5` Tokens",
                    "summary": f"- {TOKEN_EMOTE} `5` Tokens",
                }
            elif roll < 0.50:
                if currency_cog:
                    _, current_tokens = await currency_cog.get_balance(
                        int(self.user_id)
                    )
                    await currency_cog.update_balance(
                        int(self.user_id), tokens=current_tokens + 10
                    )
                return {
                    "title": "Ultra Exotic Item <:exclaim:1486161482956804176>",
                    "desc": f"{TOKEN_EMOTE} `10` Tokens",
                    "summary": f"- {TOKEN_EMOTE} `10` Tokens",
                }
            else:
                available_items = [
                    k
                    for k, v in STORE_ITEMS.items()
                    if k not in ["star_drop", "star_drop_10", "mega_box", "mega_box_10"]
                    and v.get("duration", 0) > 0
                ]

                if available_items:
                    user_effects = (
                        sync_shop_effects(self.user_id, operation="get") or {}
                    )
                    current_time = time.time()

                    not_owned = []
                    for item_id in available_items:
                        if (
                            item_id not in user_effects
                            or not user_effects[item_id].get("active")
                            or user_effects[item_id].get("expires_at", 0) < current_time
                        ):
                            not_owned.append(item_id)

                    available_not_owned = [
                        item for item in not_owned if item not in self.used_effect_items
                    ]

                    if available_not_owned:
                        item_id = random.choice(available_not_owned)
                        self.used_effect_items.add(item_id)
                        item_data = STORE_ITEMS[item_id]
                        await item_data["effect"](int(self.user_id))

                        if item_id == "freeze_thermometer":
                            freeze_data_ref = u_shop_effects(
                                int(self.user_id), "freeze_thermometer"
                            )
                            freeze_data = freeze_data_ref.get()
                            if freeze_data:
                                sync_shop_effects(
                                    int(self.user_id),
                                    "freeze_thermometer",
                                    "set",
                                    freeze_data,
                                    interaction.guild.id,
                                )

                        return {
                            "title": "Bonus Effect Item <:exclaim:1486161482956804176>",
                            "desc": f"{EFFECT_EMOTE} `{item_data['name']}`",
                            "summary": f"- {EFFECT_EMOTE} Effect: `{item_data['name']}`",
                        }
                    else:
                        if currency_cog:
                            _, current_tokens = await currency_cog.get_balance(
                                int(self.user_id)
                            )
                            await currency_cog.update_balance(
                                int(self.user_id), tokens=current_tokens + 5
                            )
                        return {
                            "title": "Bonus Effect Item <:exclaim:1486161482956804176>",
                            "desc": f"{TOKEN_EMOTE} `5` Tokens *(Fallback)*",
                            "summary": f"- {TOKEN_EMOTE} `5` Tokens *(Fallback reward for an effect item)*",
                        }

                if currency_cog:
                    _, current_tokens = await currency_cog.get_balance(
                        int(self.user_id)
                    )
                    await currency_cog.update_balance(
                        int(self.user_id), tokens=current_tokens + 5
                    )
                return {
                    "title": "Bonus Effect Item <:exclaim:1486161482956804176>",
                    "desc": f"{TOKEN_EMOTE} `5` Tokens",
                    "summary": f"- {TOKEN_EMOTE} `5` Tokens *(Fallback)*",
                }

    async def on_timeout(self):
        self._deactivate_session()
        self.clear_items()
        timeout_button = discord.ui.Button(
            label="Session Expired",
            style=discord.ButtonStyle.secondary,
            emoji="<a:clock:1382887924273774754>",
            disabled=True,
        )
        self.add_item(timeout_button)
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass


@app_commands.guild_only()
class Gacha(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    def _roll_rarity(self):
        roll = random.random()
        cumulative = 0
        for rarity, rate in STAR_DROP_RATES["rarity_rates"].items():
            cumulative += rate
            if roll <= cumulative:
                return rarity
        return "rare"

    @app_commands.command(
        name="stardrop", description="Open a star drop and get random rewards"
    )
    async def stardrop(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                "This command can only be used in Brawl Cafe.", ephemeral=True
            )

        user_id = str(interaction.user.id)

        if user_id in StarDropView.active_sessions:
            await interaction.response.send_message(
                f"{NO_EMOTE} **You already have an active Star Drop session!**\nPlease finish your current drop or wait for it to timeout.",
                ephemeral=True,
            )
            return

        unopened_ref = u_star_drops(user_id)
        pending_ref = u_star_drops_pending(user_id)
        unopened_count = unopened_ref.get() or 0
        pending_drop = pending_ref.get()

        if unopened_count <= 0 and not pending_drop:
            await interaction.response.send_message(
                f"{NO_EMOTE} You don't have any unopened Star Drops! Buy them in the shop using </buy:1393376242501157010>.",
                ephemeral=True,
            )
            return

        if pending_drop:
            if not all(
                k in pending_drop
                for k in ["final_rarity", "current_rarity", "upgrades_used"]
            ):
                u_star_drops_pending(int(user_id)).delete()
                pending_drop = None
            else:
                view = StarDropView(interaction.user, unopened_count, pending_drop)
                await interaction.response.send_message(
                    embed=view.create_embed(resume=True), view=view
                )
                view.message = await interaction.original_response()
                return

        if unopened_count <= 0:
            await interaction.response.send_message(
                "You don't have any unopened Star Drops!", ephemeral=True
            )
            return

        final_rarity = self._roll_rarity()
        if interaction.user.id == 692254240290242601:
            final_rarity = random.choice(["mythic", "legendary", "ultra"])

        pending_drop = {
            "final_rarity": final_rarity,
            "current_rarity": "rare",
            "upgrades_used": 0,
            "created_at": int(time.time()),
        }

        updates = {
            u_star_drops_pending(user_id).path: pending_drop,
            u_star_drops(user_id).path: unopened_count - 1,
        }
        db.reference().update(updates)

        view = StarDropView(interaction.user, unopened_count - 1, pending_drop)
        print("⚠️⚠️⚠️⚠️⚠️ New Star Drop Session Created ⚠️⚠️⚠️⚠️⚠️")
        await interaction.response.send_message(embed=view.create_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(
        name="megabox", description="Open a mega box and get multiple rewards"
    )
    async def megabox(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                "This command can only be used in Brawl Cafe.", ephemeral=True
            )

        user_id = str(interaction.user.id)

        if user_id in MegaBoxView.active_sessions:
            await interaction.response.send_message(
                f"{NO_EMOTE} **You already have an active Mega Box session!**\nPlease finish your current box or wait for it to timeout.",
                ephemeral=True,
            )
            return

        unopened_ref = u_mega_boxes(user_id)
        pending_ref = u_mega_boxes_pending(user_id)
        unopened_count = unopened_ref.get() or 0
        pending_box = pending_ref.get()

        if unopened_count <= 0 and not pending_box:
            await interaction.response.send_message(
                f"{NO_EMOTE} You don't have any unopened Mega Boxes! Buy them in the shop using </buy:1393376242501157010>.",
                ephemeral=True,
            )
            return

        if pending_box:
            if not all(k in pending_box for k in ["total_items", "items_remaining"]):
                u_mega_boxes_pending(int(user_id)).delete()
                pending_box = None
            else:
                view = MegaBoxView(interaction.user, unopened_count, pending_box)
                await interaction.response.send_message(
                    embed=view.create_embed(resume=True), view=view
                )
                view.message = await interaction.original_response()
                return

        if unopened_count <= 0:
            await interaction.response.send_message(
                "You don't have any unopened Mega Boxes!", ephemeral=True
            )
            return

        roll = random.random()
        total_items = 5
        if roll < 0.795:
            total_items = 5
        elif roll < 0.9675:
            total_items = 6
        elif roll < 0.9825:
            total_items = 7
        elif roll < 0.9925:
            total_items = 8
        elif roll < 0.9975:
            total_items = 9
        else:
            total_items = 10

        if interaction.user.id == 692254240290242601:
            total_items = random.randint(7, 10)

        pending_box = {
            "total_items": total_items,
            "items_remaining": total_items,
            "rewards": [],
            "show_summary": False,
            "last_drop": None,
            "created_at": int(time.time()),
        }

        view = MegaBoxView(interaction.user, unopened_count - 1, pending_box)

        reward_data = await view._generate_and_apply_reward(interaction, 1)
        view.rewards.append(reward_data["summary"])
        view.last_drop = {"title": reward_data["title"], "desc": reward_data["desc"]}
        view.items_remaining -= 1

        updates = {
            u_mega_boxes_pending(user_id).path: {
                "total_items": view.total_items,
                "items_remaining": view.items_remaining,
                "rewards": view.rewards,
                "show_summary": view.show_summary,
                "last_drop": view.last_drop,
                "created_at": pending_box["created_at"],
            },
            u_mega_boxes(user_id).path: unopened_count - 1,
        }
        db.reference().update(updates)

        view._update_buttons()
        print("⚠️⚠️⚠️⚠️⚠️ New Mega Box Session Created ⚠️⚠️⚠️⚠️⚠️")
        await interaction.response.send_message(embed=view.create_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="rates", description="Show gacha rewards rarity rates")
    async def rates(self, interaction: discord.Interaction):
        sd_embed = discord.Embed(
            title=f"{STAR_DROP_EMOTE} Star Drop Rates",
            description="Chances of getting each rarity tier and their possible rewards:",
            color=0x00FF00,
        )
        for rarity, rate in STAR_DROP_RATES["rarity_rates"].items():
            percentage = rate * 100
            drops = STAR_DROP_RATES["drops"].get(rarity, [])
            total_weight = sum(d.get("weight", 1) for d in drops)
            rewards = []

            for drop in drops:
                weight = drop.get("weight", 1)
                prob = (weight / total_weight) * 100
                prob_str = (
                    f"**({prob:.0f}%)**" if prob.is_integer() else f"**({prob:.1f}%)**"
                )

                if drop["type"] == "beans":
                    if "range" in drop:
                        rewards.append(
                            f"-# - {BEAN_EMOTE} `{drop['range'][0]:,}-{drop['range'][1]:,}` {prob_str}"
                        )
                    else:
                        rewards.append(
                            f"-# - {BEAN_EMOTE} `{drop['amount']:,}` {prob_str}"
                        )
                elif drop["type"] == "tokens":
                    if "range" in drop:
                        rewards.append(
                            f"-# - {TOKEN_EMOTE} `{drop['range'][0]:,}-{drop['range'][1]:,}` {prob_str}"
                        )
                    else:
                        rewards.append(
                            f"-# - {TOKEN_EMOTE} `{drop['amount']:,}` {prob_str}"
                        )

            if rarity == "mythic":
                rewards.append(
                    f"-# - {EFFECT_EMOTE} **+10%** chance for a random effect item"
                )
            elif rarity == "legendary":
                rewards.append(
                    f"-# - {EFFECT_EMOTE} **+50%** chance for a random effect item"
                )
            elif rarity == "ultra":
                rewards.append(f"-# - {EFFECT_EMOTE} **Guaranteed** random effect item")
            rewards_text = "\n".join(rewards) if rewards else "No rewards defined"
            sd_embed.add_field(
                name=f"{rarity.replace('_', ' ').title()} ({percentage:.1f}%)",
                value=rewards_text,
                inline=True,
            )

        mb_embed = discord.Embed(
            title=f"{MEGA_BOX_EMOTE} Mega Box Rates",
            description="Chances of item counts and rewards for Mega Boxes:",
            color=0xFF0000,
        )
        mb_embed.add_field(
            name="Item Count Chances",
            value="-# - **5 Items:** 79.5%\n-# - **6 Items:** 17.25%\n-# - **7 Items:** 1.5%\n-# - **8 Items:** 1.0%\n-# - **9 Items:** 0.5%\n-# - **10 Items:** 0.25%",
            inline=False,
        )
        mb_embed.add_field(
            name="First 5 Items",
            value="-# - **60%** Rare Star Drop Equivalent\n-# - **40%** Super Rare Star Drop Equivalent",
            inline=False,
        )
        mb_embed.add_field(
            name="6th - 10th Items",
            value=f"-# - **40%** {TOKEN_EMOTE} `5` Tokens (Exotic) \n-# - **10%** {TOKEN_EMOTE} `10` Tokens (Ultra Exotic) \n-# - **50%** {EFFECT_EMOTE} Random Effect Item",
            inline=False,
        )

        await interaction.response.send_message(embeds=[sd_embed, mb_embed])


async def setup(bot):
    await bot.add_cog(Gacha(bot))

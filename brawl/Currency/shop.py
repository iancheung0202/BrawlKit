import asyncio
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency.db import (
    g_shops,
    g_thermometer,
    sync_sell_alarm,
    sync_shop_effects,
    u_customization,
    u_daily_chat_earnings,
    u_mega_boxes,
    u_mega_boxes_purchases,
    u_pin_message,
    u_star_drops,
    u_star_drops_purchases,
)
from brawl.Currency.helper import (
    BEAN_EMOTE,
    EFFECT_EMOTE,
    MAIN_GUILD_ID,
    MEGA_BOX_EMOTE,
    NO_EMOTE,
    PERFECT_BREW_CHANCE,
    REPLY_EMOTE,
    ROAST_TYPES,
    STAR_DROP_EMOTE,
    STORE_ITEMS,
    TOKEN_EMOTE,
    ULTRA_TIER_ROLE_ID,
    YES_EMOTE,
    get_current_date_key,
    get_next_day_timestamp,
)
from brawl.Currency.pagination import BasePaginationView
from brawl.Currency.quests import update_quest


class FilterSelection(discord.ui.Select):
    def __init__(
        self,
        default=None,
        initial_author=None,
        sort_default="sort by cost (high to low)",
    ):
        self.initial_author = initial_author
        self.sort_default = sort_default
        options = []
        filterOptions = [
            "All Items",
            "Cost Beans",
            "Cost Tokens",
            "Effect Items",
            "Supercell Items",
        ]
        filterOptionsEmoji = [
            "<:Information:855023058255478794>",
            BEAN_EMOTE,
            TOKEN_EMOTE,
            EFFECT_EMOTE,
            "<:account:1486161374601154601>",
        ]
        # Default to "All Items" if no filter is selected
        default_filter = default if default else "All Items"
        for i in filterOptions:
            options.append(
                discord.SelectOption(
                    label=i,
                    emoji=filterOptionsEmoji[filterOptions.index(i)],
                    default=(i == default_filter),
                )
            )

        super().__init__(
            placeholder="Filter items...",
            max_values=1,
            min_values=1,
            options=options,
            custom_id="filterselection",
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        ref = g_shops(interaction.guild.id)
        rewards = ref.get() or []

        filter_map = {
            "Cost Beans": "beans",
            "Cost Tokens": "tokens",
            "Effect Items": "effect_items",
            "Supercell Items": "supercell",
            "All Items": None,
        }
        filter_type = filter_map.get(self.values[0])

        sort_by = "cost" if "cost" in self.sort_default else "name"
        reverse = "high to low" in self.sort_default or "z-a" in self.sort_default

        pages = await get_shop_embeds(
            interaction,
            rewards,
            empty_condition=(len(rewards) == 0),
            sort_by=sort_by,
            reverse=reverse,
            filter_type=filter_type,
        )

        if interaction.user.guild_permissions.administrator:
            view = Panel(
                sort_default=self.sort_default,
                filter_default=self.values[0],
                pages=pages,
                initial_author=self.initial_author,
            )
        else:
            view = SortSelectionView(
                sort_default=self.sort_default,
                filter_default=self.values[0],
                pages=pages,
                initial_author=self.initial_author,
            )

        view.page = 0
        view.update_buttons()
        await interaction.response.edit_message(embed=pages[0], view=view)
        view.message = interaction.message


class SortSelection(discord.ui.Select):
    def __init__(
        self,
        sort_default="sort by cost (high to low)",
        filter_default=None,
        initial_author=None,
    ):
        self.initial_author = initial_author
        self.filter_default = filter_default
        options = []
        sortOptions = [
            "sort by cost (low to high)",
            "sort by cost (high to low)",
            "sort by name (a-z)",
            "sort by name (z-a)",
        ]
        sortOptionsEmoji = [
            "<:price_ascending:1346329079145562112>",
            "<:price_descending:1346329080462577725>",
            "<:name_ascending:1346329053455585324>",
            "<:name_descending:1346329054634053703>",
        ]
        for i in sortOptions:
            options.append(
                discord.SelectOption(
                    label=i,
                    emoji=sortOptionsEmoji[sortOptions.index(i)],
                    default=(i == sort_default),
                )
            )

        super().__init__(
            placeholder="Choose the Sorting",
            max_values=1,
            min_values=1,
            options=options,
            custom_id="sortselection",
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        ref = g_shops(interaction.guild.id)
        rewards = ref.get() or []
        sort_by = "cost" if "cost" in self.values[0] else "name"
        reverse = "high to low" in self.values[0] or "z-a" in self.values[0]
        filter_map = {
            "Cost Beans": "beans",
            "Cost Tokens": "tokens",
            "Effect Items": "effect_items",
            "Supercell Items": "supercell",
            "All Items": None,
        }
        filter_type = (
            filter_map.get(self.filter_default) if self.filter_default else None
        )

        pages = await get_shop_embeds(
            interaction,
            rewards,
            empty_condition=(len(rewards) == 0),
            sort_by=sort_by,
            reverse=reverse,
            filter_type=filter_type,
        )

        if interaction.user.guild_permissions.administrator:
            view = Panel(
                sort_default=self.values[0],
                filter_default=self.filter_default,
                pages=pages,
                initial_author=self.initial_author,
            )
        else:
            view = SortSelectionView(
                sort_default=self.values[0],
                filter_default=self.filter_default,
                pages=pages,
                initial_author=self.initial_author,
            )

        view.page = 0
        view.update_buttons()
        await interaction.response.edit_message(embed=pages[0], view=view)
        view.message = interaction.message


class SortSelectionView(BasePaginationView):
    def __init__(
        self,
        sort_default="sort by cost (high to low)",
        filter_default=None,
        pages=None,
        initial_author=None,
        timeout=300,
    ):
        super().__init__(pages=pages, initial_author=initial_author, timeout=timeout)
        self.sort_default = sort_default
        self.filter_default = filter_default
        self.add_item(
            SortSelection(
                sort_default=sort_default,
                filter_default=filter_default,
                initial_author=self.initial_author,
            )
        )
        self.add_item(
            FilterSelection(
                default=filter_default,
                initial_author=self.initial_author,
                sort_default=sort_default,
            )
        )
        self.update_buttons()


class Panel(BasePaginationView):
    def __init__(
        self,
        sort_default="sort by cost (high to low)",
        filter_default=None,
        pages=None,
        initial_author=None,
    ):
        super().__init__(pages=pages, initial_author=initial_author, timeout=300)
        self.sort_default = sort_default
        self.filter_default = filter_default
        self.add_item(
            SortSelection(
                sort_default=sort_default,
                filter_default=filter_default,
                initial_author=self.initial_author,
            )
        )
        self.add_item(
            FilterSelection(
                default=filter_default,
                initial_author=self.initial_author,
                sort_default=sort_default,
            )
        )
        self.update_buttons()

    @discord.ui.button(
        label="Add Reward",
        style=discord.ButtonStyle.green,
        custom_id="addreward",
        row=0,
    )
    async def add_reward(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Missing Administrator permission.", ephemeral=True
            )
        modal = RewardModal("add", interaction.guild.id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if hasattr(modal, "pages") and modal.pages is not None:
            view = (
                Panel(
                    sort_default=self.sort_default,
                    filter_default=self.filter_default,
                    pages=modal.pages,
                    initial_author=interaction.user,
                )
                if interaction.user.guild_permissions.administrator
                else SortSelectionView(
                    sort_default=self.sort_default,
                    filter_default=self.filter_default,
                    pages=modal.pages,
                    initial_author=interaction.user,
                )
            )
            view.page = 0
            view.update_buttons()
            await interaction.edit_original_response(embed=modal.pages[0], view=view)
        await modal.on_submit_interaction.response.send_message(
            embed=modal.update, ephemeral=True
        )

    @discord.ui.button(
        label="Remove Reward",
        style=discord.ButtonStyle.red,
        custom_id="removereward",
        row=0,
    )
    async def remove_reward(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Missing Administrator permission.", ephemeral=True
            )
        modal = RewardModal("remove", interaction.guild.id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if hasattr(modal, "pages") and modal.pages is not None:
            view = (
                Panel(
                    sort_default=self.sort_default,
                    filter_default=self.filter_default,
                    pages=modal.pages,
                    initial_author=interaction.user,
                )
                if interaction.user.guild_permissions.administrator
                else SortSelectionView(
                    sort_default=self.sort_default,
                    filter_default=self.filter_default,
                    pages=modal.pages,
                    initial_author=interaction.user,
                )
            )
            view.page = 0
            view.update_buttons()
            await interaction.edit_original_response(embed=modal.pages[0], view=view)
        await modal.on_submit_interaction.response.send_message(
            embed=modal.update, ephemeral=True
        )

    @discord.ui.button(
        label="Edit Cost", style=discord.ButtonStyle.grey, custom_id="editcost", row=0
    )
    async def edit_cost(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Missing Administrator permission.", ephemeral=True
            )
        modal = RewardModal("edit_cost", interaction.guild.id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.pages is not None:
            view = (
                Panel(
                    sort_default=self.sort_default,
                    filter_default=self.filter_default,
                    pages=modal.pages,
                    initial_author=interaction.user,
                )
                if interaction.user.guild_permissions.administrator
                else SortSelectionView(
                    sort_default=self.sort_default,
                    filter_default=self.filter_default,
                    pages=modal.pages,
                    initial_author=interaction.user,
                )
            )
            view.page = 0
            view.update_buttons()
            await interaction.edit_original_response(embed=modal.pages[0], view=view)
        await modal.on_submit_interaction.response.send_message(
            embed=modal.update, ephemeral=True
        )

    @discord.ui.button(
        label="Edit Stock", style=discord.ButtonStyle.grey, custom_id="editstock", row=0
    )
    async def edit_stock(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Missing Administrator permission.", ephemeral=True
            )
        modal = RewardModal("edit_stock", interaction.guild.id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.pages is not None:
            view = (
                Panel(
                    sort_default=self.sort_default,
                    filter_default=self.filter_default,
                    pages=modal.pages,
                    initial_author=interaction.user,
                )
                if interaction.user.guild_permissions.administrator
                else SortSelectionView(
                    sort_default=self.sort_default,
                    filter_default=self.filter_default,
                    pages=modal.pages,
                    initial_author=interaction.user,
                )
            )
            view.page = 0
            view.update_buttons()
            await interaction.edit_original_response(embed=modal.pages[0], view=view)
        await modal.on_submit_interaction.response.send_message(
            embed=modal.update, ephemeral=True
        )


class RewardModal(discord.ui.Modal):
    def __init__(self, operation: str, guild_id: int):
        self.operation = operation  # add, remove, edit_cost, edit_stock
        self.guild_id = guild_id
        super().__init__(title=self._get_title())
        self._add_inputs()
        self.update = None
        self.pages = None
        self.on_submit_interaction = None

    def _get_title(self) -> str:
        titles = {
            "add": "Add a Custom Reward",
            "remove": "Remove a Custom Reward",
            "edit_cost": "Edit Reward Cost",
            "edit_stock": "Edit Reward Stock",
        }
        return titles.get(self.operation, "Reward Management")

    def _add_inputs(self):
        self.name_input = discord.ui.TextInput(
            label="Role ID / Reward Title",
            style=discord.TextStyle.short,
            placeholder="Role ID or Reward Title",
            required=True,
            max_length=50,
        )
        self.add_item(self.name_input)

        if self.operation == "add":
            self.desc_input = discord.ui.TextInput(
                label="Description / Perk",
                style=discord.TextStyle.short,
                placeholder="Short description",
                required=True,
                max_length=150,
            )
            self.cost_input = discord.ui.TextInput(
                label="Cost",
                style=discord.TextStyle.short,
                placeholder="Integer cost (e.g. 100 beans, 5 tokens)",
                required=True,
                max_length=15,
            )
            self.multiple_input = discord.ui.TextInput(
                label="Enable multiple purchases? (Titles only)",
                style=discord.TextStyle.short,
                placeholder="yes or no",
                required=False,
                max_length=3,
            )
            self.stock_input = discord.ui.TextInput(
                label="Stock Count (optional)",
                style=discord.TextStyle.short,
                placeholder="Leave blank for unlimited",
                required=False,
                max_length=10,
            )
            self.add_item(self.desc_input)
            self.add_item(self.cost_input)
            self.add_item(self.multiple_input)
            self.add_item(self.stock_input)
        elif self.operation == "edit_cost":
            self.cost_input = discord.ui.TextInput(
                label="New Cost",
                style=discord.TextStyle.short,
                placeholder="Integer cost (e.g. 100 beans, 5 tokens)",
                required=True,
                max_length=15,
            )
            self.add_item(self.cost_input)
        elif self.operation == "edit_stock":
            self.stock_input = discord.ui.TextInput(
                label="New Stock Count",
                style=discord.TextStyle.short,
                placeholder="Integer stock count or blank for unlimited",
                required=False,
                max_length=10,
            )
            self.add_item(self.stock_input)

    async def on_submit(self, interaction: discord.Interaction):
        ref = g_shops(self.guild_id)
        rewards = ref.get() or []

        if self.operation == "add":
            await self._handle_add(interaction, rewards, ref)
        elif self.operation == "remove":
            await self._handle_remove(interaction, rewards, ref)
        elif self.operation == "edit_cost":
            await self._handle_edit_cost(interaction, rewards, ref)
        elif self.operation == "edit_stock":
            await self._handle_edit_stock(interaction, rewards, ref)

    async def _send_response(self, interaction, rewards, message: str, is_error: bool):
        """Send standardized response."""
        self.update = discord.Embed(
            description=message,
            color=discord.Color.red() if is_error else discord.Color.green(),
        )
        self.pages = await get_shop_embeds(interaction, rewards, False)
        self.on_submit_interaction = interaction
        self.stop()

    async def _handle_add(self, interaction, rewards, ref):
        if any(str(item[0]) == str(self.name_input.value) for item in rewards):
            await self._send_response(
                interaction, rewards, f"{NO_EMOTE} Duplicate reward entry found.", True
            )
            return
        try:
            cost_int = int(self.cost_input.value.replace(",", "").split(" ")[0].strip())
            currency_type = (
                "beans"
                if "bean" in self.cost_input.value.split(" ")[1].lower()
                else "tokens"
            )
            if cost_int <= 0:
                raise ValueError
        except:
            await self._send_response(
                interaction,
                rewards,
                f"{NO_EMOTE} Cost must be a positive integer.",
                True,
            )
            return
        try:
            stock_int = (
                int(self.stock_input.value.strip())
                if self.stock_input.value.strip()
                else -1
            )
            if stock_int < -1:
                raise ValueError
        except:
            await self._send_response(
                interaction,
                rewards,
                f"{NO_EMOTE} Stock must be a non-negative integer or blank for unlimited.",
                True,
            )
            return
        multiple_bool = (
            (self.multiple_input.value.lower() == "yes")
            if self.multiple_input.value
            else False
        )
        rewards.append(
            [
                str(self.name_input.value),
                str(self.desc_input.value),
                cost_int,
                currency_type,
                multiple_bool,
                stock_int,
            ]
        )
        ref.set(rewards)
        await self._send_response(
            interaction, rewards, "Reward added successfully.", False
        )

    async def _handle_remove(self, interaction, rewards, ref):
        item_to_remove = next(
            (item for item in rewards if str(item[0]) == str(self.name_input.value)),
            None,
        )
        if not item_to_remove:
            await self._send_response(
                interaction, rewards, f"{NO_EMOTE} Reward not found.", True
            )
            return
        rewards.remove(item_to_remove)
        ref.set(rewards)
        await self._send_response(
            interaction, rewards, "Reward removed successfully.", False
        )

    async def _handle_edit_cost(self, interaction, rewards, ref):
        try:
            cost_int = int(self.cost_input.value.replace(",", "").split(" ")[0].strip())
            currency_type = (
                "beans"
                if "bean" in self.cost_input.value.split(" ")[1].lower()
                else "tokens"
            )
            if cost_int <= 0:
                raise ValueError
        except:
            await self._send_response(
                interaction,
                rewards,
                f"{NO_EMOTE} Cost must be a positive integer.",
                True,
            )
            return
        for idx, item in enumerate(rewards):
            if str(item[0]) == str(self.name_input.value):
                rewards[idx][2] = cost_int
                rewards[idx][3] = currency_type
                ref.set(rewards)
                await self._send_response(
                    interaction, rewards, "Reward cost updated successfully.", False
                )
                return
        await self._send_response(
            interaction, rewards, f"{NO_EMOTE} Reward not found.", True
        )

    async def _handle_edit_stock(self, interaction, rewards, ref):
        try:
            stock_val = (
                int(self.stock_input.value.strip())
                if self.stock_input.value.strip()
                else -1
            )
            if stock_val < -1:
                raise ValueError
        except:
            await self._send_response(
                interaction,
                rewards,
                f"{NO_EMOTE} Stock must be a non-negative integer or blank for unlimited.",
                True,
            )
            return
        for idx, item in enumerate(rewards):
            if str(item[0]) == str(self.name_input.value):
                rewards[idx][5] = stock_val
                ref.set(rewards)
                await self._send_response(
                    interaction, rewards, "Reward stock updated successfully.", False
                )
                return
        await self._send_response(
            interaction, rewards, f"{NO_EMOTE} Reward not found.", True
        )


async def get_shop_embeds(
    interaction,
    item_list,
    empty_condition,
    sort_by="cost",
    reverse=True,
    filter_type=None,
):
    def categorize_item(item, is_effect=False):
        """Categorize item as 'beans', 'tokens', or 'effect'"""
        if is_effect:
            return "effect"
        currency = item[3]
        if currency.lower() == "tokens":
            return "tokens"
        return "beans"

    effect_items = []
    for item_id, item_data in STORE_ITEMS.items():
        price_parts = item_data["price"].split()
        cost = int(price_parts[0])
        currency = "tokens" if "token" in price_parts[1].lower() else "beans"
        if "star drop" in item_data["name"].lower():
            emote = STAR_DROP_EMOTE
        elif "mega box" in item_data["name"].lower():
            emote = MEGA_BOX_EMOTE
        else:
            emote = EFFECT_EMOTE
        effect_items.append(
            [
                item_data["name"],
                item_data["description"],
                cost,
                currency,
                True,  # Always allow multiple purchases for effect items
                -1,  # Unlimited stock
                item_id,  # Item ID (effect only)
                f"{emote}",  # Emoji (effect only)
                item_data.get("cooldown", 0),  # Cooldown in seconds (effect only)
            ]
        )

    formatted_custom_items = []
    for custom_item in item_list or []:
        if custom_item is None:
            continue
        if len(custom_item) == 6:
            formatted_custom_items.append(custom_item + [None, None, None])
        else:
            formatted_custom_items.append(custom_item)

    combined_items = effect_items + formatted_custom_items

    if filter_type:
        filtered_items = []
        for item in combined_items:
            is_effect = len(item) >= 9 and item[6] is not None
            if filter_type == "effect_items":
                if is_effect:
                    filtered_items.append(item)
            elif filter_type == "beans":
                if item[3].lower() == "beans":
                    filtered_items.append(item)
            elif filter_type == "tokens":
                if item[3].lower() == "tokens":
                    filtered_items.append(item)
            elif filter_type == "supercell":
                if "<:account:1486161374601154601>" in str(item[0]):
                    filtered_items.append(item)
        combined_items = filtered_items

    if not combined_items:
        return [
            discord.Embed(
                title="Shop is empty!",
                description="This server has no purchasable items yet.",
                color=discord.Color.red(),
            )
        ]

    sort_index = {"cost": 2, "name": 0}

    def key_func(x):
        if sort_by == "cost":
            cost = int(x[2])
            currency = x[3]
            return cost * 1000 if currency == "tokens" else cost
        else:
            if isinstance(x[0], int) or str(x[0]).isdigit():
                role = interaction.guild.get_role(int(x[0]))
                return role.name.lower() if role else ""
            return str(x[0]).lower()

    order_text = "Descending" if reverse else "Ascending"
    sort_text = "Cost" if sort_by == "cost" else "Name"

    filter_map = {
        "beans": "Bean Items",
        "tokens": "Token Items",
        "effect_items": "Effect Items",
        "supercell": "Supercell Items",
    }
    filter_text = (
        filter_map.get(filter_type, "All Items") if filter_type else "All Items"
    )

    sorted_items = sorted(combined_items, key=key_func, reverse=reverse)
    pages = []
    embed = discord.Embed(
        title=f"{interaction.guild.name} Server Store",
        description=(
            f"You can use {BEAN_EMOTE} `Starr Beans` or {TOKEN_EMOTE} `Starr Tokens` to purchase these items.\n"
            f"-# <:reply:1036792837821435976> *Use </balance:1393376242501157005> to check your balance and </buy:1393376242501157010> to purchase an item.*\n"
            f"-# <:reply:1036792837821435976> *🔄 indicates the item can be purchased multiple times.*\n"
            f"-# <:reply:1036792837821435976> *{EFFECT_EMOTE} Effect items have cooldowns between purchases.*"
        ),
        color=discord.Color.gold(),
    )

    for i, item in enumerate(sorted_items):
        count = i + 1
        stock_count = (
            f"\n> **Remaining:** {'<a:out_of_stock:1384990609584033812> ' if item[5] == 0 else ''}`{item[5]}`"
            if len(item) > 5 and item[5] != -1
            else ""
        )

        currency_type = item[3]
        currency_emote = BEAN_EMOTE if currency_type.lower() == "beans" else TOKEN_EMOTE
        is_effect_item = len(item) >= 9 and item[6] is not None

        if isinstance(item[0], int) or str(item[0]).isdigit():
            role = interaction.guild.get_role(int(item[0]))
            name = role.name if role else "Unknown Role"
            mention = role.mention if role else "N/A"
            embed.add_field(
                name=f"{count}  {currency_emote} {int(item[2]):,} {currency_type.title()} • {name} {'🔄' if (len(item) > 4 and item[4]) else ''}",
                value=f"> **Role:** {mention}\n> **Description:** {item[1]}{stock_count}",
                inline=False,
            )
        else:
            if is_effect_item:
                item_name = item[0]
                emoji = item[7] if len(item) > 7 else EFFECT_EMOTE
                cooldown_seconds = item[8] if len(item) > 8 else 0
                if cooldown_seconds == 0:
                    cooldown_text = "No cooldown"
                else:
                    days = cooldown_seconds // (24 * 3600)
                    hours = (cooldown_seconds % (24 * 3600)) // 3600
                    if days > 0:
                        if hours > 0:
                            cooldown_text = f"{days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''}"
                        else:
                            cooldown_text = f"{days} day{'s' if days != 1 else ''}"
                    elif hours > 0:
                        cooldown_text = f"{hours} hour{'s' if hours != 1 else ''}"
                    else:
                        minutes = cooldown_seconds // 60
                        cooldown_text = f"{minutes} minute{'s' if minutes != 1 else ''}"

                embed.add_field(
                    name=f"{count}  {currency_emote} {int(item[2]):,} {currency_type.title()} • {item_name} {emoji} {'🔄' if (len(item) > 4 and item[4]) else ''}",
                    value=f"> **Description:** {item[1]}{stock_count}\n> **Purchase Cooldown:** {cooldown_text}",
                    inline=False,
                )
            else:
                embed.add_field(
                    name=f"{count}  {currency_emote} {int(item[2]):,} {currency_type.title()} • {item[0]} {'🔄' if (len(item) > 4 and item[4]) else ''}",
                    value=f"> **Description:** {item[1]}{stock_count}",
                    inline=False,
                )

        if (count) % 5 == 0 or count == len(sorted_items):
            embed.set_footer(
                text=f"Showing {filter_text} • Sorted by {sort_text} in {order_text} order • Page {len(pages) + 1} of {((len(sorted_items) - 1) // 5) + 1}"
            )
            pages.append(embed)
            embed = discord.Embed(
                title=f"{interaction.guild.name} Server Currency Shop",
                description=(
                    f"You can use {BEAN_EMOTE} **Starr Beans** or {TOKEN_EMOTE} **Starr Tokens** to purchase these items.\n"
                    f"-# <:reply:1036792837821435976> *Use </balance:1393376242501157005> to check your balance and </buy:1393376242501157010> to purchase an item.*\n"
                    f"-# <:reply:1036792837821435976> *🔄 indicates the item can be purchased multiple times.*\n"
                    f"-# <:reply:1036792837821435976> *{EFFECT_EMOTE} Effect items have cooldowns between purchases.*"
                ),
                color=discord.Color.gold(),
            )

    return pages


global_purchase_queue = asyncio.Queue()
processing_global_queue = False


class PurchaseRequest:
    __slots__ = ("interaction", "item", "timestamp")

    def __init__(self, interaction, item):
        self.interaction = interaction
        self.item = item
        self.timestamp = time.time()


async def process_global_queue():
    global processing_global_queue
    processing_global_queue = True
    try:
        while not global_purchase_queue.empty():
            request = await global_purchase_queue.get()
            try:
                cog = request.interaction.client.get_cog("Shop")
                if cog:
                    await cog._process_purchase(request)
            except Exception as e:
                print(f"Error processing purchase: {e}")
            finally:
                global_purchase_queue.task_done()
    finally:
        processing_global_queue = False


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def economy(self):
        return self.bot.get_cog("CurrencySystem")

    @app_commands.command(
        name="pin", description="Pin a message using your Message Pin credits"
    )
    @app_commands.describe(message_link="Discord message link to pin")
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def pin(self, interaction: discord.Interaction, message_link: str):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )

        user_id = interaction.user.id

        ref = u_pin_message(user_id)
        data = ref.get() or {"count": 0}
        pin_count = data.get("count", 0)

        if pin_count <= 0:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You don't have any message pin credits! Purchase **1 Message Pin** from the shop to pin messages.",
                ephemeral=True,
            )

        try:
            parts = message_link.strip().split("/")
            if len(parts) < 3 or "discord.com" not in message_link:
                raise ValueError("Invalid message link")

            message_id = int(parts[-1])
            channel_id = int(parts[-2])
            guild_id = int(parts[-3])

            if guild_id != interaction.guild.id:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You can only pin messages from this server!",
                    ephemeral=True,
                )

        except (ValueError, IndexError):
            return await interaction.response.send_message(
                f"{NO_EMOTE} Invalid message link! Please provide a valid Discord message link.\n"
                f"-# Example: `https://discord.com/channels/1234567/2345678/78901234`",
                ephemeral=True,
            )

        await interaction.response.defer(thinking=True)

        try:
            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                return await interaction.followup.send(
                    f"{NO_EMOTE} Channel not found! Make sure the message is from this server.",
                    ephemeral=True,
                )

            if not channel.permissions_for(interaction.guild.me).manage_messages:
                return await interaction.followup.send(
                    f"{NO_EMOTE} I don't have permission to pin messages in {channel.mention}!",
                    ephemeral=True,
                )

            message = await channel.fetch_message(message_id)

            if message.pinned:
                return await interaction.followup.send(
                    f"{NO_EMOTE} That message is already pinned!", ephemeral=True
                )

            await message.pin(
                reason=f"Pinned by {interaction.user} using Message Pin item"
            )

            data["count"] = pin_count - 1
            ref.set(data)

            embed = discord.Embed(
                title="📌 Message Pinned!",
                description=f"Successfully pinned [this message]({message_link}) in {channel.mention}!",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Remaining Pin Credits",
                value=f"📌 `{data['count']}` pin{'s' if data['count'] != 1 else ''} remaining",
                inline=False,
            )
            embed.set_footer(text=f"Purchase more pins from the shop with /buy")

            await interaction.followup.send(embed=embed)

        except discord.NotFound:
            await interaction.followup.send(
                f"{NO_EMOTE} Message not found! Make sure the link is correct and I can access that channel.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"{NO_EMOTE} I don't have permission to pin messages in that channel!",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            if "Maximum number of pins reached" in str(e):
                await interaction.followup.send(
                    f"{NO_EMOTE} That channel has reached the maximum number of pinned messages (50)! Please unpin some messages first.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"{NO_EMOTE} Failed to pin message: {str(e)}", ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"{NO_EMOTE} An error occurred: {str(e)}", ephemeral=True
            )

    @pin.error
    async def pin_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    @app_commands.command(
        name="shop", description="View the guild shop (Admins can edit)"
    )
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def shop(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )
        await interaction.response.defer(thinking=True)
        ref = g_shops(interaction.guild.id)
        shop_data = ref.get() or []

        pages = await get_shop_embeds(interaction, shop_data, empty_condition=False)

        if interaction.user.guild_permissions.administrator:
            view = Panel(
                sort_default="sort by cost (high to low)",
                filter_default=None,
                pages=pages,
                initial_author=interaction.user,
            )
        else:
            view = SortSelectionView(
                sort_default="sort by cost (high to low)",
                filter_default=None,
                pages=pages,
                initial_author=interaction.user,
            )

        view.message = await interaction.followup.send(embed=pages[0], view=view)

        if hasattr(self.economy, "tutorial_manager"):
            asyncio.create_task(
                self.economy.tutorial_manager.on_shop_viewed(interaction.user.id)
            )

    @shop.error
    async def shop_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    async def get_shop_items(self, guild_id):
        ref = g_shops(guild_id)
        items = ref.get() or []
        return items

    async def update_shop_stock(self, guild_id, item_name, new_stock):
        ref = g_shops(guild_id)
        items = ref.get() or []
        for i, item in enumerate(items):
            if item[0] == item_name:
                items[i][5] = new_stock
                ref.set(items)
                return True
        return False

    @app_commands.command(
        name="buy", description="Purchase a reward with your Starr Beans or Tokens"
    )
    @app_commands.describe(item="Item name or role ID to buy")
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def buy(self, interaction: discord.Interaction, item: str):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )
        request = PurchaseRequest(interaction, item)
        await global_purchase_queue.put(request)

        queue_size = global_purchase_queue.qsize()
        if queue_size > 1:
            await interaction.response.send_message(
                f"<a:loading_circle:1393439258886537352> Your purchase is in queue. Position: {queue_size}. Please wait...",
            )
        else:
            await interaction.response.send_message(
                "<a:loading_circle:1393439258886537352> Processing your purchase...",
            )

        if not processing_global_queue:
            asyncio.create_task(process_global_queue())

    @buy.error
    async def buy_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    async def _process_purchase(self, request):
        interaction = request.interaction
        item = request.item

        if time.time() - request.timestamp > 900:
            return await interaction.edit_original_response(
                content="⌛ Your purchase request has expired. Please try again.",
            )

        guild_id = interaction.guild.id
        user_id = interaction.user.id
        member = interaction.user

        effect_item_id = None
        for item_id, item_data in STORE_ITEMS.items():
            if item_data["name"].lower() == item.lower():
                effect_item_id = item_id
                break

        if effect_item_id:
            return await self._process_effect_purchase(
                interaction, user_id, effect_item_id
            )

        shop_items = await self.get_shop_items(guild_id)
        if not shop_items:
            return await interaction.edit_original_response(
                content=f"{NO_EMOTE} The shop is currently empty."
            )

        reward = None
        for r in shop_items:
            if str(r[0]).lower() == item.lower():
                reward = r
                break
        if reward is None:
            return await interaction.edit_original_response(
                content=f"{NO_EMOTE} Item `{item}` not found in the shop."
            )

        name, desc, cost, currency_type, multiple, stock = reward

        beans, tokens = await self.economy.get_balance(user_id)

        if stock == 0:
            return await interaction.edit_original_response(
                content=f"<a:out_of_stock:1384990609584033812> Sorry, **{name}** is currently out of stock.",
            )

        user_currency = beans if currency_type.lower() == "beans" else tokens
        currency_emote = BEAN_EMOTE if currency_type.lower() == "beans" else TOKEN_EMOTE

        if user_currency < cost:
            return await interaction.edit_original_response(
                content=f"{NO_EMOTE} You do not have enough {currency_type}. You have {currency_emote} `{user_currency}`, but this costs {currency_emote} `{cost}`."
            )

        if multiple is False:
            role = interaction.guild.get_role(int(name)) if name.isdigit() else None
            if role and role in member.roles:
                return await interaction.edit_original_response(
                    content=f"{NO_EMOTE} You already own the role **{role.name}** and cannot purchase it again.",
                )

        if currency_type.lower() == "beans":
            new_beans = beans - cost
            await self.economy.update_balance(user_id, beans=new_beans)
            new_tokens = tokens
        else:
            new_tokens = tokens - cost
            await self.economy.update_balance(user_id, tokens=new_tokens)
            new_beans = beans

        if stock > 0:
            await self.update_shop_stock(guild_id, name, stock - 1)

        await update_quest(user_id, guild_id, {"shop_purchases": 1}, self.bot)
        stamp_cog = self.bot.get_cog("StampCard")
        if stamp_cog:
            await stamp_cog.update_progress(user_id, "shop_purchases", 1)

        display_name = name
        if name.isdigit():
            role = interaction.guild.get_role(int(name))
            if role:
                display_name = f"<@&{name}>"
                try:
                    await member.add_roles(role, reason="Purchased from shop")
                except discord.Forbidden:
                    return await interaction.edit_original_response(
                        content=f"Purchased **{role.name}**, but I do not have permission to assign the role."
                    )
                except Exception as e:
                    return await interaction.edit_original_response(
                        content=f"{NO_EMOTE} Error assigning role: {e}",
                    )

        reply_message = (
            f"\n{REPLY_EMOTE} *Redeem your reward by creating a ticket in <#1390908939767648328>!*\n"
            if not name.isdigit()
            else ""
        )
        await interaction.edit_original_response(
            content=None,
            embed=discord.Embed(
                description=f"{YES_EMOTE} Successfully purchased {display_name} for {currency_emote} `{cost}`!{reply_message}\n-# **Your new balance:** {BEAN_EMOTE} `{new_beans}` Beans, {TOKEN_EMOTE} `{new_tokens}` Tokens.",
                color=discord.Color.green(),
            ),
        )

    async def _process_effect_purchase(self, interaction, user_id: int, item_id: str):
        """Process purchase of effect items"""
        item_data = STORE_ITEMS[item_id]

        if item_id == "star_drop" or item_id == "star_drop_10":
            date_key = get_current_date_key()
            purchases_ref = u_star_drops_purchases(user_id, date_key)
            purchases = purchases_ref.get() or 0

            amount_to_buy = 10 if item_id == "star_drop_10" else 1
            limit = 10
            ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
            if ultra_role and ultra_role in interaction.user.roles:
                limit = 20

            if purchases + amount_to_buy > limit:
                remaining = max(0, limit - purchases)
                return await interaction.edit_original_response(
                    content=None,
                    embed=discord.Embed(
                        description=f"🛑 You have **{remaining} purchases** remaining today *(Limit: {limit} per day)*.\n<a:clock:1382887924273774754> Come back <t:{get_next_day_timestamp()}:R>!",
                        color=discord.Color.red(),
                    ),
                )

        if item_id == "mega_box" or item_id == "mega_box_10":
            date_key = get_current_date_key()
            purchases_ref = u_mega_boxes_purchases(user_id, date_key)
            purchases = purchases_ref.get() or 0

            amount_to_buy = 10 if item_id == "mega_box_10" else 1
            limit = 10
            ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
            if ultra_role and ultra_role in interaction.user.roles:
                limit = 20

            if purchases + amount_to_buy > limit:
                remaining = max(0, limit - purchases)
                return await interaction.edit_original_response(
                    content=None,
                    embed=discord.Embed(
                        description=f"🛑 You have **{remaining} purchases** remaining today *(Limit: {limit} per day)*.\n<a:clock:1382887924273774754> Come back <t:{get_next_day_timestamp()}:R>!",
                        color=discord.Color.red(),
                    ),
                )

        if await self.economy.effect_manager.check_user_cooldown(user_id, item_id):
            remaining = await self.economy.effect_manager.get_cooldown_remaining(
                user_id, item_id
            )
            hours, remainder = divmod(remaining, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = (
                f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
                if hours > 0
                else f"{int(minutes)}m {int(seconds)}s"
            )

            return await interaction.edit_original_response(
                content=None,
                embed=discord.Embed(
                    description=f"⏰ **{item_data['name']}** is on cooldown for another **{time_str}**.",
                    color=discord.Color.red(),
                ),
            )

        price_parts = item_data["price"].split()
        cost = int(price_parts[0])
        currency = "tokens" if "token" in price_parts[1].lower() else "beans"

        beans, tokens = await self.economy.get_balance(user_id)
        user_currency = beans if currency == "beans" else tokens
        currency_emote = BEAN_EMOTE if currency == "beans" else TOKEN_EMOTE

        if user_currency < cost:
            return await interaction.edit_original_response(
                content=None,
                embed=discord.Embed(
                    description=f"{NO_EMOTE} You need {currency_emote} `{cost}` {currency.title()} but only have {currency_emote} `{user_currency}`.",
                    color=discord.Color.red(),
                ),
            )

        if currency == "beans":
            new_beans = beans - cost
            new_tokens = tokens
            await self.economy.update_balance(user_id, beans=new_beans)
        else:
            new_beans = beans
            new_tokens = tokens - cost
            await self.economy.update_balance(user_id, tokens=new_tokens)

        await update_quest(
            user_id, interaction.guild.id, {"shop_purchases": 1}, self.bot
        )
        stamp_cog = self.bot.get_cog("StampCard")
        if stamp_cog:
            await stamp_cog.update_progress(user_id, "shop_purchases", 1)

        if item_id == "reset_chat_cap":
            earnings_data = self.economy.chat_system.earnings_cache.get(
                user_id, {"earnings": 0, "reset_time": 0}
            )
            earnings_data["earnings"] = 0
            self.economy.chat_system.earnings_cache[user_id] = earnings_data
            u_daily_chat_earnings(user_id).update({"earnings": 0, "reset_time": 0})
            effect_msg = (
                f"\n🔄 **Chat cap reset!** You can now earn chat beans again today."
            )

        elif item_id == "thermometer_boost":
            current_heat = self.economy.thermometer_heat
            boost_amount = 30
            new_heat = min(130, current_heat + boost_amount)
            self.economy.thermometer_heat = new_heat
            g_thermometer(interaction.guild.id).update({"heat": new_heat})
            effect_msg = f"\n🔥 **Thermometer boosted!** Heat increased by {boost_amount} points (now at {new_heat})."

        elif item_id == "instant_brew":
            active_brew = await self.economy.get_active_brew(user_id)
            if not active_brew:
                return await interaction.edit_original_response(
                    content=None,
                    embed=discord.Embed(
                        description=f"{NO_EMOTE} You don't have any active brew to complete.",
                        color=discord.Color.red(),
                    ),
                )

            roast_type = active_brew["roast_type"]
            roast_data = ROAST_TYPES[roast_type]

            rewards = roast_data["payout"]
            weights = roast_data["weights"]
            tokens_earned = random.choices(rewards, weights=weights)[0]

            is_perfect = False
            if tokens_earned > 0:
                active_effects = (
                    await self.economy.effect_manager.get_user_active_effects(user_id)
                )
                perfect_chance = (
                    25
                    if "perfect_brew_boost" in active_effects
                    else PERFECT_BREW_CHANCE
                )

                if random.randint(1, 100) <= perfect_chance:
                    is_perfect = True
                    tokens_earned += random.randint(3, 8)

            await self.economy.add_tokens(user_id, tokens_earned)
            stamp_cog = self.bot.get_cog("StampCard")
            if stamp_cog:
                await stamp_cog.update_progress(user_id, "brew_sells", 1)
            await update_quest(
                user_id, interaction.guild.id, {"brew_sells": 1}, self.bot
            )
            await self.economy.remove_active_brew(user_id)
            await self.economy.update_brew_stats_on_sell(
                user_id,
                tokens_earned,
                roast_type,
                is_perfect,
                active_brew.get("insured", False),
                False,
            )

            if sync_sell_alarm(user_id, "get"):
                sync_sell_alarm(user_id, "delete", guild_id=interaction.guild.id)

            effect_msg = f"\n🚀 **Instant completion!** Earned {TOKEN_EMOTE} `{tokens_earned}` tokens{'✨ **Perfect brew!**' if is_perfect else ''}."

        elif item_id == "star_drop" or item_id == "star_drop_10":
            amount_to_buy = 10 if item_id == "star_drop_10" else 1
            date_key = get_current_date_key()
            purchases_ref = u_star_drops_purchases(user_id, date_key)
            purchases = purchases_ref.get() or 0
            purchases_ref.set(purchases + amount_to_buy)

            inventory_ref = u_star_drops(user_id)
            current_count = inventory_ref.get() or 0
            inventory_ref.set(current_count + amount_to_buy)

            effect_msg = f"\n{STAR_DROP_EMOTE} You now have {current_count + amount_to_buy} unopened drops. Use </stardrop:1447676573020065996> to open them!"

        elif item_id == "mega_box" or item_id == "mega_box_10":
            amount_to_buy = 10 if item_id == "mega_box_10" else 1
            date_key = get_current_date_key()
            purchases_ref = u_mega_boxes_purchases(user_id, date_key)
            purchases = purchases_ref.get() or 0
            purchases_ref.set(purchases + amount_to_buy)

            inventory_ref = u_mega_boxes(user_id)
            current_count = inventory_ref.get() or 0
            inventory_ref.set(current_count + amount_to_buy)
            effect_msg = f"\n{MEGA_BOX_EMOTE} You now have {current_count + amount_to_buy} unopened Mega Boxes. Use </megabox:1486191980349358224> to open them!"

        elif item_id == "message_pin":
            await item_data["effect"](user_id)
            pin_ref = u_pin_message(user_id)
            pin_data = pin_ref.get() or {"count": 0}
            pin_count = pin_data.get("count", 0)
            effect_msg = f"\n📌 **Message Pin added!** You now have `{pin_count}` pin{'s' if pin_count != 1 else ''} available. Use </pin:1427543833792610344> to pin messages!"

        elif item_id == "custom_credit":
            await item_data["effect"](user_id)
            ref = u_customization(user_id)
            data = ref.get() or {"credits": 0}
            credits = data.get("credits", 0)
            effect_msg = f"\n🎨 **Customization Credit added!** You now have `{credits}` credit{'s' if credits != 1 else ''}. Use </customize:1486174479489957908> to design your background!"

        else:
            await item_data["effect"](user_id)

            if item_id == "sell_alarm":
                active_brew = await self.economy.get_active_brew(user_id)
                if active_brew:
                    sync_sell_alarm(
                        user_id,
                        "set",
                        {
                            "roast_type": active_brew.get("roast_type"),
                            "end_time": active_brew.get("end_time"),
                            "batch_id": active_brew.get("batch_id"),
                            "notified": False,
                        },
                        interaction.guild.id,
                    )

                if hasattr(self.economy, "tutorial_manager"):
                    asyncio.create_task(
                        self.economy.tutorial_manager.on_item_bought(user_id, item_id)
                    )

            elif item_id == "freeze_thermometer":
                freeze_data = await self.economy.effect_manager.get_user_active_effects(
                    user_id
                )
                if "freeze_thermometer" in freeze_data:
                    sync_shop_effects(
                        user_id,
                        "freeze_thermometer",
                        "set",
                        freeze_data["freeze_thermometer"],
                        interaction.guild.id,
                    )

            effect_msg = (
                f"\n{EFFECT_EMOTE} **{item_data['name']}** effect is now active!"
            )

        await self.economy.effect_manager.set_user_cooldown(user_id, item_id)

        await interaction.edit_original_response(
            content=None,
            embed=discord.Embed(
                description=f"{YES_EMOTE} Successfully purchased **{item_data['name']}** for {currency_emote} `{cost}` {currency.title()}!{effect_msg}\n-# **Your new balance:** {BEAN_EMOTE} `{new_beans}` Beans, {TOKEN_EMOTE} `{new_tokens}` Tokens.",
                color=discord.Color.green(),
            ),
        )

    @buy.autocomplete("item")
    async def item_autocomplete(self, interaction: discord.Interaction, current: str):
        current_lower = current.lower()
        results = []

        for item_id, item_data in STORE_ITEMS.items():
            name = item_data["name"]
            desc = item_data["description"]
            price = item_data["price"]

            if current_lower in name.lower() or current_lower in desc.lower():
                label = f"{name} ({price})"
                results.append(app_commands.Choice(name=label[:100], value=name))
                if len(results) >= 12:  # Limit effect items to save space
                    break

        guild_id = interaction.guild.id
        shop_items = await self.get_shop_items(guild_id)

        for item in shop_items or []:
            if len(results) >= 25:
                break

            stored_value = str(item[0])
            display_name = stored_value
            if stored_value.isdigit():
                role = interaction.guild.get_role(int(stored_value))
                display_name = role.name if role else stored_value
            desc = item[1]
            currency_type = item[3]
            currency_emote = (
                BEAN_EMOTE if currency_type.lower() == "beans" else TOKEN_EMOTE
            )

            if current_lower in display_name.lower() or current_lower in desc.lower():
                label = f"{display_name} ({item[2]} {'Beans' if currency_emote == BEAN_EMOTE else 'Tokens'})"
                results.append(
                    app_commands.Choice(name=label[:100], value=stored_value)
                )
        return results


async def setup(bot):
    await bot.add_cog(Shop(bot))

import discord
import re
import secrets
import asyncio
import time
import random
import io
import aiohttp
import os

from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands
from discord import app_commands
from firebase_admin import db
from discord.ui import View, Select, Button
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from typing import Dict, Optional

from brawl.Currency.levels import get_level
from brawl.Currency.tutorial import TutorialManager
from brawl.Currency.quests import update_quest, QUEST_TYPES
from brawl.Currency.db import (
    U_ROOT, u_balance, u_brews, u_shop_effects, u_shop_cooldowns,
    u_star_drops, u_mega_boxes, u_daily_chat_earnings, u_gambling_limits, u_thermometer_cooldown, 
    u_pin_message, u_customization, u_tag, u_daily_checkin_streaks, u_quests,
    u_star_drops_pending, u_mega_boxes_pending, u_star_drops_purchases, u_mega_boxes_purchases,
    g_shops, g_tables, g_invites_monthly, g_invites_member_data,
    g_member_history, g_referral_milestones, g_thermometer, g_boss_inspection,
    g_sell_alarm, g_shop_effects, g_mega_pass_config, g_mega_pass_current,
    sync_shop_effects, sync_sell_alarm, staff_app, staff_app_cooldown
)
from brawl.Currency.helper import (
    SERVER_STORE, BOT_COMMANDS, INVITE_LOG, TRAINEE_ROLE_ID, BRIDGE_ROLE_ID, MASTER_ROLE_ID, ULTRA_TIER_ROLE_ID,
    NO_EMOTE, YES_EMOTE, BEAN_EMOTE, TOKEN_EMOTE, REPLY_EMOTE, EFFECT_EMOTE, LB_EMOTE, STAR_DROP_EMOTE, MEGA_BOX_EMOTE,
    BOSS_INSPECTION_ACTIONS, BOSS_INSPECTION_ROLE_ID, MAIN_CHAT_CHANNELS, BOSS_EMBED,
    STAR_DROP_RATES, COLORS, IMAGES, AUTORESPONSE_MAP, MAIN_GUILD_ID, TABLE_QUEST_TYPES,
    ROAST_TYPES, PERFECT_BREW_CHANCE, UNLOCK_REQ, EMOJIS, DAILY_GAMBLING_LIMITS, STORE_ITEMS,
    get_current_month_key, get_current_date_key, get_next_day_timestamp
)

global_purchase_queue = asyncio.Queue()
processing_global_queue = False

class EffectManager:
    def __init__(self, bot):
        self.bot = bot
        
    async def cleanup_expired_effects(self):
        """Remove expired effects from database"""
        try:
            effects_ref = u_shop_effects(None)
            all_effects = effects_ref.get() or {}
            current_time = time.time()

            for user_id, user_effects in all_effects.items():
                for effect_name, effect_data in user_effects.items():
                    if isinstance(effect_data, dict) and effect_data.get("active", False):
                        expires_at = effect_data.get("expires_at", 0)
                        if current_time >= expires_at:
                            # Deactivate the effect in both user and guild paths
                            sync_shop_effects(int(user_id), effect_name, 'update',
                                            {"active": False}, MAIN_GUILD_ID)
        except Exception as e:
            print(f"Error cleaning up expired effects: {e}")
    
    async def get_user_active_effects(self, user_id: int):
        """Get all active effects for a user"""
        ref = u_shop_effects(user_id)
        effects = ref.get() or {}
        current_time = time.time()
        
        active_effects = {}
        for effect_name, effect_data in effects.items():
            if isinstance(effect_data, dict) and effect_data.get("active", False):
                expires_at = effect_data.get("expires_at", 0)
                if current_time < expires_at:
                    active_effects[effect_name] = effect_data
                    
        return active_effects
    
    async def check_user_cooldown(self, user_id: int, item_id: str):
        """Check if user is on cooldown for purchasing an item"""
        ref = u_shop_cooldowns(user_id, item_id)
        cooldown_data = ref.get()
        
        if not cooldown_data:
            return False
            
        current_time = time.time()
        last_purchase = cooldown_data.get("last_purchase", 0)
        cooldown_duration = STORE_ITEMS[item_id]["cooldown"]
        
        return current_time < (last_purchase + cooldown_duration)
    
    async def set_user_cooldown(self, user_id: int, item_id: str):
        """Set cooldown for user after purchase"""
        ref = u_shop_cooldowns(user_id, item_id)
        ref.set({
            "last_purchase": time.time(),
            "item_name": STORE_ITEMS[item_id]["name"]
        })
    
    async def get_cooldown_remaining(self, user_id: int, item_id: str):
        """Get remaining cooldown time in seconds"""
        ref = u_shop_cooldowns(user_id, item_id)
        cooldown_data = ref.get()
        
        if not cooldown_data:
            return 0
            
        current_time = time.time()
        last_purchase = cooldown_data.get("last_purchase", 0)
        cooldown_duration = STORE_ITEMS[item_id]["cooldown"]
        
        remaining = (last_purchase + cooldown_duration) - current_time
        return max(0, remaining)

class PurchaseRequest:
    __slots__ = ('interaction', 'item', 'timestamp')
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
                cog = request.interaction.client.get_cog("CurrencySystem")
                if cog:
                    await cog._process_purchase(request)
            except Exception as e:
                print(f"Error processing purchase: {e}")
            finally:
                global_purchase_queue.task_done()
    finally:
        processing_global_queue = False

class BasePaginationView(View):
    def __init__(self, pages=None, initial_author=None, timeout=60):
        super().__init__(timeout=timeout)
        self.initial_author = initial_author
        self.page = 0
        self.pages = pages or []
        self.message = None
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.initial_author != interaction.user:
            await interaction.response.send_message(f"{NO_EMOTE} You are not the author of this command.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, Button) and child.style == discord.ButtonStyle.link:
                continue
            child.disabled = True
            if isinstance(child, Select):
                child.options = [discord.SelectOption(label="Disabled due to timeout", value="X", emoji="⛔", default=True)]
        try:
            if self.message:
                await self.message.edit(view=self)
        except (discord.NotFound, AttributeError):
            pass
        self.stop()
        
    def update_buttons(self):
        if len(self.pages) <= 1:
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id in ["first_page", "prev_page", "next_page", "last_page"]:
                    child.disabled = True
        else:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    if child.custom_id == "first_page":
                        child.disabled = self.page == 0
                    elif child.custom_id == "prev_page":
                        child.disabled = self.page == 0
                    elif child.custom_id == "next_page":
                        child.disabled = self.page >= len(self.pages) - 1
                    elif child.custom_id == "last_page":
                        child.disabled = self.page >= len(self.pages) - 1

    @discord.ui.button(emoji="<:fastbackward:1351972112696479824>", style=discord.ButtonStyle.grey, custom_id="first_page", row=1)
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(emoji="<:backarrow:1351972111010369618>", style=discord.ButtonStyle.grey, custom_id="prev_page", row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(emoji="<:rightarrow:1351972116819480616>", style=discord.ButtonStyle.grey, custom_id="next_page", row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < len(self.pages) - 1:
            self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(emoji="<:fastforward:1351972114433048719>", style=discord.ButtonStyle.grey, custom_id="last_page", row=1)
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = len(self.pages) - 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

class JumpToPageModal(discord.ui.Modal, title="Jump to Page"):
    def __init__(self, view, max_page):
        super().__init__()
        self.view_ref = view
        self.max_page = max_page
        
        self.page_input = discord.ui.TextInput(
            label="Page Number",
            placeholder=f"Enter a page number (1-{max_page})",
            default=str(view.page + 1),
            min_length=1,
            max_length=len(str(max_page))
        )
        self.add_item(self.page_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page_num = int(self.page_input.value)
            if 1 <= page_num <= self.max_page:
                await self.view_ref.show_page(interaction, page_num - 1)
            else:
                await interaction.response.send_message(f"Please enter a valid page number between 1 and {self.max_page}.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)

class LeaderboardView(BasePaginationView):
    def __init__(self, interaction, pages):
        super().__init__(pages=pages, initial_author=interaction.user, timeout=120)
        self.interaction = interaction
        self.total_pages = len(pages)
        self.page = 0
        self.update_buttons()

    async def show_page(self, interaction, page_idx):
        self.page = page_idx
        self.update_buttons()
        embed = self.pages[page_idx]
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="<:fastbackward:1351972112696479824>", style=discord.ButtonStyle.grey, custom_id="first_page", row=2)
    async def first_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, 0)

    @discord.ui.button(emoji="<:backarrow:1351972111010369618>", style=discord.ButtonStyle.grey, custom_id="prev_page", row=2)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            await self.show_page(interaction, self.page - 1)
    
    @discord.ui.button(label="Jump", style=discord.ButtonStyle.blurple, custom_id="jump_page", row=2)
    async def jump_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(JumpToPageModal(self, self.total_pages))

    @discord.ui.button(emoji="<:rightarrow:1351972116819480616>", style=discord.ButtonStyle.grey, custom_id="next_page", row=2)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            await self.show_page(interaction, self.page + 1)

    @discord.ui.button(emoji="<:fastforward:1351972114433048719>", style=discord.ButtonStyle.grey, custom_id="last_page", row=2)
    async def last_page_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.show_page(interaction, self.total_pages - 1)

class FilterSelection(discord.ui.Select):
    def __init__(self, default=None, initial_author=None, sort_default="sort by cost (high to low)"):
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
            options.append(discord.SelectOption(label=i, emoji=filterOptionsEmoji[filterOptions.index(i)], default=(i==default_filter)))

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
        
        filter_map = {"Cost Beans": "beans", "Cost Tokens": "tokens", "Effect Items": "effect_items", "Supercell Items": "supercell", "All Items": None}
        filter_type = filter_map.get(self.values[0])
        
        sort_by = "cost" if "cost" in self.sort_default else "name"
        reverse = "high to low" in self.sort_default or "z-a" in self.sort_default
        
        pages = await get_shop_embeds(interaction, rewards, empty_condition=(len(rewards)==0), sort_by=sort_by, reverse=reverse, filter_type=filter_type)

        if interaction.user.guild_permissions.administrator:
            view = Panel(sort_default=self.sort_default, filter_default=self.values[0], pages=pages, initial_author=self.initial_author)
        else:
            view = SortSelectionView(sort_default=self.sort_default, filter_default=self.values[0], pages=pages, initial_author=self.initial_author)

        view.page = 0
        view.update_buttons()
        await interaction.response.edit_message(embed=pages[0], view=view)
        view.message = interaction.message

class SortSelection(discord.ui.Select):
    def __init__(self, sort_default="sort by cost (high to low)", filter_default=None, initial_author=None):
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
            options.append(discord.SelectOption(label=i, emoji=sortOptionsEmoji[sortOptions.index(i)], default=(i==sort_default)))

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
        filter_map = {"Cost Beans": "beans", "Cost Tokens": "tokens", "Effect Items": "effect_items", "Supercell Items": "supercell", "All Items": None}
        filter_type = filter_map.get(self.filter_default) if self.filter_default else None
        
        pages = await get_shop_embeds(interaction, rewards, empty_condition=(len(rewards)==0), sort_by=sort_by, reverse=reverse, filter_type=filter_type)

        if interaction.user.guild_permissions.administrator:
            view = Panel(sort_default=self.values[0], filter_default=self.filter_default, pages=pages, initial_author=self.initial_author)
        else:
            view = SortSelectionView(sort_default=self.values[0], filter_default=self.filter_default, pages=pages, initial_author=self.initial_author)

        view.page = 0
        view.update_buttons()
        await interaction.response.edit_message(embed=pages[0], view=view)
        view.message = interaction.message

class SortSelectionView(BasePaginationView):
    def __init__(self, sort_default="sort by cost (high to low)", filter_default=None, pages=None, initial_author=None, timeout=300):
        super().__init__(pages=pages, initial_author=initial_author, timeout=timeout)
        self.sort_default = sort_default
        self.filter_default = filter_default
        self.add_item(SortSelection(sort_default=sort_default, filter_default=filter_default, initial_author=self.initial_author))
        self.add_item(FilterSelection(default=filter_default, initial_author=self.initial_author, sort_default=sort_default))
        self.update_buttons()  

class Panel(BasePaginationView):
    def __init__(self, sort_default="sort by cost (high to low)", filter_default=None, pages=None, initial_author=None):
        super().__init__(pages=pages, initial_author=initial_author, timeout=300)
        self.sort_default = sort_default
        self.filter_default = filter_default
        self.add_item(SortSelection(sort_default=sort_default, filter_default=filter_default, initial_author=self.initial_author))
        self.add_item(FilterSelection(default=filter_default, initial_author=self.initial_author, sort_default=sort_default))
        self.update_buttons()  

    @discord.ui.button(label="Add Reward", style=discord.ButtonStyle.green, custom_id="addreward", row=0)
    async def add_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(f"{NO_EMOTE} Missing Administrator permission.", ephemeral=True)
        modal = RewardModal("add", interaction.guild.id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if hasattr(modal, 'pages') and modal.pages is not None:
            view = Panel(sort_default=self.sort_default, filter_default=self.filter_default, pages=modal.pages, initial_author=interaction.user) if interaction.user.guild_permissions.administrator else SortSelectionView(sort_default=self.sort_default, filter_default=self.filter_default, pages=modal.pages, initial_author=interaction.user)
            view.page = 0  
            view.update_buttons()  
            await interaction.edit_original_response(embed=modal.pages[0], view=view)
        await modal.on_submit_interaction.response.send_message(embed=modal.update, ephemeral=True)

    @discord.ui.button(label="Remove Reward", style=discord.ButtonStyle.red, custom_id="removereward", row=0)
    async def remove_reward(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(f"{NO_EMOTE} Missing Administrator permission.", ephemeral=True)
        modal = RewardModal("remove", interaction.guild.id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if hasattr(modal, 'pages') and modal.pages is not None:
            view = Panel(sort_default=self.sort_default, filter_default=self.filter_default, pages=modal.pages, initial_author=interaction.user) if interaction.user.guild_permissions.administrator else SortSelectionView(sort_default=self.sort_default, filter_default=self.filter_default, pages=modal.pages, initial_author=interaction.user)
            view.page = 0  
            view.update_buttons()  
            await interaction.edit_original_response(embed=modal.pages[0], view=view)
        await modal.on_submit_interaction.response.send_message(embed=modal.update, ephemeral=True)

    @discord.ui.button(label="Edit Cost", style=discord.ButtonStyle.grey, custom_id="editcost", row=0)
    async def edit_cost(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(f"{NO_EMOTE} Missing Administrator permission.", ephemeral=True)
        modal = RewardModal("edit_cost", interaction.guild.id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.pages is not None:
            view = Panel(sort_default=self.sort_default, filter_default=self.filter_default, pages=modal.pages, initial_author=interaction.user) if interaction.user.guild_permissions.administrator else SortSelectionView(sort_default=self.sort_default, filter_default=self.filter_default, pages=modal.pages, initial_author=interaction.user)
            view.page = 0 
            view.update_buttons() 
            await interaction.edit_original_response(embed=modal.pages[0], view=view)
        await modal.on_submit_interaction.response.send_message(embed=modal.update, ephemeral=True)

    @discord.ui.button(label="Edit Stock", style=discord.ButtonStyle.grey, custom_id="editstock", row=0)
    async def edit_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(f"{NO_EMOTE} Missing Administrator permission.", ephemeral=True)
        modal = RewardModal("edit_stock", interaction.guild.id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.pages is not None:
            view = Panel(sort_default=self.sort_default, filter_default=self.filter_default, pages=modal.pages, initial_author=interaction.user) if interaction.user.guild_permissions.administrator else SortSelectionView(sort_default=self.sort_default, filter_default=self.filter_default, pages=modal.pages, initial_author=interaction.user)
            view.page = 0 
            view.update_buttons() 
            await interaction.edit_original_response(embed=modal.pages[0], view=view)
        await modal.on_submit_interaction.response.send_message(embed=modal.update, ephemeral=True)


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
            "edit_stock": "Edit Reward Stock"
        }
        return titles.get(self.operation, "Reward Management")

    def _add_inputs(self):
        self.name_input = discord.ui.TextInput(label="Role ID / Reward Title", style=discord.TextStyle.short, placeholder="Role ID or Reward Title", required=True, max_length=50)
        self.add_item(self.name_input)
        
        if self.operation == "add":
            self.desc_input = discord.ui.TextInput(label="Description / Perk", style=discord.TextStyle.short, placeholder="Short description", required=True, max_length=150)
            self.cost_input = discord.ui.TextInput(label="Cost", style=discord.TextStyle.short, placeholder="Integer cost (e.g. 100 beans, 5 tokens)", required=True, max_length=15)
            self.multiple_input = discord.ui.TextInput(label="Enable multiple purchases? (Titles only)", style=discord.TextStyle.short, placeholder="yes or no", required=False, max_length=3)
            self.stock_input = discord.ui.TextInput(label="Stock Count (optional)", style=discord.TextStyle.short, placeholder="Leave blank for unlimited", required=False, max_length=10)
            self.add_item(self.desc_input)
            self.add_item(self.cost_input)
            self.add_item(self.multiple_input)
            self.add_item(self.stock_input)
        elif self.operation == "edit_cost":
            self.cost_input = discord.ui.TextInput(label="New Cost", style=discord.TextStyle.short, placeholder="Integer cost (e.g. 100 beans, 5 tokens)", required=True, max_length=15)
            self.add_item(self.cost_input)
        elif self.operation == "edit_stock":
            self.stock_input = discord.ui.TextInput(label="New Stock Count", style=discord.TextStyle.short, placeholder="Integer stock count or blank for unlimited", required=False, max_length=10)
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
        self.update = discord.Embed(description=message, color=discord.Color.red() if is_error else discord.Color.green())
        self.pages = await get_shop_embeds(interaction, rewards, False)
        self.on_submit_interaction = interaction
        self.stop()

    async def _handle_add(self, interaction, rewards, ref):
        if any(str(item[0]) == str(self.name_input.value) for item in rewards):
            await self._send_response(interaction, rewards, f"{NO_EMOTE} Duplicate reward entry found.", True)
            return
        try:
            cost_int = int(self.cost_input.value.replace(',', '').split(' ')[0].strip())
            currency_type = 'beans' if 'bean' in self.cost_input.value.split(' ')[1].lower() else 'tokens'
            if cost_int <= 0: raise ValueError
        except:
            await self._send_response(interaction, rewards, f"{NO_EMOTE} Cost must be a positive integer.", True)
            return
        try:
            stock_int = int(self.stock_input.value.strip()) if self.stock_input.value.strip() else -1
            if stock_int < -1: raise ValueError
        except:
            await self._send_response(interaction, rewards, f"{NO_EMOTE} Stock must be a non-negative integer or blank for unlimited.", True)
            return
        multiple_bool = (self.multiple_input.value.lower() == "yes") if self.multiple_input.value else False
        rewards.append([str(self.name_input.value), str(self.desc_input.value), cost_int, currency_type, multiple_bool, stock_int])
        ref.set(rewards)
        await self._send_response(interaction, rewards, "Reward added successfully.", False)

    async def _handle_remove(self, interaction, rewards, ref):
        item_to_remove = next((item for item in rewards if str(item[0]) == str(self.name_input.value)), None)
        if not item_to_remove:
            await self._send_response(interaction, rewards, f"{NO_EMOTE} Reward not found.", True)
            return
        rewards.remove(item_to_remove)
        ref.set(rewards)
        await self._send_response(interaction, rewards, "Reward removed successfully.", False)

    async def _handle_edit_cost(self, interaction, rewards, ref):
        try:
            cost_int = int(self.cost_input.value.replace(',', '').split(' ')[0].strip())
            currency_type = 'beans' if 'bean' in self.cost_input.value.split(' ')[1].lower() else 'tokens'
            if cost_int <= 0: raise ValueError
        except:
            await self._send_response(interaction, rewards, f"{NO_EMOTE} Cost must be a positive integer.", True)
            return
        for idx, item in enumerate(rewards):
            if str(item[0]) == str(self.name_input.value):
                rewards[idx][2] = cost_int
                rewards[idx][3] = currency_type
                ref.set(rewards)
                await self._send_response(interaction, rewards, "Reward cost updated successfully.", False)
                return
        await self._send_response(interaction, rewards, f"{NO_EMOTE} Reward not found.", True)

    async def _handle_edit_stock(self, interaction, rewards, ref):
        try:
            stock_val = int(self.stock_input.value.strip()) if self.stock_input.value.strip() else -1
            if stock_val < -1: raise ValueError
        except:
            await self._send_response(interaction, rewards, f"{NO_EMOTE} Stock must be a non-negative integer or blank for unlimited.", True)
            return
        for idx, item in enumerate(rewards):
            if str(item[0]) == str(self.name_input.value):
                rewards[idx][5] = stock_val
                ref.set(rewards)
                await self._send_response(interaction, rewards, "Reward stock updated successfully.", False)
                return
        await self._send_response(interaction, rewards, f"{NO_EMOTE} Reward not found.", True)

async def get_shop_embeds(
    interaction, item_list, empty_condition, sort_by="cost", reverse=True, filter_type=None
):
    def categorize_item(item, is_effect=False):
        """Categorize item as 'beans', 'tokens', or 'effect'"""
        if is_effect:
            return 'effect'
        currency = item[3]
        if currency.lower() == 'tokens':
            return 'tokens'
        return 'beans'
    
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
        effect_items.append([
            item_data["name"],
            item_data["description"],
            cost,
            currency,
            True, # Always allow multiple purchases for effect items
            -1, # Unlimited stock
            item_id, # Item ID (effect only)
            f"{emote}", # Emoji (effect only)
            item_data.get("cooldown", 0) # Cooldown in seconds (effect only)
        ])
    
    formatted_custom_items = []
    for custom_item in (item_list or []):
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
            if filter_type == 'effect_items':
                if is_effect:
                    filtered_items.append(item)
            elif filter_type == 'beans':
                if item[3].lower() == 'beans':
                    filtered_items.append(item)
            elif filter_type == 'tokens':
                if item[3].lower() == 'tokens':
                    filtered_items.append(item)
            elif filter_type == 'supercell':
                if "<:account:1486161374601154601>" in str(item[0]):
                    filtered_items.append(item)
        combined_items = filtered_items
    
    if not combined_items:
        return [discord.Embed(title="Shop is empty!", description="This server has no purchasable items yet.", color=discord.Color.red())]

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
    
    filter_map = {'beans': 'Bean Items', 'tokens': 'Token Items', 'effect_items': 'Effect Items', 'supercell': 'Supercell Items'}
    filter_text = filter_map.get(filter_type, 'All Items') if filter_type else 'All Items'

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
            if len(item) > 5 and item[5] != -1 else ""
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

class ChatRewardSystem:
    def __init__(self, bot):
        self.bot = bot
        self.user_cooldowns = {}
        self.message_counts = {}
        self.thermo_bean_cache = {}
        self.daily_thresholds = {}
        self.last_messages = {}
        self.first_message_times = {}
        self.earnings_cache = {}
        self.thermo_bean_lock = asyncio.Lock()

    def is_effortful_message(self, message: str, user_id: int) -> tuple[bool, str]:
        content = message.strip()

        if len(content) < 5:
            return False, f"{NO_EMOTE} Too short (< 5 characters)"

        total_chars = len(content)
        non_alnum_chars = len(re.findall(r"[^\w\s]", content))
        if total_chars > 0 and (non_alnum_chars / total_chars) > 0.6:
            return False, f"{NO_EMOTE} Too many symbols/non-alphanumeric characters"

        emoji_match = re.sub(r"<a?:\w+:\d+>|[\u2600-\u27BF\u2190-\u21FF\u2300-\u23FF]", "", content)
        if len(emoji_match.strip()) == 0:
            return False, f"{NO_EMOTE} Only emojis or custom emojis"

        words = content.lower().split()
        if len(set(words)) <= 2 and len(words) > 5:
            return False, f"{NO_EMOTE} Too repetitive (e.g., 'lol lol lol')"

        if re.search(r"(.)\1{4,}", content):
            return False, f"{NO_EMOTE} Excessive repeated characters (e.g., 'nooooo')"

        if content.startswith("="):
            return False, f"{NO_EMOTE} Carl-bot command detected"

        last_msg = self.last_messages.get(user_id)
        if last_msg:
            similarity = SequenceMatcher(None, last_msg.strip().lower(), content.lower()).ratio()
            if similarity > 0.9:
                return False, f"{NO_EMOTE} Too similar to previous message"

        if re.search(r"(https?:\/\/|www\.|discord\.gg\/|^\/\w+)", content.lower()):
            return False, f"{NO_EMOTE} Looks like spam or a link"

        if re.fullmatch(r"(\s*<a?:\w+:\d+>\s*){1,4}", content):
            return False, f"{NO_EMOTE} Only emojis or emoji + fillers"

        return True, f"{YES_EMOTE} Effortful message"

    async def process_message(self, message, cog):
        if message.author.bot:
            return

        user_id = message.author.id
        current_time = time.time()
        
        if user_id not in self.user_cooldowns:
            self.user_cooldowns[user_id] = 0
            self.message_counts[user_id] = 0
            self.last_messages[user_id] = ""
            self.daily_thresholds[user_id] = random.randint(9, 11)

        if user_id in self.earnings_cache:
            earnings_data = self.earnings_cache[user_id]
        else:
            ref = u_daily_chat_earnings(user_id)
            data = ref.get() or {"earnings": 0, "reset_time": 0}
            earnings_data = data
            self.earnings_cache[user_id] = earnings_data

        reset_time = earnings_data.get("reset_time", 0)
        if current_time > reset_time:
            earnings_data["earnings"] = 0
            earnings_data["reset_time"] = current_time + 86400
            self.earnings_cache[user_id] = earnings_data

        today_earnings = earnings_data["earnings"]

        if current_time - self.user_cooldowns[user_id] < 5:
            return

        effortful, reason = self.is_effortful_message(message.content, user_id)
        if not effortful:
            return

        self.user_cooldowns[user_id] = current_time
        self.message_counts[user_id] += 1
        self.last_messages[user_id] = message.content.strip()

        MAX_DAILY_CHAT_BEAN_LIMIT = 1000
        booster_role = message.guild.premium_subscriber_role
        if booster_role in message.author.roles:
            MAX_DAILY_CHAT_BEAN_LIMIT = 1500
        
        ultra_role = message.guild.get_role(ULTRA_TIER_ROLE_ID)
        if ultra_role and ultra_role in message.author.roles:
            MAX_DAILY_CHAT_BEAN_LIMIT = 5000

        if datetime.now(timezone.utc).weekday() >= 5:  
            MAX_DAILY_CHAT_BEAN_LIMIT *= 2
            
        active_effects = await cog.effect_manager.get_user_active_effects(user_id)
        chat_boost_active = "chat_boost" in active_effects
        if chat_boost_active:
            MAX_DAILY_CHAT_BEAN_LIMIT *= 3

        if message.channel.id in MAIN_CHAT_CHANNELS:
            freeze_ref = g_shop_effects(message.guild.id)
            all_effects = freeze_ref.get() or {}
            current_time = time.time()
            
            frozen = False
            for user_id_check, user_effects in all_effects.items():
                freeze_data = user_effects.get("freeze_thermometer", {})
                if freeze_data.get("active", False) and current_time < freeze_data.get("expires_at", 0):
                    frozen = True
                    break
            
            if not frozen:
                heat_add = random.randint(1, 2)
                cog.thermometer_heat = min(130, cog.thermometer_heat + heat_add)
                g_thermometer(message.guild.id).update({"heat": cog.thermometer_heat})

        display_heat = min(cog.thermometer_heat, 100)

        if display_heat >= 100: 
            thermo_beans = 6
        elif display_heat >= 75: 
            thermo_beans = 4
        elif display_heat >= 50: 
            thermo_beans = 2
        else:
            thermo_beans = 0

        if thermo_beans > 0:
            async with self.thermo_bean_lock:
                self.thermo_bean_cache[user_id] = self.thermo_bean_cache.get(user_id, 0) + thermo_beans
        
        bonus_tokens = 0
        bonus_message = None
        roll = random.random()
        if display_heat >= 100:
            if roll < 0.005: 
                bonus_tokens = 5
                bonus_message = "🎉 **JACKPOT!** You hit the 0.5% jackpot!"
            elif roll < 0.02: 
                bonus_tokens = random.choice([1, 1, 2])
        elif display_heat >= 75:
            if roll < 0.01: 
                bonus_tokens = 1

        if bonus_tokens > 0:
            can_receive, current_count, reset_time = await cog.check_and_update_token_reward_limit(user_id)
            if not can_receive:
                bonus_tokens = 0
                bonus_message = None

        embed = None
        if bonus_tokens > 0:
            await cog.add_tokens(user_id, bonus_tokens)
            _, tokens_balance = await cog.get_balance(user_id)

            embed = discord.Embed(
                title="☕ Chat Thermometer Bonus!",
                color=0xFFD700,
                description=f"You received {TOKEN_EMOTE} **{bonus_tokens} Tokens**!"
            )
            if bonus_message:
                embed.description += f"\n{bonus_message}"

            current_time = time.time()
            remaining = int(reset_time - current_time)
            if remaining > 0:
                hours, remainder = divmod(remaining, 3600)
                minutes, _ = divmod(remainder, 60)
                formatted = f"in {hours}h {minutes}m"
            else:
                formatted = "soon"
            embed.set_footer(text=f"Token rewards today: {current_count}/3 (resets {formatted})")

            embed.add_field(
                name="Thermometer Level",
                value=f"{display_heat}% - {'Boiling 🔥' if display_heat >= 100 else 'Hot 🌡️' if display_heat >= 75 else 'Warm ☕'}",
                inline=True,
            )
            embed.add_field(
                name="New Token Balance",
                value=f"{TOKEN_EMOTE} `{tokens_balance}`",
                inline=True,
            )

            stamp_cog = self.bot.get_cog("StampCard")
            if stamp_cog:
                await stamp_cog.update_progress(user_id, "thermometer_bonuses", 1)

        daily_threshold = self.daily_thresholds[user_id]
        beans_earned = 0
        new_earnings = today_earnings
        reward_triggered = False

        if self.message_counts[user_id] >= daily_threshold:
            self.message_counts[user_id] = 0
            self.daily_thresholds[user_id] = random.randint(9, 11)

            if today_earnings < MAX_DAILY_CHAT_BEAN_LIMIT:
                active_effects = await cog.effect_manager.get_user_active_effects(user_id)
                
                min_beans = 100 if "chat_bean_boost" not in active_effects else 150
                max_beans = 201 if "chat_bean_boost" not in active_effects else 301
                beans_earned = random.randint(min_beans, max_beans)
                
                if chat_boost_active:
                    beans_earned *= 3
                
                ultra_role = message.guild.get_role(ULTRA_TIER_ROLE_ID)
                if ultra_role and ultra_role in message.author.roles:
                    beans_earned *= 3
                
                if today_earnings + beans_earned > MAX_DAILY_CHAT_BEAN_LIMIT:
                    beans_earned = MAX_DAILY_CHAT_BEAN_LIMIT - today_earnings

                new_earnings = today_earnings + beans_earned
                earnings_data["earnings"] = new_earnings
                u_daily_chat_earnings(user_id).set(earnings_data)
                self.earnings_cache[user_id] = earnings_data

                await cog.add_beans(user_id, beans_earned)
                await update_quest(user_id, message.guild.id, {"chat_earnings": beans_earned}, self.bot)
                reward_triggered = True
                reset_time = earnings_data["reset_time"]

        try:
            if reward_triggered:
                emoji = "<:Like:793027164731605033>"
                table_cog = self.bot.get_cog("table")
                if table_cog:
                    table_data = await table_cog.get_user_table(user_id, message.guild.id)
                    if table_data and table_data.get("formalized", False):
                        emoji = table_data["emoji"]
                await message.channel.send(
                    f"{emoji} {message.author.mention} earned {BEAN_EMOTE} **{beans_earned} Beans** "
                    f"for chatting actively! *(Daily Cap: `{new_earnings}/{MAX_DAILY_CHAT_BEAN_LIMIT}`)* {EFFECT_EMOTE if chat_boost_active else ''} \n"
                    f"> -# <a:clock:1382887924273774754> Resets <t:{int(reset_time)}:R>. "
                    "Use </balance:1393376242501157005> to check your progress!",
                    embed=embed
                )
            elif embed is not None:
                await message.channel.send(message.author.mention, embed=embed)
        except Exception as e:
            print(f"Failed to send bean reward message: {e}")

class ThermometerView(View):
    def __init__(self, cog, initial_embed, full_embed):
        super().__init__(timeout=None)
        self.cog = cog
        self.initial_embed = initial_embed
        self.full_embed = full_embed

    @discord.ui.button(label="Reward Breakdown", style=discord.ButtonStyle.grey)
    async def show_breakdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=self.full_embed, ephemeral=True)

class BalanceInfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.message = None

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.style == discord.ButtonStyle.link:
                continue
            child.disabled = True
            if isinstance(child, discord.ui.Select):
                child.options = [discord.SelectOption(label="Disabled due to timeout", value="X", emoji="⛔", default=True)]
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except (discord.NotFound, AttributeError, discord.HTTPException):
            pass

    def _remove_selects(self):
        to_remove = []
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                to_remove.append(child)
            elif getattr(child, "custom_id", "") == "bsort_select":
                to_remove.append(child)
        for child in to_remove:
            self.remove_item(child)

    @discord.ui.button(style=discord.ButtonStyle.blurple, emoji="📮", custom_id="stampcard", label="Stampcard")
    async def stampcard_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = int(interaction.message.attachments[0].filename.split("_")[1].split(".")[0])
        if interaction.user.id != user_id:
            return await interaction.response.send_message("This is not your command.", ephemeral=True)
        stamp_cog = interaction.client.get_cog("StampCard")
        if not stamp_cog:
            return await interaction.response.send_message("Stamp Card system unavailable.", ephemeral=True)
        embed, _ = await stamp_cog.get_stamp_embed(interaction.user, interaction.guild)
        self._remove_selects()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(style=discord.ButtonStyle.grey, custom_id="effect_info", emoji=EFFECT_EMOTE, label="Inventory")
    async def effect_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = int(interaction.message.attachments[0].filename.split("_")[1].split(".")[0])
        if interaction.user.id != user_id:
            return await interaction.response.send_message("This is not your command. You cannot use this button.", ephemeral=True)
        
        active_effects = await interaction.client.get_cog("CurrencySystem").effect_manager.get_user_active_effects(user_id)
        embed = discord.Embed(color=discord.Color.random())
        if active_effects:
            effect_list = []
            for effect_name, effect_data in active_effects.items():
                expires_at = effect_data.get("expires_at", 0)
                item_name = None
                for item_id, item_info in STORE_ITEMS.items():
                    if item_id == effect_name:
                        item_name = item_info["name"]
                        break
                
                if item_name:
                    indicator = ""
                    if effect_name == "streak_insurance":
                        uses = effect_data.get("uses_remaining", 0)
                        if uses > 0:
                            indicator = f" ({uses} use left)"
                        else:
                            continue
                    elif effect_name == "chat_bean_boost":
                        indicator = " (min 200 beans)"
                        
                    effect_list.append(f"-# {REPLY_EMOTE} `{item_name}`{indicator} *(Expires <t:{int(expires_at)}:R>)*")

            if effect_list:
                embed.add_field(
                    name=f"{EFFECT_EMOTE} Active Effects",
                    value="\n".join(effect_list),
                    inline=True
                )
        
        pin_ref = u_pin_message(user_id)
        pin_data = pin_ref.get() or {"count": 0}
        pin_count = pin_data.get("count", 0)
        
        if pin_count > 0:
            embed.add_field(
                name="📌 Message Pins",
                value=f"`{pin_count}` pin{'s' if pin_count != 1 else ''} available\n-# Use </pin:1427543833792610344> to pin messages",
                inline=True
            )

        customize_ref = u_customization(user_id)
        customize_data = customize_ref.get() or {"credits": 0}
        customize_credits = customize_data.get("credits", 0)

        if customize_credits > 0:
            embed.add_field(
                name="🎨 Background Customization",
                value=f"`{customize_credits}` credit{'s' if customize_credits != 1 else ''} available\n-# Use </customize:1486174479489957908> to edit card background",
                inline=True
            )

        star_drop_ref = u_star_drops(user_id)
        unopened_drops = star_drop_ref.get() or 0
        if unopened_drops > 0:
            embed.add_field(
                name=f"{STAR_DROP_EMOTE} Star Drops",
                value=f"`{unopened_drops}` star drop{'s' if unopened_drops != 1 else ''} unopened!\n-# Use </stardrop:1447676573020065996> to open them",
                inline=True
            )

        mega_box_ref = u_mega_boxes(user_id)
        unopened_boxes = mega_box_ref.get() or 0
        if unopened_boxes > 0:
            embed.add_field(
                name=f"{MEGA_BOX_EMOTE} Mega Boxes",
                value=f"`{unopened_boxes}` mega box{'es' if unopened_boxes != 1 else ''} unopened!\n-# Use </megabox:1486191980349358224> to open them",
                inline=True
            )

        if len(embed.fields) > 0:
            embed.title = f"{EFFECT_EMOTE} Your Active Effects & Inventory"
        else:
            embed.description = f"{NO_EMOTE} You have no active effects and inventory items."
            embed.color = discord.Color.red()

        self._remove_selects()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji="<a:invites:1456860324459184372>", custom_id="balance_invites", label="Invites")
    async def balance_invites(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = int(interaction.message.attachments[0].filename.split("_")[1].split(".")[0])
        if interaction.user.id != user_id:
            return await interaction.response.send_message("This is not your command. You cannot use this button.", ephemeral=True)

        ref = g_invites_monthly(interaction.guild.id, get_current_month_key(), interaction.user.id)
        data = ref.get() or {"valid": 0, "total": 0, "left": 0}
        valid = data.get("valid", 0)
        total = data.get("total", 0)
        left = data.get("left", 0)

        year, month_num = get_current_month_key().split('-')

        def _month_name(month_num):
            months = ["January", "February", "March", "April", "May", "June",
                     "July", "August", "September", "October", "November", "December"]
            return months[month_num - 1] if 1 <= month_num <= 12 else f"Month {month_num}"
        
        embed = discord.Embed(
            title=f"<:BrockCool:1391630483867172935> Your Monthly Invites ({_month_name(int(month_num))} {year})",
            description=f"> **`{valid}` invites** (`{total}` total, `{left}` left)",
            color=discord.Color.purple()
        )
        
        ref = g_invites_member_data(interaction.guild.id)
        all_data = ref.get() or {}
        months = set()
        
        for member_id, data in all_data.items():
            if data.get('inviter') == str(interaction.user.id):
                months.add(data.get('join_month'))
        
        months = sorted(months, reverse=True)[:25]
        ref_milestone = g_referral_milestones(interaction.guild.id, get_current_month_key(), interaction.user.id)
        milestone = ref_milestone.get() or {}
        progress = []
        trainee_emote = YES_EMOTE if milestone.get("trainee_done", False) else NO_EMOTE
        bridge_emote = YES_EMOTE if milestone.get("bridge_done", False) else NO_EMOTE
        master_emote = YES_EMOTE if milestone.get("master_done", False) else NO_EMOTE

        embed.add_field(
            name="<a:LeonConfused:1391625863107444820> Monthly Referrals Bonuses",
            value=(
                f"{trainee_emote} <@&{TRAINEE_ROLE_ID}>\n"
                f"-# {REPLY_EMOTE} Invite `1` new member to brew *(**Reward:** `+300` {BEAN_EMOTE})*\n"
                f"{bridge_emote} <@&{BRIDGE_ROLE_ID}>\n"
                f"-# {REPLY_EMOTE} Get `1` new member to sell *(**Reward:** `+3,000` {BEAN_EMOTE})*\n"
                f"{master_emote} <@&{MASTER_ROLE_ID}>\n"
                f"-# {REPLY_EMOTE} Get `3` sells from **any** new members " 
                f"*(**Reward:** earn `+50%` {TOKEN_EMOTE} every brew this month)*\n"
            ),
            inline=False
        )
        
        if not months:
            embed.description = "You haven't referred anyone yet! Invite your friends **using your own invite link**!\n-# <:reply:1036792837821435976> [How do I generate my personal invite link?](https://support.discord.com/hc/en-us/articles/208866998-Invites-101)"
            self._remove_selects()
            return await interaction.response.edit_message(embed=embed, view=self)
        
        self._remove_selects()
        from brawl.Currency.invitetracker import MonthSelect
        select = MonthSelect(interaction.user, months)
        select.row = 1
        self.add_item(select)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji="🍽️", custom_id="table_info", label="Table")
    async def table_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            user_id = int(interaction.message.attachments[0].filename.split("_")[1].split(".")[0])
        except:
            user_id = interaction.user.id
            
        if interaction.user.id != user_id:
            return await interaction.response.send_message("This is not your command. You cannot use this button.", ephemeral=True)

        table_cog = interaction.client.get_cog("table")
        if not table_cog:
             embed = discord.Embed(description="Table system is currently unavailable.", color=discord.Color.red())
             return await interaction.response.edit_message(embed=embed, view=self)
        
        table_data = await table_cog.get_user_table(interaction.user.id, interaction.guild.id)
        if not table_data:
            embed = discord.Embed(description=f"{NO_EMOTE} You're not seated at any table.", color=discord.Color.red())
            return await interaction.response.edit_message(embed=embed, view=self)
        
        host = await interaction.client.fetch_user(table_data["host"])
        host_name = host.mention if host else f"Unknown ({table_data['host']})"

        user_contributions = table_data.get('user_contributions', {})
        user_beans = user_contributions.get(str(interaction.user.id), 0)  

        embed = discord.Embed(
            title=f"{table_data['emoji']} Table: {table_data['name']}",
            description=f"\"{table_data['motto']}\"",
            color=int(table_data["color"].lstrip("#"), 16)
        )

        embed.add_field(name="🍽️ Host", value=host_name, inline=True)
        embed.add_field(name="🎨 Color", value=table_data['color'], inline=True)
        embed.add_field(name="📋 Status", value=f"{YES_EMOTE} Officially recognized table!" if table_data.get("formalized") else f"{NO_EMOTE} Not yet recognized (requires **5 people seated**).", inline=True)
        embed.add_field(name="📦 Weekly Beans", value=f"{BEAN_EMOTE} `{table_data.get('weekly_beans', 0):,}`", inline=True)
        embed.add_field(name="🙋 Your Contribution", value=f"{BEAN_EMOTE} `{user_beans:,}`", inline=True)
        embed.add_field(name="📅 Reserved At", value=f"<t:{int(table_data['created_at'])}:F>", inline=True)

        quest = table_data.get("quest", {})
        if quest and table_data.get("formalized", False):
            quest_config = TABLE_QUEST_TYPES["bean_collector"]
            current_tier = quest.get("current_tier", 0)
            completed_tiers = quest.get("completed_tiers", [])
            weekly_beans = table_data.get("weekly_beans", 0)
            
            quest_lines = []
            for i, (target, reward) in enumerate(zip(quest_config["targets"], quest_config["rewards"])):
                if i in completed_tiers:
                    quest_lines.append(f"- -# **Tier {i+1}:** {BEAN_EMOTE} `{target:,}` <a:Yes_dimmed:1393015472676540436>")
                elif i == current_tier:
                    progress_pct = min(100, int((weekly_beans / target) * 100))
                    bar_length = 16
                    filled = int((progress_pct / 100) * bar_length)
                    bar = "█" * filled + "░" * (bar_length - filled)
                    quest_lines.append(f"- **Tier {i+1}: `{bar}` {progress_pct}%**")
                    quest_lines.append(f"-# *<:reply:1036792837821435976> {BEAN_EMOTE} `{weekly_beans:,} / {target:,}` • Reward: {BEAN_EMOTE} `{reward}` per member*")
                else:
                    quest_lines.append(f"- -# **Tier {i+1}:** {BEAN_EMOTE} `{target:,}` 🔒")
            
            embed.add_field(
                name="🎯 Weekly Bean Collector Quest",
                value="\n".join(quest_lines) if quest_lines else "Quest data not available...",
                inline=True
            )

        members_list = [f"-# - {(await interaction.client.fetch_user(m)).mention if (await interaction.client.fetch_user(m)) else f'Unknown member ({m})'}" for m in table_data.get("members", [])]
        embed.add_field(name=f"📋 Seated Members ({len(table_data.get('members', []))}/10)", value="\n".join(members_list) if members_list else "No one seated", inline=True)
        embed.set_footer(text="Once your table is officially recognized, your emoji will be added to the daily chat bean notification")

        self._remove_selects()
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(style=discord.ButtonStyle.grey, emoji="<:quest:1490123182345293824>", custom_id="quests", label="Quests")
    async def quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user_id = int(interaction.message.attachments[0].filename.split("_")[1].split(".")[0])
            if interaction.user.id != user_id:
                return await interaction.response.send_message("This is not your command. You cannot use this button.", ephemeral=True)
        except:
            pass

        guild_id = interaction.guild.id
        
        # Refresh quests in case they need to reset
        await update_quest(user_id, guild_id, {}, interaction.client, refresh_only=True)
        
        # Import quest constants
        from brawl.Currency.quests import QUEST_DESCRIPTIONS, QUEST_BEAN_REWARDS, QUEST_BONUS_BEANS
        from brawl.Currency.db import u_quests
        
        ref = u_quests(user_id)
        quest_data = ref.get() or {}
        
        quest_text = []
        for duration in ["daily", "weekly", "monthly"]:
            dur_data = quest_data.get(duration, {})
            quests = dur_data.get("quests", {})
            completed = dur_data.get("completed", {})
            end_time = dur_data.get("end_time", 0)
            
            if not quests:
                continue
                
            reset_time = f"<t:{end_time}:R>" if end_time else "Unknown"
            quest_text.append(f"### {duration.capitalize()} Quests - {BEAN_EMOTE} `{QUEST_BEAN_REWARDS[duration]}` Beans each *(resets {reset_time})*")
            
            for q_type, data in quests.items():
                status = f"`{data['current']}/{data['goal']}` <:yes:1036811164891480194>" if q_type in completed else f"`{data['current']}/{data['goal']}`"
                quest_text.append(f"- {QUEST_DESCRIPTIONS.get(q_type, q_type)}: {status}")
                
            if dur_data.get("bonus_awarded"):
                quest_text.append(f"-# <:reply:1036792837821435976> *{BEAN_EMOTE} `{QUEST_BONUS_BEANS[duration]}` Beans bonus already claimed! <:resolved:1364813186028797984>*")
            else:
                quest_text.append(f"-# <:reply:1036792837821435976> *Complete all for `+{QUEST_BONUS_BEANS[duration]}` Beans bonus! <a:tada:1227425729654820885>*")
        
        if not quest_text:
            quest_text = ["No active quests. Check back when new quests are available!"]
        
        embed = discord.Embed(
            title="<:quest:1490123182345293824> Your Quests",
            description="\n".join(quest_text),
            color=discord.Color.green()
        )
        embed.set_footer(text="Tip: Quests reset at midnight UTC time")
        
        self._remove_selects()
        await interaction.response.edit_message(embed=embed, view=self)

    # @discord.ui.button(style=discord.ButtonStyle.grey, emoji="<:account:1486161374601154601>", custom_id="brawl_home", label="Profile")
    # async def brawl_home(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     try:
    #         user_id = int(interaction.message.attachments[0].filename.split("_")[1].split(".")[0])
    #         if interaction.user.id != user_id:
    #             return await interaction.response.send_message("This is not your command. You cannot use this button.", ephemeral=True)
    #     except:
    #         pass

    #     ref = u_tag(interaction.user.id)
    #     data = ref.get()
    #     if not data or 'tag' not in data:
    #         embed = discord.Embed(
    #             description=f"{NO_EMOTE} You haven't linked your Brawl Stars profile yet. Use `/profile` to link it.",
    #             color=discord.Color.red()
    #         )
    #         return await interaction.response.send_message(embed=embed, ephemeral=True)
            
    #     tag = data['tag']
    #     from brawl.Utility.profile import fetch_profile, make_home
        
    #     prof_resp, prof_data = fetch_profile(tag)
    #     if not prof_resp.ok:
    #         return await interaction.response.send_message(f"Error fetching profile: {prof_resp.status_code}", ephemeral=True)
            
    #     raw_color = prof_data.get('nameColor','0xFFFFFF')
    #     try: color = int(raw_color,16)&0xFFFFFF
    #     except: color = 0xFFFFFF
        
    #     embed = await make_home(prof_data, color)
    #     embed.description = "Use </profile:1341939588301590551> to view full profile, such as Brawlers and Matches."
    #     self._remove_selects()
    #     await interaction.response.edit_message(embed=embed, view=self)


class CurrencySystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.chat_system = ChatRewardSystem(self.bot)
        self.effect_manager = EffectManager(self.bot)
        self.tutorial_manager = TutorialManager(self.bot)
        self.bot.loop.create_task(self.monthly_referral_reset())
        heat_ref = g_thermometer(MAIN_GUILD_ID).get()
        self.thermometer_heat = heat_ref.get("heat", 0) if heat_ref else 0
        self.thermometer_decay_task = self.bot.loop.create_task(self.thermometer_decay_loop())
        self.thermo_bean_update_task = self.bot.loop.create_task(self.thermo_bean_update_loop())
        self.effect_cleanup_task = self.bot.loop.create_task(self.effect_cleanup_loop())
        self.sell_alarm_task = self.bot.loop.create_task(self.sell_alarm_check_loop())
        self.boss_inspection_task = self.bot.loop.create_task(self.boss_inspection_loop())

    async def check_and_update_token_reward_limit(self, user_id: int):
        """Check if user can receive token rewards today and update count"""
        ref = u_thermometer_cooldown(user_id)
        data = ref.get() or {}
        current_time = time.time()
        
        if 'first_reward_time' in data and current_time - data['first_reward_time'] >= 86400:
            data = {'count': 0, 'first_reward_time': current_time}
        
        if 'count' not in data:
            data['count'] = 0
        if 'first_reward_time' not in data:
            data['first_reward_time'] = current_time
            
        if data['count'] >= 3:
            return False, data['count'], data['first_reward_time'] + 86400
        
        data['count'] += 1
        ref.set(data)
        
        return True, data['count'], data['first_reward_time'] + 86400

    async def thermo_bean_update_loop(self):
        """Process cached thermo beans every minute to reduce database writes"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(60) 
            
            async with self.chat_system.thermo_bean_lock:
                cache = self.chat_system.thermo_bean_cache
                self.chat_system.thermo_bean_cache = {}
            
            for user_id, beans in cache.items():
                await self.add_beans(user_id, beans)
    
    async def effect_cleanup_loop(self):
        """Clean up expired effects every minute"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self.effect_manager.cleanup_expired_effects()
            except Exception as e:
                print(f"Error cleaning up effects: {e}")
            await asyncio.sleep(60)

    async def thermometer_decay_loop(self):
        """Decay thermometer heat by 5% every minute"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(60) 
            
            freeze_ref = g_shop_effects(MAIN_GUILD_ID)
            all_effects = freeze_ref.get() or {}
            current_time = time.time()
            current_time = time.time()
            
            frozen = False
            for user_id, user_effects in all_effects.items():
                freeze_data = user_effects.get("freeze_thermometer", {})
                if freeze_data.get("active", False) and current_time < freeze_data.get("expires_at", 0):
                    frozen = True
                    if freeze_data.get("frozen_heat") is None:
                        freeze_data["frozen_heat"] = self.thermometer_heat
                        sync_shop_effects(int(user_id), "freeze_thermometer", 'update', {"frozen_heat": self.thermometer_heat}, MAIN_GUILD_ID)
                    break
            
            if frozen:
                continue
                
            current_heat = self.thermometer_heat
            if current_heat > 0:
                if current_heat > 100:
                    new_heat = max(0, current_heat - 20)
                elif current_heat > 75:
                    new_heat = max(0, current_heat - 10)
                elif current_heat > 50:
                    new_heat = max(0, current_heat - 5)
                else:
                    new_heat = max(0, current_heat - 2)
                self.thermometer_heat = new_heat
                g_thermometer(MAIN_GUILD_ID).set({"heat": new_heat})
    
    async def monthly_referral_reset(self):
        """Reset referral system on 1st of each month"""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            now = datetime.now(timezone.utc)
            if now.day == 1 and now.hour == 0:
                guild = self.bot.get_guild(MAIN_GUILD_ID)
                if not guild:
                    await asyncio.sleep(3600)
                    continue

                for role_id in [TRAINEE_ROLE_ID, BRIDGE_ROLE_ID, MASTER_ROLE_ID]:
                    role = guild.get_role(role_id)
                    if role:
                        for member in role.members:
                            await member.remove_roles(role)

                current_month = get_current_month_key()
                g_referral_milestones(guild.id, current_month).delete()

                channel = self.bot.get_channel(INVITE_LOG)
                if channel:
                    await channel.send(
                        f"🔄 **Monthly Referral Reset**\n"
                        f"All Barista roles removed\n"
                        f"Milestone data cleared for {current_month}"
                    )

                await asyncio.sleep(82800)
            else:
                await asyncio.sleep(3600)

    async def sell_alarm_check_loop(self):
        """Check every 5 minutes for brews ready to sell and send DM notifications"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                await asyncio.sleep(300)
                
                alarm_ref = g_sell_alarm(MAIN_GUILD_ID)
                all_alarms = alarm_ref.get() or {}
                current_time = time.time()
                
                for user_id_str, alarm_data in all_alarms.items():
                    user_id = int(user_id_str)
                    
                    if alarm_data.get("notified", False):
                        continue
                    
                    end_time = alarm_data.get("end_time", 0)
                    if current_time >= end_time:
                        active_effects = await self.effect_manager.get_user_active_effects(user_id)
                        if "sell_alarm" not in active_effects:
                            sync_sell_alarm(user_id, 'delete', guild_id=MAIN_GUILD_ID)
                            continue
                        
                        try:
                            user = await self.bot.fetch_user(user_id)
                            if user:
                                guild = self.bot.get_guild(MAIN_GUILD_ID)
                                bot_channel = guild.get_channel(BOT_COMMANDS) if guild else None
                                
                                embed = discord.Embed(
                                    title="☕ Brew Ready to Sell!",
                                    description=f"Your **{ROAST_TYPES.get(alarm_data.get('roast_type', 'light'), {}).get('name', 'coffee')}** (Batch ID: `{alarm_data.get('batch_id', 'N/A')}`) is ready to sell!",
                                    color=0x6F4E37 
                                )
                                embed.add_field(
                                    name="What to do?",
                                    value=f"Head to {bot_channel.mention if bot_channel else 'the bot channel'} and use </sell:1396588612790784071> to collect your tokens!",
                                    inline=False
                                )
                                embed.set_footer(text="This is an automated reminder from your Sell Alarm effect")
                                
                                view = discord.ui.View()
                                if bot_channel:
                                    button = discord.ui.Button(
                                        label="Go to Bot Channel",
                                        style=discord.ButtonStyle.link,
                                        url=f"https://discord.com/channels/{guild.id}/{bot_channel.id}"
                                    )
                                    view.add_item(button)
                                
                                await user.send(embed=embed, view=view if bot_channel else None)
                                sync_sell_alarm(user_id, 'update', {"notified": True}, MAIN_GUILD_ID)
                                
                        except discord.Forbidden:
                            sync_sell_alarm(user_id, 'update', {"notified": True}, MAIN_GUILD_ID)
                        except Exception as e:
                            print(f"Error sending sell alarm DM to user {user_id}: {e}")
                            
            except Exception as e:
                print(f"Error in sell_alarm_check_loop: {e}")
                await asyncio.sleep(60)

    async def boss_inspection_loop(self):
        """Drop Boss Inspection 1-3 times a day in random chat channels (UTC time)"""
        await self.bot.wait_until_ready()
        
        await asyncio.sleep(10)
        
        while not self.bot.is_closed():
            try:
                current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                ref = g_boss_inspection(MAIN_GUILD_ID)
                inspection_data = ref.get() or {}
                
                if not inspection_data:
                    drops_today = random.randint(1, 3)
                    inspection_data = {
                        "total_drops": drops_today,
                        "completed_drops": 0,
                        "last_drop_time": 0
                    }
                    ref.set(inspection_data)
                    print(f"Boss Inspection: New day initialized with {drops_today} drops planned")
                
                if inspection_data["completed_drops"] >= inspection_data["total_drops"]:
                    now = datetime.now(timezone.utc)
                    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    seconds_until_midnight = (next_midnight - now).total_seconds()
                    
                    print(f"Boss Inspection: All drops complete for today. Sleeping until midnight ({seconds_until_midnight/3600:.2f} hours)")
                    await asyncio.sleep(seconds_until_midnight + 60) 
                    continue
                
                min_wait = 30 * 60 
                max_wait = 8 * 3600 
                wait_time = random.uniform(min_wait, max_wait)
                
                now = datetime.now(timezone.utc)
                next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until_midnight = (next_midnight - now).total_seconds()
                
                if wait_time >= seconds_until_midnight:
                    print(f"Boss Inspection: Not enough time for another drop today. Waiting until midnight.")
                    await asyncio.sleep(seconds_until_midnight + 60)
                    continue
                
                print(f"Boss Inspection: Waiting {wait_time/3600:.2f} hours until next drop")
                await asyncio.sleep(wait_time)
                
                if self.bot.is_closed():
                    break
                
                new_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if new_date != current_date:
                    print("Boss Inspection: Day changed during sleep, restarting loop")
                    continue
                
                if not MAIN_CHAT_CHANNELS:
                    print("Warning: Boss Inspection channels not configured!")
                    await asyncio.sleep(3600)
                    continue
                    
                channel_id = random.choice(MAIN_CHAT_CHANNELS)
                channel = self.bot.get_channel(channel_id)
                
                if not channel:
                    print(f"Warning: Could not find channel {channel_id} for Boss Inspection")
                    await asyncio.sleep(3600)
                    continue
                
                all_action_keys = list(BOSS_INSPECTION_ACTIONS.keys())
                selected_action_keys = random.sample(all_action_keys, 3)
                
                view = BossInspectionView(self, selected_action_keys)
                message = await channel.send(
                    content=f"<@&{BOSS_INSPECTION_ROLE_ID}> The boss has arrived for a surprise inspection! 😰",
                    embed=BOSS_EMBED, 
                    view=view
                )
                view.message = message
                
                inspection_data["completed_drops"] += 1
                inspection_data["last_drop_time"] = time.time()
                ref.set(inspection_data)
                print(f"Boss Inspection dropped in {channel.name} (drop {inspection_data['completed_drops']}/{inspection_data['total_drops']})")
            except Exception as e:
                print(f"Error in boss_inspection_loop: {e}")
                await asyncio.sleep(3600)  

    def _get_balance_ref(self, user_id: int):
        return u_balance(user_id)

    async def add_beans(self, user_id: int, amount: int, skip_quest_check: bool = False):
        """Add Beans to user balance."""
        ref = self._get_balance_ref(user_id)
        data = ref.get() or {}
        beans = data.get('Beans', 0)
        new_beans = beans + amount
        ref.update({'Beans': new_beans})

        mega_pass = self.bot.get_cog("MegaPass") or self.bot.get_cog("megapass")
        if mega_pass:
            asyncio.create_task(mega_pass.add_contribution(user_id, beans=amount))

        if skip_quest_check:
            return new_beans

        table_cog = self.bot.get_cog("table")
        if table_cog:
            table_data = await table_cog.get_user_table(user_id, MAIN_GUILD_ID)
            if table_data and table_data.get("formalized", False):
                table_ref = table_cog._get_table_ref(MAIN_GUILD_ID, table_data["name"].lower())
                current_beans = table_data.get("weekly_beans", 0)
                new_total_beans = current_beans + amount
                user_contributions = table_data.get("user_contributions", {})
                user_current_contribution = user_contributions.get(str(user_id), 0)
                user_contributions[str(user_id)] = user_current_contribution + amount
                
                table_ref.update({
                    "weekly_beans": new_total_beans,
                    "user_contributions": user_contributions
                })
                try:
                    quest_result = await table_cog.check_and_reward_quest(
                        MAIN_GUILD_ID, 
                        table_data["name"].lower(), 
                        new_total_beans
                    )
                except Exception as e:
                    print(f"Error checking quest: {e}")
        return new_beans

    async def add_tokens(self, user_id: int, amount: int):
        """Add Tokens to user balance."""
        ref = self._get_balance_ref(user_id)
        data = ref.get() or {}
        tokens = data.get('Tokens', 0)
        new_tokens = tokens + amount
        ref.update({'Tokens': new_tokens})
        
        mega_pass = self.bot.get_cog("MegaPass") or self.bot.get_cog("megapass")
        if mega_pass:
            asyncio.create_task(mega_pass.add_contribution(user_id, tokens=amount))
            
        return new_tokens

    async def get_balance(self, user_id: int):
        """Get user's current Beans and Tokens balance."""
        ref = self._get_balance_ref(user_id)
        data = ref.get() or {}
        beans = data.get('Beans', 0)
        tokens = data.get('Tokens', 0)
        return beans, tokens

    async def update_balance(self, user_id: int, beans: int = None, tokens: int = None):
        """Update user's Beans and/or Tokens balance."""
        ref = self._get_balance_ref(user_id)
        data = ref.get() or {}
        if beans is not None:
            data['Beans'] = beans
        if tokens is not None:
            data['Tokens'] = tokens
        ref.set(data)

    async def check_gambling_limit(self, user_id: int, game_type: str):
        """Check if user has reached their daily gambling limit for a specific game."""
        if game_type not in DAILY_GAMBLING_LIMITS:
            return True, 0 
        
        date_key = get_current_date_key()
        ref = u_gambling_limits(user_id, date_key)
        data = ref.get() or {}
        current_usage = data.get(game_type, 0)
        limit = DAILY_GAMBLING_LIMITS[game_type]
        
        guild = self.bot.get_guild(MAIN_GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            ultra_role = guild.get_role(ULTRA_TIER_ROLE_ID)
            if member and ultra_role and ultra_role in member.roles:
                limit *= 2
        
        return current_usage < limit, current_usage

    async def increment_gambling_usage(self, user_id: int, game_type: str):
        """Increment the user's daily gambling usage for a specific game."""
        if game_type not in DAILY_GAMBLING_LIMITS:
            return
        
        date_key = get_current_date_key()
        ref = u_gambling_limits(user_id, date_key)
        data = ref.get() or {}
        current_usage = data.get(game_type, 0)
        data[game_type] = current_usage + 1
        ref.set(data)
    
    def _get_brew_ref(self, user_id: int):
        return u_brews(user_id)

    async def get_active_brew(self, user_id: int):
        ref = self._get_brew_ref(user_id)
        data = ref.get()
        return data.get('active_brew') if data else None

    async def set_active_brew(self, user_id: int, brew_data: dict):
        ref = self._get_brew_ref(user_id)
        data = ref.get() or {}
        data['active_brew'] = brew_data
        ref.set(data)

    async def remove_active_brew(self, user_id: int):
        ref = self._get_brew_ref(user_id)
        data = ref.get() or {}
        if 'active_brew' in data:
            del data['active_brew']
            ref.set(data)
            return True
        return False

    async def update_brew_stats(self, user_id: int, stats: dict):
        ref = self._get_brew_ref(user_id)
        data = ref.get() or {}
        data['stats'] = stats
        ref.set(data)

    async def get_brew_stats(self, user_id: int):
        ref = self._get_brew_ref(user_id)
        data = ref.get()
        return data.get('stats') if data else None

    async def record_brew_history(self, user_id: int, history_data: dict):
        ref = self._get_brew_ref(user_id)
        data = ref.get() or {}
        history = data.get('history', [])
        history.append(history_data)
        data['history'] = history[-10:]  # Keep last 10 brews to avoid unbounded growth
        ref.set(data)

    async def update_brew_stats_on_brew(self, user_id: int, roast_type: str):
        stats = await self.get_brew_stats(user_id) or {
            "total_brews": 0,
            "total_tokens": 0,
            "light": 0,
            "medium": 0,
            "dark": 0,
            "golden": 0,
            "most_brewed": "none",
            "last_brew": None
        }

        stats["total_brews"] += 1
        stats[roast_type] = stats.get(roast_type, 0) + 1
        roasts = ["light", "medium", "dark", "golden"]
        roast_counts = {r: stats.get(r, 0) for r in roasts}
        max_roast = max(roast_counts, key=roast_counts.get)
        stats["most_brewed"] = max_roast
        await self.update_brew_stats(user_id, stats)
        return stats

    async def update_brew_stats_on_sell(self, user_id: int, tokens: int, roast_type: str, perfect: bool, insured: bool, saved_burn: bool):
        stats = await self.get_brew_stats(user_id) or {
            "total_brews": 0,
            "total_tokens": 0,
            "light": 0,
            "medium": 0,
            "dark": 0,
            "golden": 0,
            "most_brewed": "none",
            "last_brew": None
        }

        stats["total_tokens"] += tokens
        stats["last_brew"] = {
            "roast_type": roast_type,
            "tokens": tokens,
            "perfect": perfect,
            "insured": insured,
            "saved_burn": saved_burn,
            "time": time.time()
        }

        await self.update_brew_stats(user_id, stats)
        return stats
    
    async def insure_brew(self, user_id: int, roast_type: str):
        """Insure an active brew and deduct insurance cost"""
        insurance_cost = ROAST_TYPES[roast_type]["insurance_cost"]
        active_effects = await self.effect_manager.get_user_active_effects(user_id)
        free_insurance = "free_insurance" in active_effects

        guild = self.bot.get_guild(MAIN_GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            ultra_role = guild.get_role(ULTRA_TIER_ROLE_ID)
            if member and ultra_role and ultra_role in member.roles:
                free_insurance = True
        
        if not free_insurance:
            beans, tokens = await self.get_balance(user_id)
            if beans < insurance_cost:
                return False
            
            new_beans = beans - insurance_cost
            await self.update_balance(user_id, beans=new_beans)
        
        ref = self._get_brew_ref(user_id)
        data = ref.get() or {}
        if 'active_brew' in data:
            data['active_brew']['insured'] = True
            data['active_brew']['free_insurance'] = free_insurance
            ref.set(data)
            
            if hasattr(self, 'tutorial_manager'):
                asyncio.create_task(self.tutorial_manager.on_insured(user_id))

            return True
        return False

    def get_min_nonzero_reward(self, roast_type: str) -> int:
        """Get the minimum non-zero reward for a roast type"""
        rewards = ROAST_TYPES[roast_type]["payout"]
        non_zero = [r for r in rewards if r > 0]
        return min(non_zero) if non_zero else 0
    
    async def process_invitee_welcome_bonus(self, interaction, event_type, invitee):
        """Process welcome bonus for an invitee and notify inviter"""
        guild = interaction.guild
        ref_mapping = g_invites_member_data(guild.id, invitee.id)
        mapping = ref_mapping.get() or {}

        if not mapping.get("inviter") or not mapping.get("is_new"):
            return None

        inviter_id = int(mapping["inviter"])
        try:
            inviter = await guild.fetch_member(inviter_id)
        except (discord.NotFound, discord.HTTPException):
            return None
        if not inviter:
            return None

        account_age = (datetime.now(timezone.utc) - invitee.created_at).days
        if account_age < 14:
            return None

        current_month = get_current_month_key()
        ref_history = g_member_history(guild.id, invitee.id)
        history = ref_history.get()
        if history and history.get("first_join") and history["first_join"] < current_month:
            return None  

        bonus_key = f"{event_type}_done"
        if mapping.get(bonus_key, False):
            return None  
        
        mapping[bonus_key] = True
        ref_mapping.set(mapping)

        if event_type == 'brew':
            beans_earned = 150
            message_invitee = f"🎉 **Welcome bonus!** You earned a bonus {BEAN_EMOTE} **{beans_earned} Beans** for your first brew!"
            message_inviter = f"☕ Your invitee {invitee.mention} **brewed** their first coffee and earned a welcome bonus!"
            await self.log_referral_milestone(f"{inviter.mention}'s (inviter) invitee {invitee.mention} **brewed** their first coffee and earned a welcome bonus!", "Brew Welcome Bonus")
        else: 
            beans_earned = 500
            message_invitee = f"🎉 **Welcome bonus!** You earned a bonus {BEAN_EMOTE} **{beans_earned} Beans** for your first sale!"
            message_inviter = f"☕ Your invitee {invitee.mention} **sold** their first coffee and earned a welcome bonus!"
            await self.log_referral_milestone(f"{inviter.mention}'s (inviter) invitee {invitee.mention} **sold** their first coffee and earned a welcome bonus!", "Sell Welcome Bonus")

        await self.add_beans(invitee.id, beans_earned)
        
        try:
            await inviter.send(embed=discord.Embed(description=message_inviter, color=0x808080))
        except (discord.Forbidden, discord.HTTPException):
            pass
        return message_invitee
    
    async def process_referral_milestone(self, interaction, milestone_type, invitee):
        """Process referral milestones (inviter only)"""
        guild = interaction.guild
        current_month = get_current_month_key()

        ref_mapping = g_invites_member_data(guild.id, invitee.id)
        mapping = ref_mapping.get() or {}

        if not mapping.get("inviter") or not mapping.get("is_new"):
            return None, None

        inviter_id = int(mapping["inviter"])
        try:
            inviter = await guild.fetch_member(inviter_id)
        except (discord.NotFound, discord.HTTPException):
            return None, None
        if not inviter:
            return None, None

        account_age = (datetime.now(timezone.utc) - invitee.created_at).days
        if account_age < 14:
            return None, None

        ref_history = g_member_history(interaction.guild.id, invitee.id)
        history = ref_history.get()
        if history and history.get("first_join") and history["first_join"] < current_month:
            return None, None 

        ref_milestone = g_referral_milestones(guild.id, current_month, inviter_id)
        milestone = ref_milestone.get() or {
            "trainee_done": False,
            "bridge_done": False,
            "master_done": False,
            "sells": 0
        }

        reward_message = ""
        role_granted = None
        log_entry = None

        if milestone_type == "trainee" and not milestone["trainee_done"]:
            milestone["trainee_done"] = True
            mapping["brew_done"] = True
            role_granted = TRAINEE_ROLE_ID
            await self.add_beans(inviter_id, 300) 
            reward_message = f"🎉 Your invitee {invitee.mention} brewed their first coffee! You **earned {BEAN_EMOTE} `300` Beans** and unlocked the `Trainee Barista` role!"
            log_entry = f"🎯 **Milestone Reached:** <@&{TRAINEE_ROLE_ID}>\n🎁 **Reward:** `+300` Beans to {inviter.mention} (inviter)\n👤 **Invitee:** {invitee.mention}"

        elif milestone_type == "bridge" and not milestone["bridge_done"] and milestone["trainee_done"]:
            milestone["bridge_done"] = True
            mapping["sell_done"] = True
            role_granted = BRIDGE_ROLE_ID
            await self.add_beans(inviter_id, 3000) 
            reward_message = f"🎉 Your invitee {invitee.mention} sold their first coffee! You **earned {BEAN_EMOTE} `3,000` Beans** and unlocked the `Bridge Barista` role!"
            log_entry = f"🎯 **Milestone Reached:** <@&{BRIDGE_ROLE_ID}>\n🎁 **Reward:** `+3000` Beans to {inviter.mention} (inviter)\n👤 **Invitee:** {invitee.mention}"

        elif milestone_type == "sell":
            milestone["sells"] = milestone.get("sells", 0) + 1
            if milestone["sells"] >= 3 and not milestone["master_done"]:
                milestone["master_done"] = True
                role_granted = MASTER_ROLE_ID
                reward_message = f"🏆 Your invitee(s) have successfully sold a total of 3 coffees! You unlocked the `Master Barista` role and will now **earn {TOKEN_EMOTE} `+50%` Tokens per non-burnt brew** until the end of this month."
                log_entry = f"🎯 **Milestone Reached:** <@&{MASTER_ROLE_ID}>\n🎁 **Reward:** `+`1 Token per future brew for {inviter.mention} (inviter)\n👤 **Invitee:** {invitee.mention}"

        color = discord.Color.blurple()
        if role_granted:
            role = guild.get_role(role_granted)
            if role:
                await inviter.add_roles(role)
                color = role.color

        ref_milestone.set(milestone)
        ref_mapping.set(mapping)

        if reward_message:
            try:
                await inviter.send(embed=discord.Embed(description=reward_message, color=color))
            except (discord.Forbidden, discord.HTTPException):
                pass

        return log_entry, inviter

    async def log_referral_milestone(self, log_entry, title_override = None):
        """Log milestone to referral channel"""
        channel = self.bot.get_channel(INVITE_LOG)
        if channel and log_entry:
            embed = discord.Embed(
                title=title_override if title_override else "New Referral Milestone!",
                description=log_entry,
                color=discord.Color.gold()
            )
            embed.set_footer(text=f"🕒 Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
            await channel.send(embed=embed)

    async def get_user_ranks(self, user_id: int):
        eco_ref = db.reference(U_ROOT)
        eco_data = eco_ref.get() or {}
        
        beans_list = []
        tokens_list = []
        streak_list = []
        
        for uid_str, user_data in eco_data.items():
            if not (uid_str.isdigit()):
                continue
            
            # Get balance
            balance = user_data.get('balance', {})
            beans = balance.get('Beans', 0)
            tokens = balance.get('Tokens', 0)
            
            if beans > 0:
                beans_list.append((uid_str, beans))
            if tokens > 0:
                tokens_list.append((uid_str, tokens))
            
            # Get daily checkin streak
            progress = user_data.get('progress', {})
            daily_checkin = progress.get('daily_checkin_streaks', {})
            streak = daily_checkin.get('current_streak', 0)
            if streak > 0:
                streak_list.append((uid_str, streak))
        
        beans_list.sort(key=lambda x: x[1], reverse=True)
        tokens_list.sort(key=lambda x: x[1], reverse=True)
        streak_list.sort(key=lambda x: x[1], reverse=True)
        
        beans_rank = 0
        for i, (uid, _) in enumerate(beans_list):
            if str(uid) == str(user_id):
                beans_rank = i + 1
                break
        
        tokens_rank = 0
        for i, (uid, _) in enumerate(tokens_list):
            if str(uid) == str(user_id):
                tokens_rank = i + 1
                break
        
        streak_rank = 0
        for i, (uid, _) in enumerate(streak_list):
            if str(uid) == str(user_id):
                streak_rank = i + 1
                break
        
        return beans_rank, tokens_rank, streak_rank

    async def generate_balance_card(self, user: discord.Member, beans: int, tokens: int, streak: int, earnings: int, max_earnings: int, reset_time: float, active_brew: dict = None, total_brews: int = 0, table_name: str = None, table_emoji_url: str = None, level: int = 0, rank: int = 0, current_xp: int = 0, xp_needed: int = 100, beans_rank: int = 0, tokens_rank: int = 0, streak_rank: int = 0, custom_bg: str = None, custom_bg_bytes: bytes = None) -> discord.File:
        WIDTH, HEIGHT = 900, 370
        
        img = None
        if custom_bg_bytes:
            try:
                img = Image.open(io.BytesIO(custom_bg_bytes)).convert("RGBA")
            except Exception as e:
                print(f"Error loading custom bg bytes: {e}")
        elif custom_bg:
            try:
                if os.path.exists(custom_bg):
                    img = Image.open(custom_bg).convert("RGBA")
            except Exception as e:
                print(f"Error loading custom bg: {e}")
                
        if img:
            try:
                img_ratio = img.width / img.height
                target_ratio = WIDTH / HEIGHT
                
                if img_ratio > target_ratio:
                    new_width = int(img.height * target_ratio)
                    offset = (img.width - new_width) // 2
                    img = img.crop((offset, 0, offset + new_width, img.height))
                elif img_ratio < target_ratio:
                    new_height = int(img.width / target_ratio)
                    offset = (img.height - new_height) // 2
                    img = img.crop((0, offset, img.width, offset + new_height))
                    
                img = img.resize((WIDTH, HEIGHT))
                
                overlay = Image.new('RGBA', img.size, (0, 0, 0, 180))
                img = Image.alpha_composite(img, overlay).convert("RGB")
            except Exception as e:
                print(f"Error loading custom bg: {e}")
                pass
                
        if not img:
            BG = (34, 34, 38)
            img = Image.new("RGB", (WIDTH, HEIGHT), BG)
            
        draw = ImageDraw.Draw(img)
        
        fill_color = (115, 219, 250)
        for role in sorted(user.roles, key=lambda r: r.position, reverse=True):
            if role.color.value != 0:
                fill_color = role.color.to_rgb()
                break

        def try_load_font(preferred_names, size):
            for name in preferred_names:
                try:
                    return ImageFont.truetype(name, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        bold_candidates = [
            "/root/Vanity/assets/LilitaOne-Regular.ttf",
            "arialbd.ttf", "Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        ]
        regular_candidates = [
            "arial.ttf", "Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]

        LABEL_SIZE = 20
        VALUE_SIZE = 36
        USERNAME_SIZE = 40
        
        label_font = try_load_font(regular_candidates, LABEL_SIZE)
        value_font = try_load_font(bold_candidates, VALUE_SIZE)
        small_value_font = try_load_font(bold_candidates, VALUE_SIZE - 10)
        username_font = try_load_font(bold_candidates, USERNAME_SIZE)

        AVATAR_SIZE = 180
        AVATAR_X = 50
        AVATAR_Y = (HEIGHT - AVATAR_SIZE - 50) // 2

        try:
            avatar_url = str(user.display_avatar.url)
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    avatar_bytes = await resp.read()
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((AVATAR_SIZE, AVATAR_SIZE))
            mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, AVATAR_SIZE, AVATAR_SIZE), fill=255)
            img.paste(avatar, (AVATAR_X, AVATAR_Y), mask)
        except Exception:
            draw.ellipse((AVATAR_X, AVATAR_Y, AVATAR_X + AVATAR_SIZE, AVATAR_Y + AVATAR_SIZE), fill=(80, 80, 80))

        badge_size = 40
        badge_gap = 10
        
        badge_icons = []
        sorted_roles = sorted(user.roles, key=lambda r: r.position, reverse=True)
        for role in sorted_roles:
            if role.icon:
                badge_icons.append(role.icon.url)
            if len(badge_icons) >= 3:
                break
        
        if badge_icons:
            total_width = (len(badge_icons) * badge_size) + ((len(badge_icons) - 1) * badge_gap)
            start_x = AVATAR_X + (AVATAR_SIZE - total_width) // 2
            badge_y = AVATAR_Y + AVATAR_SIZE + 10
            
            current_x = start_x
            for badge_url in badge_icons:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(badge_url) as resp:
                            if resp.status == 200:
                                badge_bytes = await resp.read()
                                badge_img = Image.open(io.BytesIO(badge_bytes)).convert("RGBA").resize((badge_size, badge_size))
                                img.paste(badge_img, (int(current_x), int(badge_y)), badge_img)
                                current_x += badge_size + badge_gap
                except Exception:
                    continue

        CONTENT_X = AVATAR_X + AVATAR_SIZE + 50
        CURRENT_Y = 28

        draw.text((CONTENT_X, CURRENT_Y), f"{user.display_name}", font=username_font, fill=(255, 255, 255))
        CURRENT_Y += USERNAME_SIZE + 10

        table_text = f"{table_name}" if table_name else "Not in a Table"
        draw.text((CONTENT_X, CURRENT_Y), table_text, font=label_font, fill=(200, 200, 200))
        
        if table_emoji_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(table_emoji_url) as resp:
                        emoji_bytes = await resp.read()
                emoji_img = Image.open(io.BytesIO(emoji_bytes)).convert("RGBA").resize((30, 30))
                text_len = draw.textlength(table_text, font=label_font)
                img.paste(emoji_img, (int(CONTENT_X + text_len + 10), int(CURRENT_Y - 5)), emoji_img)
            except:
                pass
        CURRENT_Y += 30

        STATS_Y = CURRENT_Y + 20
        ICON_SIZE = 50
        
        async def draw_stat(x, y, label, value, icon_url, rank_val=0):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(icon_url) as resp:
                        icon_bytes = await resp.read()
                icon = Image.open(io.BytesIO(icon_bytes)).convert("RGBA").resize((ICON_SIZE, ICON_SIZE))
                img.paste(icon, (x, y), icon)
            except:
                pass
            
            draw.text((x + ICON_SIZE + 15, y), label, font=label_font, fill=(170, 170, 170))
            
            if rank_val > 0:
                rank_text = f"#{rank_val}"
                label_width = draw.textlength(label, font=label_font)
                
                tag_font = try_load_font(bold_candidates, 14)
                tag_width = draw.textlength(rank_text, font=tag_font) + 10
                tag_height = 20
                tag_x = x + ICON_SIZE + 15 + label_width + 10
                tag_y = y
                
                draw.rounded_rectangle([(tag_x, tag_y), (tag_x + tag_width, tag_y + tag_height)], radius=5, fill=(60, 60, 60))
                draw.text((tag_x + 5, tag_y + 2), rank_text, font=tag_font, fill=(200, 200, 200))

            draw.text((x + ICON_SIZE + 15, y + 25), f"{value:,}", font=value_font, fill=(255, 255, 255) if label != "Tokens" else fill_color)

        await draw_stat(CONTENT_X, STATS_Y, "Beans", beans, "https://cdn.discordapp.com/emojis/1393442086279315456.png", beans_rank)
        await draw_stat(CONTENT_X + 200, STATS_Y, "Tokens", tokens, "https://cdn.discordapp.com/emojis/1393442089894940846.png", tokens_rank)
        await draw_stat(CONTENT_X + 400, STATS_Y, "Streak", streak, "https://cdn.discordapp.com/emojis/1371651844652273694.png", streak_rank)

        VAULT_ICON_SIZE_W = 86
        VAULT_ICON_SIZE_H = 100
        VAULT_X = WIDTH - VAULT_ICON_SIZE_W - 30
        VAULT_Y = 30
        
        current_time = time.time()
        if not active_brew:
            status_text = "Empty"
            icon_path = "/root/Vanity/assets/empty.png"
        elif active_brew['end_time'] > current_time:
            status_text = active_brew['roast_type'].capitalize()
            icon_path = "/root/Vanity/assets/brewing.png"
        else:
            status_text = active_brew['roast_type'].capitalize()
            icon_path = "/root/Vanity/assets/ready.png"
            
        try:
            vault_icon = Image.open(icon_path).convert("RGBA").resize((int(VAULT_ICON_SIZE_W * 0.8), int(VAULT_ICON_SIZE_H * 0.8)))
            img.paste(vault_icon, (VAULT_X, VAULT_Y), vault_icon)
        except Exception as e:
            print(f"Error loading vault icon: {e}")
            
        TEXT_X = VAULT_X - 20
        TEXT_Y = VAULT_Y + 5
        
        status_width = draw.textlength(status_text, font=small_value_font)
        
        if active_brew and active_brew.get('insured', False):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get("https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/1f6e1.png") as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            shield_img = Image.open(io.BytesIO(data)).convert("RGBA")
                            shield_size = 26
                            shield_img = shield_img.resize((shield_size, shield_size))
                            
                            shield_x = int(TEXT_X - status_width - shield_size - 5)
                            shield_y = int(TEXT_Y + 2)
                            img.paste(shield_img, (shield_x, shield_y), shield_img)
            except Exception as e:
                print(f"Error loading shield: {e}")

        draw.text((TEXT_X - status_width, TEXT_Y), status_text, font=small_value_font, fill=(255, 255, 255))
        
        total_text = f"Total: {total_brews:,}"
        total_width = draw.textlength(total_text, font=label_font)
        draw.text((TEXT_X - total_width, TEXT_Y + 38), total_text, font=label_font, fill=(170, 170, 170))

        BAR_X = CONTENT_X
        BAR_Y = STATS_Y + ICON_SIZE + 60
        BAR_WIDTH = 500
        BAR_HEIGHT = 24
        
        font_16 = try_load_font(regular_candidates, 16)
        base_label = "Daily Chat Earnings"
        draw.text((BAR_X, BAR_Y - 30), base_label, font=font_16, fill=(170, 170, 170))
        
        if earnings > 0 and reset_time > time.time():
             diff = reset_time - time.time()
             if diff > 3600:
                 time_str = f"Resets in {int(diff // 3600)} hours"
             elif diff > 60:
                 time_str = f"Resets in {int(diff // 60)} minutes"
             else:
                 time_str = f"Resets in {int(diff)} seconds"
             
             x_offset = draw.textlength(base_label, font=font_16)
             draw.text((BAR_X + x_offset, BAR_Y - 30), " (", font=font_16, fill=(170, 170, 170))
             x_offset += draw.textlength(" (", font=font_16)
             
             draw.text((BAR_X + x_offset, BAR_Y - 30), time_str, font=font_16, fill=(255, 255, 255))
             x_offset += draw.textlength(time_str, font=font_16)
             
             draw.text((BAR_X + x_offset, BAR_Y - 30), ")", font=font_16, fill=(170, 170, 170))
        
        progress_text = f"{earnings}/{max_earnings} Beans"
        text_width = draw.textlength(progress_text, font=try_load_font(regular_candidates, 16))
        draw.text((BAR_X + BAR_WIDTH - text_width, BAR_Y - 30), progress_text, font=try_load_font(regular_candidates, 16), fill=(255, 255, 255))

        radius = BAR_HEIGHT // 2
        bg_bar_color = (60, 60, 60)
        border_bar_color = (90, 90, 90)
        
        draw.rounded_rectangle([(BAR_X, BAR_Y), (BAR_X + BAR_WIDTH, BAR_Y + BAR_HEIGHT)], radius=radius, fill=bg_bar_color)
        draw.rounded_rectangle([(BAR_X, BAR_Y), (BAR_X + BAR_WIDTH, BAR_Y + BAR_HEIGHT)], radius=radius, outline=border_bar_color, width=2)
        
        progress = min(max(0.0, float(earnings) / max_earnings), 1.0) if max_earnings > 0 else 0
        progress_width = int(BAR_WIDTH * progress)
        
        if progress_width > 0:
             draw.rounded_rectangle([(BAR_X, BAR_Y), (BAR_X + progress_width, BAR_Y + BAR_HEIGHT)], radius=radius, fill=fill_color)

        LEVEL_BAR_Y = BAR_Y + BAR_HEIGHT + 50
        
        level_text = f"Total Experience"
        leve_num_text = f" (Level {level})"
        
        draw.text((BAR_X, LEVEL_BAR_Y - 30), level_text, font=font_16, fill=(170, 170, 170)) 
        level_width = draw.textlength(level_text, font=font_16)
        draw.text((BAR_X + level_width, LEVEL_BAR_Y - 30), leve_num_text, font=font_16, fill=(255, 255, 255)) 

        if rank > 0:
            rank_text = f"#{rank}"
            leve_num_width = draw.textlength(leve_num_text, font=font_16)
            
            tag_font = try_load_font(bold_candidates, 14)
            tag_width = draw.textlength(rank_text, font=tag_font) + 10
            tag_height = 20
            tag_x = BAR_X + level_width + leve_num_width + 10
            tag_y = LEVEL_BAR_Y - 30
            
            draw.rounded_rectangle([(tag_x, tag_y), (tag_x + tag_width, tag_y + tag_height)], radius=5, fill=(60, 60, 60))
            draw.text((tag_x + 5, tag_y + 2), rank_text, font=tag_font, fill=(200, 200, 200))
        
        xp_text = f"{int(current_xp)}/{int(xp_needed)} XP"
        xp_text_width = draw.textlength(xp_text, font=try_load_font(regular_candidates, 16))
        draw.text((BAR_X + BAR_WIDTH - xp_text_width, LEVEL_BAR_Y - 30), xp_text, font=try_load_font(regular_candidates, 16), fill=(255, 255, 255))
        
        draw.rounded_rectangle([(BAR_X, LEVEL_BAR_Y), (BAR_X + BAR_WIDTH, LEVEL_BAR_Y + BAR_HEIGHT)], radius=radius, fill=bg_bar_color)
        draw.rounded_rectangle([(BAR_X, LEVEL_BAR_Y), (BAR_X + BAR_WIDTH, LEVEL_BAR_Y + BAR_HEIGHT)], radius=radius, outline=border_bar_color, width=2)
        
        level_progress = min(max(0.0, float(current_xp) / xp_needed), 1.0) if xp_needed > 0 else 0
        level_progress_width = int(BAR_WIDTH * level_progress)
        
        if level_progress_width > 0:
             draw.rounded_rectangle([(BAR_X, LEVEL_BAR_Y), (BAR_X + level_progress_width, LEVEL_BAR_Y + BAR_HEIGHT)], radius=radius, fill=fill_color)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename=f"balance_{user.id}.png")


    @app_commands.command(name='balance', description='Check your Starr Beans and Tokens balance')
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def balance(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)
        
        await interaction.response.defer(thinking=True)
        user_id = interaction.user.id
        beans, tokens = await self.get_balance(user_id)

        ref = u_daily_checkin_streaks(user_id)
        streak_data = ref.get() or {
            "last_claim": 0,
            "current_streak": 0,
            "all_time_high": 0,
            "total_claims": 0
        }
        current_streak = streak_data['current_streak']

        table_name = None
        table_emoji_url = None
        table_cog = self.bot.get_cog("table")
        if table_cog:
            table_data = await table_cog.get_user_table(user_id, interaction.guild.id)
            if table_data and table_data.get("formalized", False):
                table_name = table_data["name"]
                emoji_str = table_data["emoji"]
                custom_emoji_match = re.search(r'<a?:.+:(\d+)>', emoji_str)
                if custom_emoji_match:
                    emoji_id = custom_emoji_match.group(1)
                    table_emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.png"

        ref = u_daily_chat_earnings(user_id)
        data = ref.get() or {"earnings": 0, "reset_time": 0}
        reset_time = data.get("reset_time", 0)
        earnings = data.get("earnings", 0)
        
        MAX_DAILY_CHAT_BEAN_LIMIT = 1000

        booster_role = interaction.guild.premium_subscriber_role
        if booster_role in interaction.user.roles:
            MAX_DAILY_CHAT_BEAN_LIMIT = 1500

        ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
        if ultra_role and ultra_role in interaction.user.roles:
            MAX_DAILY_CHAT_BEAN_LIMIT = 5000

        if datetime.now(timezone.utc).weekday() >= 5: 
            MAX_DAILY_CHAT_BEAN_LIMIT *= 2

        active_effects = await self.effect_manager.get_user_active_effects(user_id)
        if "chat_boost" in active_effects:
            MAX_DAILY_CHAT_BEAN_LIMIT *= 3
            
        if reset_time < time.time():
            earnings = 0
            reset_message = ""
        else:
            reset_message = f"\nResets <t:{int(reset_time)}:R>"

        active_brew = await self.get_active_brew(user_id)
        brew_stats = await self.get_brew_stats(user_id)
        total_brews = brew_stats.get('total_brews', 0) if brew_stats else 0

        level_cog = self.bot.get_cog("Leveling")
        level = 0
        rank = 0
        current_xp = 0
        xp_needed = 100
        
        if level_cog and level_cog.pool:
            try:
                row = await level_cog.pool.fetchrow("SELECT xp, level FROM levels WHERE id = $1 AND guild = $2", str(user_id), str(interaction.guild.id))
                if row:
                    xp = row['xp']
                    level = row['level']
                    rank = await level_cog.pool.fetchval("SELECT COUNT(*) FROM levels WHERE guild = $1 AND xp > $2", str(interaction.guild.id), xp)
                    rank += 1
                    _, current_xp, xp_needed = get_level(xp)
            except Exception as e:
                print(f"Error fetching level data: {e}")

        beans_rank, tokens_rank, streak_rank = await self.get_user_ranks(user_id)

        custom_bg_path = f"assets/Balance Backgrounds/{user_id}.png"
        if not os.path.exists(custom_bg_path):
            custom_bg_path = None

        card = await self.generate_balance_card(interaction.user, beans, tokens, current_streak, earnings, MAX_DAILY_CHAT_BEAN_LIMIT, reset_time, active_brew, total_brews, table_name, table_emoji_url, level, rank, current_xp, xp_needed, beans_rank, tokens_rank, streak_rank, custom_bg=custom_bg_path)

        view = BalanceInfoView()
        
        message = await interaction.followup.send(file=card, view=view)
        view.message = message

        if custom_bg_path is None and tokens > 10:
            embed = discord.Embed(
                description=(
                    "<:PandaCool:855023241306963988> **Customize your background** with **any** image of your choice! <:PandaLeon:855023465429991444>\n\n"
                    "-# **1.** </buy:1393376242501157010> a Customization Credit\n"
                    "-# **2.** </customize:1486174479489957908> your background with self-uploaded image\n"
                    "-# **3.** Flex every time you check your balance! <:PandaAppear:855023228396371998>"
                ), 
                color=COLORS["ultra"]
            )
            embed.set_footer(text="You have enough tokens to get a customization credit!")
            await interaction.followup.send(embed=embed, ephemeral=True)

    @balance.error
    async def balance_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    @app_commands.command(name='thermometer', description='Check the current Cup Thermometer status')
    async def thermometer(self, interaction: discord.Interaction):
        heat = self.thermometer_heat
        
        freeze_ref = g_shop_effects(interaction.guild.id)
        all_effects = freeze_ref.get() or {}
        current_time = time.time()
        
        frozen = False
        freeze_user = None
        for user_id_check, user_effects in all_effects.items():
            freeze_data = user_effects.get("freeze_thermometer", {})
            if freeze_data.get("active", False) and current_time < freeze_data.get("expires_at", 0):
                frozen = True
                freeze_user = await interaction.guild.fetch_member(int(user_id_check))
                break
        
        if heat >= 100:
            level = "Boiling 🔥"
            color = 0xFF0000
            description = f"{BEAN_EMOTE} `3` Beans per effortful message + `1%` chance for {TOKEN_EMOTE} `1` Tokens\n-# <:reply:1036792837821435976> *Plus a special `0.1%` jackpot chance for {TOKEN_EMOTE} `3` Tokens!*"
        elif heat >= 75:
            level = "Hot 🌡️"
            color = 0xFFA500
            description = f"{BEAN_EMOTE} `2` Beans per effortful message + `0.5%` chance for {TOKEN_EMOTE} `1` Token"
        elif heat >= 50:
            level = "Warm ☕"
            color = 0xFFFF00
            description = f"{BEAN_EMOTE} `1` Bean per effortful message"
        else:
            level = "Cold ❄️"
            color = 0xADD8E6
            description = f"No active bonuses - keep chatting to heat it up!"
        
        if frozen:
            if level == "Cold ❄️":
                description = "No active bonuses!"
            freeze_expires = min([freeze_data.get("expires_at", 0) for user_effects in all_effects.values() 
                                 for freeze_data in [user_effects.get("freeze_thermometer", {})] 
                                 if freeze_data.get("active", False)])
            description += f"\n<:reply:1036792837821435976> *Thermometer frozen by {freeze_user.mention if freeze_user else 'Unknown'} until <t:{int(freeze_expires)}:t>*"
        
        initial_embed = discord.Embed(
            title=f"Cup Thermometer: {level}",
            description=description,
            color=color
        )
        
        bar_length = 20
        filled = min(int(heat / 100 * bar_length), bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        initial_embed.add_field(
            name=f"Heat Level: {min(heat, 100)}%",
            value=f"`{bar}`",
            inline=False
        )
        
        initial_embed.set_footer(text="Heat decays gradually per minute. Chat in any of the three main channels to heat it up!")
        full_embed = discord.Embed(color=discord.Color.blurple()).add_field(
            name="List of Rewards",
            value=(
                f"<a:warning:1391215594430402742> **Thermometer rewards are granted on every effortful message!**\n"
                f"> - **Cold** `(0-49%)`: No bonuses\n"
                f"> - **Warm** `(50-74%)`: {BEAN_EMOTE} `1` Bean\n"
                f"> - **Hot** `(75-99%)`: {BEAN_EMOTE} `2` Beans + `0.5%` chance for {TOKEN_EMOTE} `1` Token\n"
                f"> - **Boiling** `(100%)`: {BEAN_EMOTE} `3` Beans + `1%` chance for {TOKEN_EMOTE} `1` Token\n"
                f"> -# <:reply:1036792837821435976> *Plus a special `0.1%` jackpot chance for {TOKEN_EMOTE} `3` Tokens when boiling!*"
            ),
            inline=False
        )
        
        view = ThermometerView(self, initial_embed, full_embed)
        await interaction.response.send_message(embed=initial_embed, view=view)
    @thermometer.error
    async def thermometer_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)


    class CustomizeConfirmView(discord.ui.View):
        def __init__(self, bg_bytes: bytes, user_id: int):
            super().__init__(timeout=60)
            self.bg_bytes = bg_bytes
            self.user_id = user_id

        @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, custom_id="custom_confirm")
        async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("This is not your confirmation.", ephemeral=True)
            
            ref = u_customization(self.user_id)
            data = ref.get() or {"credits": 0}
            if data.get("credits", 0) <= 0:
                for child in self.children:
                    child.disabled = True
                return await interaction.response.edit_message(content=f"{NO_EMOTE} You no longer have any Customization Credits.", view=self)
            
            data["credits"] -= 1
            ref.set(data)
            
            os.makedirs("assets/Balance Backgrounds", exist_ok=True)
            path = f"assets/Balance Backgrounds/{self.user_id}.png"
            with open(path, "wb") as f:
                f.write(self.bg_bytes)
            
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content=f"{YES_EMOTE} Customization applied! Check out your new `/balance` card!", view=self)

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="custom_cancel")
        async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("This is not your confirmation.", ephemeral=True)
            
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content=f"{NO_EMOTE} Customization cancelled.", view=self)

    class CustomizeRemoveView(discord.ui.View):
        def __init__(self, user_id: int):
            super().__init__(timeout=60)
            self.user_id = user_id

        @discord.ui.button(label="Confirm Remove", style=discord.ButtonStyle.danger, custom_id="custom_remove")
        async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("This is not your confirmation.", ephemeral=True)
            
            path = f"assets/Balance Backgrounds/{self.user_id}.png"
            if os.path.exists(path):
                try:
                    os.remove(path)
                    for child in self.children:
                        child.disabled = True
                    return await interaction.response.edit_message(content=f"{YES_EMOTE} Your custom background has been removed successfully.", view=self)
                except Exception as e:
                    return await interaction.response.send_message(f"{NO_EMOTE} Failed to remove background: {e}", ephemeral=True)
            else:
                for child in self.children:
                    child.disabled = True
                return await interaction.response.edit_message(content=f"{NO_EMOTE} You don't have a custom background to remove.", view=self)

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="custom_cancel_remove")
        async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("This is not your confirmation.", ephemeral=True)
            
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content=f"{NO_EMOTE} Removal cancelled.", view=self)

    @app_commands.command(name='customize', description='Customize your balance rank card background (requires 1 Customization Credit)')
    @app_commands.describe(attachment='Attach an image file to use as your background', url='Or provide a direct image URL (png, jpg, webp)')
    @app_commands.checks.cooldown(rate=1, per=30.0)
    async def customize(self, interaction: discord.Interaction, attachment: discord.Attachment = None, url: str = None):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)

        user_id = interaction.user.id
        
        if not attachment and not url:
            path = f"assets/Balance Backgrounds/{user_id}.png"
            if os.path.exists(path):
                view = self.CustomizeRemoveView(user_id=user_id)
                return await interaction.response.send_message(f"**Are you sure you want to remove your custom background?** This action cannot be reversed and the previous credit spent will not be refunded.", view=view, ephemeral=True)
            else:
                return await interaction.response.send_message(f"{NO_EMOTE} You don't have a custom background to remove.\n\n💡 Tip: To add one, provide an image attachment or URL. It costs **1 Customization Credit**.", ephemeral=True)
            
        bg_url = url if url else attachment.url
        if not (bg_url.startswith("http") and any(bg_url.split("?")[0].lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"])):
            return await interaction.response.send_message("Please provide a valid image (png, jpg, jpeg, gif, webp).", ephemeral=True)

        ref = u_customization(user_id)
        data = ref.get() or {"credits": 0}
        
        if data.get("credits", 0) <= 0:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have any Customization Credits. Buy them in the shop using </buy:1393376242501157010>!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(bg_url) as resp:
                    if resp.status != 200:
                        return await interaction.followup.send(f"{NO_EMOTE} Failed to download image.", ephemeral=True)
                    bg_bytes = await resp.read()
                    
            mock_card = await self.generate_balance_card(
                interaction.user, beans=9999, tokens=99, streak=10, 
                earnings=1500, max_earnings=3000, reset_time=0.0, 
                active_brew=None, total_brews=10, table_name="Master Brewer", 
                table_emoji_url=None, level=50, rank=10, current_xp=9500, 
                xp_needed=10000, beans_rank=1, tokens_rank=1, streak_rank=1, 
                custom_bg_bytes=bg_bytes
            )
            
            msg = (
                "## Preview Background\n"
                f"{REPLY_EMOTE} Do you want to apply the change for **1 Customization Credit**?\n\n"
                f"-# <a:warning:1391215594430402742> Make sure your image follows all server rules. "
                "*Inappropriate, NSFW, or rule-breaking photos will result in an **instant ban***."
            )
            
            view = self.CustomizeConfirmView(bg_bytes=bg_bytes, user_id=user_id)
            await interaction.followup.send(content=msg, file=mock_card, view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to generate preview: {e}", ephemeral=True)


    @app_commands.command(name='leaderboard', description='View the top users by Beans, Tokens, or Invites')
    @app_commands.choices(currency=[
        app_commands.Choice(name='🫘 Starr Beans', value='Beans'),
        app_commands.Choice(name='🌟 Starr Tokens', value='Tokens'),
        app_commands.Choice(name='🫂 Monthly Server Invites', value='Invites'),
        app_commands.Choice(name='🍽️ Weekly Table Beans', value='Tables'),
        app_commands.Choice(name='🔥 Daily Streaks', value='Streaks'),
        app_commands.Choice(name='☕ Coffee Brews', value='Brews'),
        app_commands.Choice(name='📊 XP Levels', value='Levels')
    ])
    @app_commands.checks.cooldown(rate=1, per=10.0)
    @app_commands.describe(currency='Which leaderboard to view')
    async def leaderboard(self, interaction: discord.Interaction, currency: str):
        await interaction.response.defer(thinking=True)
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.followup.send(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)
        
        data = []
        formatter = None
        title = ""

        async def get_name(guild, uid):
            if uid == 0: return "Unknown"
            member = guild.get_member(uid)
            return member.mention if member else f"<@{uid}>"

        if currency == "Tables":
            all_tables = g_tables(interaction.guild.id).get() or {}
            formalized_tables = {
                name: data for name, data in all_tables.items() if data.get("formalized", False)
            }

            if not formalized_tables:
                return await interaction.followup.send(
                    f"{NO_EMOTE} No officially recognized tables yet!", ephemeral=True
                )

            data = sorted(
                formalized_tables.items(),
                key=lambda x: (x[1].get("weekly_beans", 0), len(x[1].get("members", []))),
                reverse=True
            )
            title = f"Top Tables"

            async def table_formatter(rank, item, guild):
                name, tdata = item
                return (
                    f"**{rank}. {tdata.get('emoji', '')} {tdata.get('name', name)}**\n"
                    f"-# <:reply:1036792837821435976> {BEAN_EMOTE} **`{tdata.get('weekly_beans', 0):,}` Beans**\n"
                    f"-# <:reply:1036792837821435976> `{len(tdata.get('members', []))}/10` people seated\n"
                    f"-# <:reply:1036792837821435976> **Host:** <@{tdata.get('host')}>"
                )
            formatter = table_formatter

        elif currency == "Streaks":
            ref = db.reference(U_ROOT)
            all_users = ref.get() or {}
            
            for uid_str, user_data in all_users.items():
                if uid_str and uid_str.isdigit():
                    progress = user_data.get("progress", {})
                    sdata = progress.get("daily_checkin_streaks", {})
                    streak = sdata.get("current_streak", 0)
                    if streak > 0:
                        data.append((int(uid_str), streak))
            
            data.sort(key=lambda x: x[1], reverse=True)
            title = "Top Daily Streaks"

            async def streak_formatter(rank, item, guild):
                uid, streak = item
                name = await get_name(guild, uid)
                return f"{rank}. {name} - **`{streak}`** day{'s' if streak != 1 else ''}"
            formatter = streak_formatter

        elif currency == "Brews":
            ref = db.reference(U_ROOT)
            all_users = ref.get() or {}
            
            for uid_str, user_data in all_users.items():
                if uid_str and uid_str.isdigit():
                    inventory = user_data.get("inventory", {})
                    bdata = inventory.get("brews", {})
                    stats = bdata.get("stats", {})
                    total_brews = stats.get("total_brews", 0)
                    if total_brews > 0:
                        data.append((int(uid_str), total_brews))
            
            data.sort(key=lambda x: x[1], reverse=True)
            title = "Top Brewers"

            async def brew_formatter(rank, item, guild):
                uid, brews = item
                name = await get_name(guild, uid)
                return f"{rank}. {name} - **`{brews:,}`** brew{'s' if brews != 1 else ''}"
            formatter = brew_formatter

        elif currency == "Invites":
            current_month = get_current_month_key()
            ref = g_invites_monthly(interaction.guild.id, current_month)
            all_data = ref.get() or {}
            
            if not all_data:
                return await interaction.followup.send(f"{NO_EMOTE} No invite data available yet", ephemeral=True)

            inv_data = []
            for uid_str, idata in all_data.items():
                 inv_data.append((uid_str, idata))

            data = sorted(
                inv_data, 
                key=lambda x: x[1].get("valid", 0), 
                reverse=True
            )
            title = "Top Monthly Inviters"

            async def invite_formatter(rank, item, guild):
                uid_str, idata = item
                name = await get_name(guild, int(uid_str))
                valid = idata.get("valid", 0)
                total = idata.get("total", 0)
                left = idata.get("left", 0)
                return f"{rank}. {name} - **`{valid}` invite{'s' if valid > 1 else ''}** (`{total}` total, `{left}` left)"
            formatter = invite_formatter

        elif currency == "Levels":
             leveling_cog = self.bot.get_cog("Leveling")
             if not leveling_cog or not leveling_cog.pool:
                 return await interaction.followup.send(f"{NO_EMOTE} Leveling system is currently unavailable.", ephemeral=True)
             
             async with leveling_cog.pool.acquire() as conn:
                 rows = await conn.fetch("SELECT id, xp, level FROM levels WHERE guild = $1 ORDER BY xp DESC LIMIT 2000", str(interaction.guild.id))
             
             data = rows 
             title = "Top Level XP"

             async def level_formatter(rank, item, guild):
                 uid = int(item['id'])
                 name = await get_name(guild, uid)
                 level = item['level']
                 xp = item['xp']
                 return f"{rank}. {name} - **Level {level}** (`{xp:,}` XP)"
             formatter = level_formatter

        else: # Beans or Tokens
            ref = db.reference(U_ROOT)
            all_users = ref.get() or {}
            
            target_field = currency 
            
            for uid_str, user_data in all_users.items():
                if uid_str and uid_str.isdigit():
                    bdata = user_data.get("balance", {})
                    amount = bdata.get(target_field, 0)
                    data.append((int(uid_str), amount))
            
            data.sort(key=lambda x: x[1], reverse=True)
            emoji = BEAN_EMOTE if currency == 'Beans' else TOKEN_EMOTE
            title = f"Top Starr {currency} Holders {emoji}"

            async def balance_formatter(rank, item, guild):
                uid, amt = item
                name = await get_name(guild, uid)
                return f"{rank}. {name} - {emoji} `{amt:,}` Starr {currency}"
            formatter = balance_formatter

        if not data:
            return await interaction.followup.send(f"{NO_EMOTE} No data available for this leaderboard.", ephemeral=True)

        pages = []
        per_page = 10
        total_pages = (len(data) - 1) // per_page + 1

        user_rank = "N/A"
        try:
            if currency == "Levels":
                rnk = next((i for i, x in enumerate(data) if int(x['id']) == interaction.user.id), None)
            elif currency == "Invites":
                rnk = next((i for i, x in enumerate(data) if int(x[0]) == interaction.user.id), None)
            elif currency == "Tables":
                rnk = None
            else:
                rnk = next((i for i, x in enumerate(data) if hasattr(x, '__getitem__') and x[0] == interaction.user.id), None)
            
            if rnk is not None:
                user_rank = f"#{rnk + 1}"
        except Exception:
            pass 

        for page_num in range(total_pages):
            start = page_num * per_page
            end = start + per_page
            current_data = data[start:end]
            
            description = ""
            for i, item in enumerate(current_data, start + 1):
                try:
                    line = await formatter(i, item, interaction.guild)
                    description += f"{line}\n"
                except Exception as e:
                    print(f"Error formatting leaderboard item: {e}")
                    continue
            
            embed = discord.Embed(title=f"{LB_EMOTE} {title}", description=description, color=0xF1C40F)
            footer_text = f"Page {page_num + 1}/{total_pages} • Total: {len(data)}"
            if user_rank != "N/A":
                footer_text += f" • Your Rank: {user_rank}"
            
            embed.set_footer(text=footer_text)
            pages.append(embed)
            
        view = LeaderboardView(interaction, pages)
        view.message = await interaction.followup.send(embed=pages[0], view=view)
    @leaderboard.error
    async def leaderboard_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    
    class InsuranceView(View):
        def __init__(self, cog):
            super().__init__(timeout=None) 
            self.cog = cog
            
        async def update_button_for_user(self, user_id):
            active_effects = await self.cog.effect_manager.get_user_active_effects(user_id)
            free_insurance = "free_insurance" in active_effects
            
            guild = self.cog.bot.get_guild(MAIN_GUILD_ID)
            if guild:
                member = guild.get_member(user_id)
                ultra_role = guild.get_role(ULTRA_TIER_ROLE_ID)
                if member and ultra_role and ultra_role in member.roles:
                    free_insurance = True

            for child in self.children:
                if hasattr(child, 'custom_id') and child.custom_id == "insure_with_beans":
                    if free_insurance:
                        child.label = "Get FREE Insurance"
                        child.emoji = EFFECT_EMOTE
                        child.style = discord.ButtonStyle.blurple
                elif hasattr(child, 'custom_id') and child.custom_id == "no_thanks":
                    self.remove_item(child)
                    
        @discord.ui.button(label="Insure with Beans", style=discord.ButtonStyle.green, emoji="🛡️", custom_id="insure_with_beans")
        async def insure_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            user_id = interaction.user.id
            if str(user_id) not in interaction.message.embeds[0].description:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} This is not your brew!",
                    ephemeral=True
                )
            self.roast_type = interaction.message.embeds[0].title.split(" ")[1].lower() 
            try:
                self.insurance_cost = int(interaction.message.embeds[0].description.split("`")[1])
            except (ValueError, IndexError):
                self.insurance_cost = 0
            self.batch_id = interaction.message.embeds[0].fields[2].value.split("`")[1]
            
            active_effects = await self.cog.effect_manager.get_user_active_effects(user_id)
            free_insurance = "free_insurance" in active_effects
            
            guild = self.cog.bot.get_guild(MAIN_GUILD_ID)
            if guild:
                member = guild.get_member(user_id)
                ultra_role = guild.get_role(ULTRA_TIER_ROLE_ID)
                if member and ultra_role and ultra_role in member.roles:
                    free_insurance = True
            
            success = await self.cog.insure_brew(user_id, self.roast_type)
            if success:
                for child in self.children:
                    child.disabled = True
                    
                embed = interaction.message.embeds[0]
                insurance_text = f"{EFFECT_EMOTE} **Brew Insured for free!** (Barista's Protection Plan)" if free_insurance else f"{YES_EMOTE} **Brew Insured!**"
                embed.description = embed.description.replace(
                    "🛡️ **Brew Insurance Offer**",
                    insurance_text
                )
                embed.description = embed.description.replace(
                    f"{EFFECT_EMOTE} **FREE Insurance Available!**",
                    insurance_text
                )
                embed.color = 0x00FF00
                
                await interaction.response.edit_message(embed=embed, view=None)
            else:
                await interaction.response.send_message(
                    f"{NO_EMOTE} You don't have enough Beans to insure this brew!",
                    ephemeral=True
                )
                
        @discord.ui.button(label="No Thanks", style=discord.ButtonStyle.grey, custom_id="no_thanks")
        async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if str(interaction.user.id) not in interaction.message.embeds[0].description:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} This is not your brew!",
                    ephemeral=True
                )
            for child in self.children:
                child.disabled = True
                
            embed = interaction.message.embeds[0]
            embed.description = embed.description.replace(
                "🛡️ **Brew Insurance Offer**",
                f"{NO_EMOTE} **Not Insured**"
            )
            
            await interaction.response.edit_message(embed=embed, view=None)

    @app_commands.command(name='brew', description='Brew a batch of coffee using your Beans')
    @app_commands.choices(roast_type=[
        app_commands.Choice(name='Light Roast', value='light'),
        app_commands.Choice(name='Medium Roast', value='medium'),
        app_commands.Choice(name='Dark Roast', value='dark'),
        app_commands.Choice(name='Golden Roast', value='golden'),
    ])
    @app_commands.checks.cooldown(rate=1, per=10.0)
    @app_commands.describe(roast_type='Type of roast (Leave blank to view rewards breakdown)')
    async def brew(self, interaction: discord.Interaction, roast_type: app_commands.Choice[str] = None):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)
        if roast_type is None:
            embed = discord.Embed(
                title="☕ Coffee Machine Vault - Brewing Guide",
                description=(
                    "- Convert your Beans into delicious coffee and **sell it for Tokens**!\n"
                    "- Each roast type has different costs, brewing times, and reward chances.\n"
                    f"- **Use </brew:1396588612790784070> to start and </sell:1396588612790784071> when ready.** Check with </balance:1393376242501157005>!\n"
                    f"- You can only have **one active brew at a time**\n"
                    f"- 🛡️ **Brew Insurance** protects against burns for a small fee"
                ),
                color=0x6F4E37
            )

            for key, data in ROAST_TYPES.items():
                emoji = EMOJIS.get(key, "")
                name = f"{emoji} {data['name']}"
                cost = f"{BEAN_EMOTE} `{data['cost']:,}`"
                hours = data['time'] // 3600
                time_str = f"`{hours} hour{'s' if hours != 1 else ''}`"
                insurance_cost = f"{BEAN_EMOTE} `{data['insurance_cost']:,}`" if data['insurance_cost'] > 0 else "Not applicable"

                payout_lines = []
                for reward, weight in zip(data['payout'], data['weights']):
                    if reward == 0:
                        payout_lines.append(f"> -# `{weight}%` - 💀 Burnt Brew")
                    else:
                        payout_lines.append(f"> -# `{weight}%` - {TOKEN_EMOTE} `{reward}` Token{'s' if reward > 1 else ''}")

                payout_lines.append(f"-# ✨ **Perfect Brew** (`{PERFECT_BREW_CHANCE}%` chance) for double reward!")
                payout_lines.append(f"-# 🛡️ **Insurance**: {insurance_cost}")

                if key == "golden":
                    payout_lines.insert(0, f"*🔓 Requires `{UNLOCK_REQ}` total brews to unlock*")
                    payout_lines.append(f"-# 💀 No risk of burnt brew. Guaranteed reward!")

                value = (
                    f"**Cost:** {cost}\n"
                    f"**Brew Time:** {time_str}\n" +
                    "\n".join(payout_lines)
                )

                embed.add_field(name=name, value=value, inline=True)

            embed.set_footer(text="Brew wisely! Higher roasts = better rewards!")
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        user_id = interaction.user.id
        roast = roast_type.value
        
        active_brew = await self.get_active_brew(user_id)
        if active_brew:
            current_time = time.time()
            if current_time < active_brew['end_time']:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You already have an active brew! You can </sell:1396588612790784071> it <t:{int(active_brew['end_time'])}:R>.",
                    ephemeral=True
                )
            else:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You have a brew ready to sell! Use </sell:1396588612790784071> first.",
                    ephemeral=True
                )
        
        if roast == 'golden':
            stats = await self.get_brew_stats(user_id)
            total_brews = stats.get('total_brews', 0) if stats else 0
            if total_brews < UNLOCK_REQ:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You need `{UNLOCK_REQ}` brews to unlock **Golden Roast**. You only have `{total_brews}`.",
                    ephemeral=True
                )
        
        cost = ROAST_TYPES[roast]['cost']
        beans, tokens = await self.get_balance(user_id)
        if beans < cost:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You need {BEAN_EMOTE} `{cost:,}` Beans for a **{ROAST_TYPES[roast]['name']}**. You only have `{beans:,}`.",
                ephemeral=True
            )
        
        await interaction.response.defer(thinking=True)
        
        new_beans = beans - cost
        await self.update_balance(user_id, beans=new_beans)
        
        current_time = time.time()
        brew_time = ROAST_TYPES[roast]['time']
        
        active_effects = await self.effect_manager.get_user_active_effects(user_id)
        if "half_brew_time" in active_effects:
            brew_time = brew_time // 2
            
        brew_data = {
            'roast_type': roast,
            'start_time': current_time,
            'end_time': current_time + brew_time,
            'batch_id': secrets.token_hex(4).upper(),
            'insured': False 
        }
        
        await self.set_active_brew(user_id, brew_data)
        await self.update_brew_stats_on_brew(user_id, roast)
        await update_quest(user_id, interaction.guild.id, {"brew_start": 1}, self.bot)

        if hasattr(self, 'tutorial_manager'):
            asyncio.create_task(self.tutorial_manager.on_brew_started(user_id, roast))
        
        if "sell_alarm" in active_effects:
            sync_sell_alarm(user_id, 'set', {
                "roast_type": roast,
                "end_time": brew_data['end_time'],
                "batch_id": brew_data['batch_id'],
                "notified": False
            }, interaction.guild.id)
        
        embed = discord.Embed(
            title=f"☕ {ROAST_TYPES[roast]['name']} Started!",
            description=f"{interaction.user.mention}, your coffee is now brewing. Ready to </sell:1396588612790784071> <t:{int(brew_data['end_time'])}:R>.",
            color=0x6F4E37 
        )
        
        if "half_brew_time" in active_effects:
            embed.description += "\n<:reply:1036792837821435976> **Turbo Brewing Kit** - 50% faster brewing time! ⚡"
        
        if roast != 'golden' and ROAST_TYPES[roast]['insurance_cost'] > 0:
            insurance_cost = ROAST_TYPES[roast]['insurance_cost']
            
            active_effects = await self.effect_manager.get_user_active_effects(user_id)
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
            
        ref_mapping = g_invites_member_data(interaction.guild.id, interaction.user.id)
        mapping = ref_mapping.get() or {}

        if mapping and not mapping.get("brew_done", False) and mapping.get("is_new", False):
            log_entry, inviter = await self.process_referral_milestone(
                interaction, 
                "trainee", 
                interaction.user
            )
            if log_entry:
                await self.log_referral_milestone(log_entry)
                embed.description += f"\n\n<:Information:855023058255478794> **Referral Milestone:** Your inviter {inviter.mention} earned <@&{TRAINEE_ROLE_ID}> too!"   
            
        welcome_bonus_msg = await self.process_invitee_welcome_bonus(interaction, 'brew', interaction.user)
        if welcome_bonus_msg:
            extra_newline = "\n" if "<:Information:855023058255478794>" not in embed.description else ""
            embed.description += f"\n{extra_newline}{welcome_bonus_msg}"
            new_beans += 150
        
        embed.add_field(name="Cost", value=f"{BEAN_EMOTE} `{cost:,}` Beans", inline=True)
        embed.add_field(name="Remaining", value=f"{BEAN_EMOTE} `{new_beans:,}` Beans", inline=True)
        embed.add_field(name="Brew ID", value=f"`{brew_data['batch_id']}`", inline=True)
            
        if view is not None:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)
    @brew.error
    async def brew_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        try:
            await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)
        except Exception:
            await interaction.followup.send(f"```{str(error)}```", ephemeral=True)

    @app_commands.command(name='sell', description='Sell your brewed coffee for Tokens')
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def sell(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)
        user_id = interaction.user.id
        
        active_brew = await self.get_active_brew(user_id)
        if not active_brew:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You don't have an active brew to sell.",
                ephemeral=True
            )
            
        current_time = time.time()
        if current_time < active_brew['end_time']:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Your brew isn't ready yet! You can sell it <t:{int(active_brew['end_time'])}:R>.",
                ephemeral=True
            )
        
        await interaction.response.defer(thinking=True)
            
        roast_type = active_brew['roast_type']
        payout_info = ROAST_TYPES[roast_type]
        base_payout = random.choices(payout_info['payout'], weights=payout_info['weights'])[0]
        insured = active_brew.get('insured', False)
        saved_burn = False
        
        active_effects = await self.effect_manager.get_user_active_effects(user_id)
        
        burnt_to_perfect = False
        if base_payout == 0:
            if "burnt_to_perfect" in active_effects:
                base_payout = max(payout_info['payout']) 
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
        if base_payout != 0 and interaction.guild.get_role(MASTER_ROLE_ID) in interaction.user.roles:
            master_bonus = max(int(base_payout * 0.5), 1)
            tokens += master_bonus
            
        new_tokens = await self.add_tokens(user_id, tokens)
        await update_quest(user_id, interaction.guild.id, {"brew_sells": 1}, self.bot)
        
        await self.update_brew_stats_on_sell(user_id, tokens, roast_type, perfect, insured, saved_burn)
        await self.record_brew_history(user_id, {
            **active_brew,
            'sold_time': current_time,
            'tokens_earned': tokens,
            'perfect': perfect,
            'insured': insured,
            'saved_burn': saved_burn
        })
        
        await self.remove_active_brew(user_id)
        
        if sync_sell_alarm(user_id, 'get'):
            sync_sell_alarm(user_id, 'delete', guild_id=interaction.guild.id)
        
        embed = discord.Embed(
            title=f"☕ Sold {ROAST_TYPES[roast_type]['name']}!",
            color=0xD4AF37 if perfect else 0x6F4E37
        )
        
        if tokens == 0:
            embed.description = f"💀 **Burnt Brew!** {interaction.user.mention}, you didn't earn any {TOKEN_EMOTE} Tokens."
            if not insured:
                embed.description += f"\n-# 🛡️ **Tip:** Insurance would have protected this brew!"
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
                embed.description += f"\n☕ **Master Barista Bonus!** ({master_bonus} extra Tokens)"
            
            stamp_cog = self.bot.get_cog("StampCard")
            if stamp_cog:
                await stamp_cog.update_progress(user_id, "brew_sells", 1)
        
        embed.add_field(name="New Token Balance", value=f"{TOKEN_EMOTE} `{new_tokens}` Tokens", inline=True)
        embed.add_field(name="Brew ID", value=f"`{active_brew['batch_id']}`", inline=True)
        if insured:
            embed.add_field(name="Insurance Status", value="🛡️ Insured", inline=True)
        
        if tokens != 0:
            flavor_notes = {
                "light": [
                    "Bright and acidic with floral notes",
                    "Citrusy and tea-like with a crisp finish",
                    "Delicate and aromatic with hints of jasmine",
                    "Fruity and lively with a honey sweetness"
                ],
                "medium": [
                    "Balanced with caramel sweetness",
                    "Smooth and nutty with hints of cocoa",
                    "Well-rounded with brown sugar and spice tones",
                    "Rich and mellow with toffee notes"
                ],
                "dark": [
                    "Bold and smoky with chocolate undertones",
                    "Intense and full-bodied with molasses sweetness",
                    "Dark chocolate and roasted nut flavor",
                    "Earthy and strong with a slightly bitter finish"
                ],
                "golden": [
                    "Exotic and complex with fruity essence",
                    "Vibrant and layered with tropical fruit and spice",
                    "Smooth and buttery with floral aromatics",
                    "Sweet and lush with notes of mango and honey"
                ]
            }

            embed.add_field(
                name="Flavor Profile",
                value=random.choice(flavor_notes[roast_type]),
                inline=False
            )

            ref_mapping = g_invites_member_data(interaction.guild.id, interaction.user.id)
            mapping = ref_mapping.get() or {}

            if mapping and mapping.get("inviter") and mapping.get("is_new", False):
                earned_rewards = ""

                if not mapping.get("brew_done", False):
                    log_entry, inviter = await self.process_referral_milestone(
                        interaction, 
                        "trainee", 
                        interaction.user
                    )
                    if log_entry:
                        earned_rewards = f"Your inviter {inviter.mention} earned <@&{TRAINEE_ROLE_ID}> too!"

                log_entry, inviter = await self.process_referral_milestone(
                    interaction, 
                    "bridge", 
                    interaction.user
                )
                if log_entry:
                    await self.log_referral_milestone(log_entry)
                    earned_rewards = f"Your inviter {inviter.mention} earned <@&{BRIDGE_ROLE_ID}> too!"

                master_log, inviter = await self.process_referral_milestone(interaction, "sell", interaction.user)
                if master_log:
                    await self.log_referral_milestone(master_log)
                    earned_rewards = f"Your inviter {inviter.mention} earned <@&{MASTER_ROLE_ID}> too!"

                if earned_rewards:
                    embed.description += (
                        f"\n\n<:Information:855023058255478794> **Referral Milestone::** {earned_rewards}"
                    )
                    
            welcome_bonus_msg = await self.process_invitee_welcome_bonus(interaction, 'sell', interaction.user)
            if welcome_bonus_msg:
                extra_newline = "\n" if "<:Information:855023058255478794>" not in embed.description else ""
                embed.description += f"\n{extra_newline}{welcome_bonus_msg}"

        await interaction.followup.send(embed=embed)
    @sell.error
    async def sell_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        try:
            await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)
        except Exception:
            await interaction.followup.send(f"```{str(error)}```", ephemeral=True)

    
    @app_commands.command(name='pin', description='Pin a message using your Message Pin credits')
    @app_commands.describe(message_link='Discord message link to pin')
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def pin(self, interaction: discord.Interaction, message_link: str):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)
        
        user_id = interaction.user.id
        
        ref = u_pin_message(user_id)
        data = ref.get() or {"count": 0}
        pin_count = data.get("count", 0)
        
        if pin_count <= 0:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You don't have any message pin credits! Purchase **1 Message Pin** from the shop to pin messages.",
                ephemeral=True
            )
        
        try:
            parts = message_link.strip().split('/')
            if len(parts) < 3 or 'discord.com' not in message_link:
                raise ValueError("Invalid message link")
            
            message_id = int(parts[-1])
            channel_id = int(parts[-2])
            guild_id = int(parts[-3])
            
            if guild_id != interaction.guild.id:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You can only pin messages from this server!",
                    ephemeral=True
                )
            
        except (ValueError, IndexError):
            return await interaction.response.send_message(
                f"{NO_EMOTE} Invalid message link! Please provide a valid Discord message link.\n"
                f"-# Example: `https://discord.com/channels/1234567/2345678/78901234`",
                ephemeral=True
            )
        
        await interaction.response.defer(thinking=True)
        
        try:
            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                return await interaction.followup.send(
                    f"{NO_EMOTE} Channel not found! Make sure the message is from this server.",
                    ephemeral=True
                )
            
            if not channel.permissions_for(interaction.guild.me).manage_messages:
                return await interaction.followup.send(
                    f"{NO_EMOTE} I don't have permission to pin messages in {channel.mention}!",
                    ephemeral=True
                )
            
            message = await channel.fetch_message(message_id)
            
            if message.pinned:
                return await interaction.followup.send(
                    f"{NO_EMOTE} That message is already pinned!",
                    ephemeral=True
                )
            
            await message.pin(reason=f"Pinned by {interaction.user} using Message Pin item")
            
            data["count"] = pin_count - 1
            ref.set(data)
            
            embed = discord.Embed(
                title="📌 Message Pinned!",
                description=f"Successfully pinned [this message]({message_link}) in {channel.mention}!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Remaining Pin Credits",
                value=f"📌 `{data['count']}` pin{'s' if data['count'] != 1 else ''} remaining",
                inline=False
            )
            embed.set_footer(text=f"Purchase more pins from the shop with /buy")
            
            await interaction.followup.send(embed=embed)
            
        except discord.NotFound:
            await interaction.followup.send(
                f"{NO_EMOTE} Message not found! Make sure the link is correct and I can access that channel.",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"{NO_EMOTE} I don't have permission to pin messages in that channel!",
                ephemeral=True
            )
        except discord.HTTPException as e:
            if "Maximum number of pins reached" in str(e):
                await interaction.followup.send(
                    f"{NO_EMOTE} That channel has reached the maximum number of pinned messages (50)! Please unpin some messages first.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"{NO_EMOTE} Failed to pin message: {str(e)}",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"{NO_EMOTE} An error occurred: {str(e)}",
                ephemeral=True
            )
    
    @pin.error
    async def pin_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)


    @app_commands.command(name='add', description='Add Beans, Tokens, Star Drops or Mega Boxes to a user (Admin only)')
    @app_commands.describe(user='Target user', currency='Currency or Item to add', amount='Amount to add')
    @app_commands.choices(currency=[
        app_commands.Choice(name='🫘 Starr Beans', value='Beans'),
        app_commands.Choice(name='🌟 Starr Tokens', value='Tokens'),
        app_commands.Choice(name='⭐ Star Drops', value='StarDrops'),
        app_commands.Choice(name='📦 Mega Boxes', value='MegaBoxes'),
    ])
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def add(self, interaction: discord.Interaction, user: discord.Member, currency: str, amount: int):
        if not interaction.user.guild_permissions.administrator or interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)

        if amount <= 0:
            return await interaction.response.send_message(f"{NO_EMOTE} Amount must be positive.", ephemeral=True)

        if currency == 'Tokens':
            new_amount = await self.add_tokens(user.id, amount)
        elif currency == 'StarDrops':
            ref = u_star_drops(user.id)
            current = ref.get() or 0
            new_amount = current + amount
            ref.set(new_amount)
            currency = 'Star Drops'
        elif currency == 'MegaBoxes':
            ref = u_mega_boxes(user.id)
            current = ref.get() or 0
            new_amount = current + amount
            ref.set(new_amount)
            currency = 'Mega Boxes'
        else:
            new_amount = await self.add_beans(user.id, amount)

        await interaction.response.send_message(
            embed=discord.Embed(description=f"Added `{amount:,}` {currency} to {user.mention}. \n-# **New balance:** `{new_amount:,}` {currency}.", color=discord.Color.green())
        )
    @add.error
    async def add_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)
    
    @app_commands.command(name="update-quest", description="Update a user's quest progress (Admin only)")
    @app_commands.describe(user='Target user', quest='Quest type to update', amount='Amount to add to the quest')
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def update_quest_cmd(self, interaction: discord.Interaction, user: discord.Member, quest: str, amount: int):
        if not interaction.user.guild_permissions.administrator or interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)

        if amount <= 0:
            return await interaction.response.send_message(f"{NO_EMOTE} Amount must be positive.", ephemeral=True)
        
        if quest not in QUEST_TYPES:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Invalid quest type. Valid types are: {', '.join(QUEST_TYPES)}",
                ephemeral=True
            )
        
        # Call update_quest to properly track the quest completion
        messages = await update_quest(user.id, interaction.guild.id, {quest: amount}, self.bot)
        
        result = "\n".join(messages) if messages else f"Updated {user.mention}'s **{quest}** quest by `{amount}`."
        
        await interaction.response.send_message(
            embed=discord.Embed(
                description=result,
                color=discord.Color.green()
            )
        )
    
    @update_quest_cmd.autocomplete("quest")
    async def quest_autocomplete(self, interaction: discord.Interaction, current: str):
        try:
            # Get user ID from interaction data
            user_id = None
            if interaction.data and "options" in interaction.data:
                for option in interaction.data["options"]:
                    if option.get("name") == "user":
                        user_id = int(option.get("value", 0))
                        break
            
            if not user_id:
                return []
            
            ref = u_quests(user_id)
            quest_data = ref.get() or {}
            
            # Get all unique quest types the user has across all durations
            quest_types_available = set()
            current_lower = current.lower()
            
            for duration in ["daily", "weekly", "monthly"]:
                dur_data = quest_data.get(duration, {})
                quests = dur_data.get("quests", {})
                quest_types_available.update(quests.keys())
            
            options = []
            for quest_type in sorted(quest_types_available):
                if current_lower in quest_type.lower():
                    options.append(app_commands.Choice(name=quest_type, value=quest_type))
            
            return options[:25]  # Discord limits to 25 choices
        except Exception:
            return []
    
    @update_quest_cmd.error
    async def update_quest_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    @app_commands.command(name="shop", description="View the guild shop (Admins can edit)")
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def shop(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)
        await interaction.response.defer(thinking=True)
        ref = g_shops(interaction.guild.id)
        shop_data = ref.get() or []

        pages = await get_shop_embeds(interaction, shop_data, empty_condition=False)

        if interaction.user.guild_permissions.administrator:
            view = Panel(sort_default="sort by cost (high to low)", filter_default=None, pages=pages, initial_author=interaction.user)
        else:
            view = SortSelectionView(sort_default="sort by cost (high to low)", filter_default=None, pages=pages, initial_author=interaction.user)

        view.message = await interaction.followup.send(embed=pages[0], view=view)

        if hasattr(self, 'tutorial_manager'):
            asyncio.create_task(self.tutorial_manager.on_shop_viewed(interaction.user.id))
    @shop.error
    async def shop_error(
        self, interaction: discord.Interaction, error: Exception
    ):
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

    @app_commands.command(name="buy", description="Purchase a reward with your Starr Beans or Tokens")
    @app_commands.describe(item="Item name or role ID to buy")
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def buy(self, interaction: discord.Interaction, item: str):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)
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
    async def buy_error(
        self, interaction: discord.Interaction, error: Exception
    ):
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
            return await self._process_effect_purchase(interaction, user_id, effect_item_id)

        shop_items = await self.get_shop_items(guild_id)
        if not shop_items:
            return await interaction.edit_original_response(content=f"{NO_EMOTE} The shop is currently empty.")

        reward = None
        for r in shop_items:
            if str(r[0]).lower() == item.lower():
                reward = r
                break
        if reward is None:
            return await interaction.edit_original_response(content=f"{NO_EMOTE} Item `{item}` not found in the shop.")

        name, desc, cost, currency_type, multiple, stock = reward

        beans, tokens = await self.get_balance(user_id)

        if stock == 0:
            return await interaction.edit_original_response(
                content=f"<a:out_of_stock:1384990609584033812> Sorry, **{name}** is currently out of stock.",
            )

        user_currency = beans if currency_type.lower() == "beans" else tokens
        currency_emote = BEAN_EMOTE if currency_type.lower() == "beans" else TOKEN_EMOTE

        if user_currency < cost:
            return await interaction.edit_original_response(content=f"{NO_EMOTE} You do not have enough {currency_type}. You have {currency_emote} `{user_currency}`, but this costs {currency_emote} `{cost}`.")

        if multiple is False:
            role = interaction.guild.get_role(int(name)) if name.isdigit() else None
            if role and role in member.roles:
                return await interaction.edit_original_response(
                    content=f"{NO_EMOTE} You already own the role **{role.name}** and cannot purchase it again.",
                )

        if currency_type.lower() == "beans":
            new_beans = beans - cost
            await self.update_balance(user_id, beans=new_beans)
            new_tokens = tokens
        else:
            new_tokens = tokens - cost
            await self.update_balance(user_id, tokens=new_tokens)
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

        reply_message = f'\n{REPLY_EMOTE} *Redeem your reward by creating a ticket in <#1390908939767648328>!*\n' if not name.isdigit() else ''
        await interaction.edit_original_response(
            content=None,
            embed=discord.Embed(
                description=f"{YES_EMOTE} Successfully purchased {display_name} for {currency_emote} `{cost}`!{reply_message}\n-# **Your new balance:** {BEAN_EMOTE} `{new_beans}` Beans, {TOKEN_EMOTE} `{new_tokens}` Tokens.",
                color=discord.Color.green()
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
                        color=discord.Color.red()
                    )
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
                        color=discord.Color.red()
                    )
                )

        if await self.effect_manager.check_user_cooldown(user_id, item_id):
            remaining = await self.effect_manager.get_cooldown_remaining(user_id, item_id)
            hours, remainder = divmod(remaining, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s" if hours > 0 else f"{int(minutes)}m {int(seconds)}s"
            
            return await interaction.edit_original_response(
                content=None,
                embed=discord.Embed(
                    description=f"⏰ **{item_data['name']}** is on cooldown for another **{time_str}**.",
                    color=discord.Color.red()
                )
            )
        
        price_parts = item_data["price"].split()
        cost = int(price_parts[0])
        currency = "tokens" if "token" in price_parts[1].lower() else "beans"
        
        beans, tokens = await self.get_balance(user_id)
        user_currency = beans if currency == "beans" else tokens
        currency_emote = BEAN_EMOTE if currency == "beans" else TOKEN_EMOTE
        
        if user_currency < cost:
            return await interaction.edit_original_response(
                content=None,
                embed=discord.Embed(
                    description=f"{NO_EMOTE} You need {currency_emote} `{cost}` {currency.title()} but only have {currency_emote} `{user_currency}`.",
                    color=discord.Color.red()
                )
            )

        if currency == "beans":
            new_beans = beans - cost
            new_tokens = tokens
            await self.update_balance(user_id, beans=new_beans)
        else:
            new_beans = beans
            new_tokens = tokens - cost
            await self.update_balance(user_id, tokens=new_tokens)
        
        await update_quest(user_id, interaction.guild.id, {"shop_purchases": 1}, self.bot)
        stamp_cog = self.bot.get_cog("StampCard")
        if stamp_cog:
            await stamp_cog.update_progress(user_id, "shop_purchases", 1)
        
        if item_id == "reset_chat_cap":
            earnings_data = self.chat_system.earnings_cache.get(user_id, {"earnings": 0, "reset_time": 0})
            earnings_data["earnings"] = 0
            self.chat_system.earnings_cache[user_id] = earnings_data
            u_daily_chat_earnings(user_id).update({"earnings": 0, "reset_time": 0})
            effect_msg = f"\n🔄 **Chat cap reset!** You can now earn chat beans again today."
            
        elif item_id == "thermometer_boost":
            current_heat = self.thermometer_heat
            boost_amount = 30
            new_heat = min(130, current_heat + boost_amount)
            self.thermometer_heat = new_heat
            g_thermometer(interaction.guild.id).update({"heat": new_heat})
            effect_msg = f"\n🔥 **Thermometer boosted!** Heat increased by {boost_amount} points (now at {new_heat})."
        
        elif item_id == "instant_brew":
            active_brew = await self.get_active_brew(user_id)
            if not active_brew:
                return await interaction.edit_original_response(content=None, embed=discord.Embed(description=f"{NO_EMOTE} You don't have any active brew to complete.", color=discord.Color.red()))

            roast_type = active_brew["roast_type"]
            roast_data = ROAST_TYPES[roast_type]

            rewards = roast_data["payout"]
            weights = roast_data["weights"]
            tokens_earned = random.choices(rewards, weights=weights)[0]
            
            is_perfect = False
            if tokens_earned > 0:
                active_effects = await self.effect_manager.get_user_active_effects(user_id)
                perfect_chance = 25 if "perfect_brew_boost" in active_effects else PERFECT_BREW_CHANCE
                
                if random.randint(1, 100) <= perfect_chance:
                    is_perfect = True
                    tokens_earned += random.randint(3, 8)
            
            await self.add_tokens(user_id, tokens_earned)
            stamp_cog = self.bot.get_cog("StampCard")
            if stamp_cog:
                await stamp_cog.update_progress(user_id, "brew_sells", 1)
            await update_quest(user_id, interaction.guild.id, {"brew_sells": 1}, self.bot)
            await self.remove_active_brew(user_id)
            await self.update_brew_stats_on_sell(user_id, tokens_earned, roast_type, is_perfect, active_brew.get("insured", False), False)
            
            if sync_sell_alarm(user_id, 'get'):
                sync_sell_alarm(user_id, 'delete', guild_id=interaction.guild.id)
            
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
                active_brew = await self.get_active_brew(user_id)
                if active_brew:
                    sync_sell_alarm(user_id, 'set', {
                        "roast_type": active_brew.get("roast_type"),
                        "end_time": active_brew.get("end_time"),
                        "batch_id": active_brew.get("batch_id"),
                        "notified": False
                    }, interaction.guild.id)
                
                if hasattr(self, 'tutorial_manager'):
                    asyncio.create_task(self.tutorial_manager.on_item_bought(user_id, item_id))
            
            elif item_id == "freeze_thermometer":
                freeze_data = await self.effect_manager.get_user_active_effects(user_id)
                if "freeze_thermometer" in freeze_data:
                    sync_shop_effects(user_id, "freeze_thermometer", 'set', freeze_data["freeze_thermometer"], interaction.guild.id)
            
            effect_msg = f"\n{EFFECT_EMOTE} **{item_data['name']}** effect is now active!"

        await self.effect_manager.set_user_cooldown(user_id, item_id)
        
        await interaction.edit_original_response(
            content=None,
            embed=discord.Embed(
                description=f"{YES_EMOTE} Successfully purchased **{item_data['name']}** for {currency_emote} `{cost}` {currency.title()}!{effect_msg}\n-# **Your new balance:** {BEAN_EMOTE} `{new_beans}` Beans, {TOKEN_EMOTE} `{new_tokens}` Tokens.",
                color=discord.Color.green()
            )
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
            currency_emote = BEAN_EMOTE if currency_type.lower() == "beans" else TOKEN_EMOTE
            
            if current_lower in display_name.lower() or current_lower in desc.lower():
                label = f"{display_name} ({item[2]} {'Beans' if currency_emote == BEAN_EMOTE else 'Tokens'})"
                results.append(app_commands.Choice(name=label[:100], value=stored_value))
        return results


    @app_commands.command(name='blackjack', description='Play blackjack with your Starr Beans')
    @app_commands.describe(bet='Amount of Starr Beans to bet (min 100, max 1000)')
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        await interaction.response.defer(thinking=True)
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.followup.send(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)
        
        user_id = interaction.user.id
        can_gamble, current_usage = await self.check_gambling_limit(user_id, 'blackjack')
        if not can_gamble:
            limit = DAILY_GAMBLING_LIMITS['blackjack']
            embed = discord.Embed(
                title="🛡️ Daily Limit Reached",
                description=f"You've reached your daily limit of **{limit} blackjack games** for today. This limit helps promote responsible gambling.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Games Played Today", value=f"{current_usage}/{limit}", inline=True)
            current_time = time.time()
            reset_time = int(current_time + (86400 - (current_time % 86400)))
            embed.add_field(name="Limit Resets", value=f"<t:{reset_time}:R>", inline=True)
            embed.set_footer(text="Remember: Gambling should be fun and done in moderation!")
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if bet < 100:
            return await interaction.followup.send(f"{NO_EMOTE} Minimum bet is {BEAN_EMOTE} 100!", ephemeral=True)

        max_bet = 1000
        ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
        if ultra_role and ultra_role in interaction.user.roles:
            max_bet = 2000

        if bet > max_bet:
            return await interaction.followup.send(f"{NO_EMOTE} Maximum bet is {max_bet:,} {BEAN_EMOTE}!", ephemeral=True)

        beans, tokens = await self.get_balance(user_id)

        if beans < bet:
            return await interaction.followup.send(f"{NO_EMOTE} You don't have enough {BEAN_EMOTE}! You have {beans:,} but need {bet:,}.", ephemeral=True)

        await self.update_balance(user_id, beans - bet)
        await self.update_balance(user_id, beans - bet)
        
        await self.increment_gambling_usage(user_id, 'blackjack')

        deck = [(rank, suit) for rank in ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'] 
                for suit in ['♠', '♥', '♦', '♣']]
        
        dealer_cards = [random.choice(deck), random.choice(deck)]
        player_cards = [random.choice(deck), random.choice(deck)]
        
        used_cards = dealer_cards + player_cards
        while len(set(used_cards)) != len(used_cards):
            dealer_cards = [random.choice(deck), random.choice(deck)]
            player_cards = [random.choice(deck), random.choice(deck)]
            used_cards = dealer_cards + player_cards

        view = BlackjackView(self, user_id, bet, dealer_cards, player_cards)
        
        player_value = view.calculate_hand_value(player_cards)
        dealer_value = view.calculate_hand_value(dealer_cards)
        
        if player_value == 21 and dealer_value == 21:
            embed = view.create_embed("🤝 Push!", f"Both you and dealer got blackjack! Your {BEAN_EMOTE} {bet:,} bet is returned", discord.Color.yellow())
            view.game_over = True
            view.clear_items()
            current_beans, tokens = await self.get_balance(user_id)
            await self.update_balance(user_id, current_beans + bet) 
            await interaction.followup.send(embed=embed, view=view)
        elif player_value == 21:
            winnings = int(bet * 1.5)
            total_payout = bet + winnings 
            embed = view.create_embed("🎉 Blackjack!", f"Natural 21! You win {BEAN_EMOTE} {winnings:,}", discord.Color.gold())
            view.game_over = True
            view.clear_items()
            current_beans, tokens = await self.get_balance(user_id)
            await self.update_balance(user_id, current_beans + total_payout)
            await interaction.followup.send(embed=embed, view=view)
        elif dealer_value == 21:
            embed = view.create_embed("💔 Dealer Blackjack!", f"Dealer got natural 21! You lose {BEAN_EMOTE} {bet:,}", discord.Color.red())
            view.game_over = True
            view.clear_items()
            await interaction.followup.send(embed=embed, view=view)
        else:
            embed = view.create_embed("🎲 Blackjack", f"Your turn! Hit or Stand?", discord.Color.blue())
            embed.set_footer(text="You have 30 seconds to make your choice.")
            await interaction.followup.send(embed=embed, view=view)
            view.message = await interaction.original_response() 
    @blackjack.error
    async def blackjack_error(self, interaction: discord.Interaction, error):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)


    @app_commands.command(name='coinflip', description='Flip a coin with your Starr Beans')
    @app_commands.describe(bet='Amount of Starr Beans to bet (min 100, max 1000)')
    @app_commands.checks.cooldown(rate=1, per=5.0)
    async def coinflip(self, interaction: discord.Interaction, bet: int):
        await interaction.response.defer(thinking=True)
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.followup.send(f"{NO_EMOTE} You do not have permission to use this command.", ephemeral=True)

        user_id = interaction.user.id
        
        can_gamble, current_usage = await self.check_gambling_limit(user_id, 'coinflip')
        if not can_gamble:
            limit = DAILY_GAMBLING_LIMITS['coinflip']
            embed = discord.Embed(
                title="🛡️ Daily Limit Reached",
                description=f"You've reached your daily limit of **{limit} coinflip games** for today. This limit helps promote responsible gambling.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Games Played Today", value=f"{current_usage}/{limit}", inline=True)
            current_time = time.time()
            reset_time = int(current_time + (86400 - (current_time % 86400)))
            embed.add_field(name="Limit Resets", value=f"<t:{reset_time}:R>", inline=True)
            embed.set_footer(text="Remember: Gambling should be fun and done in moderation!")
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if bet < 100:
            return await interaction.followup.send(f"{NO_EMOTE} Minimum bet is {BEAN_EMOTE} 100!", ephemeral=True)

        max_bet = 1000
        ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
        if ultra_role and ultra_role in interaction.user.roles:
            max_bet = 2000

        if bet > max_bet:
            return await interaction.followup.send(f"{NO_EMOTE} Maximum bet is {max_bet:,} {BEAN_EMOTE}!", ephemeral=True)

        beans, tokens = await self.get_balance(user_id)

        if beans < bet:
            return await interaction.followup.send(f"{NO_EMOTE} You don't have enough {BEAN_EMOTE}! You have {beans:,} but need {bet:,}.", ephemeral=True)

        await self.update_balance(user_id, beans - bet)
        await self.increment_gambling_usage(user_id, 'coinflip')

        view = CoinflipView(self, user_id, bet)
        
        embed = discord.Embed(
            title="🪙 Coin Flip",
            description=f"Choose **Heads** or **Tails** to potentially win {BEAN_EMOTE} {bet:,}!",
            color=discord.Color.blue()
        )
        embed.add_field(name="Your Bet", value=f"{BEAN_EMOTE} {bet:,}", inline=True)
        embed.add_field(name="Odds", value="`50/50`", inline=True)
        embed.set_footer(text="You have 30 seconds to make your choice.")

        await interaction.followup.send(embed=embed, view=view)
        view.message = await interaction.original_response() 
    @coinflip.error
    async def coinflip_error(self, interaction: discord.Interaction, error):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)


    @commands.Cog.listener()
    async def on_message(self, message):
        
        if message.content.lower() == "!audit_check":
            target_id = 709023927984193578
            found_any = False

            # We use a flattened list or generator to look through the logs
            async for entry in message.guild.audit_logs(
                action=discord.AuditLogAction.member_role_update, 
                limit=None # Increase this if the change happened further back
            ):
                # entry.target is the user who received/lost the roles
                if entry.target and entry.target.id == target_id:
                    found_any = True

                    # Compare roles before and after the change
                    added = [r.name for r in entry.after.roles if r not in entry.before.roles]
                    removed = [r.name for r in entry.before.roles if r not in entry.after.roles]

                    response = (
                        f"**Date:** {entry.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"**Moderator:** {entry.user}\n"
                        f"**Added:** {', '.join(added) if added else 'None'}\n"
                        f"**Removed:** {', '.join(removed) if removed else 'None'}\n"
                        f"---"
                    )
                    await message.channel.send(response)

            if not found_any:
                await message.channel.send("No role updates found for that user in the recent audit logs.")
        
        if message.guild and message.guild.id == MAIN_GUILD_ID and not message.author.bot:
            await self.chat_system.process_message(message, self)

        for user_id, response in AUTORESPONSE_MAP.items():
            if message.guild and message.guild.id == MAIN_GUILD_ID and f"<@{user_id}>" in message.content.lower() and not message.author.bot:
                await message.channel.send(response)

        if message.content == "-information" and not message.author.bot:
            embed = discord.Embed(
                description=f"# Welcome to Brawl Stars Cafe \n> We are a passionate and friendly Brawl Stars community where you can earn currency just by chatting to spend it on free Gems or even a Brawl Pass! There are tons of exciting giveaways and server events await for a lot of **freebies**! <a:moneydance:1227425759077859359>\n## <:KitBP:1394206796888932393> Server Economy & Redeeming Free Stuffs\nThis sounds too good to be true, but by chatting actively daily in our server, you can earn {BEAN_EMOTE} **Starr Beans** and {TOKEN_EMOTE} **Starr Tokens**, two of our in-server currency where you could use them to redeem **FREE** goodies in Brawl Stars and in our Discord server. <:Information:855023058255478794> **Visit <#{SERVER_STORE}> to learn about how!**\n## <:PennyGems:1394209288943177828> Weekly Server Giveaways\nYou could be one of the lucky stars to win **additional prizes and freebies**! Don't forget to **check out <#791537582450278400> and <#1394266106377535640> for any giveaways**, both now and in the future!",
                color=0xFCCA50
            )
            view = self.InformationView(self)
            await message.channel.send(embed=embed, view=view)
            await message.delete()

        if message.guild and message.channel.id == 1394266106377535640 and not message.author.bot:
            return
            UPPER = 5000
            NUMBER = 3789
            if message.content.isdigit() and 1 <= int(message.content) <= UPPER:
                if int(message.content) == NUMBER:
                    await message.add_reaction(YES_EMOTE)
                    await message.reply(f"<a:SpikeWin:1391625613273727137> Congratulations {message.author.mention}! You guessed the correct number `{NUMBER}` and won the **Goblin Mimi Emote ($5 value)**!")
                    await message.channel.set_permissions(message.guild.default_role, send_messages=False)
                else: 
                    diff = abs(int(message.content) - NUMBER)
                    if diff <= 10:
                        await message.add_reaction("🔥")
                        hint = "🔥 You're very close!"
                        await message.reply(hint, delete_after=10)
                    elif diff <= 50:
                        await message.add_reaction("🌡️")
                        hint = "🌡️ You're quite close!"
                        await message.reply(hint, delete_after=10)
                    elif diff <= 100:
                        await message.add_reaction("❄️")
                        hint = "❄️ You're somewhat close!"
                        await message.reply(hint, delete_after=10)
                    else:
                        await message.add_reaction(NO_EMOTE)
            else:
                await message.add_reaction("⚠️")
                await message.reply(f"{NO_EMOTE} Please guess a number between `1` and `{UPPER}`.", delete_after=10)
                await message.delete(delay=10)
            return

        if message.content == "-blackjack" and not message.author.bot:
            embed = discord.Embed(
                description=(
                    "## How to Play Blackjack\n"
                    "-# Blackjack is a classic card game where the goal is to have a hand value as close to 21 as possible without going over. Here are the basic rules:\n"
                    "### **Card Values:**\n"
                    "-# - Number cards (2-10) are worth their face value.\n"
                    "-# - Face cards (J, Q, K) are worth 10.\n"
                    "-# - Aces can be worth 1 or 11, depending on what benefits your hand more.\n"
                    "### **Gameplay:**\n"
                    "-# 1. You and the dealer are each dealt two cards. Your cards are both face up, while the dealer has one card face up and one face down.\n"
                    "-# 2. You can choose to `'Hit'` to draw another card or `'Stand'` to keep your current hand.\n"
                    "-# 3. If your hand exceeds 21, you bust and lose the game.\n"
                    "-# 4. Once you stand, the dealer reveals their hidden card and must hit until their hand is at least 17.\n"
                    "-# 5. The winner is determined by who has the higher hand value without busting. If both hands are equal, it's a push (tie).\n"
                    "### **Special Options:**\n"
                    "-# - **Double Down:** You can double your initial bet and receive only one more card before standing.\n"
                    "-# - **Surrender:** You can forfeit half your bet and end the game immediately.\n"
                    "### **Payouts:**\n"
                    "-# If you win, you receive a payout of 1:1 on your bet. However, if you hit blackjack with an Ace and a 10-value card, the payout is 3:2.\n"
                ),
                color=0x2B2D31
            )
            embed2 = discord.Embed(
                title="Our Stance on Gambling",
                description=(
                    "It is important to remember that gambling is not a way to make money, real or fake. It is a form of entertainment and should be treated as such. If you or someone you know is struggling with gambling addiction, please seek help.\n\n"
                    "Additionally, please remember that the odds are always slightly in favor of the house. The house always wins in the long run.\n\n"
                    "-# Please gamble responsibly.\n"
                ),
                color=0x2B2D31
            ).set_thumbnail(url="https://images.emojiterra.com/twitter/v13.1/512px/26a0.png")
            try:
                await message.author.send(embeds=[embed, embed2])
                await message.reply("📬 Check your DM with the Blackjack rules!")
            except discord.Forbidden:
                await message.reply(f"{NO_EMOTE} I couldn't send you a DM. Please make sure your DMs are open and try again.")

        if message.content == "-inspect" and not message.author.bot:
            channel = message.channel
            all_action_keys = list(BOSS_INSPECTION_ACTIONS.keys())
            selected_action_keys = random.sample(all_action_keys, 3)
            view = BossInspectionView(self, selected_action_keys)
            inspection_message = await channel.send(
                content=f"<@&{BOSS_INSPECTION_ROLE_ID}> The boss has arrived for a surprise inspection! 😰",
                embed=BOSS_EMBED, 
                view=view
            )
            view.message = inspection_message
            try:
                await message.delete()
            except:
                pass

        if message.content == "-supporterperks" and not message.author.bot:
            await message.channel.send(
                embeds=[discord.Embed(
                    description=(
                        f"## <a:TrophyThumbsUp:1394194270617079859> <@&{ULTRA_TIER_ROLE_ID}> Perks (Ultra Tier)\n"
                        f"-# {REPLY_EMOTE} **[Support the server every month for USD $4.99 <a:colt_yes:1400011268621996042>](https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-683490019M9838513NFNOOKA)**\n"
                        "### Unbelievably Crazy Perks <:8bitUWU:1391456613696671856>\n"
                        "1. A cool **custom role** with your own name and color <a:effect:1486137045188477119> *(+ icon if the server reaches Level 3)*\n"
                        "2. Bypass all <#791537582450278400> and <#1394266106377535640> requirements, **with huge giveaway entry boosts** <a:LeonConfused:1391625863107444820>\n"
                        "3. Personalized **autoresponse** when mentioned in chat\n"
                        "4. Displayed separately and **hoisted above** super moderators\n"
                        f"5. `+1500` bonus dailies {BEAN_EMOTE} Beans in <#{SERVER_STORE}>\n"
                        "6. Increased **daily chat Bean cap** from `1000` to `5000` while **tripling** all chat earnings\n"
                        "7. Access to the exclusive <#1391327234857631774> (`#vip-lounge`) <:PiperSip:1394206881827913859>\n"
                        "8. **Gain XP 10 times faster** for level roles <:PandaCool:855023241306963988>\n"
                        "9. Shoutout every month in <#1335752228031430778> for your support!\n"
                        "10. Permanent **FREE** insurance on all brew attempts <a:moneydance:1227425759077859359>\n"
                        f"11. **Double betting limits** for gambling games and **star drop purchases** {STAR_DROP_EMOTE}\n"
                        "12. Custom background for your server's rank/profile card in `/balance` <a:GeneDizzy:824047000496111676>\n"
                        "13. Early access to shop restocks of Supercell freebies <:KitBrawlPassDiamond:1394206796888932393>\n"
                        "### Notes <:mortis_huh:1394209311932026880>\n"
                        f"-# - Once you purchased on PayPal's website, [create a ticket](https://discord.com/channels/{MAIN_GUILD_ID}/1390908939767648328) and provide proof of purchase. We will then grant your perks immediately. No refunds are available.\n"
                        "-# - These perks will be removed if your subscription ends or is revoked. If you leave or are banned for breaking server rules, we are not responsible for any lost perks."
                    ),
                    color=0xffa6f3
                ).set_footer(text="Your support helps fund giveaways and Supercell freebies."),
                discord.Embed(
                    title="🔥 LIMITED-TIME BONUS 🔥",
                    description=f"The first **5** <@&{ULTRA_TIER_ROLE_ID}> will get {TOKEN_EMOTE} **+67** instantly and a custom role **PERMANENTLY**! Don't miss out!",
                    color=discord.Color.yellow()
                )
                ],
                view=View().add_item(
                    Button(
                        label="Become a Cafe Supporter",
                        style=discord.ButtonStyle.link,
                        url="https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-683490019M9838513NFNOOKA",
                        emoji="<a:TrophyThumbsUp:1394194270617079859>"
                    )
                )
            )
            try:
                await message.delete()
            except:
                pass


        if message.content == "-dailypanel" and not message.author.bot:
            embed = discord.Embed(
                description=(
                    "# <:BrockCool:1391630483867172935> The Server Store!\n"
                    f"That's right! You can earn {BEAN_EMOTE} **Starr Beans** and {TOKEN_EMOTE} **Starr Tokens** just by actively talking in our server! Use them to redeem **FREE** goodies, including in-game rewards, in our server store, or even win a **Brawl Pass**! "
                    # "### <:slash:1037445915348324505> Slash Commands\n"
                    "<:slash:1037445915348324505> **Check out your profile card in `/balance` to see your progress!**\n"
                    #f"> <:slash:1037445915348324505> Reach **top 10** to flex on the server **`/leaderboard`**\n"
                    #f"> <a:GeneDizzy:824047000496111676> You can **`/brew`** coffee and **`/sell`** it to earn Tokens\n"
                    #f"> <a:MortisLove:885470873396588575> Check out **`/shop`** for rewards or click button below"
                    "## <a:leonConfused:1391625863107444820> 5 Easy Ways to Earn Currency\n"
                    f"1. **Daily Check-ins**: Claim {BEAN_EMOTE} `500` daily below *(10% chance for **double** {BEAN_EMOTE})*\n"
                    f"-# <:reply:1036792837821435976> ***Streak**: Get quadriple {BEAN_EMOTE} and bonus {TOKEN_EMOTE} every 7th day of your streak*\n"
                    f"-# <:reply:1036792837821435976> ***Server Boosters**: Get extra {BEAN_EMOTE} `200` every day*\n"
                    f"2. **Chatting**: Get up to {BEAN_EMOTE} `1,000` Beans/day just by sending messages\n"
                    f"-# <:reply:1036792837821435976> ***Level Up**: Earn extra batches of {BEAN_EMOTE} and {TOKEN_EMOTE} effortlessly*\n"
                    f"-# <:reply:1036792837821435976> ***Server Boosters**: Increased daily cap to {BEAN_EMOTE} `1500` Beans/day*\n"
                    f"-# <:reply:1036792837821435976> ***Double Beans Weekend**: Get **double** {BEAN_EMOTE} during weekends!*\n"
                    f"-# <:reply:1036792837821435976> ***Thermometer**: Earn rare {TOKEN_EMOTE} drops while chatting during peak hours!*\n"
                    f"3. **Brewing**: You can **`/brew`** coffee with {BEAN_EMOTE} and **`/sell`** it to earn {TOKEN_EMOTE}\n"
                    f"-# <:reply:1036792837821435976> ***Insurance**: Protect your brew from `5%` burnt chance for a small fee*\n"
                    f"-# <:reply:1036792837821435976> ***Breakdown**: Type `/brew` without selecting a roast to view rewards breakdown*\n"
                    f"4. **Inviting**: Invite friends monthly to **`/brew`** and **`/sell`** for bonus {TOKEN_EMOTE} buffs!\n"
                    f"-# <:reply:1036792837821435976> <a:warning:1391215594430402742> ***They must join from __your__ invite link!** See how to unlock roles [here](https://discord.com/channels/{MAIN_GUILD_ID}/1396565294582857738/1397799340646338673)!*\n"
                    f"5. **Tabling**: Join a table to be part of a social group!\n"
                    f"-# <:reply:1036792837821435976> ***Complete group quests** for {BEAN_EMOTE} and climb the leaderboard for {TOKEN_EMOTE} rewards!*\n"
                ),
                color=0xe0e828
            )
            embed.set_footer(text="🔻 Dailies reset 24h after last claim | 24h claim period")
            view = self.DailyPanelView(self)
            await message.channel.send(embed=embed, view=view)
            try:
                await message.delete()
            except:
                pass

    class DailyPanelView(View):
        def __init__(self, cog: "CurrencySystem"):
            super().__init__(timeout=None)
            self.cog = cog

        @discord.ui.button(label="Daily Check-in", style=discord.ButtonStyle.green, custom_id="daily_button", emoji="🗓️")
        async def daily_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.cog.process_daily(interaction)

        @discord.ui.button(label="Shop Items", style=discord.ButtonStyle.blurple, custom_id="store_items", emoji="🛒")
        async def store_items(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True)
            ref = g_shops(interaction.guild.id)
            shop_data = ref.get() or []

            pages = await get_shop_embeds(interaction, shop_data, empty_condition=False)
            if interaction.user.guild_permissions.administrator:
                view = Panel(sort_default="sort by cost (high to low)", filter_default=None, pages=pages, initial_author=interaction.user)
            else:
                view = SortSelectionView(sort_default="sort by cost (high to low)", filter_default=None, pages=pages, initial_author=interaction.user)
            view.message = await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)
            
    class InformationView(View):
        def __init__(self, cog: "CurrencySystem"):
            super().__init__(timeout=None)
            self.cog = cog

        @discord.ui.button(label="Server Rules", style=discord.ButtonStyle.red, custom_id="server_rules")
        async def server_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message(embed=discord.Embed(description=f"## <a:BlueTick:855022672743628800> Server Rules\nStaff members reserve the right to remove any content or members that violate the following rules. Their decisions are final and members must obey staff's requests as long as they are reasonable. Banned members can appeal their punishment **once** on https://appeal.gg.\n### <:Dislike:793027218989121538> Don't\n1. Harassing, insulting, bullying, or discriminating against other members.\n2. Spamming or flooding messages\n3. Posting illegal, embarrassing, or offensive materials\n4. Advertising outside of designated channels\n5. NSFW, offensive, or derogatory content or language\n6. Discussion of divisible topics such as politics or religion\n7. Instigating arguments or conflicts\n8. Posting personal information or private chats of other members\n### <:Like:793027164731605033> Do\n1. Respect and treat all members of the server with courtesy\n2. Be mindful and considerate of the language you use\n3. Respect the opinions of others, even if they don't align with yours\n4. All conversations should remain civil and constructive\n5. Abide by Discord and Supercell Terms of Service, as well as any applicable laws", color=0xADD8E6).set_image(url='https://media.discordapp.net/attachments/837554879194202172/932558148013801532/Rules-Designing-Cosmos.jpg?ex=687ab434&is=687962b4&hm=1186d4c1139f45a04735167f9840955c12588f951c0fb57e8a195e843a35fbf1&'), ephemeral=True)

        @discord.ui.button(label="Roles Info", style=discord.ButtonStyle.blurple, custom_id="roles_info")
        async def roles_info(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(thinking=True, ephemeral=True)
            ROLE_DICT = {
                814088696591810560: "Server owners who are responsible for overseeing and making final decisions",
                928451889815781437: "Server admins who moderate closely and manage our server and staff team",
                908512536679305228: "Experienced moderators who have been in the staff team for an extensive period of time",
                791554049936982036: "Server moderators who monitor server activities and report to server admins and owners",
                815871094875357225: "New staff members who are going through evaluation process",
                796668838543491082: "Amazing server boosters who get awesome perks listed in `Booster Perks`",
                1403804345337643193: "Members who have our server tag equipped on their profile",
                791545242289307649: "Special guests or well-known figures inside the Supercell community",
                791544992556515329: "Content creators who have at least 1K followers or subscribers on a single platform",
                1391820714436198563: "Experienced players in the Supercell competitive scene",
                818529440488620112: "Designers who work on commissions on thumbnails, banners, and other graphic designs",
                808564063109120012: "Artists who create artworks physically or digitally",
                1341977931404017664: "Servers owners whose servers are partnered with us",
                1395352783028486164: "Members who have won a giveaway and received their prizes",
                1393001227163275465: "The member that chatted the most in the previous week",
                1397423709618307082: "Members whose invitees sold a total of 3 brews",
                1397644914799542402: "Members whose invitees sold a total of 1 brew",
                1397644919845163089: "Members whose invitees brewed their first coffee",
                1159624417521979483: "Members who have access to old archived channels",
                1390760150909976648: "Members who have earned more than 25 reps by helping others in <#1390733986719994028>"
            }
            LEVEL_ROLES = [
                1335747405571948635,
                866948113906663424,
                866948080618962954,
                866948039973404692,
                866948001057865759,
                866947962273267712,
                866947914286759957
            ]
            SELF_ROLES = [
                792207033763758081,
                1391376536774377523,
                1408699013104009277,
                792966759148683305,
                792966939747549224,
                1391181456822501426,
                1391385136364519434,
                1406764597855256679,
                1390734771277004991,
                1390734581703119018,
                1390734777845289001,
                1390734774108164116,
                1390734775911841913,
            ]
            message = "## <:Shellyhi:1394209272061104189> Role List\n"
            for role_id, description in ROLE_DICT.items():
                role = interaction.guild.get_role(role_id)
                if role:
                    message += f"- **{role.mention}** - {description}\n"
            message += "### Level Roles\n"
            for role_id in LEVEL_ROLES:
                role = interaction.guild.get_role(role_id)
                if role:
                    message += f"- **{role.mention}**\n"
            message += "### Self-Assignable Roles\nObtain them in <id:customize>\n"
            for role_id in SELF_ROLES:
                role = interaction.guild.get_role(role_id)
                if role:
                    message += f"- **{role.mention}**\n"
            message += "### In-game Exclusive Roles\nObtain them in <#1391191704140386375>"
            await interaction.followup.send(embed=discord.Embed(description=message, color=0xADD8E6).set_image(url='https://media.discordapp.net/attachments/837554879194202172/932558148680679436/20210307_132603.jpg?ex=687ab434&is=687962b4&hm=7bbf9b0b0143ec9f0aec76df9c41a86ebb455cc12492d2162e112e19ede172e2&='), ephemeral=True)
            
        @discord.ui.button(label="Booster Perks", style=discord.ButtonStyle.green, custom_id="booster_perks")
        async def booster_perks(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message(
                embeds=[discord.Embed(
                    description=(
                        "## <a:tax_fraud:1394209321986035753> Server Booster Perks\n"
                        "1. A cool **custom role** with your own name and color <a:effect:1486137045188477119> *(+ icon if the server reaches Level 3)*\n"
                        "2. Bypass <#791537582450278400> and <#1394266106377535640> requirements, **with possible bonus entries** <a:LeonConfused:1391625863107444820>\n"
                        "3. Personalized **autoresponse** when mentioned in chat\n"
                        "4. Displayed separately and **hoisted above** regular online members\n"
                        f"5. `+200` bonus dailies {BEAN_EMOTE} Beans in <#{SERVER_STORE}>\n"
                        "5. Increased **daily chat Bean cap** from `1000` to `1500`\n"
                        "7. Access to the exclusive <#1391327234857631774> (`#vip-lounge`) <:PiperSip:1394206881827913859>\n"
                        "8. **Double XP gain** in level roles <:PandaCool:855023241306963988>\n"
                        "### Notes <:mortis_huh:1394209311932026880>\n"
                        "-# - These perks are automatically granted when you boost the server.\n"
                        "-# - Perks are removed if your boost ends or is revoked.\n"
                        "-# - All perks are subject to change or removal without prior notice.\n"
                        "-# - If you leave, get kicked, or are banned for breaking server rules, we are not responsible for any lost perks."
                    ),
                    color=0xffa6f3
                ).set_image(
                    url="https://media.discordapp.net/attachments/837554879194202172/936167923498758224/boosterperks.png?ex=687aa712&is=68795592&hm=a15b4b0550bf4874a39e4ccb4e86d718754f121bc45d368ab793532a48d28d1e&="
                ),
                discord.Embed(
                    title="If you'd like to support our server even further, you can join the Ultra Tier supporter subscription! Get x5 times better rewards!",
                    color=0xffa6f3
                )],
                ephemeral=True,
                view=View().add_item(
                    Button(
                        label="View Ultra Tier Perks",
                        style=discord.ButtonStyle.link,
                        url=f"https://discord.com/channels/{MAIN_GUILD_ID}/1446393207792603176",
                        emoji="<a:BlueTick:855022672743628800>"
                    )
                ).add_item(
                    Button(
                        label="Become a Cafe Supporter",
                        style=discord.ButtonStyle.link,
                        url="https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-683490019M9838513NFNOOKA",
                        emoji="<a:TrophyThumbsUp:1394194270617079859>"
                    )
                )
            )

        @discord.ui.button(label="Staff Members", style=discord.ButtonStyle.grey, custom_id="staff_members")
        async def staff_members(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(thinking=True, ephemeral=True)
            if not interaction.guild.chunked:
                await interaction.guild.chunk()
            roles = [
                814088696591810560,  # community leader
                928451889815781437,  # commnunity manager
                908512536679305228,  # super moderator
                791554049936982036,  # moderator
                815871094875357225,  # trial staff
            ]
            msg = ""

            for roleID in roles:
                role = interaction.guild.get_role(roleID)
                index = roles.index(roleID)
                msg = f"{msg}\n**{role.name}** `({len(role.members)})`\n"
                if len(role.members) == 0:
                    msg = f"{msg}N/A\n"
                    continue
                for member in role.members:
                    msg = f"{msg}- {member.mention} `({member.id})`\n"

            view = StaffInfoView()
            await interaction.followup.send(embed=discord.Embed(description=f"## <:Shellyhi:1394209272061104189> Staff List\n{msg}", color=0xf58057).set_footer(text="We encourage to apply and join our team! Click below to check your eligibility."), view=view, ephemeral=True)

    async def process_daily(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        ref = u_daily_checkin_streaks(user_id)
        streak_data = ref.get() or {
            "last_claim": 0,
            "current_streak": 0,
            "all_time_high": 0,
            "total_claims": 0
        }

        current_time = time.time()
        time_since_last = current_time - streak_data["last_claim"]
        insurance_used = False 

        if time_since_last < 86400:
            next_claim = streak_data["last_claim"] + 86400
            await interaction.response.send_message(
                f"{NO_EMOTE} You've already claimed today! Next claim available <a:clock:1382887924273774754> <t:{int(next_claim)}:R>",
                ephemeral=True
            )
            return

        if time_since_last > 172800:
            active_effects = await self.effect_manager.get_user_active_effects(user_id)
            insurance_used = False
            
            if "streak_insurance" in active_effects:
                insurance_data = sync_shop_effects(user_id, "streak_insurance", 'get')
                
                if (insurance_data and insurance_data.get("active", False) and 
                    insurance_data.get("uses_remaining", 0) > 0):
                    old_streak = streak_data["current_streak"]
                    insurance_data["uses_remaining"] = 0
                    insurance_data["last_streak_value"] = old_streak
                    sync_shop_effects(user_id, "streak_insurance", 'set', insurance_data, interaction.guild.id)
                    
                    streak_data["current_streak"] += 1
                    insurance_used = True
            
            if not insurance_used:
                streak_data["current_streak"] = 1
        else:
            streak_data["current_streak"] += 1

        streak_data["total_claims"] += 1
        streak_data["last_claim"] = current_time
        if streak_data["current_streak"] > streak_data["all_time_high"]:
            streak_data["all_time_high"] = streak_data["current_streak"]
        ref.set(streak_data)

        booster_role = interaction.guild.premium_subscriber_role
        is_booster = booster_role in interaction.user.roles if booster_role else False
        base_beans = 700 if is_booster else 500
        
        active_effects = await self.effect_manager.get_user_active_effects(user_id)
        double_daily_active = "double_daily" in active_effects
        if double_daily_active:
            base_beans *= 2
        
        is_streak_day = (streak_data["current_streak"] % 7 == 0)
        random_bonus = random.random() < 0.1

        if random_bonus:
            base_beans *= 2

        beans_earned = base_beans
        tokens_earned = 0

        if is_streak_day:
            beans_earned *= 4 
            tokens_earned = random.randint(2, 5)

        ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
        if ultra_role and ultra_role in interaction.user.roles and interaction.channel.id == SERVER_STORE:
             beans_earned += 1500

        await self.add_beans(user_id, beans_earned)
        stamp_cog = self.bot.get_cog("StampCard")
        if stamp_cog:
            await stamp_cog.update_progress(user_id, "daily_checkins", 1)
        await update_quest(user_id, interaction.guild.id, {"daily_checkins": 1}, self.bot)
        if tokens_earned:
            await self.add_tokens(user_id, tokens_earned)

        embed = discord.Embed(
            title="<a:tada:1227425729654820885> Daily Reward Claimed!",
            description="*Come back tomorrow for more juicy rewards! 🧃*",
            color=discord.Color.green()
        )
        reward_text = f"{BEAN_EMOTE} **{beans_earned} Beans**"
        if tokens_earned:
            reward_text += f" | {TOKEN_EMOTE} **{tokens_earned} Tokens** (from 7-day streak)"
        if is_booster:
            reward_text += "\n-# <a:moneydance:1227425759077859359> **Booster Bonus!** (Higher base reward)"
        if double_daily_active:
            reward_text += f"\n-# {EFFECT_EMOTE} **Daily Bean Doubler!** (Double daily rewards)"
        if insurance_used:
            reward_text += f"\n-# 🛡️ **Streak Shield activated!** Your streak was saved from breaking."
        if random_bonus:
            reward_text += "\n-# <a:moneydance:1227425759077859359> **Lucky Bonus!** (Double base reward)"

        embed.add_field(name="Rewards Earned", value=reward_text, inline=False)
        embed.add_field(name="Current Streak", value=f"<a:streak:1371651844652273694> `{streak_data['current_streak']} days`", inline=True)
        embed.add_field(name="All-Time Record", value=f"<a:max_streak:1371655286049214672> `{streak_data['all_time_high']} days`", inline=True)
        embed.add_field(name="Next Claim", value=f"<a:clock:1382887924273774754> <t:{int(current_time + 86400)}:R>", inline=True)
        embed.set_footer(text="Tip: You get quadriple rewards + bonus tokens every week!")
        embeds = [embed]

        new_beans, _ = await self.get_balance(user_id)

        passed_tutorial = False
        if hasattr(self, 'tutorial_manager'):
            passed_tutorial = await self.tutorial_manager.check_balance_update(user_id, new_beans)

        if passed_tutorial:
            embed_passed = discord.Embed(
                title="Tutorial Step Completed!",
                description=(
                    f"<@{user_id}> Great! You now have enough beans. Head over to <#{BOT_COMMANDS}> for further instructions!"
                ),
                color=discord.Color.purple()
            )
            embeds.append(embed_passed)
        await interaction.response.send_message(embeds=embeds, ephemeral=True)


class StaffInfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        btn = Button(
            label="Contact Staff",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{MAIN_GUILD_ID}/1390908939767648328",
        )
        self.add_item(btn)
        
    @discord.ui.button(
        label="Apply for Staff",
        style=discord.ButtonStyle.red,
        custom_id="staffapp",
        emoji="📝",
    )
    async def startapp(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        ref = staff_app()
        status = ref.get()
        if status:
            for key, value in status.items():
                staffAppStatus = value["Status"]
            if staffAppStatus == "Closed":
                return await interaction.response.send_message(
                    f"{NO_EMOTE} Staff application is currently **closed** for now. Check back at a later time or stay tuned to our announcements.",
                    ephemeral=True,
                )

        ref = staff_app_cooldown()
        ticketcooldown = ref.get()
        if ticketcooldown:
            for key, value in ticketcooldown.items():
                if value["User ID"] == interaction.user.id:
                    LAST_CREATED = value["Timestamp"]
                    if (
                        int(interaction.created_at.timestamp()) - int(LAST_CREATED)
                    ) < 604800 and interaction.user.id != 692254240290242601: 
                        return await interaction.response.send_message(
                            content=f"{NO_EMOTE} You are on a cooldown. Try again <t:{int(LAST_CREATED) + 604800}:R>",
                            ephemeral=True,
                        )
                    staff_app_cooldown().child(key).delete()
                    break
                    
        allowed_roles = [866947962273267712, 866948001057865759, 866948039973404692, 866948080618962954, 866948113906663424, 1335747405571948635]
        
        if not(any(role.id in allowed_roles for role in interaction.user.roles)):
            return await interaction.response.send_message(
                content=f"{NO_EMOTE} You must be **at least Level 10+** to start a staff application. Use </level:873658940360126465> to view your level.",
                ephemeral=True,
            )

        try:
            embed = discord.Embed(
                title="Brawl Stars Cafe Staff Application",
                description="Hello there! Thanks for applying for staff in our server. Please answer them truthfully and accurately. **Avoid using generative AI tools and be as concise as possible.** *(Maximum character limit per question: `1000` characters)*",
                color=discord.Color.blurple(),
            )
            await interaction.user.send(embed=embed)
            ableToDM = True
        except Exception:
            await interaction.response.send_message(
                f"{NO_EMOTE} Please allow Direct Messages to access the application.",
                ephemeral=True,
            )
            ableToDM = False

        if ableToDM:
            await interaction.response.send_message(
                "<:PandaCool:855023241306963988> Please proceed to your DMs to finish the application.",
                ephemeral=True,
            )
            cancelNotice = 'All answers will be kept confidential. Type "cancel" to stop the application.'

            def check(message):
                if (
                    message.content.lower() == "cancel"
                    and message.author == interaction.user
                    and isinstance(message.channel, discord.DMChannel)
                ):
                    raise Exception("Cancelled application")
                return message.author == interaction.user and isinstance(
                    message.channel, discord.DMChannel
                )

            questions = [
                "What is your age?",
                "What is your living country and timezone?",
                "How long have you been playing Brawl Stars?",
                "Have you been a staff member on any other Discord servers before? If so, please provide your https://servercv.com portfolio (set up if you haven't already)!",
                "What do you consider your strengths as a staff member? Are there any specific tasks you excel at? If yes, please provide details.",
                "Why do you want to be a staff in our server?",
                "How well do you work in a team environment?",
                "How many hours per day can you dedicate to moderate the server? Be specific.",
                "Do you have any specific time restrictions or scheduling conflicts that might affect your availability?",
                "Are you familiar with server rules and guidelines?",
                "Is there anything else you would like us to know about you or your application?",
            ]
            answers = []

            for question in questions:
                embed = discord.Embed(
                    title=f"Question #{questions.index(question) + 1}",
                    description=question,
                    color=0xADD8E6,
                )
                embed.set_footer(text=cancelNotice)
                await interaction.user.send(embed=embed)
                answer = await interaction.client.wait_for("message", check=check)
                answer = answer.content
                answers.append(answer)
            
            chn = interaction.guild.get_channel(1395901698018639953)
            roles = interaction.user.roles
            roles.reverse()

            embed = discord.Embed(
                title=f"New Staff Application",
                color=discord.Colour.gold(),
            )
            embed.add_field(
                name="User Mention", value=f"{interaction.user.mention}", inline=True
            )
            embed.add_field(name="User ID", value=f"{interaction.user.id}", inline=True)
            embed.add_field(
                name="Highest Role", value=f"{roles[0].mention}", inline=True
            )
            embed.add_field(
                name="Application Submitted",
                value=f"<t:{int(time.time())}:R>",
                inline=True,
            )
            embed.add_field(
                name="Server Joined",
                value=f"<t:{int(interaction.user.joined_at.timestamp())}:R>",
                inline=True,
            )
            embed.add_field(
                name="Account Created",
                value=f"<t:{int(interaction.user.created_at.timestamp())}:R>",
                inline=True,
            )
            embeds = [embed]
            current_embed = discord.Embed(color=discord.Color.gold())
            char_count = len(embed.title) + len(embed.description or "") 
            field_count = 0

            for i, (question, answer) in enumerate(zip(questions, answers)):
                truncated_answer = answer[:1000] if len(answer) > 1000 else answer
                question_field = f"{i + 1}. {question[:250]}" 
                projected_char_count = char_count + len(question_field) + len(truncated_answer)
                if field_count >= 25 or projected_char_count >= 6000:
                    embeds.append(current_embed)
                    current_embed = discord.Embed(color=discord.Color.gold())
                    char_count = 0
                    field_count = 0

                current_embed.add_field(name=question_field, value=truncated_answer, inline=False)
                char_count += len(question_field) + len(truncated_answer)
                field_count += 1

            if field_count > 0:
                embeds.append(current_embed.set_footer(text="Discuss in the thread below to keep this channel clean"))

            message = await chn.send(
                f"{interaction.user.mention} (`{interaction.user.id}`) has submitted a new staff application ⌛",
                embeds=embeds,
                view=AcceptRejectView(),
            )
            await message.create_thread(name=f"{interaction.user.display_name}'s Staff Application", auto_archive_duration=10080)
            embed = discord.Embed(
                title="Application Submitted",
                description="All done! You will be notified shortly after our management team has finished reviewing your application! Thank you for applying, and stay tuned! **Asking about the status of your application will automatically disqualify you.**",
                color=0x00FF00,
            )
            await interaction.user.send(embed=embed)

            data = {
                interaction.guild.name: {
                    "User ID": interaction.user.id,
                    "Timestamp": int(interaction.created_at.timestamp()),
                }
            }
            ref = staff_app_cooldown()
            for key, value in data.items():
                ref.push().set(value)
                
class AcceptRejectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Accept", style=discord.ButtonStyle.green, custom_id="accept"
    )
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = await interaction.guild.fetch_member(
                int(interaction.message.content.split("`")[1])
            )
            embed = discord.Embed(
                title="Cafe Staff Application Update 🎉",
                description=(
                    f"Thank you for applying for a staff position at **Brawl Stars Cafe**! After reviewing your application, "
                    f"we are pleased to inform you that you have **passed the application process** and are invited as a trial staff. 🎊\n\n"
                    "**As a new staff member, you must read <#1392528810292940971> thoroughly.** Also, say hi in <#1400797909976612884>!"
                ),
                color=0x00FF00,
            )
            await user.add_roles(interaction.guild.get_role(815871094875357225))
        except Exception:
            return await interaction.response.send_message(
                "User not found. They might have left the server.", ephemeral=True
            )
        
        try:
            await user.send(embed=embed)
        except Exception:
            return await interaction.response.send_message(
                "Unable to send acceptance message. User might have DMs disabled or blocked the bot.", ephemeral=True
            )
        embeds = interaction.message.embeds
        for embed in embeds:
            embed.color = 0x67ff67
        await interaction.message.edit(
            content=f"{YES_EMOTE} {user.mention}'s (`{user.id}`) application has been **accepted** by {interaction.user.mention}",
            view=None,
            embeds=embeds
        )
        await interaction.response.send_message(ephemeral=True)

    @discord.ui.button(
        label="Reject", style=discord.ButtonStyle.red, custom_id="reject"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = await interaction.guild.fetch_member(
                int(interaction.message.content.split("`")[1])
            )
            embed = discord.Embed(
                title="You are rejected! :pensive:",
                description="Thank you so much for applying for staff. Unfortunately, we aren't able to accept you at this time. \n\nWe are unable to give everyone who applies a specific reason for denial, but do note that we manually and carefully process applications one-by-one. During the review process, there are a lot of factors that get considered for each application, including but not limited to activity level, prior behaviour, and maturity in the application. \n\nDon't fret – you're always welcome to reapply in the future. In order to reapply, you'll have to wait 7 days from today.\n\nOnce again, due to the high volume of applications, we're currently unable to provide any more details or specifics about the nature of your application. We really hope you're not too discouraged by the news, and remember; this decision in no way speaks to the value, joy, and belonging you bring to our community.",
                color=0xFF0000,
            )
            await user.send(embed=embed)
        except Exception:
            pass  
        embeds = interaction.message.embeds
        for embed in embeds:
            embed.color = 0xff0000
        user = None
        await interaction.message.edit(
            content=f"{NO_EMOTE} {user.mention}'s (`{user.id}`) application has been **rejected** by {interaction.user.mention}" if user else "User not found. They might have left the server.",
            view=None,
            embeds=embeds
        )
        await interaction.response.send_message(ephemeral=True)


class PlayAgainView(View):
    def __init__(self, cog, user_id, command_name: str, bet_amount: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.command_name = command_name
        self.bet_amount = bet_amount

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.grey, emoji="🔁")
    async def play_again_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)

        cmd_attr = getattr(self.cog, self.command_name, None)
        if cmd_attr is None:
            return await interaction.response.send_message("Unable to start the game. Contact the bot developer.", ephemeral=True)

        try:
            if isinstance(cmd_attr, app_commands.Command):
                func = cmd_attr.callback
                bound = func.__get__(self.cog, type(self.cog))
                await bound(interaction, self.bet_amount)
                self.clear_items()
                await self.message.edit(view=self)
                return
        except Exception:
            pass

        if callable(cmd_attr):
            await cmd_attr(interaction, self.bet_amount)
            self.clear_items()
            await self.message.edit(view=self)
            return

        cls_attr = getattr(type(self.cog), self.command_name, None)
        if callable(cls_attr):
            bound = cls_attr.__get__(self.cog, type(self.cog))
            await bound(interaction, self.bet_amount)
            self.clear_items()
            await self.message.edit(view=self)
            return

        return await interaction.response.send_message("Unable to start the game. Unknown error.", ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)


class BlackjackView(View):
    def __init__(self, cog, user_id, bet_amount, dealer_cards, player_cards):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.dealer_cards = dealer_cards
        self.player_cards = player_cards
        self.game_over = False
        self.message = None 

    def calculate_hand_value(self, cards):
        value = 0
        aces = 0
        for card in cards:
            if card[0] in ['J', 'Q', 'K']:
                value += 10
            elif card[0] == 'A':
                aces += 1
                value += 11
            else:
                value += int(card[0]) if card[0] != '10' else 10
        
        while value > 21 and aces:
            value -= 10
            aces -= 1
        
        return value

    def format_cards(self, cards, hide_first=False):
        card_emojis = {
            '♠': '♠️', '♥': '♥️', '♦': '♦️', '♣': '♣️'
        }
        formatted = []
        for i, (rank, suit) in enumerate(cards):
            if hide_first and i == 0:
                formatted.append("`??`")
            else:
                formatted.append(f"`{rank}{card_emojis[suit]}`")
        return " ".join(formatted)

    def create_embed(self, title, description, color):
        embed = discord.Embed(title=title, description=description, color=color)
        
        dealer_value = self.calculate_hand_value(self.dealer_cards)
        player_value = self.calculate_hand_value(self.player_cards)
        
        if self.game_over:
            embed.add_field(name="🎩 Dealer", value=f"{self.format_cards(self.dealer_cards)} (Value: {dealer_value})", inline=False)
        else:
            embed.add_field(name="🎩 Dealer", value=f"{self.format_cards(self.dealer_cards, hide_first=True)} (Value: ?)", inline=False)
        
        embed.add_field(name="🎲 Your Hand", value=f"{self.format_cards(self.player_cards)} (Value: {player_value})", inline=False)
        embed.add_field(name="💰 Bet", value=f"{BEAN_EMOTE} {self.bet_amount:,}", inline=False)
        return embed

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🎯", row=0)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)

        deck = [(rank, suit) for rank in ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'] 
                for suit in ['♠', '♥', '♦', '♣']]
        used_cards = self.dealer_cards + self.player_cards
        available_cards = [card for card in deck if card not in used_cards]
        new_card = random.choice(available_cards)
        self.player_cards.append(new_card)

        player_value = self.calculate_hand_value(self.player_cards)

        if player_value > 21:
            self.game_over = True
            embed = self.create_embed("💥 Bust!", f"You went over 21! You lose {BEAN_EMOTE} {self.bet_amount:,}", discord.Color.red())
            self.clear_items()
            view = PlayAgainView(self.cog, self.user_id, 'blackjack', self.bet_amount)
            await interaction.response.edit_message(embed=embed, view=view)
            view.message = await interaction.original_response()
        elif player_value == 21:
            await self._stand_logic(interaction)
        else:
            embed = self.create_embed("🎲 Blackjack", f"Your turn! Hit or Stand?", discord.Color.blue())
            embed.set_footer(text="You have 30 seconds to make your choice.")
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.green, emoji="✋", row=0)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        
        await self._stand_logic(interaction)

    async def _stand_logic(self, interaction):
        self.game_over = True
        
        deck = [(rank, suit) for rank in ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'] 
                for suit in ['♠', '♥', '♦', '♣']]
        used_cards = self.dealer_cards + self.player_cards
        
        while self.calculate_hand_value(self.dealer_cards) < 17:
            available_cards = [card for card in deck if card not in used_cards]
            new_card = random.choice(available_cards)
            self.dealer_cards.append(new_card)
            used_cards.append(new_card)

        dealer_value = self.calculate_hand_value(self.dealer_cards)
        player_value = self.calculate_hand_value(self.player_cards)

        if dealer_value > 21:
            winnings = self.bet_amount * 2  
            title = "🎉 You Win!"
            description = f"Dealer busted! You win {BEAN_EMOTE} {self.bet_amount:,}"
            color = discord.Color.green()
            beans, tokens = await self.cog.get_balance(self.user_id)
            await self.cog.update_balance(self.user_id, beans + winnings)
        elif player_value > dealer_value:
            winnings = self.bet_amount * 2  
            title = "🎉 You Win!"
            description = f"You beat the dealer! You win {BEAN_EMOTE} {self.bet_amount:,}"
            color = discord.Color.green()
            beans, tokens = await self.cog.get_balance(self.user_id)
            await self.cog.update_balance(self.user_id, beans + winnings)
        elif dealer_value > player_value:
            title = "💔 You Lose!"
            description = f"Dealer wins! You lose {BEAN_EMOTE} {self.bet_amount:,}"
            color = discord.Color.red()
        else:
            title = "🤝 Push!"
            description = f"It's a tie! Your {BEAN_EMOTE} {self.bet_amount:,} bet is returned"
            color = discord.Color.yellow()
            beans, tokens = await self.cog.get_balance(self.user_id)
            await self.cog.update_balance(self.user_id, beans + self.bet_amount)

        embed = self.create_embed(title, description, color)
        self.clear_items()
        view = PlayAgainView(self.cog, self.user_id, 'blackjack', self.bet_amount)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()
    
    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.red, emoji="💵", row=0)
    async def double_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)

        beans, tokens = await self.cog.get_balance(self.user_id)
        if beans < self.bet_amount:
            return await interaction.response.send_message(f"{NO_EMOTE} You don't have enough {BEAN_EMOTE} to double down!", ephemeral=True)

        self.bet_amount *= 2
        await self.cog.update_balance(self.user_id, beans - (self.bet_amount // 2))  

        deck = [(rank, suit) for rank in ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'] 
                for suit in ['♠', '♥', '♦', '♣']]
        used_cards = self.dealer_cards + self.player_cards
        available_cards = [card for card in deck if card not in used_cards]
        new_card = random.choice(available_cards)
        self.player_cards.append(new_card)

        player_value = self.calculate_hand_value(self.player_cards)

        if player_value > 21:
            self.game_over = True
            embed = self.create_embed("💥 Bust!", f"You went over 21! You lose {BEAN_EMOTE} {self.bet_amount:,}", discord.Color.red())
            self.clear_items()
            view = PlayAgainView(self.cog, self.user_id, 'blackjack', self.bet_amount)
            await interaction.response.edit_message(embed=embed, view=view)
            view.message = await interaction.original_response()
        else:
            await self._stand_logic(interaction)

    @discord.ui.button(label="Surrender", style=discord.ButtonStyle.grey, emoji="🏳️", row=1)
    async def surrender_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)

        self.game_over = True
        refund = self.bet_amount // 2
        embed = self.create_embed("🏳️ Surrendered", f"You surrendered! You get back {BEAN_EMOTE} {refund:,} (half of your bet)", discord.Color.orange())
        self.clear_items()
        beans, tokens = await self.cog.get_balance(self.user_id)
        await self.cog.update_balance(self.user_id, beans + refund)
        view = PlayAgainView(self.cog, self.user_id, 'blackjack', self.bet_amount)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(emoji="<:info:1037445870469267638>", style=discord.ButtonStyle.grey, row=1)
    async def blackjack_info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        
        embed = discord.Embed(
            description=(
                "## How to Play Blackjack\n"
                "-# Blackjack is a classic card game where the goal is to have a hand value as close to 21 as possible without going over. Here are the basic rules:\n"
                "### **Card Values:**\n"
                "-# - Number cards (2-10) are worth their face value.\n"
                "-# - Face cards (J, Q, K) are worth 10.\n"
                "-# - Aces can be worth 1 or 11, depending on what benefits your hand more.\n"
                "### **Gameplay:**\n"
                "-# 1. You and the dealer are each dealt two cards. Your cards are both face up, while the dealer has one card face up and one face down.\n"
                "-# 2. You can choose to `'Hit'` to draw another card or `'Stand'` to keep your current hand.\n"
                "-# 3. If your hand exceeds 21, you bust and lose the game.\n"
                "-# 4. Once you stand, the dealer reveals their hidden card and must hit until their hand is at least 17.\n"
                "-# 5. The winner is determined by who has the higher hand value without busting. If both hands are equal, it's a push (tie).\n"
                "### **Special Options:**\n"
                "-# - **Double Down:** You can double your initial bet and receive only one more card before standing.\n"
                "-# - **Surrender:** You can forfeit half your bet and end the game immediately.\n"
                "### **Payouts:**\n"
                "-# If you win, you receive a payout of 1:1 on your bet. However, if you hit blackjack with an Ace and a 10-value card, the payout is 3:2.\n"
            ),
            color=0x2B2D31
        ).set_footer(text="Type \"-blackjack\" to send this to your DMs! Your 30-second countdown timer is ticking! ⚠️")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(emoji="<a:warning:1391215594430402742>", style=discord.ButtonStyle.grey, row=1)
    async def gambling_warning_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        
        embed = discord.Embed(
            title="Our Stance on Gambling",
            description=(
                "It is important to remember that gambling is not a way to make money, real or fake. It is a form of entertainment and should be treated as such. If you or someone you know is struggling with gambling addiction, please seek help.\n\n"
                "Additionally, please remember that the odds are always slightly in favor of the house. The house always wins in the long run.\n\n"
                f"We've implemented daily limits (**{DAILY_GAMBLING_LIMITS['blackjack']}** blackjack games per day) to promote responsible gambling. Use `/balance` to check your usage.\n\n"
                "-# Please gamble responsibly.\n"
            ),
            color=0x2B2D31
        ).set_thumbnail(url="https://images.emojiterra.com/twitter/v13.1/512px/26a0.png")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        if not self.game_over and self.message:
            self.game_over = True
            embed = discord.Embed(title="⏰ Game Timeout!", description=f"You took too long to make a decision! You lose your bet of {BEAN_EMOTE} {self.bet_amount:,}", color=discord.Color.red())
            embed.add_field(name="🎩 Dealer", value=f"{self.format_cards(self.dealer_cards)} (Value: {self.calculate_hand_value(self.dealer_cards)})", inline=False)
            embed.add_field(name="🎲 Your Hand", value=f"{self.format_cards(self.player_cards)} (Value: {self.calculate_hand_value(self.player_cards)})", inline=False)
            self.clear_items()
            try:
                await self.message.edit(embed=embed, view=self)
            except:
                pass 

class CoinflipView(View):
    def __init__(self, cog, user_id, bet_amount):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.game_over = False
        self.message = None 

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.blurple, emoji="🪙", row=0)
    async def heads_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your coinflip!", ephemeral=True)
        
        await self._flip_coin(interaction, "heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.blurple, emoji="🪙", row=0)
    async def tails_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your coinflip!", ephemeral=True)
        
        await self._flip_coin(interaction, "tails")

    @discord.ui.button(emoji="<a:warning:1391215594430402742>", style=discord.ButtonStyle.grey, row=0)
    async def gambling_warning_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your coinflip!", ephemeral=True)
        
        embed = discord.Embed(
            title="Our Stance on Gambling",
            description=(
                "It is important to remember that gambling is not a way to make money, real or fake. It is a form of entertainment and should be treated as such. If you or someone you know is struggling with gambling addiction, please seek help.\n\n"
                f"We've implemented daily limits (**{DAILY_GAMBLING_LIMITS['coinflip']}** coinflips per day) to promote responsible gambling. Use `/balance` to check your usage.\n\n"
                "-# Even though this game is truly a 50/50 chance, please gamble responsibly.\n"
            ),
            color=0x2B2D31
        ).set_thumbnail(url="https://images.emojiterra.com/twitter/v13.1/512px/26a0.png")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _flip_coin(self, interaction, choice):
        self.game_over = True
        result = random.choice(["heads", "tails"])
        
        embed = discord.Embed(title="🪙 Coin Flip Result", color=discord.Color.blue())
        embed.add_field(name="Your Choice", value=choice.capitalize(), inline=True)
        embed.add_field(name="Result", value=result.capitalize(), inline=True)
        embed.add_field(name="Bet Amount", value=f"{BEAN_EMOTE} {self.bet_amount:,}", inline=True)

        if choice == result:
            winnings = self.bet_amount * 2  
            embed.description = f"🎉 **You Win!** You earn {BEAN_EMOTE} {self.bet_amount:,}"
            embed.color = discord.Color.green()
            beans, tokens = await self.cog.get_balance(self.user_id)
            await self.cog.update_balance(self.user_id, beans + winnings)
        else:
            embed.description = f"💔 **You Lose!** You lose {BEAN_EMOTE} {self.bet_amount:,}"
            embed.color = discord.Color.red()

        self.clear_items()
        view = PlayAgainView(self.cog, self.user_id, 'coinflip', self.bet_amount)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def on_timeout(self):
        if not self.game_over and self.message:
            embed = discord.Embed(
                title="⏰ Coinflip Timeout!",
                description=f"You took too long to choose! You lose your bet of {BEAN_EMOTE} {self.bet_amount:,}",
                color=discord.Color.red()
            )
            embed.add_field(name="Bet Amount", value=f"{BEAN_EMOTE} {self.bet_amount:,}", inline=True)
            embed.add_field(name="Result", value="Game canceled due to timeout", inline=True)
            self.clear_items()
            try:
                await self.message.edit(embed=embed, view=self)
            except:
                pass

class BossInspectionView(View):
    def __init__(self, cog, action_keys):
        super().__init__(timeout=120) 
        self.cog = cog
        self.action_keys = action_keys  
        self.participants = {}  
        self.message = None
        self.start_time = time.time()  
        self.ended = False
        
        for i, action_key in enumerate(action_keys):
            action_data = BOSS_INSPECTION_ACTIONS[action_key]
            button = discord.ui.Button(
                label=action_data["label"],
                style=discord.ButtonStyle.primary,
                custom_id=f"boss_action_{i}",
                row=0
            )
            button.callback = self.create_action_callback(action_key)
            self.add_item(button)
    
    def create_action_callback(self, action_key):
        async def action_callback(interaction: discord.Interaction):
            if self.ended:
                return await interaction.response.send_message(
                    "⏰ This inspection has already ended!",
                    ephemeral=True
                )
            
            elapsed_time = time.time() - self.start_time
            if elapsed_time >= 120: 
                self.ended = True
                await self.end_inspection()
                return await interaction.response.send_message(
                    "⏰ Time's up! The inspection has already ended before you acted.",
                    ephemeral=True
                )
            
            user_id = interaction.user.id
            if user_id in self.participants:
                return await interaction.response.send_message(
                    "You've already attempted to impress the boss! Chill out... 😰",
                    ephemeral=True
                )
            
            action_data = BOSS_INSPECTION_ACTIONS[action_key]
            roll = random.random()
            
            if roll < 0.50: 
                result = {
                    "outcome": "success",
                    "beans": 0,
                    "tokens": 0,
                    "message": action_data["success"]
                }
                
                ref = u_mega_boxes(user_id)
                current = ref.get() or 0
                ref.set(current + 1)

                title = f"{YES_EMOTE} Boss Impressed!"
                description = f"{action_data['success']}\n\n-# You earned {MEGA_BOX_EMOTE} **1 Mega Box**! Use </megabox:1486191980349358224> to open it."
                color = discord.Color.green()

            elif roll < 0.75: 
                result = {
                    "outcome": "nothing",
                    "beans": 0,
                    "tokens": 0,
                    "message": action_data["nothing"]
                }
                
                ref = u_star_drops(user_id)
                current = ref.get() or 0
                ref.set(current + 1)
                
                title = "😐 Boss Neutral"
                description = f"{action_data['nothing']}\n\n-# You only got {STAR_DROP_EMOTE} **1 Star Drop**! Use </stardrop:1447676573020065996> to open it."
                color = discord.Color.yellow()

            else: 
                result = {
                    "outcome": "penalty",
                    "beans": 0,
                    "tokens": 0,
                    "message": action_data["fail"]
                }
                
                title = f"{NO_EMOTE} Boss Unimpressed!"
                description = f"{action_data['fail']}\n\n-# You gasped for air as you almost lost your job, but at least you got the air you deserved. You're welcome."
                color = discord.Color.red()

            self.participants[user_id] = {
                "action_key": action_key,
                "result": result
            }

            stamp_cog = interaction.client.get_cog("StampCard")
            if stamp_cog:
                await stamp_cog.update_progress(interaction.user.id, "boss_inspections", 1)
            
            await interaction.response.send_message(embed=discord.Embed(title=title, description=description, color=color), ephemeral=True)
        
        return action_callback
    
    async def end_inspection(self):
        """End the inspection and show results"""
        if not self.message or self.ended:
            return
        
        self.ended = True
        
        embed = discord.Embed(
            title="⏰ Boss Inspection Complete!",
            description="The boss has finished and left the café. Here are the results:",
            color=0xE67E22
        )
        
        if not self.participants:
            embed.add_field(name="No Participants", value="Nobody tried to impress the boss... 😔", inline=False)
        else:
            # Sort participants by outcome
            success_list = []
            nothing_list = []
            penalty_list = []
            
            for user_id, data in self.participants.items():
                user = self.message.guild.get_member(user_id)
                username = user.mention if user else f"<@{user_id}>"
                action_key = data["action_key"]
                action_label = BOSS_INSPECTION_ACTIONS[action_key]["label"]
                result = data["result"]
                
                if result["outcome"] == "success":
                    reward_text = f"{MEGA_BOX_EMOTE} 1 Mega Box"
                    success_list.append(f"{username}: *{action_label}* → {reward_text}")
                elif result["outcome"] == "nothing":
                    nothing_list.append(f"{username}: *{action_label}* → {STAR_DROP_EMOTE} 1 Star Drop")
                else:
                    penalty_list.append(f"{username}: *{action_label}* → Nothing")
            
            if success_list: 
                embed.add_field(name=f"{YES_EMOTE} Boss Impressed", value="\n".join(success_list), inline=False)
            
            if nothing_list: 
                embed.add_field(name="😐 Boss Neutral", value="\n".join(nothing_list), inline=False)
                
            if penalty_list: 
                embed.add_field(name=f"{NO_EMOTE} Boss Unimpressed", value="\n".join(penalty_list), inline=False)
        
        embed.set_footer(text="Better luck next time, employees! 👔")
        
        self.clear_items()
        try:
            await self.message.edit(embed=embed, view=self)
        except:
            pass
    
    async def on_timeout(self):
        await self.end_inspection()

class ToggleApp(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        
    @app_commands.command(
        name="toggle-application", description="Toggle the status of staff application"
    )
    async def ticket_toggle(self, interaction: discord.Interaction) -> None:
        allowed_roles = [814088696591810560, 928451889815781437]
        
        if not(any(role.id in allowed_roles for role in interaction.user.roles)):
            return await interaction.response.send_message(
                content=f"{NO_EMOTE} You must be community leader or manager to use this command.",
                ephemeral=True,
            )
        ref = staff_app()
        status = ref.get()
        staffAppStatus = "Open"
        if status:
            for key, value in status.items():
                staffAppStatus = value["Status"]
                staff_app().child(key).delete()
                break
        
        new = "Open" if staffAppStatus == "Closed" else "Closed"
        data = {interaction.guild.name: {"Status": new}}
        for key, value in data.items():
            ref.push().set(value)
        await interaction.response.send_message(f"**Staff Application Status:** {new}")
        
        
@app_commands.guild_only()
class MegaPass(commands.GroupCog, name="megapass"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.config = {"beans_threshold": 0, "tokens_threshold": 0, "announcement_channel": 0}
        ref = g_mega_pass_config(MAIN_GUILD_ID)
        if saved_config := ref.get():
            self.config.update(saved_config)
        super().__init__()

    async def cog_load(self):
        self.bot.add_view(ReloadView(self))
    
    def _save_config(self):
        ref = g_mega_pass_config(MAIN_GUILD_ID)
        ref.set(self.config)
    
    async def get_pass_data(self) -> Dict:
        ref = g_mega_pass_current(MAIN_GUILD_ID)
        data = ref.get() or {
            "beans_progress": 0,
            "tokens_progress": 0,
            "participants": {},
            "is_full": False,
            "last_reset": time.time(),
            "cycle": 1
        }
        return data
    
    async def save_pass_data(self, data: Dict):
        ref = g_mega_pass_current(MAIN_GUILD_ID)
        ref.set(data)
    
    async def reset_pass(self):
        current_data = await self.get_pass_data()
        data = {
            "beans_progress": 0,
            "tokens_progress": 0,
            "participants": {},
            "is_full": False,
            "last_reset": time.time(),
            "cycle": current_data.get("cycle", 1) + 1
        }
        await self.save_pass_data(data)
        return data
    
    async def add_contribution(self, user_id: int, beans: int = 0, tokens: int = 0):
        """Add a contribution to the pass"""
        if beans <= 0 and tokens <= 0:
            return

        data = await self.get_pass_data()

        beans_threshold = self.config.get("beans_threshold", 0)
        tokens_threshold = self.config.get("tokens_threshold", 0)
        
        participants = data.get("participants", {})
        user_data = participants.get(str(user_id), {"beans": 0, "tokens": 0})
        
        user_data["beans"] += beans
        user_data["tokens"] += tokens
        participants[str(user_id)] = user_data
        data["participants"] = participants
        
        if beans_threshold > 0:
            data["beans_progress"] = min(data.get("beans_progress", 0) + beans, beans_threshold)
        
        if tokens_threshold > 0:
            data["tokens_progress"] = min(data.get("tokens_progress", 0) + tokens, tokens_threshold)
            
        beans_full = beans_threshold == 0 or data["beans_progress"] >= beans_threshold
        tokens_full = tokens_threshold == 0 or data["tokens_progress"] >= tokens_threshold
        
        if beans_threshold == 0 and tokens_threshold == 0:
            is_full = False
        else:
            is_full = beans_full and tokens_full
            
        if is_full and not data.get("is_full", False):
            data["is_full"] = True
            await self.announce_full()
            
        await self.save_pass_data(data)
        return data

    async def announce_full(self):
        """Announce that the Mega Pass is full"""
        channel_id = self.config.get("announcement_channel")
        if not channel_id:
            return
            
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return
            
        embed = discord.Embed(
            title="🎉 Mega Pass Unlocked!",
            description="The community has reached the goal! The Mega Pass has been unlocked.",
            color=0xFFD700
        )
        await channel.send(embed=embed)

    def create_progress_bar(self, progress: int, threshold: int, length: int = 10) -> str:
        """Create a visual progress bar"""
        if threshold <= 0:
            return ""
        filled = int(progress / threshold * length)
        filled = min(filled, length)
        empty = length - filled
        return f"[{'█' * filled}{'░' * empty}]"

    async def generate_mega_pass_image(self, guild, data, beans_threshold, tokens_threshold):
        WIDTH, HEIGHT = 900, 400
        BG = (44, 47, 51)
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
        draw = ImageDraw.Draw(img)

        def try_load_font(preferred_names, size):
            for name in preferred_names:
                try:
                    return ImageFont.truetype(name, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        bold_candidates = [
            "arialbd.ttf", "Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        ]
        regular_candidates = [
            "arial.ttf", "Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]

        title_font = try_load_font(bold_candidates, 42)
        subtitle_font = try_load_font(regular_candidates, 24)
        text_font = try_load_font(regular_candidates, 20)
        small_font = try_load_font(regular_candidates, 16)

        def draw_rounded_bar(draw, x, y, w, h, progress, color, bg_color=(30, 30, 30)):
            draw.rounded_rectangle([x, y, x + w, y + h], radius=h//2, fill=bg_color)
            if progress > 0:
                pw = int(w * progress)
                pw = max(pw, h) 
                pw = min(pw, w)
                draw.rounded_rectangle([x, y, x + pw, y + h], radius=h//2, fill=color)

        y_offset = 80
        bar_height = 30
        bar_width = WIDTH - 100
        
        if beans_threshold > 0:
            progress = data.get("beans_progress", 0)
            percent = min((progress / beans_threshold), 1.0)
            
            draw.text((50, y_offset), "Beans Progress", font=subtitle_font, fill=(255, 255, 255), anchor="ls")
            draw.text((WIDTH-50, y_offset), f"{progress:,}/{beans_threshold:,} ({percent*100:.1f}%)", font=subtitle_font, fill=(255, 255, 255), anchor="rs")
            
            y_offset += 15
            draw_rounded_bar(draw, 50, y_offset, bar_width, bar_height, percent, (210, 180, 140))
            y_offset += 80

        if tokens_threshold > 0:
            progress = data.get("tokens_progress", 0)
            percent = min((progress / tokens_threshold), 1.0)
            
            draw.text((50, y_offset), "Tokens Progress", font=subtitle_font, fill=(255, 255, 255), anchor="ls")
            draw.text((WIDTH-50, y_offset), f"{progress:,}/{tokens_threshold:,} ({percent*100:.1f}%)", font=subtitle_font, fill=(255, 255, 255), anchor="rs")
            
            y_offset += 15
            draw_rounded_bar(draw, 50, y_offset, bar_width, bar_height, percent, (255, 255, 153))
            y_offset += 80

        participants = data.get("participants", {})
        if participants:
            draw.text((WIDTH//2, y_offset), "Top Contributors", font=subtitle_font, fill=(255, 255, 255), anchor="mm")
            y_offset += 30
            
            sorted_beans = sorted(participants.items(), key=lambda x: x[1].get("beans", 0), reverse=True)
            sorted_tokens = sorted(participants.items(), key=lambda x: x[1].get("tokens", 0), reverse=True)
            
            top5_bean_ids = {u[0] for u in sorted_beans[:5] if u[1].get("beans", 0) > 0}
            top5_token_ids = {u[0] for u in sorted_tokens[:5] if u[1].get("tokens", 0) > 0}
            rainbow_ids = top5_bean_ids.intersection(top5_token_ids)
            
            final_list = []
            b_idx, t_idx = 0, 0
            while len(final_list) < 10 and (b_idx < len(sorted_beans) or t_idx < len(sorted_tokens)):
                if b_idx < len(sorted_beans):
                    uid = sorted_beans[b_idx][0]
                    if uid not in [u[0] for u in final_list]:
                        final_list.append((uid, "bean"))
                    b_idx += 1
                
                if len(final_list) >= 10: break
                
                if t_idx < len(sorted_tokens):
                    uid = sorted_tokens[t_idx][0]
                    if participants[uid].get("tokens", 0) > 0:
                        if uid not in [u[0] for u in final_list]:
                            final_list.append((uid, "token"))
                    t_idx += 1

            avatar_size = 64
            gap = 20
            total_width = len(final_list) * avatar_size + (len(final_list) - 1) * gap
            start_x = (WIDTH - total_width) // 2
            
            async with aiohttp.ClientSession() as session:
                for i, (uid, type_) in enumerate(final_list):
                    try:
                        member = guild.get_member(int(uid))
                        if not member:
                            try:
                                member = await guild.fetch_member(int(uid))
                            except:
                                pass
                        
                        if member:
                            avatar_url = str(member.display_avatar.url)
                            async with session.get(avatar_url) as resp:
                                if resp.status == 200:
                                    avatar_bytes = await resp.read()
                                    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((avatar_size, avatar_size))
                                    
                                    mask = Image.new("L", (avatar_size, avatar_size), 0)
                                    mask_draw = ImageDraw.Draw(mask)
                                    mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                                    
                                    x = start_x + i * (avatar_size + gap)
                                    img.paste(avatar, (x, y_offset), mask)
                                    
                                    if uid in rainbow_ids:
                                        colors = [(255, 0, 0), (255, 165, 0), (255, 255, 0), (0, 128, 0), (0, 0, 255), (75, 0, 130), (238, 130, 238)]
                                        start_angle = 0
                                        step = 360 / len(colors)
                                        for color in colors:
                                            draw.arc([x, y_offset, x + avatar_size, y_offset + avatar_size], start=start_angle, end=start_angle + step + 2, fill=color, width=4)
                                            start_angle += step
                                    else:
                                        border_color = (210, 180, 140) if type_ == "bean" else (255, 255, 153)
                                        draw.ellipse((x, y_offset, x + avatar_size, y_offset + avatar_size), outline=border_color, width=3)
                    except Exception as e:
                        print(f"Error drawing avatar for {uid}: {e}")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    @app_commands.command(name="status", description="Check the current Mega Pass status")
    async def status(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message("This command can only be used in Brawl Cafe.", ephemeral=True)
        await interaction.response.defer()
        await self.send_status(interaction)

    async def send_status(self, interaction: discord.Interaction, is_update=False):
        data = await self.get_pass_data()

        participants = data.get("participants", {})
        
        embed = discord.Embed(
            title="🧧 Earn Beans and Tokens to fill the Mega Pass!",
            description=f"Once full, a server-wide raffle for a free Brawl Pass Plus / Diamond Pass will be held. Only contributors who contributed {BEAN_EMOTE} `20,000` or {TOKEN_EMOTE} `100` will be eligible to join the raffle, with an entry cost of 50 tokens. **So far, `{len(participants)}` unique contributors have participated!**",
            color=0xFFB6C1
        )
        
        if data.get("is_full", False):
            embed.title = "🧧 Mega Pass has been unlocked!"
            embed.description = "You guys crushed it! Now, wait for the owners to announce the raffle."
            embed.color = 0xFFD700
        
        beans_threshold = self.config.get("beans_threshold", 0)
        tokens_threshold = self.config.get("tokens_threshold", 0)
        
        # if beans_threshold > 0:
        #     progress = data.get("beans_progress", 0)
        #     bar = self.create_progress_bar(progress, beans_threshold)
        #     percent = (progress / beans_threshold) * 100
        #     embed.add_field(
        #         name="Beans Progress",
        #         value=f"{bar} {progress}/{beans_threshold} ({percent:.1f}%)",
        #         inline=False
        #     )
            
        # if tokens_threshold > 0:
        #     progress = data.get("tokens_progress", 0)
        #     bar = self.create_progress_bar(progress, tokens_threshold)
        #     percent = (progress / tokens_threshold) * 100
        #     embed.add_field(
        #         name="Tokens Progress",
        #         value=f"{bar} {progress}/{tokens_threshold} ({percent:.1f}%)",
        #         inline=False
        #     )
            
        if beans_threshold == 0 and tokens_threshold == 0:
            embed.description = "Mega Pass is currently not configured."

        image_buffer = await self.generate_mega_pass_image(interaction.guild, data, beans_threshold, tokens_threshold)
        image_channel = interaction.client.get_channel(1026968305208131645)
        if image_channel:
            file = discord.File(image_buffer, filename="megapass.png")
            msg = await image_channel.send(file=file)
            image_url = msg.attachments[0].url
            embed.set_image(url=image_url)
        
        if participants:
            sorted_beans = sorted(participants.items(), key=lambda x: x[1].get("beans", 0), reverse=True)[:5]
            beans_text = ""
            rank = 1
            for uid, pdata in sorted_beans:
                if pdata.get("beans", 0) > 0:
                    name = f"<@{uid}>"
                    beans_text += f"-# {rank}. {name}: {BEAN_EMOTE} `{pdata['beans']}`\n"
                    rank += 1
            
            if beans_text:
                embed.add_field(name="Top 5 Bean Earners", value=beans_text, inline=True)

            sorted_tokens = sorted(participants.items(), key=lambda x: x[1].get("tokens", 0), reverse=True)[:5]
            tokens_text = ""
            rank = 1
            for uid, pdata in sorted_tokens:
                if pdata.get("tokens", 0) > 0:
                    name = f"<@{uid}>"
                    tokens_text += f"-# {rank}. {name}: {TOKEN_EMOTE} `{pdata['tokens']}`\n"
                    rank += 1
            
            if tokens_text:
                embed.add_field(name="Top 5 Token Earners", value=tokens_text, inline=True)

        last_reset = data.get("last_reset", time.time())
        embed.set_footer(text=f"Cycle #{data.get('cycle', 1)} | Last reset: {datetime.fromtimestamp(last_reset).strftime('%Y-%m-%d %H:%M')}")
        
        view = ReloadView(self)
        if is_update:
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="config", description="Configure Mega Pass settings (admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def config(
        self, 
        interaction: discord.Interaction,
        beans_threshold: Optional[int] = None,
        tokens_threshold: Optional[int] = None,
        announcement_channel: Optional[discord.TextChannel] = None
    ):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message("This command can only be used in Brawl Cafe.", ephemeral=True)
        if beans_threshold is not None:
            self.config["beans_threshold"] = beans_threshold
        if tokens_threshold is not None:
            self.config["tokens_threshold"] = tokens_threshold
        if announcement_channel is not None:
            self.config["announcement_channel"] = announcement_channel.id
            
        self._save_config()
        
        embed = discord.Embed(title="Mega Pass Configuration", color=0x00FF00)
        embed.add_field(name="Beans Threshold", value=self.config["beans_threshold"])
        embed.add_field(name="Tokens Threshold", value=self.config["tokens_threshold"])
        channel = self.bot.get_channel(self.config["announcement_channel"])
        embed.add_field(name="Announcement Channel", value=channel.mention if channel else "None")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="reset", description="Reset the Mega Pass (admin only)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message("This command can only be used in Brawl Cafe.", ephemeral=True)
        await self.reset_pass()
        await interaction.response.send_message("Mega Pass has been reset!", ephemeral=True)

class ReloadView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(style=discord.ButtonStyle.grey, custom_id="megapass_reload", emoji="<:refresh:1048779043287351408>", label="Reload")
    async def reload(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.send_status(interaction, is_update=True)

class StarDropView(discord.ui.View):
    active_sessions = {}
    
    def __init__(self, user: discord.User, total_unopened_count: int, pending_drop: dict):
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
            pending_ref.update({
                "current_rarity": self.current_rarity,
                "upgrades_used": self.current_upgrades
            })
    
    def _deactivate_session(self):
        if self.user_id in StarDropView.active_sessions:
            if StarDropView.active_sessions[self.user_id] == self:
                del StarDropView.active_sessions[self.user_id]
    
    def create_embed(self, resume=False):
        if self.is_unlocked:
            return self.reward_embed
        
        desc = '<a:warning:1391215594430402742> Resuming your unfinished Star Drop!' if resume else 'Click `Upgrade` to try improving your drop\'s rarity!\nYou must use all 4 upgrades before unlocking.'
        embed = discord.Embed(
            title=f"{STAR_DROP_EMOTE} Star Drop",
            description=f"{desc}",
            color=COLORS.get(self.current_rarity, 0x49D532)
        )
        
        embed.set_image(url=IMAGES.get(self.current_rarity, ""))
        embed.add_field(name="Current Rarity", value=self.current_rarity.replace('_', ' ').title(), inline=True)
        embed.add_field(name="Upgrades Used", value=f"{self.current_upgrades}/{self.max_upgrades}", inline=True)
        embed.add_field(name="Remaining Drops", value=f"{self.total_unopened} more", inline=True)
        embed.set_footer(text="💡 Your progress is automatically saved!")
        return embed
    
    @discord.ui.button(label="Upgrade", style=discord.ButtonStyle.primary, emoji="<:Upgrade:1447684501735211239>")
    async def upgrade_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id != self.user.id:
            await interaction.followup.send("This is not your Star Drop!", ephemeral=True)
            return
        
        if self.current_upgrades >= self.max_upgrades:
            await interaction.followup.send("You've used all upgrades!", ephemeral=True)
            return
        
        if self.is_unlocked:
            await interaction.followup.send("This drop is already unlocked!", ephemeral=True)
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
    
    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.success, emoji="<a:unlocked:1390755948926079037>")
    async def unlock_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id != self.user.id:
            await interaction.followup.send("This is not your Star Drop!", ephemeral=True)
            return
        
        if self.current_upgrades < self.max_upgrades:
            await interaction.followup.send(f"You must use all {self.max_upgrades} upgrades first!", ephemeral=True)
            return
        
        if self.is_unlocked:
            await interaction.followup.send("This drop is already unlocked!", ephemeral=True)
            return
        
        if self.rewards_claimed:
            await interaction.followup.send(f"{NO_EMOTE} Rewards have already been claimed for this drop!", ephemeral=True)
            return
        
        self.rewards_claimed = True
        reward_description = await self._process_reward(interaction)
        
        rarity = self.final_rarity
        rate = STAR_DROP_RATES["rarity_rates"][rarity] * 100
        
        embed = discord.Embed(
            title=f"{STAR_DROP_EMOTE} Star Drop - {rarity.replace('_', ' ').title()}",
            description=f"You received: {reward_description}",
            color=COLORS.get(rarity, 0x49D532)
        )
        
        embed.set_image(url=IMAGES.get(rarity, ""))
        embed.set_footer(text=f"{rate:.1f}% chance of getting this rarity")
        
        if self.total_unopened > 0:
            embed.add_field(name="Next Drop", value=f"You have {self.total_unopened} more Star Drop{'s' if self.total_unopened > 1 else ''}!", inline=False)
        
        self.reward_embed = embed
        self.is_unlocked = True
        await self._save_pending_state()
        if self.total_unopened <= 0:
            self._deactivate_session()
        self._update_buttons()
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="Open Next", style=discord.ButtonStyle.grey, emoji=STAR_DROP_EMOTE, disabled=True)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your Star Drop!", ephemeral=True)
            return
        
        if not self.is_unlocked:
            await interaction.response.send_message("Unlock the current drop first!", ephemeral=True)
            return
        
        if self.total_unopened <= 0:
            await interaction.response.send_message("No more drops to open!", ephemeral=True)
            return
        
        inventory_ref = u_star_drops(self.user_id)
        current_count = inventory_ref.get() or 0
        
        if current_count <= 0:
            await interaction.response.send_message(f"{NO_EMOTE} No more star drops available!", ephemeral=True)
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
            "created_at": int(time.time())
        }
        
        updates = {
            u_star_drops_pending(self.user_id).path: new_pending,
            u_star_drops(self.user_id).path: current_count - 1
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
            amount = selected_drop.get("amount") or random.randint(*selected_drop["range"])
            if currency_cog:
                current_beans, _ = await currency_cog.get_balance(int(self.user_id))
                await currency_cog.update_balance(int(self.user_id), beans=current_beans + amount)
            reward_text = f"{BEAN_EMOTE} `{amount:,}` Beans"
        elif reward_type == "tokens":
            amount = selected_drop.get("amount") or random.randint(*selected_drop["range"])
            if currency_cog:
                _, current_tokens = await currency_cog.get_balance(int(self.user_id))
                await currency_cog.update_balance(int(self.user_id), tokens=current_tokens + amount)
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
                k for k, v in STORE_ITEMS.items() 
                if k != "star_drop" and v.get("duration", 0) > 0
            ]
            
            if available_items:
                user_effects = sync_shop_effects(self.user_id, operation='get') or {}
                
                not_owned = []
                current_time = time.time()
                for item_id in available_items:
                    if item_id not in user_effects or not user_effects[item_id].get("active") or user_effects[item_id].get("expires_at", 0) < current_time:
                        not_owned.append(item_id)
                
                if not_owned:
                    item_id = random.choice(not_owned)
                    item_data = STORE_ITEMS[item_id]
                    
                    await item_data["effect"](int(self.user_id))
                    
                    if item_id == "freeze_thermometer":
                        freeze_data_ref = u_shop_effects(int(self.user_id), "freeze_thermometer")
                        freeze_data = freeze_data_ref.get()
                        if freeze_data:
                            sync_shop_effects(int(self.user_id), "freeze_thermometer", 'set', freeze_data, interaction.guild.id)
                    
                    reward_text += f"\n+ {EFFECT_EMOTE} **Bonus Effect Item:** `{item_data['name']}` *(Expires <t:{int(time.time()) + item_data.get('duration', 0)}:R>)*\n-# {REPLY_EMOTE} **Description:** {item_data.get('description', '')}"
                else:
                    if currency_cog:
                        _, current_tokens = await currency_cog.get_balance(int(self.user_id))
                        await currency_cog.update_balance(int(self.user_id), tokens=current_tokens + 5)
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
            disabled=True
        )
        self.add_item(timeout_button)
        if self.message:
            try:
                await self.message.edit(view=self)
            except:
                pass


class MegaBoxView(discord.ui.View):
    active_sessions = {}
    
    def __init__(self, user: discord.User, total_unopened_count: int, pending_box: dict):
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
            pending_ref.update({
                "items_remaining": self.items_remaining,
                "rewards": self.rewards,
                "show_summary": self.show_summary,
                "last_drop": self.last_drop,
                "used_effect_items": list(self.used_effect_items)  
            })
            
    def _deactivate_session(self):
        if self.user_id in MegaBoxView.active_sessions:
            if MegaBoxView.active_sessions[self.user_id] == self:
                del MegaBoxView.active_sessions[self.user_id]
                
    def create_embed(self, resume=False):
        desc = '<a:warning:1391215594430402742> Resuming your unfinished Mega Box!\n' if resume else ''
        embed = discord.Embed(
            color=0x1E90FF
        )
        
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
                embed.add_field(name="Next Box", value=f"You have {self.total_unopened} more Mega Box{'es' if self.total_unopened > 1 else ''}!", inline=False)
        
        embed.set_footer(text="💡 Your progress is automatically saved!")
        return embed

    @discord.ui.button(label="Tap", style=discord.ButtonStyle.primary, emoji="<:v_hand:1486225684928921763>")
    async def tap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if interaction.user.id != self.user.id:
            await interaction.followup.send("This is not your Mega Box!", ephemeral=True)
            return
            
        if self.items_remaining <= 0:
            if not self.show_summary:
                self.show_summary = True
                await self._save_pending_state()
                if self.total_unopened <= 0:
                    self._deactivate_session()
                self._update_buttons()
                await interaction.edit_original_response(embed=self.create_embed(), view=self)
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

    @discord.ui.button(label="Open Next", style=discord.ButtonStyle.success, emoji=MEGA_BOX_EMOTE, disabled=True)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your Mega Box!", ephemeral=True)
            return
            
        if not self.show_summary:
            await interaction.response.send_message("Finish opening this box first!", ephemeral=True)
            return
            
        inventory_ref = u_mega_boxes(self.user_id)
        current_count = inventory_ref.get() or 0
        
        if current_count <= 0:
            await interaction.response.send_message(f"{NO_EMOTE} No more Mega Boxes available!", ephemeral=True)
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
            "created_at": int(time.time())
        }
        
        updates = {
            u_mega_boxes_pending(self.user_id).path: new_pending,
            u_mega_boxes(self.user_id).path: current_count - 1
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
            u_mega_boxes(self.user_id).path: current_count - 1
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
        if roll < 0.795: return 5
        if roll < 0.9675: return 6
        if roll < 0.9825: return 7
        if roll < 0.9925: return 8
        if roll < 0.9975: return 9
        return 10

    async def _generate_and_apply_reward(self, interaction: discord.Interaction, item_index: int) -> dict:
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
                amount = selected_drop.get("amount") or random.randint(*selected_drop["range"])
                if currency_cog:
                    current_beans, _ = await currency_cog.get_balance(int(self.user_id))
                    await currency_cog.update_balance(int(self.user_id), beans=current_beans + amount)
                return {
                    "title": f"{(rarity.replace('_', ' ').title())} Item",
                    "desc": f"{BEAN_EMOTE} `{amount:,}` Beans",
                    "summary": f"- {BEAN_EMOTE} `{amount:,}` Beans ({rarity.replace('_', ' ').title()})"
                }
            elif selected_drop["type"] == "tokens":
                amount = selected_drop.get("amount") or random.randint(*selected_drop["range"])
                if currency_cog:
                    _, current_tokens = await currency_cog.get_balance(int(self.user_id))
                    await currency_cog.update_balance(int(self.user_id), tokens=current_tokens + amount)
                return {
                    "title": f"{(rarity.replace('_', ' ').title())} Item",
                    "desc": f"{TOKEN_EMOTE} `{amount:,}` Tokens",
                    "summary": f"- {TOKEN_EMOTE} `{amount:,}` Tokens ({rarity.replace('_', ' ').title()})"
                }
            return {"title": "Unknown", "desc": "Unknown", "summary": "Unknown Reward"}
        else:
            roll = random.random()
            if roll < 0.40: 
                if currency_cog:
                    _, current_tokens = await currency_cog.get_balance(int(self.user_id))
                    await currency_cog.update_balance(int(self.user_id), tokens=current_tokens + 5)
                return {
                    "title": "Exotic Item <:exclaim:1486161482956804176>",
                    "desc": f"{TOKEN_EMOTE} `5` Tokens",
                    "summary": f"- {TOKEN_EMOTE} `5` Tokens"
                }
            elif roll < 0.50: 
                if currency_cog:
                    _, current_tokens = await currency_cog.get_balance(int(self.user_id))
                    await currency_cog.update_balance(int(self.user_id), tokens=current_tokens + 10)
                return {
                    "title": "Ultra Exotic Item <:exclaim:1486161482956804176>",
                    "desc": f"{TOKEN_EMOTE} `10` Tokens",
                    "summary": f"- {TOKEN_EMOTE} `10` Tokens"
                }
            else:
                available_items = [
                    k for k, v in STORE_ITEMS.items() 
                    if k not in ["star_drop", "star_drop_10", "mega_box", "mega_box_10"] and v.get("duration", 0) > 0
                ]
                
                if available_items:
                    user_effects = sync_shop_effects(self.user_id, operation='get') or {}
                    current_time = time.time()
                    
                    not_owned = []
                    for item_id in available_items:
                        if item_id not in user_effects or not user_effects[item_id].get("active") or user_effects[item_id].get("expires_at", 0) < current_time:
                            not_owned.append(item_id)
                    
                    available_not_owned = [item for item in not_owned if item not in self.used_effect_items]
                    
                    if available_not_owned:
                        item_id = random.choice(available_not_owned)
                        self.used_effect_items.add(item_id)  
                        item_data = STORE_ITEMS[item_id]
                        await item_data["effect"](int(self.user_id))
                        
                        if item_id == "freeze_thermometer":
                            freeze_data_ref = u_shop_effects(int(self.user_id), "freeze_thermometer")
                            freeze_data = freeze_data_ref.get()
                            if freeze_data:
                                sync_shop_effects(int(self.user_id), "freeze_thermometer", 'set', freeze_data, interaction.guild.id)
                        
                        return {
                            "title": "Bonus Effect Item <:exclaim:1486161482956804176>",
                            "desc": f"{EFFECT_EMOTE} `{item_data['name']}`",
                            "summary": f"- {EFFECT_EMOTE} Effect: `{item_data['name']}`" 
                        }
                    else:
                        if currency_cog:
                            _, current_tokens = await currency_cog.get_balance(int(self.user_id))
                            await currency_cog.update_balance(int(self.user_id), tokens=current_tokens + 5)
                        return {
                            "title": "Bonus Effect Item <:exclaim:1486161482956804176>",
                            "desc": f"{TOKEN_EMOTE} `5` Tokens *(Fallback)*",
                            "summary": f"- {TOKEN_EMOTE} `5` Tokens *(Fallback reward for an effect item)*"
                        }
                
                if currency_cog:
                    _, current_tokens = await currency_cog.get_balance(int(self.user_id))
                    await currency_cog.update_balance(int(self.user_id), tokens=current_tokens + 5)
                return {
                    "title": "Bonus Effect Item <:exclaim:1486161482956804176>",
                    "desc": f"{TOKEN_EMOTE} `5` Tokens",
                    "summary": f"- {TOKEN_EMOTE} `5` Tokens *(Fallback)*"
                }

    async def on_timeout(self):
        self._deactivate_session()
        self.clear_items()
        timeout_button = discord.ui.Button(
            label="Session Expired",
            style=discord.ButtonStyle.secondary,
            emoji="<a:clock:1382887924273774754>",
            disabled=True
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

    @app_commands.command(name="stardrop", description="Open a star drop and get random rewards")
    async def stardrop(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message("This command can only be used in Brawl Cafe.", ephemeral=True)

        user_id = str(interaction.user.id)
        
        if user_id in StarDropView.active_sessions:
            await interaction.response.send_message(f"{NO_EMOTE} **You already have an active Star Drop session!**\nPlease finish your current drop or wait for it to timeout.", ephemeral=True)
            return
        
        unopened_ref = u_star_drops(user_id)
        pending_ref = u_star_drops_pending(user_id)
        unopened_count = unopened_ref.get() or 0
        pending_drop = pending_ref.get()
        
        if unopened_count <= 0 and not pending_drop:
            await interaction.response.send_message(f"{NO_EMOTE} You don't have any unopened Star Drops! Buy them in the shop using </buy:1393376242501157010>.", ephemeral=True)
            return
        
        if pending_drop:
            if not all(k in pending_drop for k in ["final_rarity", "current_rarity", "upgrades_used"]):
                u_star_drops_pending(int(user_id)).delete()
                pending_drop = None
            else:
                view = StarDropView(interaction.user, unopened_count, pending_drop)
                await interaction.response.send_message(embed=view.create_embed(resume=True), view=view)
                view.message = await interaction.original_response()
                return
        
        if unopened_count <= 0:
            await interaction.response.send_message("You don't have any unopened Star Drops!", ephemeral=True)
            return
        
        final_rarity = self._roll_rarity()
        if interaction.user.id == 692254240290242601:
            final_rarity = random.choice(['mythic', 'legendary', 'ultra'])

        pending_drop = {
            "final_rarity": final_rarity,
            "current_rarity": "rare",
            "upgrades_used": 0,
            "created_at": int(time.time())
        }
        
        updates = {
            u_star_drops_pending(user_id).path: pending_drop,
            u_star_drops(user_id).path: unopened_count - 1
        }
        db.reference().update(updates)
        
        view = StarDropView(interaction.user, unopened_count - 1, pending_drop)
        print("⚠️⚠️⚠️⚠️⚠️ New Star Drop Session Created ⚠️⚠️⚠️⚠️⚠️")
        await interaction.response.send_message(embed=view.create_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="megabox", description="Open a mega box and get multiple rewards")
    async def megabox(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message("This command can only be used in Brawl Cafe.", ephemeral=True)

        user_id = str(interaction.user.id)
        
        if user_id in MegaBoxView.active_sessions:
            await interaction.response.send_message(f"{NO_EMOTE} **You already have an active Mega Box session!**\nPlease finish your current box or wait for it to timeout.", ephemeral=True)
            return
            
        unopened_ref = u_mega_boxes(user_id)
        pending_ref = u_mega_boxes_pending(user_id)
        unopened_count = unopened_ref.get() or 0
        pending_box = pending_ref.get()
        
        if unopened_count <= 0 and not pending_box:
            await interaction.response.send_message(f"{NO_EMOTE} You don't have any unopened Mega Boxes! Buy them in the shop using </buy:1393376242501157010>.", ephemeral=True)
            return

        if pending_box:
            if not all(k in pending_box for k in ["total_items", "items_remaining"]):
                u_mega_boxes_pending(int(user_id)).delete()
                pending_box = None
            else:
                view = MegaBoxView(interaction.user, unopened_count, pending_box)
                await interaction.response.send_message(embed=view.create_embed(resume=True), view=view)
                view.message = await interaction.original_response()
                return

        if unopened_count <= 0:
            await interaction.response.send_message("You don't have any unopened Mega Boxes!", ephemeral=True)
            return

        roll = random.random()
        total_items = 5
        if roll < 0.795: total_items = 5
        elif roll < 0.9675: total_items = 6
        elif roll < 0.9825: total_items = 7
        elif roll < 0.9925: total_items = 8
        elif roll < 0.9975: total_items = 9
        else: total_items = 10

        if interaction.user.id == 692254240290242601:
            total_items = random.randint(7, 10)

        pending_box = {
            "total_items": total_items,
            "items_remaining": total_items,
            "rewards": [],
            "show_summary": False,
            "last_drop": None,
            "created_at": int(time.time())
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
                "created_at": pending_box["created_at"]
            },
            u_mega_boxes(user_id).path: unopened_count - 1
        }
        db.reference().update(updates)

        view._update_buttons()
        print("⚠️⚠️⚠️⚠️⚠️ New Mega Box Session Created ⚠️⚠️⚠️⚠️⚠️")
        await interaction.response.send_message(embed=view.create_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="rates", description="Show gacha rewards rarity rates")
    async def rates(self, interaction: discord.Interaction):
        sd_embed = discord.Embed(title=f"{STAR_DROP_EMOTE} Star Drop Rates", description="Chances of getting each rarity tier and their possible rewards:", color=0x00FF00)
        for rarity, rate in STAR_DROP_RATES["rarity_rates"].items():
            percentage = rate * 100
            drops = STAR_DROP_RATES["drops"].get(rarity, [])
            total_weight = sum(d.get("weight", 1) for d in drops)
            rewards = []
            
            for drop in drops:
                weight = drop.get("weight", 1)
                prob = (weight / total_weight) * 100
                prob_str = f"**({prob:.0f}%)**" if prob.is_integer() else f"**({prob:.1f}%)**"
                
                if drop["type"] == "beans":
                    if "range" in drop:
                        rewards.append(f"-# - {BEAN_EMOTE} `{drop['range'][0]:,}-{drop['range'][1]:,}` {prob_str}")
                    else:
                        rewards.append(f"-# - {BEAN_EMOTE} `{drop['amount']:,}` {prob_str}")
                elif drop["type"] == "tokens":
                    if "range" in drop:
                        rewards.append(f"-# - {TOKEN_EMOTE} `{drop['range'][0]:,}-{drop['range'][1]:,}` {prob_str}")
                    else:
                        rewards.append(f"-# - {TOKEN_EMOTE} `{drop['amount']:,}` {prob_str}")
            
            if rarity == "mythic":
                rewards.append(f"-# - {EFFECT_EMOTE} **+10%** chance for a random effect item")
            elif rarity == "legendary":
                rewards.append(f"-# - {EFFECT_EMOTE} **+50%** chance for a random effect item")
            elif rarity == "ultra":
                rewards.append(f"-# - {EFFECT_EMOTE} **Guaranteed** random effect item")
            rewards_text = "\n".join(rewards) if rewards else "No rewards defined"
            sd_embed.add_field(name=f"{rarity.replace('_', ' ').title()} ({percentage:.1f}%)", value=rewards_text, inline=True)
            
        mb_embed = discord.Embed(title=f"{MEGA_BOX_EMOTE} Mega Box Rates", description="Chances of item counts and rewards for Mega Boxes:", color=0xFF0000)
        mb_embed.add_field(name="Item Count Chances", value="-# - **5 Items:** 79.5%\n-# - **6 Items:** 17.25%\n-# - **7 Items:** 1.5%\n-# - **8 Items:** 1.0%\n-# - **9 Items:** 0.5%\n-# - **10 Items:** 0.25%", inline=False)
        mb_embed.add_field(name="First 5 Items", value="-# - **60%** Rare Star Drop Equivalent\n-# - **40%** Super Rare Star Drop Equivalent", inline=False)
        mb_embed.add_field(name="6th - 10th Items", value=f"-# - **40%** {TOKEN_EMOTE} `5` Tokens (Exotic) \n-# - **10%** {TOKEN_EMOTE} `10` Tokens (Ultra Exotic) \n-# - **50%** {EFFECT_EMOTE} Random Effect Item", inline=False)

        await interaction.response.send_message(embeds=[sd_embed, mb_embed])


async def setup(bot):
    await bot.add_cog(CurrencySystem(bot))
    await bot.add_cog(ToggleApp(bot))
    await bot.add_cog(MegaPass(bot))
    await bot.add_cog(Gacha(bot))

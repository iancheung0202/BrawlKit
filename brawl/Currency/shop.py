import asyncio
import io
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency import wallet
from brawl.Currency.bag import UseNow, held, keep, note
from brawl.Currency.balancecard import draw_header
from brawl.Currency.card import BACKGROUND
from brawl.Currency.card import icon as picture
from brawl.Currency.card import item_icon, plain, render
from brawl.Currency.config import ITEM_STATIONS, SHOP
from brawl.Currency.db import (
    g_shops,
    sync_sell_alarm,
    u_balance,
    u_daily_chat_earnings,
    u_mega_boxes,
    u_mega_boxes_purchases,
    u_pin_message,
    u_shop_cooldowns,
    u_star_drops,
    u_star_drops_purchases,
)
from brawl.Currency.helper import (
    BEAN_EMOTE,
    MAIN_GUILD_ID,
    NO_EMOTE,
    PERFECT_BREW_CHANCE,
    REPLY_EMOTE,
    ROAST_TYPES,
    STORE_ITEMS,
    TOKEN_EMOTE,
    ULTRA_TIER_ROLE_ID,
    get_current_date_key,
    get_next_day_timestamp,
)
from brawl.Currency.ladder import level_of, lock_line, locked, unlocked
from brawl.Currency.panel import notice, reframed
from brawl.Currency.quests import report, update_quest
from brawl.Currency.shopcard import (
    CLAIM,
    FILTERS,
    REWARD_ICONS,
    ROLE,
    SORTS,
    SUPERCELL,
    after,
    buyable,
    draw_purchase,
    listing,
    reward_icon,
    row,
)
from brawl.Currency.stampcard import stamps

LOADING = "<a:loading_circle:1393439258886537352>"
# The shop's sign on its header: color, scene and icon.
SIGN = ((255, 140, 40), BACKGROUND, "kit/icon_shop")
EMOTES = {}


class ShopSelect(discord.ui.Select):
    def __init__(self, field, options, chosen):
        self.field = field
        super().__init__(
            custom_id=f"{field}selection",
            options=[
                discord.SelectOption(label=option, default=option == chosen)
                for option in options
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        setattr(self.view, self.field, self.values[0])
        self.view.rows = g_shops(interaction.guild.id).get() or []
        self.view.page = 0
        await self.view.turn(interaction)


async def stock_emotes(bot):
    """An emoji for every shop picture; one the bot does not have yet is uploaded."""
    have = {emoji.name: emoji for emoji in await bot.fetch_application_emojis()}
    for icon in (*map(item_icon, STORE_ITEMS), *REWARD_ICONS):
        name = f"Shop_{icon.split('/')[-1]}"
        if name not in have:
            image = io.BytesIO()
            picture(icon, 64).save(image, "PNG")
            have[name] = await bot.create_application_emoji(
                name=name, image=image.getvalue()
            )
        EMOTES[icon] = str(have[name])


class ShopView(discord.ui.LayoutView):
    """The shop: the member's wallet, a row with a price button for each item,
    then the page, sort and filter controls. Admins also get the reward editor."""

    def __init__(self, member, guild, rows, wallet):
        super().__init__(timeout=300)
        self.member, self.guild, self.rows, self.wallet = member, guild, rows, wallet
        self.sort, self.filter, self.page = "Price: low to high", "All items", 0
        self.origin = self.message = None
        self.lay_out()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member.id:
            await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} You are not the author of this command.", "bad"
                ),
                ephemeral=True,
            )
            return False
        return True

    def price(self, spot, item):
        """The button that buys one item, as /buy does; grey when it cannot be bought."""
        open_ = item in buyable([item], self.wallet)
        button = discord.ui.Button(
            style=discord.ButtonStyle.green if open_ else discord.ButtonStyle.grey,
            label=f"{item['cost']:,}",
            emoji=TOKEN_EMOTE if item["currency"] == "tokens" else BEAN_EMOTE,
            custom_id=f"buy_{spot}",
            disabled=not open_,
        )

        async def buy(interaction: discord.Interaction):
            request = await order(interaction, item["buy"])
            await request.done.wait()
            await self.restock(interaction)

        button.callback = buy
        return button

    def turner(self, custom_id, emoji, page):
        last = len(self.pages) - 1
        button = discord.ui.Button(
            style=discord.ButtonStyle.grey,
            emoji=emoji,
            custom_id=custom_id,
            disabled=page == self.page or not 0 <= page <= last,
        )

        async def go(interaction: discord.Interaction):
            self.page = page
            await self.turn(interaction)

        button.callback = go
        return button

    def editor(self, label, style, custom_id, operation):
        button = discord.ui.Button(label=label, style=style, custom_id=custom_id)

        async def edit(interaction: discord.Interaction):
            await self.edit(interaction, operation)

        button.callback = edit
        return button

    def lay_out(self):
        self.pages = listing(self.guild, self.rows, self.sort, self.filter) or [[]]
        self.page = min(self.page, len(self.pages) - 1)
        items, last = self.pages[self.page], len(self.pages) - 1
        ui = discord.ui
        box = ui.Container(
            ui.MediaGallery(discord.MediaGalleryItem("attachment://shop.jpg")),
            ui.TextDisplay(f"-# {self.filter}, page {self.page + 1} of {last + 1}"),
        )
        for spot, item in enumerate(items):
            text = row(item, self.wallet, EMOTES.get(item["icon"], ""), REPLY_EMOTE)
            box.add_item(ui.Section(text, accessory=self.price(spot, item)))
        if not items:
            box.add_item(ui.TextDisplay("Nothing matches this filter."))
        box.add_item(ui.Separator())
        box.add_item(
            ui.ActionRow(
                self.turner("first_page", "<:fastbackward:1351972112696479824>", 0),
                self.turner(
                    "prev_page", "<:backarrow:1351972111010369618>", self.page - 1
                ),
                self.turner(
                    "next_page", "<:rightarrow:1351972116819480616>", self.page + 1
                ),
                self.turner("last_page", "<:fastforward:1351972114433048719>", last),
            )
        )
        box.add_item(ui.ActionRow(ShopSelect("sort", SORTS, self.sort)))
        box.add_item(ui.ActionRow(ShopSelect("filter", FILTERS, self.filter)))
        if self.member.guild_permissions.administrator:
            box.add_item(
                ui.ActionRow(
                    self.editor(
                        "Add Reward", discord.ButtonStyle.green, "addreward", "add"
                    ),
                    self.editor(
                        "Remove Reward",
                        discord.ButtonStyle.red,
                        "removereward",
                        "remove",
                    ),
                    self.editor(
                        "Edit Cost", discord.ButtonStyle.grey, "editcost", "edit_cost"
                    ),
                    self.editor(
                        "Edit Stock",
                        discord.ButtonStyle.grey,
                        "editstock",
                        "edit_stock",
                    ),
                )
            )
        self.clear_items()
        self.add_item(box)

    async def file(self):
        """The header with the member's wallet as it is now."""
        self.lay_out()
        return await render(draw_header, "SHOP", self.wallet, SIGN, name="shop")

    async def restock(self, interaction):
        """Redraws the shop after a purchase: new balance, waits and stock."""
        self.wallet = await wallet_of(interaction)
        self.rows = g_shops(interaction.guild.id).get() or []
        try:
            await self.origin.edit_original_response(
                attachments=[await self.file()], view=self
            )
        except (discord.HTTPException, AttributeError):
            pass

    async def turn(self, interaction):
        self.lay_out()
        await interaction.response.edit_message(view=self)

    async def edit(self, interaction, operation):
        modal = RewardModal(operation, interaction.guild.id)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.pages is not None:
            self.rows = modal.pages
            self.lay_out()
            await interaction.edit_original_response(view=self)
        if modal.on_submit_interaction:
            await modal.on_submit_interaction.response.send_message(
                embed=modal.update, ephemeral=True
            )

    async def on_timeout(self) -> None:
        for child in self.walk_children():
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except discord.HTTPException:
            pass


async def wallet_of(interaction):
    """What the shop needs to know about one member: balance, background and locks."""
    user, guild = interaction.user, interaction.guild
    balance = u_balance(user.id).get() or {}
    stations = {*ITEM_STATIONS.values(), "effects"}
    effects = interaction.client.get_cog("CurrencySystem").effect_manager
    waits = {
        item: last["last_purchase"] + STORE_ITEMS[item]["cooldown"] - time.time()
        for item, last in (u_shop_cooldowns(user.id).get() or {}).items()
        if item in STORE_ITEMS
    }
    day = get_current_date_key()
    drops = u_star_drops_purchases(user.id, day).get() or 0
    boxes = u_mega_boxes_purchases(user.id, day).get() or 0
    ultra = guild.get_role(ULTRA_TIER_ROLE_ID)
    return {
        "background": BACKGROUND,
        "beans": balance.get("Beans", 0),
        "tokens": balance.get("Tokens", 0),
        "locked": {
            station
            for station in stations
            if not await unlocked(interaction.client, user.id, guild.id, station)
        },
        "owned": {role.id for role in user.roles},
        "held": set(held(user.id)),
        "active": {
            item: data.get("expires_at", 0)
            for item, data in (await effects.get_user_active_effects(user.id)).items()
        },
        "waits": {item: left for item, left in waits.items() if left > 0},
        "today": {
            "star_drop": drops,
            "star_drop_10": drops,
            "mega_box": boxes,
            "mega_box_10": boxes,
        },
        "limit": 20 if ultra and ultra in user.roles else 10,
        "stamps": stamps(user.id),
    }


async def open_shop(interaction):
    """Builds the shop for one member."""
    user, guild = interaction.user, interaction.guild
    view = ShopView(
        user, guild, g_shops(guild.id).get() or [], await wallet_of(interaction)
    )
    view.origin = interaction
    return view, await view.file()


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
        self.pages = rewards
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


global_purchase_queue = asyncio.Queue()
purchase_worker = None
PURCHASE_SECONDS = 60


class PurchaseRequest:
    __slots__ = ("interaction", "item", "timestamp", "done")

    def __init__(self, interaction, item):
        self.interaction = interaction
        self.item = item
        self.timestamp = time.time()
        self.done = asyncio.Event()


async def order(interaction, item):
    """Queues a purchase and answers with a waiting note. /buy and the shop menu both use it."""
    global purchase_worker
    request = PurchaseRequest(interaction, item)
    await global_purchase_queue.put(request)
    place = global_purchase_queue.qsize()
    await interaction.response.send_message(
        embed=notice(
            f"{LOADING} Your purchase is in queue. Position: {place}. Please wait..."
            if place > 1
            else f"{LOADING} Processing your purchase..."
        ),
    )
    if purchase_worker is None or purchase_worker.done():
        purchase_worker = asyncio.create_task(process_global_queue())
    return request


async def fail(request, reason):
    """Ends a purchase that could not finish, so its waiting note never stays up."""
    print(f"Purchase of {request.item!r} failed: {reason!r}")
    try:
        await request.interaction.edit_original_response(
            content=None,
            embed=notice(
                f"{NO_EMOTE} That purchase did not go through. Please try again.",
                "bad",
            ),
        )
    except discord.HTTPException:
        pass


async def process_global_queue():
    """Works through the queue one purchase at a time; a stuck one is dropped after a minute."""
    while not global_purchase_queue.empty():
        request = await global_purchase_queue.get()
        try:
            cog = request.interaction.client.get_cog("Shop")
            await asyncio.wait_for(cog._process_purchase(request), PURCHASE_SECONDS)
        except Exception as error:
            await fail(request, error)
        finally:
            request.done.set()
            global_purchase_queue.task_done()


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
                embed=notice(
                    f"{NO_EMOTE} You do not have permission to use this command.", "bad"
                ),
                ephemeral=True,
            )
        if await locked(interaction, "style"):
            return

        user_id = interaction.user.id

        ref = u_pin_message(user_id)
        data = ref.get() or {"count": 0}
        pin_count = data.get("count", 0)

        if pin_count <= 0:
            return await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} You don't have any message pin credits! Purchase **1 Message Pin** from the shop to pin messages.",
                    "bad",
                ),
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
                    embed=notice(
                        f"{NO_EMOTE} You can only pin messages from this server!", "bad"
                    ),
                    ephemeral=True,
                )

        except (ValueError, IndexError):
            return await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} Invalid message link! Please provide a valid Discord message link.\n"
                    f"-# Example: `https://discord.com/channels/1234567/2345678/78901234`",
                    "bad",
                ),
                ephemeral=True,
            )

        await interaction.response.defer(thinking=True)

        try:
            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                return await interaction.followup.send(
                    embed=notice(
                        f"{NO_EMOTE} Channel not found! Make sure the message is from this server.",
                        "bad",
                    ),
                    ephemeral=True,
                )

            if not channel.permissions_for(interaction.guild.me).manage_messages:
                return await interaction.followup.send(
                    embed=notice(
                        f"{NO_EMOTE} I don't have permission to pin messages in {channel.mention}!",
                        "bad",
                    ),
                    ephemeral=True,
                )

            message = await channel.fetch_message(message_id)

            if message.pinned:
                return await interaction.followup.send(
                    embed=notice(f"{NO_EMOTE} That message is already pinned!", "bad"),
                    ephemeral=True,
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
                embed=notice(
                    f"{NO_EMOTE} Message not found! Make sure the link is correct and I can access that channel.",
                    "bad",
                ),
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=notice(
                    f"{NO_EMOTE} I don't have permission to pin messages in that channel!",
                    "bad",
                ),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            if "Maximum number of pins reached" in str(e):
                await interaction.followup.send(
                    embed=notice(
                        f"{NO_EMOTE} That channel has reached the maximum number of pinned messages (50)! Please unpin some messages first.",
                        "bad",
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    embed=notice(f"{NO_EMOTE} Failed to pin message: {str(e)}", "bad"),
                    ephemeral=True,
                )
        except Exception as e:
            await interaction.followup.send(
                embed=notice(f"{NO_EMOTE} An error occurred: {str(e)}", "bad"),
                ephemeral=True,
            )

    @pin.error
    async def pin_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            embed=notice(f"```{str(error)}```"), ephemeral=True
        )

    @app_commands.command(
        name="shop", description="View the guild shop (Admins can edit)"
    )
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def shop(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} You do not have permission to use this command.", "bad"
                ),
                ephemeral=True,
            )
        if await locked(interaction, "shop"):
            return
        await interaction.response.defer(thinking=True)
        view, file = await open_shop(interaction)
        view.message = await interaction.followup.send(file=file, view=view)

    async def cog_load(self):
        try:
            await stock_emotes(self.bot)
        except discord.HTTPException as error:
            print(f"Shop emojis not ready: {error}")

    @shop.error
    async def shop_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            embed=notice(f"```{str(error)}```"), ephemeral=True
        )

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
                embed=notice(
                    f"{NO_EMOTE} You do not have permission to use this command.", "bad"
                ),
                ephemeral=True,
            )
        if await locked(interaction, "shop"):
            return
        await order(interaction, item)

    @buy.error
    async def buy_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            embed=notice(f"```{str(error)}```"), ephemeral=True
        )

    async def _process_purchase(self, request):
        interaction = request.interaction
        item = request.item

        if time.time() - request.timestamp > 900:
            return await interaction.edit_original_response(
                content=None,
                embed=notice("⌛ Your purchase request has expired. Please try again."),
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
                content=None,
                embed=notice(f"{NO_EMOTE} The shop is currently empty.", "bad"),
            )

        reward = None
        for r in shop_items:
            if str(r[0]).lower() == item.lower():
                reward = r
                break
        if reward is None:
            return await interaction.edit_original_response(
                content=None,
                embed=notice(
                    f"{NO_EMOTE} There is no item called `{item}`. "
                    f"Open {SHOP} and pick it from the menu under the shop.",
                    "bad",
                ),
            )

        name, desc, cost, currency_type, multiple, stock = reward

        beans, tokens = await self.economy.get_balance(user_id)

        if stock == 0:
            return await interaction.edit_original_response(
                content=None,
                embed=notice(
                    f"<a:out_of_stock:1384990609584033812> Sorry, **{name}** is currently out of stock."
                ),
            )

        user_currency = beans if currency_type.lower() == "beans" else tokens
        currency_emote = BEAN_EMOTE if currency_type.lower() == "beans" else TOKEN_EMOTE

        if user_currency < cost:
            return await interaction.edit_original_response(
                content=None,
                embed=notice(
                    f"{NO_EMOTE} You do not have enough {currency_type}. You have {currency_emote} `{user_currency}`, but this costs {currency_emote} `{cost}`.",
                    "bad",
                ),
            )

        if multiple is False:
            role = interaction.guild.get_role(int(name)) if name.isdigit() else None
            if role and role in member.roles:
                return await interaction.edit_original_response(
                    content=None,
                    embed=notice(
                        f"{NO_EMOTE} You already own the role **{role.name}** and cannot purchase it again.",
                        "bad",
                    ),
                )

        if currency_type.lower() == "beans":
            new_beans, new_tokens = await wallet.change(
                user_id, beans=-cost, reason="shop"
            )
        else:
            new_beans, new_tokens = await wallet.change(
                user_id, tokens=-cost, reason="shop"
            )

        if stock > 0:
            await self.update_shop_stock(guild_id, name, stock - 1)

        order = await update_quest(user_id, guild_id, {"shop_purchases": 1}, self.bot)

        display_name = name
        if name.isdigit():
            role = interaction.guild.get_role(int(name))
            if role:
                display_name = f"<@&{name}>"
                try:
                    await member.add_roles(role, reason="Purchased from shop")
                except discord.Forbidden:
                    return await interaction.edit_original_response(
                        content=None,
                        embed=notice(
                            f"Purchased **{role.name}**, but I do not have permission to assign the role."
                        ),
                    )
                except Exception as e:
                    return await interaction.edit_original_response(
                        content=None,
                        embed=notice(f"{NO_EMOTE} Error assigning role: {e}", "bad"),
                    )

        sale = {
            "background": BACKGROUND,
            "icon": reward_icon(name, SUPERCELL in name),
            "name": plain(role.name if name.isdigit() and role else display_name),
            "next": ROLE if name.isdigit() else CLAIM,
            "cost": cost,
            "currency": currency_type.lower(),
            "beans": new_beans,
            "tokens": new_tokens,
        }
        await interaction.edit_original_response(
            content=None,
            **reframed(
                await render(draw_purchase, sale, name="purchase"),
                "Purchase complete",
                (
                    None
                    if name.isdigit()
                    else "Open a ticket in <#1390908939767648328> to claim your reward."
                ),
                tone="good",
            ),
        )
        await report(interaction, order)

    async def _process_effect_purchase(self, interaction, user_id: int, item_id: str):
        """Process purchase of effect items"""
        item_data = STORE_ITEMS[item_id]
        station = ITEM_STATIONS.get(item_id, "effects")
        guild_id = interaction.guild.id
        if not await unlocked(self.bot, user_id, guild_id, station):
            level = await level_of(self.bot, user_id, guild_id)
            return await interaction.edit_original_response(
                content=None, embed=notice(lock_line(station, level), "bad")
            )

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

        if item_id in held(user_id):
            return await interaction.edit_original_response(
                content=None,
                embed=notice(
                    f"{NO_EMOTE} You already hold a {item_data['name']}. "
                    "Start it with /use before buying another.",
                    "bad",
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
            new_beans, new_tokens = await wallet.change(
                user_id, beans=-cost, reason="shop"
            )
        else:
            new_beans, new_tokens = await wallet.change(
                user_id, tokens=-cost, reason="shop"
            )

        order = await update_quest(
            user_id, interaction.guild.id, {"shop_purchases": 1}, self.bot
        )
        use_now = None

        if item_id == "reset_chat_cap":
            earnings_data = self.economy.chat_system.earnings_cache.get(
                user_id, {"earnings": 0, "reset_time": 0}
            )
            earnings_data["earnings"] = 0
            self.economy.chat_system.earnings_cache[user_id] = earnings_data
            u_daily_chat_earnings(user_id).update({"earnings": 0, "reset_time": 0})
            effect_msg = "You can earn chat Beans again today."

        elif item_id == "thermometer_boost":
            current_heat = self.economy.thermometer_heat
            boost_amount = 30
            new_heat = min(130, current_heat + boost_amount)
            await self.economy.set_heat(new_heat)
            effect_msg = f"The thermometer is now at {new_heat}."

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

            await self.economy.add_tokens(user_id, tokens_earned, reason="brew")
            order += await update_quest(
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

            effect_msg = f"Your brew sold for {tokens_earned} Tokens.{' It was a perfect brew.' if is_perfect else ''}"

        elif item_id == "star_drop" or item_id == "star_drop_10":
            amount_to_buy = 10 if item_id == "star_drop_10" else 1
            date_key = get_current_date_key()
            purchases_ref = u_star_drops_purchases(user_id, date_key)
            purchases = purchases_ref.get() or 0
            purchases_ref.set(purchases + amount_to_buy)

            inventory_ref = u_star_drops(user_id)
            current_count = inventory_ref.get() or 0
            inventory_ref.set(current_count + amount_to_buy)

            effect_msg = (
                f"You have {current_count + amount_to_buy} to open with /stardrop."
            )

        elif item_id == "mega_box" or item_id == "mega_box_10":
            amount_to_buy = 10 if item_id == "mega_box_10" else 1
            date_key = get_current_date_key()
            purchases_ref = u_mega_boxes_purchases(user_id, date_key)
            purchases = purchases_ref.get() or 0
            purchases_ref.set(purchases + amount_to_buy)

            inventory_ref = u_mega_boxes(user_id)
            current_count = inventory_ref.get() or 0
            inventory_ref.set(current_count + amount_to_buy)
            effect_msg = (
                f"You have {current_count + amount_to_buy} to open with /megabox."
            )

        elif item_id == "message_pin":
            await item_data["effect"](user_id)
            pin_ref = u_pin_message(user_id)
            pin_data = pin_ref.get() or {"count": 0}
            pin_count = pin_data.get("count", 0)
            effect_msg = f"You have {pin_count} to use with /pin."

        else:
            keep(user_id, item_id)
            use_now = UseNow(user_id, item_id)
            effect_msg = (
                f"{note(self.bot, item_id)}. Start it with /use."
                if item_id == "freeze_thermometer"
                else "Start it now or later with /use."
            )

        await self.economy.effect_manager.set_user_cooldown(user_id, item_id)

        sale = {
            "background": BACKGROUND,
            "icon": item_icon(item_id),
            "name": item_data["name"],
            "next": effect_msg,
            "cost": cost,
            "currency": currency,
            "beans": new_beans,
            "tokens": new_tokens,
        }
        await interaction.edit_original_response(
            content=None,
            **reframed(
                await render(draw_purchase, sale, name="purchase"),
                "Purchase complete",
                tone="good",
            ),
            view=use_now,
        )
        await report(interaction, order)

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

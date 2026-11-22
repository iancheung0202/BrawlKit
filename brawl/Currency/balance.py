import io
import os
import re
import time
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from firebase_admin import db
from PIL import Image, ImageDraw, ImageFont

from brawl.Currency.db import (
    U_ROOT,
    g_invites_member_data,
    g_invites_monthly,
    g_referral_milestones,
    u_customization,
    u_daily_chat_earnings,
    u_daily_checkin_streaks,
    u_mega_boxes,
    u_pin_message,
    u_star_drops,
)
from brawl.Currency.helper import (
    BEAN_EMOTE,
    BRIDGE_ROLE_ID,
    COLORS,
    EFFECT_EMOTE,
    MAIN_GUILD_ID,
    MASTER_ROLE_ID,
    MEGA_BOX_EMOTE,
    NO_EMOTE,
    REPLY_EMOTE,
    STAR_DROP_EMOTE,
    STORE_ITEMS,
    TABLE_QUEST_TYPES,
    TOKEN_EMOTE,
    TRAINEE_ROLE_ID,
    ULTRA_TIER_ROLE_ID,
    YES_EMOTE,
    get_current_month_key,
)
from brawl.Currency.levels import get_level
from brawl.Currency.quests import update_quest


class BalanceInfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.message = None

    async def on_timeout(self) -> None:
        for child in self.children:
            if (
                isinstance(child, discord.ui.Button)
                and child.style == discord.ButtonStyle.link
            ):
                continue
            child.disabled = True
            if isinstance(child, discord.ui.Select):
                child.options = [
                    discord.SelectOption(
                        label="Disabled due to timeout",
                        value="X",
                        emoji="⛔",
                        default=True,
                    )
                ]
        try:
            if hasattr(self, "message") and self.message:
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

    @discord.ui.button(
        style=discord.ButtonStyle.blurple,
        emoji="📮",
        custom_id="stampcard",
        label="Stampcard",
    )
    async def stampcard_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = int(
            interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
        )
        if interaction.user.id != user_id:
            return await interaction.response.send_message(
                "This is not your command.", ephemeral=True
            )
        stamp_cog = interaction.client.get_cog("StampCard")
        if not stamp_cog:
            return await interaction.response.send_message(
                "Stamp Card system unavailable.", ephemeral=True
            )
        embed, _ = await stamp_cog.get_stamp_embed(interaction.user, interaction.guild)
        self._remove_selects()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        custom_id="effect_info",
        emoji=EFFECT_EMOTE,
        label="Inventory",
    )
    async def effect_info(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = int(
            interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
        )
        if interaction.user.id != user_id:
            return await interaction.response.send_message(
                "This is not your command. You cannot use this button.", ephemeral=True
            )

        active_effects = await interaction.client.get_cog(
            "CurrencySystem"
        ).effect_manager.get_user_active_effects(user_id)
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

                    effect_list.append(
                        f"-# {REPLY_EMOTE} `{item_name}`{indicator} *(Expires <t:{int(expires_at)}:R>)*"
                    )

            if effect_list:
                embed.add_field(
                    name=f"{EFFECT_EMOTE} Active Effects",
                    value="\n".join(effect_list),
                    inline=True,
                )

        pin_ref = u_pin_message(user_id)
        pin_data = pin_ref.get() or {"count": 0}
        pin_count = pin_data.get("count", 0)

        if pin_count > 0:
            embed.add_field(
                name="📌 Message Pins",
                value=f"`{pin_count}` pin{'s' if pin_count != 1 else ''} available\n-# Use </pin:1427543833792610344> to pin messages",
                inline=True,
            )

        customize_ref = u_customization(user_id)
        customize_data = customize_ref.get() or {"credits": 0}
        customize_credits = customize_data.get("credits", 0)

        if customize_credits > 0:
            embed.add_field(
                name="🎨 Background Customization",
                value=f"`{customize_credits}` credit{'s' if customize_credits != 1 else ''} available\n-# Use </customize:1486174479489957908> to edit card background",
                inline=True,
            )

        star_drop_ref = u_star_drops(user_id)
        unopened_drops = star_drop_ref.get() or 0
        if unopened_drops > 0:
            embed.add_field(
                name=f"{STAR_DROP_EMOTE} Star Drops",
                value=f"`{unopened_drops}` star drop{'s' if unopened_drops != 1 else ''} unopened!\n-# Use </stardrop:1447676573020065996> to open them",
                inline=True,
            )

        mega_box_ref = u_mega_boxes(user_id)
        unopened_boxes = mega_box_ref.get() or 0
        if unopened_boxes > 0:
            embed.add_field(
                name=f"{MEGA_BOX_EMOTE} Mega Boxes",
                value=f"`{unopened_boxes}` mega box{'es' if unopened_boxes != 1 else ''} unopened!\n-# Use </megabox:1486191980349358224> to open them",
                inline=True,
            )

        if len(embed.fields) > 0:
            embed.title = f"{EFFECT_EMOTE} Your Active Effects & Inventory"
        else:
            embed.description = (
                f"{NO_EMOTE} You have no active effects and inventory items."
            )
            embed.color = discord.Color.red()

        self._remove_selects()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="<a:invites:1456860324459184372>",
        custom_id="balance_invites",
        label="Invites",
    )
    async def balance_invites(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = int(
            interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
        )
        if interaction.user.id != user_id:
            return await interaction.response.send_message(
                "This is not your command. You cannot use this button.", ephemeral=True
            )

        ref = g_invites_monthly(
            interaction.guild.id, get_current_month_key(), interaction.user.id
        )
        data = ref.get() or {"valid": 0, "total": 0, "left": 0}
        valid = data.get("valid", 0)
        total = data.get("total", 0)
        left = data.get("left", 0)

        year, month_num = get_current_month_key().split("-")

        def _month_name(month_num):
            months = [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]
            return (
                months[month_num - 1] if 1 <= month_num <= 12 else f"Month {month_num}"
            )

        embed = discord.Embed(
            title=f"<:BrockCool:1391630483867172935> Your Monthly Invites ({_month_name(int(month_num))} {year})",
            description=f"> **`{valid}` invites** (`{total}` total, `{left}` left)",
            color=discord.Color.purple(),
        )

        ref = g_invites_member_data(interaction.guild.id)
        all_data = ref.get() or {}
        months = set()

        for member_id, data in all_data.items():
            if data.get("inviter") == str(interaction.user.id):
                months.add(data.get("join_month"))

        months = sorted(months, reverse=True)[:25]
        ref_milestone = g_referral_milestones(
            interaction.guild.id, get_current_month_key(), interaction.user.id
        )
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
            inline=False,
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

    @discord.ui.button(
        style=discord.ButtonStyle.grey, emoji="🍽️", custom_id="table_info", label="Table"
    )
    async def table_info(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        try:
            user_id = int(
                interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
            )
        except:
            user_id = interaction.user.id

        if interaction.user.id != user_id:
            return await interaction.response.send_message(
                "This is not your command. You cannot use this button.", ephemeral=True
            )

        table_cog = interaction.client.get_cog("table")
        if not table_cog:
            embed = discord.Embed(
                description="Table system is currently unavailable.",
                color=discord.Color.red(),
            )
            return await interaction.response.edit_message(embed=embed, view=self)

        table_data = await table_cog.get_user_table(
            interaction.user.id, interaction.guild.id
        )
        if not table_data:
            embed = discord.Embed(
                description=f"{NO_EMOTE} You're not seated at any table.",
                color=discord.Color.red(),
            )
            return await interaction.response.edit_message(embed=embed, view=self)

        host = await interaction.client.fetch_user(table_data["host"])
        host_name = host.mention if host else f"Unknown ({table_data['host']})"

        user_contributions = table_data.get("user_contributions", {})
        user_beans = user_contributions.get(str(interaction.user.id), 0)

        embed = discord.Embed(
            title=f"{table_data['emoji']} Table: {table_data['name']}",
            description=f"\"{table_data['motto']}\"",
            color=int(table_data["color"].lstrip("#"), 16),
        )

        embed.add_field(name="🍽️ Host", value=host_name, inline=True)
        embed.add_field(name="🎨 Color", value=table_data["color"], inline=True)
        embed.add_field(
            name="📋 Status",
            value=(
                f"{YES_EMOTE} Officially recognized table!"
                if table_data.get("formalized")
                else f"{NO_EMOTE} Not yet recognized (requires **5 people seated**)."
            ),
            inline=True,
        )
        embed.add_field(
            name="📦 Weekly Beans",
            value=f"{BEAN_EMOTE} `{table_data.get('weekly_beans', 0):,}`",
            inline=True,
        )
        embed.add_field(
            name="🙋 Your Contribution",
            value=f"{BEAN_EMOTE} `{user_beans:,}`",
            inline=True,
        )
        embed.add_field(
            name="📅 Reserved At",
            value=f"<t:{int(table_data['created_at'])}:F>",
            inline=True,
        )

        quest = table_data.get("quest", {})
        if quest and table_data.get("formalized", False):
            quest_config = TABLE_QUEST_TYPES["bean_collector"]
            current_tier = quest.get("current_tier", 0)
            completed_tiers = quest.get("completed_tiers", [])
            weekly_beans = table_data.get("weekly_beans", 0)

            quest_lines = []
            for i, (target, reward) in enumerate(
                zip(quest_config["targets"], quest_config["rewards"])
            ):
                if i in completed_tiers:
                    quest_lines.append(
                        f"- -# **Tier {i+1}:** {BEAN_EMOTE} `{target:,}` <a:Yes_dimmed:1393015472676540436>"
                    )
                elif i == current_tier:
                    progress_pct = min(100, int((weekly_beans / target) * 100))
                    bar_length = 16
                    filled = int((progress_pct / 100) * bar_length)
                    bar = "█" * filled + "░" * (bar_length - filled)
                    quest_lines.append(f"- **Tier {i+1}: `{bar}` {progress_pct}%**")
                    quest_lines.append(
                        f"-# *<:reply:1036792837821435976> {BEAN_EMOTE} `{weekly_beans:,} / {target:,}` • Reward: {BEAN_EMOTE} `{reward}` per member*"
                    )
                else:
                    quest_lines.append(
                        f"- -# **Tier {i+1}:** {BEAN_EMOTE} `{target:,}` 🔒"
                    )

            embed.add_field(
                name="🎯 Weekly Bean Collector Quest",
                value=(
                    "\n".join(quest_lines)
                    if quest_lines
                    else "Quest data not available..."
                ),
                inline=True,
            )

        members_list = [
            f"-# - {(await interaction.client.fetch_user(m)).mention if (await interaction.client.fetch_user(m)) else f'Unknown member ({m})'}"
            for m in table_data.get("members", [])
        ]
        embed.add_field(
            name=f"📋 Seated Members ({len(table_data.get('members', []))}/10)",
            value="\n".join(members_list) if members_list else "No one seated",
            inline=True,
        )
        embed.set_footer(
            text="Once your table is officially recognized, your emoji will be added to the daily chat bean notification"
        )

        self._remove_selects()
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        emoji="<:quest:1490123182345293824>",
        custom_id="quests",
        label="Quests",
    )
    async def quests(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user_id = int(
                interaction.message.attachments[0].filename.split("_")[1].split(".")[0]
            )
            if interaction.user.id != user_id:
                return await interaction.response.send_message(
                    "This is not your command. You cannot use this button.",
                    ephemeral=True,
                )
        except:
            pass

        guild_id = interaction.guild.id

        # Refresh quests in case they need to reset
        await update_quest(user_id, guild_id, {}, interaction.client, refresh_only=True)

        # Import quest constants
        from brawl.Currency.db import u_quests
        from brawl.Currency.quests import (
            QUEST_BEAN_REWARDS,
            QUEST_BONUS_BEANS,
            QUEST_DESCRIPTIONS,
        )

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
            quest_text.append(
                f"### {duration.capitalize()} Quests - {BEAN_EMOTE} `{QUEST_BEAN_REWARDS[duration]}` Beans each *(resets {reset_time})*"
            )

            for q_type, data in quests.items():
                status = (
                    f"`{data['current']}/{data['goal']}` {YES_EMOTE}"
                    if q_type in completed
                    else f"`{data['current']}/{data['goal']}`"
                )
                quest_text.append(
                    f"- {QUEST_DESCRIPTIONS.get(q_type, q_type)}: {status}"
                )

            if dur_data.get("bonus_awarded"):
                quest_text.append(
                    f"-# <:reply:1036792837821435976> *{BEAN_EMOTE} `{QUEST_BONUS_BEANS[duration]}` Beans bonus already claimed! <:resolved:1364813186028797984>*"
                )
            else:
                quest_text.append(
                    f"-# <:reply:1036792837821435976> *Complete all for `+{QUEST_BONUS_BEANS[duration]}` Beans bonus! <a:tada:1227425729654820885>*"
                )

        if not quest_text:
            quest_text = ["No active quests. Check back when new quests are available!"]

        embed = discord.Embed(
            title="<:quest:1490123182345293824> Your Quests",
            description="\n".join(quest_text),
            color=discord.Color.green(),
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


class Balance(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def economy(self):
        return self.bot.get_cog("CurrencySystem")

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
            balance = user_data.get("balance", {})
            beans = balance.get("Beans", 0)
            tokens = balance.get("Tokens", 0)

            if beans > 0:
                beans_list.append((uid_str, beans))
            if tokens > 0:
                tokens_list.append((uid_str, tokens))

            # Get daily checkin streak
            progress = user_data.get("progress", {})
            daily_checkin = progress.get("daily_checkin_streaks", {})
            streak = daily_checkin.get("current_streak", 0)
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

    async def generate_balance_card(
        self,
        user: discord.Member,
        beans: int,
        tokens: int,
        streak: int,
        earnings: int,
        max_earnings: int,
        reset_time: float,
        active_brew: dict = None,
        total_brews: int = 0,
        table_name: str = None,
        table_emoji_url: str = None,
        level: int = 0,
        rank: int = 0,
        current_xp: int = 0,
        xp_needed: int = 100,
        beans_rank: int = 0,
        tokens_rank: int = 0,
        streak_rank: int = 0,
        custom_bg: str = None,
        custom_bg_bytes: bytes = None,
    ) -> discord.File:
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

                overlay = Image.new("RGBA", img.size, (0, 0, 0, 180))
                img = Image.alpha_composite(img, overlay).convert("RGB")
            except Exception as e:
                print(f"Error loading custom bg: {e}")

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
            "assets/LilitaOne-Regular.ttf",
            "arialbd.ttf",
            "Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        regular_candidates = [
            "arial.ttf",
            "Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
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
            avatar = (
                Image.open(io.BytesIO(avatar_bytes))
                .convert("RGBA")
                .resize((AVATAR_SIZE, AVATAR_SIZE))
            )
            mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, AVATAR_SIZE, AVATAR_SIZE), fill=255)
            img.paste(avatar, (AVATAR_X, AVATAR_Y), mask)
        except Exception:
            draw.ellipse(
                (AVATAR_X, AVATAR_Y, AVATAR_X + AVATAR_SIZE, AVATAR_Y + AVATAR_SIZE),
                fill=(80, 80, 80),
            )

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
            total_width = (len(badge_icons) * badge_size) + (
                (len(badge_icons) - 1) * badge_gap
            )
            start_x = AVATAR_X + (AVATAR_SIZE - total_width) // 2
            badge_y = AVATAR_Y + AVATAR_SIZE + 10

            current_x = start_x
            for badge_url in badge_icons:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(badge_url) as resp:
                            if resp.status == 200:
                                badge_bytes = await resp.read()
                                badge_img = (
                                    Image.open(io.BytesIO(badge_bytes))
                                    .convert("RGBA")
                                    .resize((badge_size, badge_size))
                                )
                                img.paste(
                                    badge_img, (int(current_x), int(badge_y)), badge_img
                                )
                                current_x += badge_size + badge_gap
                except Exception:
                    continue

        CONTENT_X = AVATAR_X + AVATAR_SIZE + 50
        CURRENT_Y = 28

        draw.text(
            (CONTENT_X, CURRENT_Y),
            f"{user.display_name}",
            font=username_font,
            fill=(255, 255, 255),
        )
        CURRENT_Y += USERNAME_SIZE + 10

        table_text = f"{table_name}" if table_name else "Not in a Table"
        draw.text(
            (CONTENT_X, CURRENT_Y), table_text, font=label_font, fill=(200, 200, 200)
        )

        if table_emoji_url:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(table_emoji_url) as resp:
                        emoji_bytes = await resp.read()
                emoji_img = (
                    Image.open(io.BytesIO(emoji_bytes)).convert("RGBA").resize((30, 30))
                )
                text_len = draw.textlength(table_text, font=label_font)
                img.paste(
                    emoji_img,
                    (int(CONTENT_X + text_len + 10), int(CURRENT_Y - 5)),
                    emoji_img,
                )
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
                icon = (
                    Image.open(io.BytesIO(icon_bytes))
                    .convert("RGBA")
                    .resize((ICON_SIZE, ICON_SIZE))
                )
                img.paste(icon, (x, y), icon)
            except:
                pass

            draw.text(
                (x + ICON_SIZE + 15, y), label, font=label_font, fill=(170, 170, 170)
            )

            if rank_val > 0:
                rank_text = f"#{rank_val}"
                label_width = draw.textlength(label, font=label_font)

                tag_font = try_load_font(bold_candidates, 14)
                tag_width = draw.textlength(rank_text, font=tag_font) + 10
                tag_height = 20
                tag_x = x + ICON_SIZE + 15 + label_width + 10
                tag_y = y

                draw.rounded_rectangle(
                    [(tag_x, tag_y), (tag_x + tag_width, tag_y + tag_height)],
                    radius=5,
                    fill=(60, 60, 60),
                )
                draw.text(
                    (tag_x + 5, tag_y + 2),
                    rank_text,
                    font=tag_font,
                    fill=(200, 200, 200),
                )

            draw.text(
                (x + ICON_SIZE + 15, y + 25),
                f"{value:,}",
                font=value_font,
                fill=(255, 255, 255) if label != "Tokens" else fill_color,
            )

        await draw_stat(
            CONTENT_X,
            STATS_Y,
            "Beans",
            beans,
            "https://cdn.discordapp.com/emojis/1393442086279315456.png",
            beans_rank,
        )
        await draw_stat(
            CONTENT_X + 200,
            STATS_Y,
            "Tokens",
            tokens,
            "https://cdn.discordapp.com/emojis/1393442089894940846.png",
            tokens_rank,
        )
        await draw_stat(
            CONTENT_X + 400,
            STATS_Y,
            "Streak",
            streak,
            "https://cdn.discordapp.com/emojis/1371651844652273694.png",
            streak_rank,
        )

        VAULT_ICON_SIZE_W = 86
        VAULT_ICON_SIZE_H = 100
        VAULT_X = WIDTH - VAULT_ICON_SIZE_W - 30
        VAULT_Y = 30

        current_time = time.time()
        if not active_brew:
            status_text = "Empty"
            icon_path = "assets/empty.png"
        elif active_brew["end_time"] > current_time:
            status_text = active_brew["roast_type"].capitalize()
            icon_path = "assets/brewing.png"
        else:
            status_text = active_brew["roast_type"].capitalize()
            icon_path = "assets/ready.png"

        try:
            vault_icon = (
                Image.open(icon_path)
                .convert("RGBA")
                .resize((int(VAULT_ICON_SIZE_W * 0.8), int(VAULT_ICON_SIZE_H * 0.8)))
            )
            img.paste(vault_icon, (VAULT_X, VAULT_Y), vault_icon)
        except Exception as e:
            print(f"Error loading vault icon: {e}")

        TEXT_X = VAULT_X - 20
        TEXT_Y = VAULT_Y + 5

        status_width = draw.textlength(status_text, font=small_value_font)

        if active_brew and active_brew.get("insured", False):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        "https://cdnjs.cloudflare.com/ajax/libs/twemoji/14.0.2/72x72/1f6e1.png"
                    ) as resp:
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

        draw.text(
            (TEXT_X - status_width, TEXT_Y),
            status_text,
            font=small_value_font,
            fill=(255, 255, 255),
        )

        total_text = f"Total: {total_brews:,}"
        total_width = draw.textlength(total_text, font=label_font)
        draw.text(
            (TEXT_X - total_width, TEXT_Y + 38),
            total_text,
            font=label_font,
            fill=(170, 170, 170),
        )

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
            draw.text(
                (BAR_X + x_offset, BAR_Y - 30), " (", font=font_16, fill=(170, 170, 170)
            )
            x_offset += draw.textlength(" (", font=font_16)

            draw.text(
                (BAR_X + x_offset, BAR_Y - 30),
                time_str,
                font=font_16,
                fill=(255, 255, 255),
            )
            x_offset += draw.textlength(time_str, font=font_16)

            draw.text(
                (BAR_X + x_offset, BAR_Y - 30), ")", font=font_16, fill=(170, 170, 170)
            )

        progress_text = f"{earnings}/{max_earnings} Beans"
        text_width = draw.textlength(
            progress_text, font=try_load_font(regular_candidates, 16)
        )
        draw.text(
            (BAR_X + BAR_WIDTH - text_width, BAR_Y - 30),
            progress_text,
            font=try_load_font(regular_candidates, 16),
            fill=(255, 255, 255),
        )

        radius = BAR_HEIGHT // 2
        bg_bar_color = (60, 60, 60)
        border_bar_color = (90, 90, 90)

        draw.rounded_rectangle(
            [(BAR_X, BAR_Y), (BAR_X + BAR_WIDTH, BAR_Y + BAR_HEIGHT)],
            radius=radius,
            fill=bg_bar_color,
        )
        draw.rounded_rectangle(
            [(BAR_X, BAR_Y), (BAR_X + BAR_WIDTH, BAR_Y + BAR_HEIGHT)],
            radius=radius,
            outline=border_bar_color,
            width=2,
        )

        progress = (
            min(max(0.0, float(earnings) / max_earnings), 1.0)
            if max_earnings > 0
            else 0
        )
        progress_width = int(BAR_WIDTH * progress)

        if progress_width > 0:
            draw.rounded_rectangle(
                [(BAR_X, BAR_Y), (BAR_X + progress_width, BAR_Y + BAR_HEIGHT)],
                radius=radius,
                fill=fill_color,
            )

        LEVEL_BAR_Y = BAR_Y + BAR_HEIGHT + 50

        level_text = f"Total Experience"
        leve_num_text = f" (Level {level})"

        draw.text(
            (BAR_X, LEVEL_BAR_Y - 30), level_text, font=font_16, fill=(170, 170, 170)
        )
        level_width = draw.textlength(level_text, font=font_16)
        draw.text(
            (BAR_X + level_width, LEVEL_BAR_Y - 30),
            leve_num_text,
            font=font_16,
            fill=(255, 255, 255),
        )

        if rank > 0:
            rank_text = f"#{rank}"
            leve_num_width = draw.textlength(leve_num_text, font=font_16)

            tag_font = try_load_font(bold_candidates, 14)
            tag_width = draw.textlength(rank_text, font=tag_font) + 10
            tag_height = 20
            tag_x = BAR_X + level_width + leve_num_width + 10
            tag_y = LEVEL_BAR_Y - 30

            draw.rounded_rectangle(
                [(tag_x, tag_y), (tag_x + tag_width, tag_y + tag_height)],
                radius=5,
                fill=(60, 60, 60),
            )
            draw.text(
                (tag_x + 5, tag_y + 2), rank_text, font=tag_font, fill=(200, 200, 200)
            )

        xp_text = f"{int(current_xp)}/{int(xp_needed)} XP"
        xp_text_width = draw.textlength(
            xp_text, font=try_load_font(regular_candidates, 16)
        )
        draw.text(
            (BAR_X + BAR_WIDTH - xp_text_width, LEVEL_BAR_Y - 30),
            xp_text,
            font=try_load_font(regular_candidates, 16),
            fill=(255, 255, 255),
        )

        draw.rounded_rectangle(
            [(BAR_X, LEVEL_BAR_Y), (BAR_X + BAR_WIDTH, LEVEL_BAR_Y + BAR_HEIGHT)],
            radius=radius,
            fill=bg_bar_color,
        )
        draw.rounded_rectangle(
            [(BAR_X, LEVEL_BAR_Y), (BAR_X + BAR_WIDTH, LEVEL_BAR_Y + BAR_HEIGHT)],
            radius=radius,
            outline=border_bar_color,
            width=2,
        )

        level_progress = (
            min(max(0.0, float(current_xp) / xp_needed), 1.0) if xp_needed > 0 else 0
        )
        level_progress_width = int(BAR_WIDTH * level_progress)

        if level_progress_width > 0:
            draw.rounded_rectangle(
                [
                    (BAR_X, LEVEL_BAR_Y),
                    (BAR_X + level_progress_width, LEVEL_BAR_Y + BAR_HEIGHT),
                ],
                radius=radius,
                fill=fill_color,
            )

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename=f"balance_{user.id}.png")

    @app_commands.command(
        name="balance", description="Check your Starr Beans and Tokens balance"
    )
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def balance(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )

        await interaction.response.defer(thinking=True)
        user_id = interaction.user.id
        beans, tokens = await self.economy.get_balance(user_id)

        ref = u_daily_checkin_streaks(user_id)
        streak_data = ref.get() or {
            "last_claim": 0,
            "current_streak": 0,
            "all_time_high": 0,
            "total_claims": 0,
        }
        current_streak = streak_data["current_streak"]

        table_name = None
        table_emoji_url = None
        table_cog = self.bot.get_cog("table")
        if table_cog:
            table_data = await table_cog.get_user_table(user_id, interaction.guild.id)
            if table_data and table_data.get("formalized", False):
                table_name = table_data["name"]
                emoji_str = table_data["emoji"]
                custom_emoji_match = re.search(r"<a?:.+:(\d+)>", emoji_str)
                if custom_emoji_match:
                    emoji_id = custom_emoji_match.group(1)
                    table_emoji_url = (
                        f"https://cdn.discordapp.com/emojis/{emoji_id}.png"
                    )

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

        active_effects = await self.economy.effect_manager.get_user_active_effects(
            user_id
        )
        if "chat_boost" in active_effects:
            MAX_DAILY_CHAT_BEAN_LIMIT *= 3

        if reset_time < time.time():
            earnings = 0
            reset_message = ""
        else:
            reset_message = f"\nResets <t:{int(reset_time)}:R>"

        active_brew = await self.economy.get_active_brew(user_id)
        brew_stats = await self.economy.get_brew_stats(user_id)
        total_brews = brew_stats.get("total_brews", 0) if brew_stats else 0

        level_cog = self.bot.get_cog("Leveling")
        level = 0
        rank = 0
        current_xp = 0
        xp_needed = 100

        if level_cog and level_cog.pool:
            try:
                row = await level_cog.pool.fetchrow(
                    "SELECT xp, level FROM levels WHERE id = $1 AND guild = $2",
                    str(user_id),
                    str(interaction.guild.id),
                )
                if row:
                    xp = row["xp"]
                    level = row["level"]
                    rank = await level_cog.pool.fetchval(
                        "SELECT COUNT(*) FROM levels WHERE guild = $1 AND xp > $2",
                        str(interaction.guild.id),
                        xp,
                    )
                    rank += 1
                    _, current_xp, xp_needed = get_level(xp)
            except Exception as e:
                print(f"Error fetching level data: {e}")

        beans_rank, tokens_rank, streak_rank = await self.get_user_ranks(user_id)

        custom_bg_path = f"assets/Balance Backgrounds/{user_id}.png"
        if not os.path.exists(custom_bg_path):
            custom_bg_path = None

        card = await self.generate_balance_card(
            interaction.user,
            beans,
            tokens,
            current_streak,
            earnings,
            MAX_DAILY_CHAT_BEAN_LIMIT,
            reset_time,
            active_brew,
            total_brews,
            table_name,
            table_emoji_url,
            level,
            rank,
            current_xp,
            xp_needed,
            beans_rank,
            tokens_rank,
            streak_rank,
            custom_bg=custom_bg_path,
        )

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
                color=COLORS["ultra"],
            )
            embed.set_footer(
                text="You have enough tokens to get a customization credit!"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    @balance.error
    async def balance_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    class CustomizeConfirmView(discord.ui.View):
        def __init__(self, bg_bytes: bytes, user_id: int):
            super().__init__(timeout=60)
            self.bg_bytes = bg_bytes
            self.user_id = user_id

        @discord.ui.button(
            label="Confirm",
            style=discord.ButtonStyle.success,
            custom_id="custom_confirm",
        )
        async def confirm_btn(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "This is not your confirmation.", ephemeral=True
                )

            ref = u_customization(self.user_id)
            data = ref.get() or {"credits": 0}
            if data.get("credits", 0) <= 0:
                for child in self.children:
                    child.disabled = True
                return await interaction.response.edit_message(
                    content=f"{NO_EMOTE} You no longer have any Customization Credits.",
                    view=self,
                )

            data["credits"] -= 1
            ref.set(data)

            os.makedirs("assets/Balance Backgrounds", exist_ok=True)
            path = f"assets/Balance Backgrounds/{self.user_id}.png"
            with open(path, "wb") as f:
                f.write(self.bg_bytes)

            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"{YES_EMOTE} Customization applied! Check out your new `/balance` card!",
                view=self,
            )

        @discord.ui.button(
            label="Cancel", style=discord.ButtonStyle.danger, custom_id="custom_cancel"
        )
        async def cancel_btn(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "This is not your confirmation.", ephemeral=True
                )

            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"{NO_EMOTE} Customization cancelled.", view=self
            )

    class CustomizeRemoveView(discord.ui.View):
        def __init__(self, user_id: int):
            super().__init__(timeout=60)
            self.user_id = user_id

        @discord.ui.button(
            label="Confirm Remove",
            style=discord.ButtonStyle.danger,
            custom_id="custom_remove",
        )
        async def confirm_btn(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "This is not your confirmation.", ephemeral=True
                )

            path = f"assets/Balance Backgrounds/{self.user_id}.png"
            if os.path.exists(path):
                try:
                    os.remove(path)
                    for child in self.children:
                        child.disabled = True
                    return await interaction.response.edit_message(
                        content=f"{YES_EMOTE} Your custom background has been removed successfully.",
                        view=self,
                    )
                except Exception as e:
                    return await interaction.response.send_message(
                        f"{NO_EMOTE} Failed to remove background: {e}", ephemeral=True
                    )
            else:
                for child in self.children:
                    child.disabled = True
                return await interaction.response.edit_message(
                    content=f"{NO_EMOTE} You don't have a custom background to remove.",
                    view=self,
                )

        @discord.ui.button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            custom_id="custom_cancel_remove",
        )
        async def cancel_btn(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message(
                    "This is not your confirmation.", ephemeral=True
                )

            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(
                content=f"{NO_EMOTE} Removal cancelled.", view=self
            )

    @app_commands.command(
        name="customize",
        description="Customize your balance rank card background (requires 1 Customization Credit)",
    )
    @app_commands.describe(
        attachment="Attach an image file to use as your background",
        url="Or provide a direct image URL (png, jpg, webp)",
    )
    @app_commands.checks.cooldown(rate=1, per=30.0)
    async def customize(
        self,
        interaction: discord.Interaction,
        attachment: discord.Attachment = None,
        url: str = None,
    ):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )

        user_id = interaction.user.id

        if not attachment and not url:
            path = f"assets/Balance Backgrounds/{user_id}.png"
            if os.path.exists(path):
                view = self.CustomizeRemoveView(user_id=user_id)
                return await interaction.response.send_message(
                    f"**Are you sure you want to remove your custom background?** This action cannot be reversed and the previous credit spent will not be refunded.",
                    view=view,
                    ephemeral=True,
                )
            else:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You don't have a custom background to remove.\n\n💡 Tip: To add one, provide an image attachment or URL. It costs **1 Customization Credit**.",
                    ephemeral=True,
                )

        bg_url = url if url else attachment.url
        if not (
            bg_url.startswith("http")
            and any(
                bg_url.split("?")[0].lower().endswith(ext)
                for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]
            )
        ):
            return await interaction.response.send_message(
                "Please provide a valid image (png, jpg, jpeg, gif, webp).",
                ephemeral=True,
            )

        ref = u_customization(user_id)
        data = ref.get() or {"credits": 0}

        if data.get("credits", 0) <= 0:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You do not have any Customization Credits. Buy them in the shop using </buy:1393376242501157010>!",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(bg_url) as resp:
                    if resp.status != 200:
                        return await interaction.followup.send(
                            f"{NO_EMOTE} Failed to download image.", ephemeral=True
                        )
                    bg_bytes = await resp.read()

            mock_card = await self.generate_balance_card(
                interaction.user,
                beans=9999,
                tokens=99,
                streak=10,
                earnings=1500,
                max_earnings=3000,
                reset_time=0.0,
                active_brew=None,
                total_brews=10,
                table_name="Master Brewer",
                table_emoji_url=None,
                level=50,
                rank=10,
                current_xp=9500,
                xp_needed=10000,
                beans_rank=1,
                tokens_rank=1,
                streak_rank=1,
                custom_bg_bytes=bg_bytes,
            )

            msg = (
                "## Preview Background\n"
                f"{REPLY_EMOTE} Do you want to apply the change for **1 Customization Credit**?\n\n"
                f"-# <a:warning:1391215594430402742> Make sure your image follows all server rules. "
                "*Inappropriate, NSFW, or rule-breaking photos will result in an **instant ban***."
            )

            view = self.CustomizeConfirmView(bg_bytes=bg_bytes, user_id=user_id)
            await interaction.followup.send(
                content=msg, file=mock_card, view=view, ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"Failed to generate preview: {e}", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Balance(bot))

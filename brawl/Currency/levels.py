import asyncio
import io
import math
import os
import random
import time
from datetime import datetime, timezone

import aiohttp
import asyncpg
import discord
from discord import app_commands
from discord.ext import commands, tasks
from firebase_admin import db
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from brawl.Currency.card import plain, render
from brawl.Currency.config import (
    LADDER,
    XP_BOOSTER_MULTIPLIER,
    XP_COOLDOWN,
    XP_PER_MESSAGE,
    XP_ULTRA_MULTIPLIER,
)
from brawl.Currency.home import background
from brawl.Currency.ladder import lessons
from brawl.Currency.panel import framed, notice
from brawl.Currency.rewardcard import draw_level_up


class LevelRewardInfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        custom_id="level_info",
        emoji="<:information:855023058255478794>",
    )
    async def level_info(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        from brawl.Currency.how import HowView, page_file

        await interaction.response.send_message(
            file=await page_file("levels"), view=HowView("levels"), ephemeral=True
        )

    @discord.ui.button(
        style=discord.ButtonStyle.grey,
        disabled=True,
        label="Use /balance to view card",
        custom_id="level_card",
    )
    async def level_card(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        pass


LEVEL_REWARDS = {
    5: 866947914286759957,
    10: 866947962273267712,
    20: 866948001057865759,
    35: 866948039973404692,
    50: 866948080618962954,
    69: 866948113906663424,
    90: 1335747405571948635,
}


def xp_for_level(level: int) -> int:
    """XP required to go from this level to the next."""
    return (100 * level) + 75


def level_up_reward(level: int) -> tuple:
    """(Beans, Tokens) paid for reaching this level."""
    return 200 + int(50 * math.log(level)), level // 10 if level % 10 == 0 else 0


def get_level(xp: int) -> tuple:
    """Calculate level and progress based on total XP."""
    level = 0
    xp_needed = xp_for_level(level)

    while xp >= xp_needed:
        xp -= xp_needed
        level += 1
        xp_needed = xp_for_level(level)

    return level, xp, xp_needed


@app_commands.guild_only()
class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.cooldowns = {}  # (guild_id, user_id): last_xp_time
        self.pool = None
        self.bot.loop.create_task(self.create_pool())
        super().__init__()

    async def create_pool(self):
        try:
            self.pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
        except Exception as e:
            print(f"Failed to create DB pool: {e}")

    async def level_of(self, user_id: int, guild_id: int) -> int:
        if not self.pool:
            return 0
        async with self.pool.acquire() as conn:
            level = await conn.fetchval(
                "SELECT level FROM levels WHERE id = $1 AND guild = $2",
                str(user_id),
                str(guild_id),
            )
        return level or 0

    async def add_xp(
        self,
        user_id: int,
        guild_id: int,
        xp_amount: int,
        message: discord.Message = None,
        booster: bool = False,
        ultra: bool = False,
    ) -> None:
        from brawl.Currency.helper import BEAN_EMOTE, REPLY_EMOTE, TOKEN_EMOTE

        """Add XP to a user and update their level."""
        if not self.pool:
            return

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT xp, level FROM levels WHERE id = $1 AND guild = $2",
                str(user_id),
                str(guild_id),
            )

            if row:
                total_xp = row["xp"]
                current_level = row["level"]
            else:
                total_xp = 0
                current_level = 0

            total_xp += xp_amount
            new_level, _, _ = get_level(total_xp)

            if message:
                username = message.author.name
                avatar = str(message.author.display_avatar.url)
                last_channel = str(message.channel.id)
                await conn.execute(
                    """
                    INSERT INTO levels (id, guild, xp, level, messages, username, avatar, lastChannel)
                    VALUES ($1, $2, $3, $4, 1, $5, $6, $7)
                    ON CONFLICT (id, guild) DO UPDATE SET
                        xp = $3,
                        level = $4,
                        messages = levels.messages + 1,
                        username = $5,
                        avatar = $6,
                        lastChannel = $7
                """,
                    str(user_id),
                    str(guild_id),
                    total_xp,
                    new_level,
                    username,
                    avatar,
                    last_channel,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO levels (id, guild, xp, level, messages, username, avatar, lastChannel)
                    VALUES ($1, $2, $3, $4, 1, '', '', '')
                    ON CONFLICT (id, guild) DO UPDATE SET
                        xp = $3,
                        level = $4
                """,
                    str(user_id),
                    str(guild_id),
                    total_xp,
                    new_level,
                )

            if new_level > current_level:
                assigned_roles = await self.assign_level_roles(
                    user_id, guild_id, current_level, new_level
                )
                if message:
                    beans_earned, tokens_earned = level_up_reward(new_level)

                    currency_cog = self.bot.get_cog("CurrencySystem")
                    if currency_cog:
                        await currency_cog.add_beans(
                            str(user_id), beans_earned, reason="level_up"
                        )
                        if tokens_earned > 0:
                            await currency_cog.add_tokens(
                                str(user_id), tokens_earned, reason="level_up"
                            )

                    if booster:
                        emoji = "<a:serverboost:1457471812731404450>"
                    elif ultra:
                        emoji = "<a:TrophyThumbsUp:1394194270617079859>"
                    else:
                        emoji = "<a:SpikeWin:1391625613273727137>"

                    final_msg = "\n\n".join(lessons(current_level, new_level))

                    try:
                        avatar = await message.author.display_avatar.replace(
                            size=128
                        ).read()
                    except Exception:
                        avatar = b""
                    leveled = {
                        "name": plain(message.author.display_name),
                        "avatar": avatar,
                        "level": new_level,
                        "beans": beans_earned,
                        "tokens": tokens_earned,
                        "unlocks": [("New role", plain(r.name)) for r in assigned_roles]
                        + [
                            ("Unlocked", name)
                            for need, name, _ in LADDER.values()
                            if current_level < need <= new_level
                        ],
                        "background": background(user_id),
                    }
                    try:
                        await message.channel.send(
                            **framed(
                                await render(draw_level_up, leveled, name="level_up"),
                                f"{emoji} Level up",
                                final_msg,
                                tone="gold",
                            ),
                            **(
                                {"view": LevelRewardInfoView()}
                                if new_level <= 20
                                else {}
                            ),
                        )
                    except Exception as error:
                        print(f"Level up message failed: {error}")

    async def assign_level_roles(
        self, user_id: int, guild_id: int, old_level: int, new_level: int
    ) -> list[discord.Role]:
        """Assign level roles appropriately, handling intermediate levels."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []
        member = guild.get_member(user_id)
        if not member:
            return []

        assigned_roles = []
        for level, role_id in LEVEL_REWARDS.items():
            if old_level < level <= new_level:
                role = guild.get_role(role_id)
                if role:
                    try:
                        await member.add_roles(role)
                        assigned_roles.append(role)
                    except:
                        pass
        return assigned_roles

    async def validate_user_level_role(self, user_id: int, guild_id: int) -> None:
        """Validate and correct a user's level role based on their current level."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        member = guild.get_member(user_id)
        if not member:
            return

        if not self.pool:
            return
        level = await self.pool.fetchval(
            "SELECT level FROM levels WHERE id = $1 AND guild = $2",
            str(user_id),
            str(guild_id),
        )
        if level is None:
            return

        for req_level, role_id in LEVEL_REWARDS.items():
            role = guild.get_role(role_id)
            if role:
                if level >= req_level:
                    if role not in member.roles:
                        await member.add_roles(role)
                else:
                    if role in member.roles:
                        await member.remove_roles(role)

    @commands.Cog.listener()
    async def on_message(self, message):
        if (
            message.author.bot
            or not message.guild
            or message.guild.id != 791534106919305226
        ):
            return

        user_id = message.author.id
        guild_id = message.guild.id
        key = (guild_id, user_id)

        current_time = time.time()
        if key in self.cooldowns and current_time - self.cooldowns[key] < XP_COOLDOWN:
            return

        xp_gain = random.randint(*XP_PER_MESSAGE)

        booster = False
        booster_role = message.guild.premium_subscriber_role
        if booster_role in message.author.roles:
            xp_gain *= XP_BOOSTER_MULTIPLIER
            booster = True

        ultra = False
        ultra_role = message.guild.get_role(1457507581227700374)
        if ultra_role and ultra_role in message.author.roles:
            xp_gain *= XP_ULTRA_MULTIPLIER
            ultra = True

        await self.add_xp(
            user_id, guild_id, xp_gain, message, booster=booster, ultra=ultra
        )

        self.cooldowns[key] = current_time

    async def generate_rank_card(
        self,
        user: discord.Member,
        xp: int,
        level: int,
        current_xp: int,
        xp_needed: int,
        rank: int,
    ) -> discord.File:
        WIDTH, HEIGHT = 900, 250
        BG = (34, 34, 38)
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
        draw = ImageDraw.Draw(img)

        def format_number(num: int) -> str:
            """Convert a number to a compact string with 'k' for thousands, max 3 digits."""
            if num < 1000:
                return str(num)
            elif num < 1_000_000:
                value = num / 1000
                if value < 10:
                    return f"{value:.2f}".rstrip("0").rstrip(".") + "K"
                elif value < 100:
                    return f"{value:.1f}".rstrip("0").rstrip(".") + "K"
                else:
                    return f"{int(value)}k"
            else:
                value = num / 1_000_000
                return f"{value:.2f}M".rstrip("0").rstrip(".")

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

        LABEL_SIZE = 18
        XP_SMALL = 26
        BIG_NUM_SIZE = 54
        USERNAME_MAX = 42
        USERNAME_MIN = 18

        label_font = try_load_font(regular_candidates, LABEL_SIZE)
        xp_font = try_load_font(regular_candidates, XP_SMALL)
        big_num_font = try_load_font(bold_candidates, BIG_NUM_SIZE)

        AVATAR_SIZE = 180
        AVATAR_X = 40
        AVATAR_Y = 35

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
            draw.ellipse(
                (
                    AVATAR_X - 3,
                    AVATAR_Y - 3,
                    AVATAR_X + AVATAR_SIZE + 3,
                    AVATAR_Y + AVATAR_SIZE + 3,
                ),
                outline=(255, 140, 0),
                width=4,
            )

        badge_size = 80
        badge_gap = 20
        badge_y = AVATAR_Y - 10
        badge_x = AVATAR_X + AVATAR_SIZE + 30
        badge_icons = []
        user_roles = sorted(user.roles, key=lambda r: r.position, reverse=True)
        for role in user_roles:
            if role.icon:
                badge_icons.append(role.icon.url)
            if len(badge_icons) >= 3:
                break
        for badge_url in badge_icons:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(badge_url) as resp:
                        badge_bytes = await resp.read()
                badge_img = (
                    Image.open(io.BytesIO(badge_bytes))
                    .convert("RGBA")
                    .resize((badge_size, badge_size))
                )
                img.paste(badge_img, (badge_x, badge_y), badge_img)
                badge_x += badge_size + badge_gap
            except Exception:
                continue

        bar_x = AVATAR_X + AVATAR_SIZE + 30
        bar_height = 34
        right_margin = 40
        bar_right_limit = WIDTH - right_margin - 20
        bar_width = bar_right_limit - bar_x
        bar_y = HEIGHT - 70
        fill_color = (115, 219, 250)
        for role in user_roles:
            if role.color.value != 0:
                fill_color = role.color.to_rgb()
                break

        safe_xp_needed = max(1, int(xp_needed))
        current_xp_str = format_number(int(current_xp))
        rest_xp_str = f" / {format_number(safe_xp_needed)} XP"
        xp_width_total = draw.textlength(
            current_xp_str, font=xp_font
        ) + draw.textlength(rest_xp_str, font=xp_font)

        username_text = "@" + str(user.name)
        username_font = None
        available_for_username = bar_width - xp_width_total - 20

        for size in range(USERNAME_MAX, USERNAME_MIN - 1, -1):
            f = try_load_font(bold_candidates, size)
            if draw.textlength(username_text, font=f) <= available_for_username:
                username_font = f
                chosen_username_size = size
                break
        if username_font is None:
            chosen_username_size = USERNAME_MIN
            username_font = try_load_font(bold_candidates, chosen_username_size)
        username_x = bar_x
        username_y = bar_y - chosen_username_size - 26
        while (
            draw.textlength(username_text, font=username_font) > available_for_username
            and len(username_text) > 3
        ):
            username_text = username_text[:-4] + "..."
        draw.text(
            (username_x, username_y),
            username_text,
            font=username_font,
            fill=(255, 255, 255),
        )

        xp_x = bar_x + bar_width - xp_width_total
        xp_y = username_y + (chosen_username_size - XP_SMALL)
        draw.text((xp_x, xp_y), current_xp_str, font=xp_font, fill=(255, 255, 255))
        cur_w = draw.textlength(current_xp_str, font=xp_font)
        draw.text((xp_x + cur_w, xp_y), rest_xp_str, font=xp_font, fill=(170, 170, 170))

        padding_between = 80
        rank_label = "RANK"
        rank_value = f"{int(rank)}"
        level_label = "LEVEL"
        level_value = str(int(level))

        rank_label_w = draw.textlength(rank_label, font=label_font)
        rank_value_w = draw.textlength(rank_value, font=big_num_font)
        level_value_w = draw.textlength(level_value, font=big_num_font)
        level_label_w = draw.textlength(level_label, font=label_font)

        rank_x = (
            WIDTH - right_margin - rank_value_w - level_value_w - padding_between - 50
        )
        rank_label_y = 26
        draw.text(
            (rank_x, rank_label_y), rank_label, font=label_font, fill=(200, 200, 200)
        )
        draw.text(
            (rank_x, rank_label_y + LABEL_SIZE + 6),
            rank_value,
            font=big_num_font,
            fill=(255, 255, 255),
        )

        level_x = rank_x + rank_value_w + padding_between
        draw.text(
            (level_x, rank_label_y), level_label, font=label_font, fill=(200, 200, 200)
        )
        draw.text(
            (level_x, rank_label_y + LABEL_SIZE + 6),
            level_value,
            font=big_num_font,
            fill=fill_color,
        )

        radius = bar_height // 2
        bg_bar_color = (60, 60, 60)
        border_color = (90, 90, 90)
        draw.rounded_rectangle(
            [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)],
            radius=radius,
            fill=bg_bar_color,
        )
        draw.rounded_rectangle(
            [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)],
            radius=radius,
            outline=border_color,
            width=2,
        )

        progress = min(max(0.0, float(current_xp) / safe_xp_needed), 1.0)
        progress_width = int(bar_width * progress)
        if progress_width > 0:
            draw.rounded_rectangle(
                [(bar_x, bar_y), (bar_x + progress_width, bar_y + bar_height)],
                radius=radius,
                fill=fill_color,
            )

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename="rank.png")


@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
class LevelingAdmin(commands.GroupCog, name="xp"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(name="add", description="Add XP to a user")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        user="The user to add XP to", amount="The amount of XP to add"
    )
    async def xp_add(
        self, interaction: discord.Interaction, user: discord.Member, amount: int
    ):
        """Add XP to a user."""
        cog = self.bot.get_cog("Leveling")
        if cog:
            await cog.add_xp(user.id, interaction.guild.id, amount)
            await interaction.response.send_message(
                embed=notice(f"Added {amount} XP to {user.mention}.")
            )
        else:
            await interaction.response.send_message(
                embed=notice("Leveling system not available."), ephemeral=True
            )

    @app_commands.command(name="remove", description="Remove XP from a user")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        user="The user to remove XP from", amount="The amount of XP to remove"
    )
    async def xp_remove(
        self, interaction: discord.Interaction, user: discord.Member, amount: int
    ):
        """Remove XP from a user."""
        cog = self.bot.get_cog("Leveling")
        if cog:
            await cog.add_xp(user.id, interaction.guild.id, -amount)
            await interaction.response.send_message(
                embed=notice(f"Removed {amount} XP from {user.mention}.")
            )
        else:
            await interaction.response.send_message(
                embed=notice("Leveling system not available."), ephemeral=True
            )

    @app_commands.command(name="reset", description="Reset a user's XP")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="The user to reset")
    async def xp_reset(self, interaction: discord.Interaction, user: discord.Member):
        """Reset a user's XP and level."""
        cog = self.bot.get_cog("Leveling")
        if cog and cog.pool:
            async with cog.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM levels WHERE id = $1 AND guild = $2",
                    str(user.id),
                    str(interaction.guild.id),
                )
            await interaction.response.send_message(
                embed=notice(f"Reset XP for {user.mention}.")
            )
        else:
            await interaction.response.send_message(
                embed=notice("Leveling system not available."), ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Leveling(bot))
    await bot.add_cog(LevelingAdmin(bot))

import asyncio
import re
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View
from firebase_admin import db

from brawl.Currency.db import (
    g_table_kicks,
    g_tables,
    g_user_tables,
    u_table_notifications,
)
from brawl.Currency.helper import (
    BEAN_EMOTE,
    MAIN_GUILD_ID,
    NO_EMOTE,
    TABLE_QUEST_TYPES,
    TOKEN_EMOTE,
    YES_EMOTE,
)


class TableConfigModal(Modal, title="Configure Table"):
    name = TextInput(
        label="Table Name", placeholder="Enter table name", max_length=32, required=True
    )
    motto = TextInput(
        label="Table Motto",
        placeholder="Enter table motto",
        max_length=100,
        required=True,
    )
    color = TextInput(
        label="Hex Color", placeholder="#FFFFFF", max_length=7, required=True
    )
    emoji = TextInput(
        label="Emoji",
        placeholder="Enter emoji (unicode or custom)",
        max_length=60,
        required=True,
    )

    def __init__(self, current_data=None):
        super().__init__()
        if current_data:
            self.name.default = current_data.get("name", "")
            self.motto.default = current_data.get("motto", "")
            self.color.default = current_data.get("color", "#FFFFFF")
            self.emoji.default = current_data.get("emoji", "")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()


class TableCloseModal(Modal, title="Confirm Table Closure"):
    confirmation = TextInput(
        label="Type table name to confirm",
        placeholder="Enter exact table name",
        required=True,
    )

    def __init__(self, table_name):
        super().__init__()
        self.table_name = table_name

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation.value != self.table_name:
            await interaction.response.send_message(
                f"{NO_EMOTE} Confirmation failed. Names don't match.", ephemeral=True
            )
            return
        await interaction.response.defer()


@app_commands.guild_only()
class TableSystem(commands.GroupCog, name="table"):
    def __init__(self, bot):
        self.bot = bot
        self.weekly_reset_task = self.bot.loop.create_task(self.weekly_bean_reset())

    def _get_table_ref(self, guild_id, table_name=None):
        if table_name:
            return g_tables(guild_id, table_name)
        return g_tables(guild_id)

    def _get_user_table_ref(self, guild_id, user_id):
        return g_user_tables(guild_id, user_id)

    def _pref_ref(self, user_id):
        return u_table_notifications(user_id)

    def _kick_ref(self, guild_id, user_id, table_name):
        return g_table_kicks(guild_id, user_id, table_name)

    async def should_send_dm(self, user_id):
        data = self._pref_ref(user_id).get()
        return data.get("enabled", True) if data else True

    def initialize_table_quest(self, table_ref):
        quest_data = {
            "type": "bean_collector",
            "current_tier": 0,
            "completed_tiers": [],
            "progress": 0,
            "start_time": time.time(),
        }
        table_ref.update({"quest": quest_data})
        return quest_data

    async def check_and_reward_quest(self, guild_id, table_name, current_beans):
        table_ref = self._get_table_ref(guild_id, table_name)
        table_data = table_ref.get()

        if not table_data or not table_data.get("formalized", False):
            return None

        quest = table_data.get("quest")
        if not quest:
            quest = self.initialize_table_quest(table_ref)

        quest_config = TABLE_QUEST_TYPES["bean_collector"]
        current_tier = quest.get("current_tier", 0)
        completed_tiers = quest.get("completed_tiers", [])

        if current_tier < len(quest_config["targets"]):
            target = quest_config["targets"][current_tier]

            if current_beans >= target and current_tier not in completed_tiers:
                reward_per_member = quest_config["rewards"][current_tier]
                members = table_data.get("members", [])

                currency_cog = self.bot.get_cog("CurrencySystem")
                if currency_cog:
                    for member_id in members:
                        try:
                            await currency_cog.add_beans(
                                member_id, reward_per_member, skip_quest_check=True
                            )
                        except Exception as e:
                            print(f"Error rewarding quest to user {member_id}: {e}")

                for member_id in members:
                    if await self.should_send_dm(member_id):
                        try:
                            user = await self.bot.fetch_user(member_id)
                            if user:
                                embed = discord.Embed(
                                    title=f"🎯 {table_data['emoji']} Quest Milestone Reached!",
                                    description=f"**{table_data['name']}** has completed a Bean Collector milestone!",
                                    color=int(table_data["color"].lstrip("#"), 16),
                                )

                                embed.add_field(
                                    name="🎊 Milestone",
                                    value=f"Tier {current_tier + 1}: {BEAN_EMOTE} **{target:,} Beans** collected",
                                    inline=False,
                                )
                                embed.add_field(
                                    name="🎁 Your Reward",
                                    value=f"{BEAN_EMOTE} **{reward_per_member:,} Beans** added to your balance!",
                                    inline=False,
                                )

                                if current_tier + 1 < len(quest_config["targets"]):
                                    next_target = quest_config["targets"][
                                        current_tier + 1
                                    ]
                                    next_reward = quest_config["rewards"][
                                        current_tier + 1
                                    ]
                                    embed.add_field(
                                        name="🎯 Next Milestone",
                                        value=f"Collect {BEAN_EMOTE} **{next_target:,} Beans** to earn {BEAN_EMOTE} **{next_reward:,} Beans** each!",
                                        inline=False,
                                    )
                                else:
                                    embed.add_field(
                                        name="🏆 All Milestones Complete!",
                                        value="Your table has completed all quest tiers this week!",
                                        inline=False,
                                    )

                                embed.set_footer(
                                    text=f"Keep chatting to help {table_data['name']} reach the next goal!"
                                )

                                await user.send(embed=embed)
                        except Exception as e:
                            print(
                                f"Error sending quest milestone DM to user {member_id}: {e}"
                            )

                completed_tiers.append(current_tier)
                table_ref.update(
                    {
                        "quest": {
                            **quest,
                            "current_tier": current_tier + 1,
                            "completed_tiers": completed_tiers,
                            "progress": current_beans,
                        }
                    }
                )

                return {
                    "tier": current_tier,
                    "target": target,
                    "reward": reward_per_member,
                    "members_count": len(members),
                }

        table_ref.update({"quest/progress": current_beans})
        return None

    async def weekly_bean_reset(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.now(timezone.utc)
            days_until_sunday = (6 - now.weekday()) % 7
            next_sunday = now + timedelta(days=days_until_sunday)
            next_sunday = next_sunday.replace(hour=0, minute=0, second=0, microsecond=0)

            if now.weekday() == 6 and now.hour == 0 and now.minute <= 5:
                all_tables = self._get_table_ref(MAIN_GUILD_ID).get() or {}

                formalized_tables = {
                    name: data
                    for name, data in all_tables.items()
                    if data.get("formalized", False)
                }

                if formalized_tables:
                    sorted_tables = sorted(
                        formalized_tables.items(),
                        key=lambda x: x[1].get("weekly_beans", 0),
                        reverse=True,
                    )

                    top_table_name, top_table_data = sorted_tables[0]
                    top_table_members = top_table_data.get("members", [])
                    top_table_beans = top_table_data.get("weekly_beans", 0)

                    if top_table_members and top_table_beans > 0:
                        currency_cog = self.bot.get_cog("CurrencySystem")

                        if currency_cog:
                            for member_id in top_table_members:
                                try:
                                    await currency_cog.add_tokens(member_id, 3)

                                    if await self.should_send_dm(member_id):
                                        user = self.bot.get_user(member_id)
                                        if user:
                                            try:
                                                embed = discord.Embed(
                                                    title="<a:tada:1227425729654820885> Weekly Table Winner!",
                                                    description=(
                                                        f"Congratulations! Your table **{top_table_data['name']}** {top_table_data['emoji']} "
                                                        f"was the **#1 top table** this week with **{top_table_beans:,}** {BEAN_EMOTE} beans earned as a table!\n\n"
                                                        f"Each member of the table, including you, has been awarded **3 {TOKEN_EMOTE} Tokens** as a reward for your table's achievement!"
                                                    ),
                                                    color=discord.Color.gold(),
                                                )
                                                embed.set_footer(
                                                    text="Keep earning beans this week to compete again!"
                                                )
                                                await user.send(embed=embed)
                                            except discord.Forbidden:
                                                pass
                                except Exception as e:
                                    print(f"Error rewarding user {member_id}: {e}")

                            channel = self.bot.get_channel(1400797909976612884)
                            if channel:
                                log_embed = discord.Embed(
                                    title="<a:tada:1227425729654820885> Weekly Top Table Rewards Distributed",
                                    description=(
                                        f"**Table:** {top_table_data['emoji']} {top_table_data['name']}\n"
                                        f"**Weekly Beans:** {BEAN_EMOTE} {top_table_beans:,}\n"
                                        f"**Members Rewarded:** {len(top_table_members)}\n"
                                        f"**Reward:** 3 {TOKEN_EMOTE} Tokens per member"
                                    ),
                                    color=discord.Color.gold(),
                                )
                                await channel.send(embed=log_embed)

                for table_name in all_tables:
                    table_ref = self._get_table_ref(MAIN_GUILD_ID, table_name)
                    table_ref.update({"weekly_beans": 0, "user_contributions": {}})
                    self.initialize_table_quest(table_ref)

                channel = self.bot.get_channel(1400797909976612884)
                if channel:
                    await channel.send(
                        embed=discord.Embed(
                            title="🔄 Weekly Table Bean Reset",
                            description="All table bean contributions have been reset.",
                            color=discord.Color.green(),
                        )
                    )

            await asyncio.sleep(3600)

    async def update_table_formalization(self, guild_id, table_name):
        table_ref = self._get_table_ref(guild_id, table_name)
        table_data = table_ref.get() or {}

        is_formalized = len(table_data.get("members", [])) >= 5
        was_formalized = table_data.get("formalized", False)

        if is_formalized != was_formalized:
            table_ref.update({"formalized": is_formalized})

            if is_formalized and not was_formalized:
                host_id = table_data["host"]
                if await self.should_send_dm(host_id):
                    host = self.bot.get_user(host_id)
                    if host:
                        try:
                            await host.send(
                                f"🎉 Your table **{table_data['name']}** has been officially recognized with 5+ people seated! You now have access to table perks."
                            )
                        except:
                            pass

    async def get_user_table(self, user_id, guild_id=MAIN_GUILD_ID):
        user_table_ref = self._get_user_table_ref(guild_id, user_id)
        table_name = user_table_ref.get()
        if not table_name:
            return None

        table_ref = self._get_table_ref(guild_id, table_name)
        return table_ref.get()

    async def table_autocomplete(self, interaction: discord.Interaction, current: str):
        tables = self._get_table_ref(interaction.guild.id).get() or {}
        return [
            app_commands.Choice(name=data["name"], value=name)
            for name, data in tables.items()
            if current.lower() in data["name"].lower()
            and len(data.get("members", [])) < 10
        ][:25]

    @app_commands.command(name="seat", description="Take a seat at (join) a table")
    @app_commands.describe(
        table="The table to join (choose from autocomplete, only tables with available seats will show)"
    )
    @app_commands.autocomplete(table=table_autocomplete)
    async def table_seat(self, interaction: discord.Interaction, table: str):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} This command is only available in the main server.",
                ephemeral=True,
            )

        if current_table := await self.get_user_table(
            interaction.user.id, interaction.guild.id
        ):
            return await interaction.response.send_message(
                f"{NO_EMOTE} You're already seated at **{current_table['name']}**. Stand up first with `/table leave`.",
                ephemeral=True,
            )

        table_ref = self._get_table_ref(interaction.guild.id, table.lower())
        table_data = table_ref.get()

        if not table_data:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Table not found.", ephemeral=True
            )

        kick_ref = self._kick_ref(
            interaction.guild.id, interaction.user.id, table.lower()
        )
        kick_time = kick_ref.get()

        if kick_time:
            elapsed = time.time() - kick_time
            if elapsed < 1209600:
                remaining = 1209600 - elapsed
                future_time = int(time.time() + remaining)
                return await interaction.response.send_message(
                    f"{NO_EMOTE} You were kicked from this table and cannot rejoin until <t:{future_time}:R>.",
                    ephemeral=True,
                )
            else:
                kick_ref.delete()

        if len(table_data.get("members", [])) >= 10:
            return await interaction.response.send_message(
                f"{NO_EMOTE} This table is full (10/10 seats).", ephemeral=True
            )

        members = table_data.get("members", [])
        members.append(interaction.user.id)
        table_ref.update({"members": members})
        self._get_user_table_ref(interaction.guild.id, interaction.user.id).set(
            table.lower()
        )
        await self.update_table_formalization(interaction.guild.id, table.lower())

        host_id = table_data["host"]
        if (
            host_id != interaction.user.id
            and await self.should_send_dm(host_id)
            and (host := self.bot.get_user(host_id))
        ):
            try:
                await host.send(
                    f"👤 **{interaction.user.display_name}** has taken a seat at your table **{table_data['name']}**!"
                )
            except:
                pass

        embed = discord.Embed(
            title=f"{table_data['emoji']} Table Joined: {table_data['name']}",
            description=f"\"{table_data['motto']}\"",
            color=int(table_data["color"].lstrip("#"), 16),
        )
        embed.add_field(name="🍽️ Host", value=f"<@{table_data['host']}>", inline=False)
        embed.add_field(
            name="👥 People Seated",
            value=f"Currently **{len(members)}/10** people seated!",
            inline=False,
        )
        embed.add_field(name="🎨 Color", value=table_data["color"], inline=True)
        embed.add_field(
            name="📅 Reserved At",
            value=f"<t:{int(table_data['created_at'])}:F>",
            inline=True,
        )
        embed.add_field(
            name="📋 Status",
            value=(
                f"{YES_EMOTE} Officially recognized table!"
                if table_data.get("formalized")
                else f"{NO_EMOTE} Not yet recognized (requires **5 people seated**)."
            ),
            inline=False,
        )
        embed.set_footer(
            text="Once your table is officially recognized, its emoji will be added to the daily chat bean notification"
        )

        await interaction.response.send_message(
            content=f"{YES_EMOTE} You've taken a seat at **{table_data['name']}**!",
            embed=embed,
        )

    @app_commands.command(name="leave", description="Leave your current table")
    async def table_leave(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} This command is only available in the main server.",
                ephemeral=True,
            )

        if not (
            table_data := await self.get_user_table(
                interaction.user.id, interaction.guild.id
            )
        ):
            return await interaction.response.send_message(
                f"{NO_EMOTE} You're not seated at any table.", ephemeral=True
            )

        table_name = table_data["name"].lower()
        table_ref = self._get_table_ref(interaction.guild.id, table_name)

        members = table_data.get("members", [])
        members.remove(interaction.user.id)
        table_ref.update({"members": members})
        self._get_user_table_ref(interaction.guild.id, interaction.user.id).delete()

        if table_data["host"] == interaction.user.id:
            if members:
                new_host = members[0]
                table_ref.update({"host": new_host})
                if await self.should_send_dm(new_host):
                    new_host_user = self.bot.get_user(new_host)
                    if new_host_user:
                        try:
                            await new_host_user.send(
                                f"🍽️ You're now the host of table **{table_data['name']}**!"
                            )
                        except:
                            pass
            else:
                table_ref.delete()
                await interaction.response.send_message(
                    f"{YES_EMOTE} You've left table **{table_data['name']}**. The table has been closed as it has no one seated."
                )
                return

        await self.update_table_formalization(interaction.guild.id, table_name)

        await interaction.response.send_message(
            f"{YES_EMOTE} You've left table **{table_data['name']}**. Feel free to take a seat at another table!"
        )

    @app_commands.command(name="reserve", description="Reserve (create) a new table")
    @app_commands.describe(
        name="Table name",
        motto="Table motto",
        color="Hex color code",
        emoji="Table emoji (only default emojis, no custom emojis)",
    )
    async def table_reserve(
        self,
        interaction: discord.Interaction,
        name: str,
        motto: str,
        color: str,
        emoji: str,
    ):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} This command is only available in the main server.",
                ephemeral=True,
            )

        if current_table := await self.get_user_table(
            interaction.user.id, interaction.guild.id
        ):
            return await interaction.response.send_message(
                f"{NO_EMOTE} You're already seated at **{current_table['name']}**. Stand up first with `/table leave`.",
                ephemeral=True,
            )

        if not re.match(r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$", color):
            return await interaction.response.send_message(
                f"{NO_EMOTE} Invalid color format. Use hex format like #FFFFFF.",
                ephemeral=True,
            )

        all_tables = self._get_table_ref(interaction.guild.id).get() or {}
        for existing_table in all_tables.values():
            if existing_table["name"].lower() == name.lower():
                return await interaction.response.send_message(
                    f"{NO_EMOTE} A table with that name already exists.", ephemeral=True
                )
            if existing_table["emoji"] == emoji:
                return await interaction.response.send_message(
                    f"{NO_EMOTE} A table with that emoji already exists.",
                    ephemeral=True,
                )

        table_data = {
            "name": name,
            "motto": motto,
            "color": color,
            "emoji": emoji,
            "host": interaction.user.id,
            "members": [interaction.user.id],
            "created_at": time.time(),
            "formalized": False,
            "weekly_beans": 0,
            "user_contributions": {},
            "quest": {
                "type": "bean_collector",
                "current_tier": 0,
                "completed_tiers": [],
                "progress": 0,
                "start_time": time.time(),
            },
        }

        self._get_table_ref(interaction.guild.id, name.lower()).set(table_data)
        self._get_user_table_ref(interaction.guild.id, interaction.user.id).set(
            name.lower()
        )
        embed = discord.Embed(
            title=f"{emoji} Table Reserved: {name}",
            description=f'"{motto}"',
            color=discord.Color.from_str(color),
        )
        embed.add_field(
            name="🍽️ Host",
            value=f"{interaction.user.mention} ({interaction.user.display_name})",
            inline=False,
        )
        embed.add_field(
            name="👥 People Seated",
            value="Currently **1 person** (you). Ask others to use `/table seat` to reach **5 people seated** and get your table officially recognized.",
            inline=False,
        )
        embed.add_field(name="🎨 Color", value=color, inline=True)
        embed.add_field(
            name="📅 Reserved At", value=f"<t:{int(time.time())}:F>", inline=True
        )
        embed.add_field(
            name="📋 Status",
            value=f"{NO_EMOTE} Not yet recognized (requires **5 people seated**).",
            inline=False,
        )
        embed.set_footer(
            text="Once your table is officially recognized, your emoji will be added to the daily chat bean notification"
        )

        await interaction.response.send_message(
            content=f"{YES_EMOTE} Table **{name}** reserved successfully!", embed=embed
        )

    @app_commands.command(
        name="config", description="Configure your table (hosts only)"
    )
    async def table_config(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} This command is only available in the main server.",
                ephemeral=True,
            )

        if not (
            table_data := await self.get_user_table(
                interaction.user.id, interaction.guild.id
            )
        ):
            return await interaction.response.send_message(
                f"{NO_EMOTE} You're not seated at any table.", ephemeral=True
            )

        if table_data["host"] != interaction.user.id:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Only the table host can configure the table.",
                ephemeral=True,
            )

        modal = TableConfigModal(current_data=table_data)
        await interaction.response.send_modal(modal)
        await modal.wait()

        new_name = modal.name.value
        new_color = modal.color.value
        new_emoji = modal.emoji.value

        if not re.match(r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$", new_color):
            return await interaction.followup.send(
                f"{NO_EMOTE} Invalid color format. Use hex format like #FFFFFF.",
                ephemeral=True,
            )

        all_tables = self._get_table_ref(interaction.guild.id).get() or {}
        current_table_name = table_data["name"].lower()

        for table_name, existing_table in all_tables.items():
            if table_name == current_table_name:
                continue
            if existing_table["name"].lower() == new_name.lower():
                return await interaction.followup.send(
                    f"{NO_EMOTE} A table with that name already exists.", ephemeral=True
                )
            if existing_table["emoji"] == new_emoji:
                return await interaction.followup.send(
                    f"{NO_EMOTE} A table with that emoji already exists.",
                    ephemeral=True,
                )

        table_ref = self._get_table_ref(interaction.guild.id, current_table_name)
        updates = {
            "name": new_name,
            "motto": modal.motto.value,
            "color": new_color,
            "emoji": new_emoji,
        }

        if new_name.lower() != current_table_name:
            for member_id in table_data.get("members", []):
                self._get_user_table_ref(interaction.guild.id, member_id).set(
                    new_name.lower()
                )

            table_ref.delete()
            self._get_table_ref(interaction.guild.id, new_name.lower()).set(
                {**table_data, **updates}
            )
        else:
            table_ref.update(updates)

        embed = discord.Embed(
            title=f"{new_emoji} Table Updated: {new_name}",
            description=f'"{modal.motto.value}"',
            color=discord.Color.from_str(new_color),
        )

        embed.add_field(
            name="🍽️ Host",
            value=f"{interaction.user.mention} ({interaction.user.display_name})",
            inline=False,
        )
        embed.add_field(
            name="👥 People Seated",
            value=f"**{len(table_data.get('members', []))} people** currently at this table.",
            inline=False,
        )
        embed.add_field(name="🎨 Color", value=new_color, inline=True)
        embed.add_field(
            name="📅 Reserved At",
            value=f"<t:{int(table_data['created_at'])}:F>",
            inline=True,
        )
        embed.add_field(
            name="📋 Status",
            value=(
                f"{YES_EMOTE} Officially recognized table!"
                if table_data.get("formalized")
                else f"{NO_EMOTE} Not yet recognized (requires **5 people seated**)."
            ),
            inline=False,
        )
        embed.set_footer(
            text="Once your table is officially recognized, your emoji will be added to the daily chat bean notification"
        )

        await interaction.followup.send(
            content=f"{YES_EMOTE} Table **{new_name}** updated successfully!",
            embed=embed,
        )

    @app_commands.command(name="close", description="Close your table (hosts only)")
    async def table_close(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} This command is only available in the main server.",
                ephemeral=True,
            )

        if not (
            table_data := await self.get_user_table(
                interaction.user.id, interaction.guild.id
            )
        ):
            return await interaction.response.send_message(
                f"{NO_EMOTE} You're not seated at any table.", ephemeral=True
            )

        if table_data["host"] != interaction.user.id:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Only the table host can close the table.", ephemeral=True
            )

        modal = TableCloseModal(table_data["name"])
        await interaction.response.send_modal(modal)
        await modal.wait()
        table_name = table_data["name"].lower()

        for member_id in table_data.get("members", []):
            self._get_user_table_ref(interaction.guild.id, member_id).delete()

        self._get_table_ref(interaction.guild.id, table_name).delete()

        await interaction.followup.send(f"{YES_EMOTE} Table closed successfully!")

    @app_commands.command(name="mine", description="View your current table")
    async def table_mine(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.followup.send(
                f"{NO_EMOTE} This command is only available in the main server.",
                ephemeral=True,
            )
        if not (
            table_data := await self.get_user_table(
                interaction.user.id, interaction.guild.id
            )
        ):
            return await interaction.followup.send(
                f"{NO_EMOTE} You're not seated at any table.", ephemeral=True
            )
        host = await interaction.client.fetch_user(table_data["host"])
        host_name = host.mention if host else f"Unknown ({table_data['host']})"

        user_beans = table_data.get("user_contributions", {}).get(
            str(interaction.user.id), 0
        )

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

        if (quest := table_data.get("quest", {})) and table_data.get(
            "formalized", False
        ):
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
            (
                f"-# - {(await interaction.client.fetch_user(m)).mention}"
                if (await interaction.client.fetch_user(m))
                else f"-# - Unknown member ({m})"
            )
            for m in table_data.get("members", [])
        ]
        embed.add_field(
            name=f"📋 Seated Members ({len(table_data.get('members', []))}/10)",
            value="\n".join(members_list) if members_list else "No one seated",
            inline=True,
        )
        embed.add_field(
            name="☕ Cocoa Inventory",
            value=f"`{table_data.get('cocoa_inventory', 0)}` successful cocoa brews collected\n-# Everyone will earn {TOKEN_EMOTE} `2` for every 10 brews!",
            inline=True,
        )
        embed.set_footer(
            text="Once your table is officially recognized, your emoji will be added to the daily chat bean notification"
        )

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="dm", description="Toggle DM notifications for table rewards"
    )
    async def table_dm_toggle(self, interaction: discord.Interaction):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} This command is only available in the main server.",
                ephemeral=True,
            )

        ref = self._pref_ref(interaction.user.id)
        new_state = not ((data := ref.get() or {}).get("enabled", True))
        ref.set({"enabled": new_state, "updated_at": time.time()})
        if new_state:
            embed = discord.Embed(
                title="🔔 DM Notifications Enabled",
                description=(
                    "You will now receive DM notifications for:\n"
                    f"{YES_EMOTE} Weekly top table rewards ({TOKEN_EMOTE} Tokens)\n"
                    f"{YES_EMOTE} Table milestone achievements\n"
                    f"{YES_EMOTE} Table host transfers\n"
                    f"{YES_EMOTE} Members joining/leaving your table"
                ),
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="🔕 DM Notifications Disabled",
                description=(
                    "You will no longer receive DM notifications for table-related activities.\n\n"
                    f"-# *You can still check your table status and rewards using `/table mine`*"
                ),
                color=discord.Color.red(),
            )

        embed.set_footer(text="Use /table dm again to toggle this setting")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="kick", description="Kick a user from your table (Host only)"
    )
    @app_commands.describe(user="The user to kick")
    async def table_kick(self, interaction: discord.Interaction, user: discord.User):
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.response.send_message(
                f"{NO_EMOTE} This command is only available in the main server.",
                ephemeral=True,
            )

        if not (
            table_data := await self.get_user_table(
                interaction.user.id, interaction.guild.id
            )
        ):
            return await interaction.response.send_message(
                f"{NO_EMOTE} You're not seated at any table.", ephemeral=True
            )

        if table_data["host"] != interaction.user.id:
            return await interaction.response.send_message(
                f"{NO_EMOTE} Only the table host can kick members.", ephemeral=True
            )
        if user.id == interaction.user.id:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You cannot kick yourself.", ephemeral=True
            )

        if user.id not in table_data.get("members", []):
            return await interaction.response.send_message(
                f"{NO_EMOTE} That user is not at your table.", ephemeral=True
            )

        table_name = table_data["name"].lower()
        table_ref = self._get_table_ref(interaction.guild.id, table_name)
        members = table_data.get("members", [])
        if user.id in members:
            members.remove(user.id)
        table_ref.update({"members": members})
        self._get_user_table_ref(interaction.guild.id, user.id).delete()
        self._kick_ref(interaction.guild.id, user.id, table_name).set(time.time())
        await self.update_table_formalization(interaction.guild.id, table_name)
        if await self.should_send_dm(user.id):
            try:
                await user.send(
                    f"You've been kicked from **{table_data['name']}** and cannot rejoin for 14 days."
                )
            except:
                pass

        await interaction.response.send_message(
            f"{YES_EMOTE} Kicked <@{user.id}> from the table. They cannot rejoin for 14 days."
        )


async def setup(bot):
    await bot.add_cog(TableSystem(bot))

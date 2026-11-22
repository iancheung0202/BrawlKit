import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, View
from firebase_admin import db

from brawl.Utility.style import NO, YES

SYSTEMS = "/Team Find Reps System"
REPS = "/Team Find Reps"
SKIPPED_GUILD = 717029019270381578
DEFAULT_MAX = 999
COMMANDS = (
    "`-giverep <user> <amount>` - Give reputation points to a user\n"
    "`-toprep` - View the reputation leaderboard\n"
    "`-rep <user>` - Check your or another user's reputation points\n"
)
NOT_ENABLED = f"{NO} Enable the reputation system first."


def get_system(guild_id: int):
    for key, system in (db.reference(SYSTEMS).get() or {}).items():
        if system["Server ID"] == guild_id:
            return key, system
    return None, None


def get_rewards(system: dict) -> dict:
    rewards = system.get("Roles")
    return rewards if isinstance(rewards, dict) else {}


def set_rewards(key: str, rewards: dict):
    db.reference(SYSTEMS).child(key).update({"Roles": rewards or "None"})


def get_totals() -> dict:
    totals = {}
    for guild in (db.reference(REPS).get() or {}).values():
        for user_id, points in guild["Users"].items():
            totals[int(user_id)] = totals.get(int(user_id), 0) + points
    return totals


def status_embed(guild_id: int) -> discord.Embed:
    _, system = get_system(guild_id)
    if not system:
        return discord.Embed(
            title="Reputation System Not Enabled",
            description="This server does not have the reputation system enabled. Click the button below to enable it.",
            color=discord.Color.red(),
        )
    embed = discord.Embed(
        title="Reputation System",
        description=f"The reputation system is enabled. Users can only give a maximum of `{system['Max Rep']}` reputation points at once.",
        color=discord.Color.blurple(),
    )
    rewards = sorted(get_rewards(system).items(), key=lambda reward: reward[1])
    lines = [
        f"{index}. <@&{role_id}> • {cost} reps"
        for index, (role_id, cost) in enumerate(rewards, start=1)
    ]
    embed.add_field(name="Roles", value="\n".join(lines) or "None", inline=False)
    embed.add_field(name="Commands", value=COMMANDS)
    return embed


def user_id(word: str):
    digits = word.strip("<@!>")
    return int(digits) if digits.isdigit() else None


async def get_member(guild: discord.Guild, id: int):
    try:
        return guild.get_member(id) or await guild.fetch_member(id)
    except discord.HTTPException:
        return None


class MaxRepModal(Modal, title="Enable/Edit Reputation System"):
    max_rep = TextInput(
        label="Maximum Reputation Points",
        placeholder=f"Max reps at once (default: {DEFAULT_MAX})",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        value = self.max_rep.value.strip() or str(DEFAULT_MAX)
        if not value.isdigit() or int(value) < 1:
            await interaction.response.send_message(
                f"{NO} The maximum must be a whole number above 0.", ephemeral=True
            )
            return
        key, _ = get_system(interaction.guild.id)
        if key:
            db.reference(SYSTEMS).child(key).update({"Max Rep": int(value)})
        else:
            db.reference(SYSTEMS).push().set(
                {
                    "Server ID": interaction.guild.id,
                    "Max Rep": int(value),
                    "Roles": "None",
                }
            )
        await interaction.response.edit_message(
            embed=status_embed(interaction.guild.id)
        )


class AddRewardModal(Modal, title="Add a Custom Reward"):
    role_id = TextInput(label="Role ID", placeholder="Enter the role ID", max_length=50)
    cost = TextInput(
        label="Cost of Reward",
        placeholder="Must be a reasonable integer",
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        key, system = get_system(interaction.guild.id)
        role_id = self.role_id.value.strip()
        cost = self.cost.value.strip()
        if not key:
            error = NOT_ENABLED
        elif not role_id.isdigit() or not interaction.guild.get_role(int(role_id)):
            error = f"{NO} There is no role with that ID in this server."
        elif not cost.isdigit() or int(cost) < 1:
            error = f"{NO} The cost must be a whole number above 0."
        elif role_id in get_rewards(system):
            error = f"{NO} This role is already a reward in this server."
        else:
            set_rewards(key, {**get_rewards(system), role_id: int(cost)})
            await interaction.response.edit_message(
                embed=status_embed(interaction.guild.id)
            )
            return
        await interaction.response.send_message(error, ephemeral=True)


class RemoveRewardModal(Modal, title="Remove a Custom Reward"):
    role_id = TextInput(
        label="Role ID", placeholder="Enter the role ID to remove", max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        key, system = get_system(interaction.guild.id)
        role_id = self.role_id.value.strip()
        if not key:
            error = NOT_ENABLED
        elif role_id not in get_rewards(system):
            error = f"{NO} That role is not a reward in this server."
        else:
            rewards = get_rewards(system)
            del rewards[role_id]
            set_rewards(key, rewards)
            await interaction.response.edit_message(
                embed=status_embed(interaction.guild.id)
            )
            return
        await interaction.response.send_message(error, ephemeral=True)


class ReputationView(View):
    @discord.ui.button(
        label="Enable/Edit Reputation System", style=discord.ButtonStyle.green
    )
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MaxRepModal())

    @discord.ui.button(label="Disable Reputation System", style=discord.ButtonStyle.red)
    async def disable(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        key, _ = get_system(interaction.guild.id)
        if key:
            db.reference(SYSTEMS).child(key).delete()
        await interaction.response.edit_message(
            embed=status_embed(interaction.guild.id)
        )

    @discord.ui.button(label="Add Reward", style=discord.ButtonStyle.green, row=1)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddRewardModal())

    @discord.ui.button(label="Remove Reward", style=discord.ButtonStyle.red, row=1)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveRewardModal())


class ReputationSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.guild.id == SKIPPED_GUILD:
            return
        words = message.content.lower().split()
        if not words or words[0] not in ("-rep", "-toprep", "-giverep"):
            return
        _, system = get_system(message.guild.id)
        if not system:
            return
        if words[0] == "-rep":
            await self.show(message, words)
        elif words[0] == "-toprep":
            await self.top(message, words)
        else:
            await self.give(message, words, system)

    async def show(self, message: discord.Message, words: list):
        id = user_id(words[1]) if len(words) > 1 else None
        member = await get_member(message.guild, id) if id else None
        member = member or message.author
        points = get_totals().get(member.id, 0)
        await message.channel.send(f"**{member.name}**: **{points}** rep")

    async def top(self, message: discord.Message, words: list):
        count = 10
        if len(words) > 1 and words[1].isdigit():
            count = min(max(int(words[1]), 1), 50)
        totals = sorted(get_totals().items(), key=lambda total: -total[1])
        if not totals:
            await message.channel.send("No reputation data found.")
            return
        lines = []
        for id, points in totals[:count]:
            member = await get_member(message.guild, id)
            name = f"**{member.name}**" if member else f"<@{id}>"
            lines.append(f"{len(lines) + 1}. {name} `({id})` - **{points}**")
        await message.channel.send(
            embed=discord.Embed(
                title=f"Global Reputation Leaderboard - Top {count}",
                description="\n".join(lines),
                color=0xEB7660,
            )
        )

    async def give(self, message: discord.Message, words: list, system: dict):
        if len(words) < 3:
            await message.reply("Command Usage: `-giverep @user amount`")
            return
        id = user_id(words[1])
        member = await get_member(message.guild, id) if id else None
        if not member or not words[2].lstrip("-").isdigit():
            await message.reply(f"{NO} Invalid format. Use `-giverep @user amount`")
            return
        amount = int(words[2])
        if amount > system["Max Rep"]:
            await message.reply(
                f"{NO} You can't give more than {system['Max Rep']} reps at once."
            )
            return
        if member == message.author:
            await message.reply(f"{NO} You can't give yourself reps!")
            return
        if amount <= 0:
            await message.reply(f"{NO} You must give at least 1 rep.")
            return
        ref = db.reference(f"{REPS}/{message.guild.id}/Users/{member.id}")
        before = ref.get() or 0
        after = before + amount
        ref.set(after)
        embeds = []
        for role_id, cost in get_rewards(system).items():
            role = message.guild.get_role(int(role_id))
            if role and before < cost <= after:
                await member.add_roles(role)
                embeds.append(
                    discord.Embed(
                        description=f"**{member.name}** just earned a new role: **{role.mention}**",
                        color=discord.Color.green(),
                    )
                )
        await message.channel.send(
            f"{YES} Gave `{amount}` Rep to **{member.name}** (current - `{after}`)",
            embeds=embeds[:10],
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ReputationSystem(bot))

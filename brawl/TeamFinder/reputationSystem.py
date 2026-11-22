import datetime

import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, View
from firebase_admin import db

from brawl.Currency import wallet
from brawl.Currency.config import REP_BEANS, REP_PAID_DAILY
from brawl.Currency.helper import BEAN_EMOTE, MAIN_GUILD_ID
from brawl.Utility.style import NO

ROLES = f"/Team Find Rep Roles/{MAIN_GUILD_ID}"
REPS = f"/Team Find Reps/{MAIN_GUILD_ID}/Users"
DAYS = "/Team Find Rep Days"
LIKE = "<:Like:793027164731605033>"


def get_rewards() -> dict:
    """Role id to the rep it takes."""
    return db.reference(ROLES).get() or {}


def get_totals() -> dict:
    return {int(id): rep for id, rep in (db.reference(REPS).get() or {}).items()}


def rep_of(user_id: int) -> int:
    return db.reference(REPS).child(str(user_id)).get() or 0


def today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def status_embed() -> discord.Embed:
    rewards = sorted(get_rewards().items(), key=lambda reward: reward[1])
    lines = [
        f"{spot}. <@&{id}> at `{rep}` rep" for spot, (id, rep) in enumerate(rewards, 1)
    ]
    return discord.Embed(
        title=f"{LIKE} Reputation",
        description=(
            "A host gives rep to the teammates who played when they close a "
            f"request. Each rep also pays {BEAN_EMOTE} `{REP_BEANS}`, up to "
            f"`{REP_PAID_DAILY}` times a day.\n### Roles\n"
            + ("\n".join(lines) or "None yet")
        ),
        color=discord.Color.blurple(),
    )


async def add_rep(member: discord.Member, amount: int) -> list:
    """Changes a member's rep and returns the roles it newly earned them."""
    ref = db.reference(REPS).child(str(member.id))
    before = ref.get() or 0
    after = max(before + amount, 0)
    ref.set(after)
    earned = []
    for role_id, rep in get_rewards().items():
        role = member.guild.get_role(int(role_id))
        if role and before < rep <= after:
            await member.add_roles(role)
            earned.append(role)
    return earned


async def thank(member: discord.Member, host_id: int):
    """One rep from a host: once a day per host, and paid a few times a day.

    Returns (Beans paid, roles earned), or None when this host already gave today.
    """
    ref = db.reference(DAYS).child(str(member.id))
    day = ref.get() or {}
    if day.get("day") != today():
        day = {"day": today()}
    hosts = day.get("hosts", [])
    if host_id in hosts:
        return None
    paid = day.get("paid", 0)
    beans = REP_BEANS if paid < REP_PAID_DAILY else 0
    ref.set({"day": day["day"], "hosts": [*hosts, host_id], "paid": paid + bool(beans)})
    roles = await add_rep(member, 1)
    if beans:
        await wallet.change(member.id, beans=beans, reason="rep")
    return beans, roles


class AddRewardModal(Modal, title="Add a rep role"):
    role_id = TextInput(label="Role ID", placeholder="Enter the role ID", max_length=50)
    rep = TextInput(label="Rep needed", placeholder="A whole number", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        role_id, rep = self.role_id.value.strip(), self.rep.value.strip()
        if not role_id.isdigit() or not interaction.guild.get_role(int(role_id)):
            error = f"{NO} There is no role with that ID in this server."
        elif not rep.isdigit() or int(rep) < 1:
            error = f"{NO} The rep needed must be a whole number above 0."
        elif role_id in get_rewards():
            error = f"{NO} This role is already a rep role."
        else:
            db.reference(ROLES).child(role_id).set(int(rep))
            await interaction.response.edit_message(embed=status_embed())
            return
        await interaction.response.send_message(error, ephemeral=True)


class RemoveRewardModal(Modal, title="Remove a rep role"):
    role_id = TextInput(
        label="Role ID", placeholder="Enter the role ID to remove", max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        role_id = self.role_id.value.strip()
        if role_id not in get_rewards():
            await interaction.response.send_message(
                f"{NO} That role is not a rep role.", ephemeral=True
            )
            return
        db.reference(ROLES).child(role_id).delete()
        await interaction.response.edit_message(embed=status_embed())


class ReputationView(View):
    @discord.ui.button(label="Add role", style=discord.ButtonStyle.blurple)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddRewardModal())

    @discord.ui.button(label="Remove role", style=discord.ButtonStyle.red)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveRewardModal())


async def setup(bot: commands.Bot):
    pass

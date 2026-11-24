from brawl.Currency.config import HOME, HOW, LADDER
from brawl.Currency.db import u_veteran
from brawl.Currency.helper import NO_EMOTE
from brawl.Currency.panel import notice


async def level_of(bot, user_id, guild_id):
    leveling = bot.get_cog("Leveling")
    return await leveling.level_of(user_id, guild_id) if leveling else 0


async def unlocked(bot, user_id, guild_id, station):
    if u_veteran(user_id).get():
        return True
    return await level_of(bot, user_id, guild_id) >= LADDER[station][0]


def lock_line(station, level):
    need, name, _ = LADDER[station]
    return (
        f"{NO_EMOTE} {name} unlocks at Level {need}. You are Level {level}.\n"
        f"Chat to level up. {HOME} shows your next unlock and {HOW} explains every station."
    )


async def locked(interaction, station):
    user_id, guild_id = interaction.user.id, interaction.guild.id
    if await unlocked(interaction.client, user_id, guild_id, station):
        return False
    level = await level_of(interaction.client, user_id, guild_id)
    send = (
        interaction.followup.send
        if interaction.response.is_done()
        else interaction.response.send_message
    )
    await send(embed=notice(lock_line(station, level), "bad"), ephemeral=True)
    return True


def next_unlock(level):
    for need, name, _ in LADDER.values():
        if need > level:
            return f"{name} unlocks at Level {need}"
    return "Every station is unlocked"


def lessons(old, new):
    return [
        f"**Unlocked {name}:** {lesson}"
        for need, name, lesson in LADDER.values()
        if old < need <= new
    ]


async def setup(bot):
    pass

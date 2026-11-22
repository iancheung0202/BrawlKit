import random
import time

from brawl.Currency.config import THERMOMETER_DAILY_TOKEN_DROPS, THERMOMETER_LEVELS
from brawl.Currency.db import g_shop_effects, u_thermometer_cooldown

DAY = 86400


def level_of(heat):
    return next(level for level in THERMOMETER_LEVELS if heat >= level[0])


def freeze(guild_id):
    """The (member id, effect) keeping the thermometer still, if any."""
    now = time.time()
    for user_id, effects in (g_shop_effects(guild_id).get() or {}).items():
        effect = effects.get("freeze_thermometer", {})
        if effect.get("active") and now < effect.get("expires_at", 0):
            return int(user_id), effect
    return None


def roll_tokens(level):
    """(Tokens, whether it was the rarest drop) for one message at this level."""
    roll = random.random()
    for spot, (odds, amounts) in enumerate(level[3]):
        if roll < odds:
            return random.choice(amounts), spot == 0 and len(level[3]) > 1
        roll -= odds
    return 0, False


def drops_today(user_id):
    data = u_thermometer_cooldown(user_id).get() or {}
    fresh = time.time() - data.get("first_reward_time", 0) < DAY
    return data.get("count", 0) if fresh else 0


def take_drop(user_id):
    """Counts one Token drop; returns its number today, or 0 at the limit."""
    count = drops_today(user_id)
    if count >= THERMOMETER_DAILY_TOKEN_DROPS:
        return 0
    ref = u_thermometer_cooldown(user_id)
    start = (ref.get() or {}).get("first_reward_time") if count else None
    ref.set({"count": count + 1, "first_reward_time": start or time.time()})
    return count + 1


async def setup(bot):
    pass

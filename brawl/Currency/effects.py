import time

from brawl.Currency.db import (
    sync_shop_effects,
    u_shop_cooldowns,
    u_shop_effects,
)
from brawl.Currency.helper import (
    MAIN_GUILD_ID,
    STORE_ITEMS,
)


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
                    if isinstance(effect_data, dict) and effect_data.get(
                        "active", False
                    ):
                        expires_at = effect_data.get("expires_at", 0)
                        if current_time >= expires_at:
                            # Deactivate the effect in both user and guild paths
                            sync_shop_effects(
                                int(user_id),
                                effect_name,
                                "update",
                                {"active": False},
                                MAIN_GUILD_ID,
                            )
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
        ref.set(
            {"last_purchase": time.time(), "item_name": STORE_ITEMS[item_id]["name"]}
        )

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


async def setup(bot):
    pass

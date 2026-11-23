from datetime import datetime, timezone

from firebase_admin import db

U_ROOT = "Cafe Economy"
G_ROOT = "Cafe Economy Guilds"

## User Paths


def u_balance(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/balance")


def u_brews(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/inventory/brews")


def u_shop_effects(user_id: int, effect_name: str = None):
    if effect_name:
        return db.reference(f"{U_ROOT}/{user_id}/inventory/effects/{effect_name}")
    return db.reference(f"{U_ROOT}/{user_id}/inventory/effects")


def u_bag(user_id: int, item_id: str = None):
    """Timed effect items the member holds and has not started."""
    if item_id:
        return db.reference(f"{U_ROOT}/{user_id}/inventory/bag/{item_id}")
    return db.reference(f"{U_ROOT}/{user_id}/inventory/bag")


def u_shop_cooldowns(user_id: int, item_id: str = None):
    if item_id:
        return db.reference(f"{U_ROOT}/{user_id}/inventory/cooldowns/{item_id}")
    return db.reference(f"{U_ROOT}/{user_id}/inventory/cooldowns")


def u_star_drops(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/inventory/star_drops/unopened")


def u_mega_boxes(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/inventory/mega_boxes/unopened")


def u_star_drops_pending(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/inventory/star_drops/pending")


def u_mega_boxes_pending(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/inventory/mega_boxes/pending")


def u_star_drops_purchases(user_id: int, date_key: str = None):
    if date_key:
        return db.reference(
            f"{U_ROOT}/{user_id}/inventory/star_drops/purchases/{date_key}"
        )
    return db.reference(f"{U_ROOT}/{user_id}/inventory/star_drops/purchases")


def u_mega_boxes_purchases(user_id: int, date_key: str = None):
    if date_key:
        return db.reference(
            f"{U_ROOT}/{user_id}/inventory/mega_boxes/purchases/{date_key}"
        )
    return db.reference(f"{U_ROOT}/{user_id}/inventory/mega_boxes/purchases")


def u_daily_chat_earnings(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/chat")


def u_tutorial(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/tutorial")


def u_gambling_limits(user_id: int, date_key: str = None):
    if date_key:
        return db.reference(f"{U_ROOT}/{user_id}/progress/gambling_limits/{date_key}")
    return db.reference(f"{U_ROOT}/{user_id}/progress/gambling_limits")


def u_thermometer_cooldown(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/thermometer_cooldown")


def u_golden_bean(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/golden_bean")


def u_thermometer_beans(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/thermometer_beans")


def u_welcome_cooldown(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/welcome_cooldown")


def u_recent_join(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/recent_join_timestamp")


def u_daily_checkin_streaks(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/daily_checkin_streaks")


def u_sell_alarm(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/sell_alarm")


def u_pin_message(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/settings/pin")


def u_customization(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/settings/customization")


def u_tag(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/settings/tag")


def u_table_notifications(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/settings/table_notifications")


def u_quests(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/quests")


def u_stamp_card(user_id: int):
    """Return reference to user's stamp card data."""
    return db.reference(f"{U_ROOT}/{user_id}/stamp_card")


## Guild Paths


def g_shops(guild_id: int):
    return db.reference(f"{G_ROOT}/{guild_id}/shops")


def g_tables(guild_id: int, table_name: str = None):
    if table_name:
        return db.reference(f"{G_ROOT}/{guild_id}/tables/{table_name.lower()}")
    return db.reference(f"{G_ROOT}/{guild_id}/tables")


def g_table_reset(guild_id: int):
    return db.reference(f"{G_ROOT}/{guild_id}/table_reset")


def g_user_tables(guild_id: int, user_id: int = None):
    if user_id:
        return db.reference(f"{G_ROOT}/{guild_id}/user_tables/{user_id}")
    return db.reference(f"{G_ROOT}/{guild_id}/user_tables")


def g_table_kicks(guild_id: int, user_id: int = None, table_name: str = None):
    if user_id and table_name:
        return db.reference(
            f"{G_ROOT}/{guild_id}/table_kicks/{user_id}/{table_name.lower()}"
        )
    elif user_id:
        return db.reference(f"{G_ROOT}/{guild_id}/table_kicks/{user_id}")
    return db.reference(f"{G_ROOT}/{guild_id}/table_kicks")


def g_invites_monthly(guild_id: int, month_key: str = None, user_id: int = None):
    if month_key and user_id:
        return db.reference(
            f"{G_ROOT}/{guild_id}/invites/monthly/{month_key}/{user_id}"
        )
    elif month_key:
        return db.reference(f"{G_ROOT}/{guild_id}/invites/monthly/{month_key}")
    return db.reference(f"{G_ROOT}/{guild_id}/invites/monthly")


def g_invites_member_data(guild_id: int, member_id: int = None):
    if member_id:
        return db.reference(f"{G_ROOT}/{guild_id}/invites/member_data/{member_id}")
    return db.reference(f"{G_ROOT}/{guild_id}/invites/member_data")


def g_member_history(guild_id: int, member_id: int = None):
    if member_id:
        return db.reference(f"{G_ROOT}/{guild_id}/member_history/{member_id}")
    return db.reference(f"{G_ROOT}/{guild_id}/member_history")


def g_referral_milestones(guild_id: int, month_key: str = None, user_id: int = None):
    if month_key and user_id:
        return db.reference(
            f"{G_ROOT}/{guild_id}/referral_milestones/{month_key}/{user_id}"
        )
    elif month_key:
        return db.reference(f"{G_ROOT}/{guild_id}/referral_milestones/{month_key}")
    return db.reference(f"{G_ROOT}/{guild_id}/referral_milestones")


def g_giveaways(guild_id: int, giveaway_id: str = None):
    if giveaway_id:
        return db.reference(f"{G_ROOT}/{guild_id}/giveaways/{giveaway_id}")
    return db.reference(f"{G_ROOT}/{guild_id}/giveaways")


def g_golden_bean(guild_id: int):
    return db.reference(f"{G_ROOT}/{guild_id}/golden_bean")


def g_thermometer(guild_id: int):
    return db.reference(f"{G_ROOT}/{guild_id}/thermometer")


def g_boss_inspection(guild_id: int):
    return db.reference(
        f'{G_ROOT}/{guild_id}/boss_inspection/{datetime.now(timezone.utc).strftime("%Y-%m-%d")}'
    )


def g_shop_effects(guild_id: int, user_id: int = None):
    if user_id:
        return db.reference(f"{G_ROOT}/{guild_id}/shop_effects/{user_id}")
    return db.reference(f"{G_ROOT}/{guild_id}/shop_effects")


def g_sell_alarm(guild_id: int, user_id: int = None):
    if user_id:
        return db.reference(f"{G_ROOT}/{guild_id}/sell_alarm/{user_id}")
    return db.reference(f"{G_ROOT}/{guild_id}/sell_alarm")


def g_stamp_redemptions(guild_id: int, month_key: str = None):
    """Track monthly stamp redemptions (max 5)."""
    if month_key:
        return db.reference(f"{G_ROOT}/{guild_id}/stamp_redemptions/{month_key}")
    return db.reference(f"{G_ROOT}/{guild_id}/stamp_redemptions")


## Sync Functions (User + Guild)


def sync_shop_effects(
    user_id: int,
    effect_name: str = None,
    operation: str = "get",
    data: dict = None,
    guild_id: int = None,
):
    if operation == "get":
        return u_shop_effects(user_id, effect_name).get()

    elif operation == "set":
        u_ref = u_shop_effects(user_id, effect_name)
        u_ref.set(data)
        if guild_id:
            g_ref = g_shop_effects(guild_id, user_id)
            g_data = g_ref.get() or {}
            if effect_name:
                g_data[effect_name] = data
            g_ref.set(g_data)

    elif operation == "update":
        u_ref = u_shop_effects(user_id, effect_name)
        u_ref.update(data)
        if guild_id:
            g_ref = g_shop_effects(guild_id, user_id)
            g_data = g_ref.get() or {}
            if effect_name:
                if effect_name not in g_data:
                    g_data[effect_name] = {}
                g_data[effect_name].update(data)
            g_ref.set(g_data)

    elif operation == "delete":
        u_ref = u_shop_effects(user_id, effect_name)
        u_ref.delete()
        if guild_id:
            g_ref = g_shop_effects(guild_id, user_id)
            g_data = g_ref.get() or {}
            if effect_name and effect_name in g_data:
                del g_data[effect_name]
            g_ref.set(g_data) if g_data else g_ref.delete()


def sync_sell_alarm(
    user_id: int, operation: str = "get", data: dict = None, guild_id: int = None
):
    if operation == "get":
        return u_sell_alarm(user_id).get()

    elif operation == "set":
        u_ref = u_sell_alarm(user_id)
        u_ref.set(data)
        if guild_id:
            g_ref = g_sell_alarm(guild_id, user_id)
            g_ref.set(data)

    elif operation == "update":
        u_ref = u_sell_alarm(user_id)
        u_ref.update(data)
        if guild_id:
            g_ref = g_sell_alarm(guild_id, user_id)
            g_ref.update(data)

    elif operation == "delete":
        u_ref = u_sell_alarm(user_id)
        u_ref.delete()
        if guild_id:
            g_ref = g_sell_alarm(guild_id, user_id)
            g_ref.delete()


## Misc Paths


def staff_app():
    return db.reference("/Staff App")


def staff_app_cooldown():
    return db.reference("/Staff App Cooldown")


async def setup(bot):
    pass


def u_background(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/settings/background")


def u_veteran(user_id: int):
    return db.reference(f"{U_ROOT}/{user_id}/progress/veteran")

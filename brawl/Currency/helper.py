import time
from datetime import datetime, timedelta, timezone

import discord
from firebase_admin import db

from brawl.Currency.config import (
    DAILY_GAMBLING_LIMITS,
    MAX_BUTTON_WELCOMES,
    PERFECT_BREW_CHANCE,
    ROAST_TYPES,
    STAMP_PRICE_RANGES,
    STAR_DROP_RATES,
    TABLE_QUEST_TYPES,
    UNLOCK_REQ,
    WELCOME_BUTTON_REWARD,
)
from brawl.Currency.db import U_ROOT, u_shop_effects
from brawl.Utility.style import NO, YES

# Channel IDs
SERVER_STORE = 1391361575641677956
BOT_COMMANDS = 1391327183225491489
GENERAL_CHAT = 1391326358466199584
INVITE_LOG = 1391324362078031912
STAFF_CHAT = 1400797909976612884
TOPIC_REVIEW = 816239111916355585

# Role IDs
TRAINEE_ROLE_ID = 1397644919845163089
BRIDGE_ROLE_ID = 1397644914799542402
MASTER_ROLE_ID = 1397423709618307082
ULTRA_TIER_ROLE_ID = 1457507581227700374

# Guild IDs
MAIN_GUILD_ID = 791534106919305226

# Emotes
NO_EMOTE = NO
YES_EMOTE = YES
BEAN_EMOTE = "<:StarrBean:1393442086279315456>"
TOKEN_EMOTE = "<:StarrToken:1393442089894940846>"
REPLY_EMOTE = "<:reply:1036792837821435976>"
EFFECT_EMOTE = "<:Cafe_effect:1573874237687726140>"
LB_EMOTE = "<:leaderboard:1486161551953231882>"
STAR_DROP_EMOTE = "<:Cafe_stardrop:1573874239335829564>"
MEGA_BOX_EMOTE = "<:Cafe_megabox:1573874236064268468>"
STAMP_EMOTE = "<:Cafe_stamp:1573874241294569532>"
CALENDAR_EMOTE = "<:Cafe_calendar:1574187867591409745>"
INVITES_EMOTE = "<:Cafe_invites:1573888554474406011>"
TABLE_EMOTE = "<:Cafe_table:1573888556752179240>"
QUEST_EMOTE = "<:Cafe_quest:1573888558513520672>"
SHOP_EMOTE = "<:Cafe_shop:1573888560606744597>"
OVERVIEW_EMOTE = "<:Cafe_overview:1573900516856168618>"
PASS_EMOTE = "<:Cafe_brawlpass:1573874242934800465>"
PASS_PLUS_EMOTE = "<:Cafe_brawlpassplus:1573874244650270750>"

# Coffee Brew

EMOJIS = {"light": "🌱", "medium": "☕", "dark": "🌳", "golden": "🌟"}

# Boss Inspection
BOSS_INSPECTION_ROLE_ID = 1406764597855256679
MAIN_CHAT_CHANNELS = [1391326358466199584, 1391326881097322596, 1409210492785791069]
BOSS_INSPECTION_ACTIONS = {
    "brew_coffee": {
        "label": "Brew the boss their favorite coffee",
        "success": "You brewed a perfect espresso with amazing crema! The boss takes a sip and smiles with satisfaction. ☕✨",
        "nothing": "You brewed the coffee, but the boss was too busy on their phone to notice your effort... 📱",
        "fail": "You accidentally used decaf beans instead of regular! The boss is not pleased with their weak coffee. 😠☕",
    },
    "organize_storage": {
        "label": "Organize the storage room",
        "success": "Everything is perfectly labeled and sorted! The boss can finally find things easily. Great job! 📦✅",
        "nothing": "You organized it well, but the boss didn't even check the storage room today... 🤷",
        "fail": "You knocked over a shelf while organizing and created an even bigger mess! The boss is furious. 💥📦",
    },
    "clean_machine": {
        "label": "Clean the coffee machine",
        "success": "The machine is sparkling clean and running perfectly! The boss appreciates your attention to detail. ✨🔧",
        "nothing": "You cleaned it thoroughly, but the boss was too distracted to notice the difference... 😐",
        "fail": "You accidentally broke a valve while cleaning! Now the machine is leaking everywhere. 💧😰",
    },
    "prepare_pastries": {
        "label": "Prepare fresh pastries for display",
        "success": "The pastries look absolutely delicious and the display is Instagram-worthy! The boss loves it! 🥐📸",
        "nothing": "You arranged them nicely, but the boss walked right past without looking... 😔",
        "fail": "You dropped the entire tray of pastries on the floor! What a waste... The boss is NOT happy. 🥐💥",
    },
    "tidy_register": {
        "label": "Balance the cash register",
        "success": "Every dollar is accounted for and the register is perfectly organized! The boss is impressed. 💵✅",
        "nothing": "You balanced it correctly, but the boss didn't audit today... Your hard work went unnoticed. 🤷",
        "fail": "You miscounted by $50 and the register doesn't balance! The boss has to stay late to fix it. 😤💸",
    },
    "restock_supplies": {
        "label": "Restock the milk and syrups",
        "success": "Everything is fully stocked and neatly arranged! The boss notices the shelves are perfectly organized. 🥛✨",
        "nothing": "You restocked everything, but the boss didn't check inventory today... 📋",
        "fail": "You ordered the wrong type of milk! Now you have 10 gallons of oat milk instead of whole milk. 🥛❌",
    },
    "polish_windows": {
        "label": "Polish all the glass windows",
        "success": "The windows are crystal clear and streak-free! Natural light floods in beautifully. The boss is delighted! 🪟✨",
        "nothing": "You polished them well, but it's a cloudy day and the boss didn't notice the difference... ☁️",
        "fail": "You left huge streaks all over the windows, making them look worse than before! 🪟😬",
    },
    "reorganize_menu": {
        "label": "Reorganize the menu board",
        "success": "The new menu layout is clear, attractive, and highlights the specials perfectly! The boss approves! 📋👍",
        "nothing": "You made it look nice, but the boss was in the back office all day... 😐",
        "fail": "You misspelled three items and got the prices wrong! Customers are confused. The boss is embarrassed. 📋❌",
    },
    "sweep_mop": {
        "label": "Sweep and mop the entire floor",
        "success": "The floor is spotless and shining! You even got those sticky spots that have been there for weeks. The boss is thrilled! 🧹✨",
        "nothing": "You cleaned thoroughly, but the boss didn't walk around the café today... 🧹",
        "fail": "You used way too much soap and now the floor is dangerously slippery! Someone almost fell. 🧹💦😱",
    },
    "wipe_tables": {
        "label": "Wipe down all tables and chairs",
        "success": "Every surface is sanitized and spotless! Customers comment on how clean everything looks. The boss notices! 🪑✨",
        "nothing": "You cleaned everything, but it was a slow day with few customers to appreciate it... 🪑",
        "fail": "You knocked over a customer's full coffee cup while wiping their table! Now you have to give them a free replacement. ☕💥",
    },
    "sort_inventory": {
        "label": "Sort and label all inventory items",
        "success": "Every item has a clear label with expiration dates! The system is foolproof now. The boss is impressed! 🏷️✅",
        "nothing": "You organized everything perfectly, but the boss forgot to check the inventory list... 📝",
        "fail": "You mixed up the labels and now nothing matches the actual contents! Complete chaos. 🏷️❌😵",
    },
    "latte_art": {
        "label": "Create a new latte art design",
        "success": "Your new rosetta design is absolutely gorgeous! The boss posts it on the café's Instagram. You're a star! ☕🎨✨",
        "nothing": "You created a beautiful design, but the boss was too busy with paperwork to look... ☕😐",
        "fail": "Your attempt at a swan looks more like a blob... The boss critiques your technique in front of everyone. ☕😬",
    },
    "take_out_trash": {
        "label": "Take out all trash and recycling",
        "success": "The café smells fresh again and all bins are empty! You even organized the recycling properly. The boss appreciates it! 🗑️✅",
        "nothing": "You took everything out, but the boss didn't notice since they were in the kitchen... 🗑️",
        "fail": "You forgot to tie the trash bag and it spilled all over the parking lot! Now you have to clean that up too. 🗑️💥🤢",
    },
    "sanitize_bathroom": {
        "label": "Sanitize the bathroom facilities",
        "success": "The bathroom is pristine and smells like fresh lavender! The boss does an inspection and gives you a thumbs up! 🚽✨👍",
        "nothing": "You cleaned it thoroughly, but the boss never checks the bathrooms... 🚽😐",
        "fail": "You clogged the toilet while cleaning and now water is overflowing everywhere! Emergency! 🚽💦😱",
    },
    "update_social": {
        "label": "Update the café's social media",
        "success": "Your post about today's special goes viral with 500 likes! The boss is thrilled with the engagement! 📱💯✨",
        "nothing": "You posted something nice, but the boss doesn't check social media often... 📱",
        "fail": "You accidentally posted a customer's complaint instead of a promotional post! The boss is mortified. 📱😱❌",
    },
    "take_order": {
        "label": "Take a customer's order perfectly",
        "success": "You handled a difficult customer with grace and even upsold them! The boss watches and nods approvingly. 💼✅",
        "nothing": "You took the order correctly, but the boss was on break and didn't see... 📝",
        "fail": "You got the entire order wrong and the customer demands to speak to the manager! The boss has to fix it. 📝😤",
    },
    "train_barista": {
        "label": "Train a new barista properly",
        "success": "The new hire learns quickly thanks to your clear instructions! The boss commends your teaching skills. 👥✅",
        "nothing": "You taught them well, but the boss was too busy to observe the training session... 👥",
        "fail": "You taught them incorrect procedures and now they're doing everything wrong! The boss has to retrain them. 👥❌😬",
    },
    "fix_tables": {
        "label": "Fix all the wobbly tables",
        "success": "Every table is now stable and sturdy! Customers can enjoy their coffee without spills. The boss is grateful! 🪛✅",
        "nothing": "You fixed them all, but the boss didn't test them out... 🪛",
        "fail": "You made the tables even more wobbly somehow! Now they're unusable. The boss is baffled. 🪛❌😵",
    },
    "decorate_cafe": {
        "label": "Decorate the café beautifully",
        "success": "Your seasonal decorations create a warm, inviting atmosphere! Customers love it and the boss does too! 🎨✨",
        "nothing": "You decorated nicely, but the boss came in through the back and didn't see the front area... 🎨",
        "fail": "Your decorations clash horribly with the café's aesthetic! The boss asks you to take everything down. 🎨❌",
    },
    "count_earnings": {
        "label": "Count and report today's earnings",
        "success": "Your financial report is accurate to the penny and well-organized! The boss is impressed by your accounting skills. 💰✅",
        "nothing": "You counted everything correctly, but the boss was too tired to review it today... 💰😐",
        "fail": "Your math is completely off and the report makes no sense! The boss has to redo all your work. 💰❌😤",
    },
}

# Star Drops

COLORS = {
    "rare": 0x49D532,
    "super_rare": 0x2673E7,
    "epic": 0xCA4DFD,
    "mythic": 0xCE3836,
    "legendary": 0xFEED28,
    "ultra": 0xF774F5,
}

IMAGES = {
    "rare": "https://media.discordapp.net/attachments/1026867655468126249/1447683244068700322/rare_with_shadow.jpg?ex=69388396&is=69373216&hm=a75c999eaee067fa038d73f4cf2428817454ef60b2f680af2efb894b838ba4a4&=",
    "super_rare": "https://media.discordapp.net/attachments/1026867655468126249/1447683244748177649/super_rare.jpg?ex=69388396&is=69373216&hm=3d85f56d8e6699e4327fdff12d70a70d7464b5ad4b63921973b2f467a596338d&=",
    "epic": "https://media.discordapp.net/attachments/1026867655468126249/1447683243754131527/epic.jpg?ex=69388395&is=69373215&hm=8e16d9c03189060a20bd0e1c94693e604f4d39efed50379375f37dca3a28b196&=",
    "mythic": "https://media.discordapp.net/attachments/1026867655468126249/1447683244530077823/mythic.jpg?ex=69388396&is=69373216&hm=4254c6a0b1d4698561ffb0f2d7a942acdc6850b34a2bdf78556450f2331086ba&=",
    "legendary": "https://media.discordapp.net/attachments/1026867655468126249/1447683244341592165/legendary.jpg?ex=69388396&is=69373216&hm=6806d01c103e1f3b4c5c37bf10f3a0554616d02ff91ac2be8b6a6132edf2dc63&=",
    "ultra": "https://media.discordapp.net/attachments/1026867655468126249/1447683243347542248/ultra.jpg?ex=69388395&is=69373215&hm=8a7833e02043fae4e15cbd65f2b9b8c9d2651584cd716d4e53bf226a09f228bf&=",
}


# Dates
def get_current_month_key():
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}"


def get_current_date_key():
    """Get current date in YYYY-MM-DD format for daily limits"""
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}-{now.day:02d}"


def get_next_day_timestamp():
    """Get the timestamp for the start of the next day (UTC)"""
    now = datetime.now(timezone.utc)
    next_day = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int(next_day.timestamp())


# Welcome

# Autoresponse
AUTORESPONSE_MAP = {
    976706552780185620: "You pinged greatness. That was brave. Take a moment to recover… until I’m summoned back online.",
    847763528047001600: "https://tenor.com/view/mini-impact-miniimpact-pokemon-slowpoke-cute-gif-11954426876652584269",
    1279454723740532892: "***I'll be right with you <:MegFire:1399931115829071985>!***",
    1287476216789471304: "https://tenor.com/view/snorlax-good-morning-gif-23873480",
    946564972966719540: "https://tenor.com/view/psyduck-pokémon-laptop-on-fire-duck-gif-11352596389714363119",
    947655504270852199: "https://tenor.com/view/kenji-brawl-stars-brawl-stars-kenji-brawl-stars-gif-15253850449038295408",
}

# Gambling Limits

# Stamp Card Objectives


# Table Quest Types


# Shop Effect Functions
async def apply_double_daily(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "double_daily")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["double_daily"]["duration"],
            "applied_at": current_time,
        }
    )


async def apply_chat_boost(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "chat_boost")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["chat_boost"]["duration"],
            "applied_at": current_time,
        }
    )


async def apply_free_insurance(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "free_insurance")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["free_insurance"]["duration"],
            "applied_at": current_time,
        }
    )


async def apply_perfect_brew_boost(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "perfect_brew_boost")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["perfect_brew_boost"]["duration"],
            "applied_at": current_time,
        }
    )


async def apply_half_brew_time(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "half_brew_time")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["half_brew_time"]["duration"],
            "applied_at": current_time,
        }
    )


async def apply_freeze_thermometer(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "freeze_thermometer")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["freeze_thermometer"]["duration"],
            "applied_at": current_time,
            "frozen_heat": None,
        }
    )


async def apply_burnt_to_perfect(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "burnt_to_perfect")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["burnt_to_perfect"]["duration"],
            "applied_at": current_time,
        }
    )


async def apply_chat_bean_boost(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "chat_bean_boost")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["chat_bean_boost"]["duration"],
            "applied_at": current_time,
        }
    )


async def apply_streak_insurance(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "streak_insurance")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["streak_insurance"]["duration"],
            "applied_at": current_time,
            "uses_remaining": 1,
            "last_streak_value": None,
        }
    )


async def apply_sell_alarm(user_id: int):
    current_time = time.time()
    ref = u_shop_effects(user_id, "sell_alarm")
    ref.set(
        {
            "active": True,
            "expires_at": current_time + STORE_ITEMS["sell_alarm"]["duration"],
            "applied_at": current_time,
        }
    )


async def apply_message_pin(user_id: int):
    ref = db.reference(f"{U_ROOT}/{user_id}/settings/pin")
    data = ref.get() or {"count": 0}
    data["count"] = data.get("count", 0) + 1
    ref.set(data)


async def apply_custom_credit(user_id: int):
    ref = db.reference(f"{U_ROOT}/{user_id}/settings/customization")
    data = ref.get() or {"credits": 0}
    data["credits"] = data.get("credits", 0) + 1
    ref.set(data)


async def apply_empty(user_id: int):
    # For items that have instant effects handled elsewhere or custom items like Star Drops and Mega Boxes
    pass


# Store Items
STORE_ITEMS = {
    "double_daily": {
        "name": "Daily Doubler",
        "price": "7 tokens",
        "description": "Doubles your Clock In rewards for 7 days.",
        "effect": apply_double_daily,
        "cooldown": 1209600,  # 14 days
        "duration": 604800,  # 7 days
    },
    "chat_boost": {
        "name": "Espresso Shot",
        "price": "3 tokens",
        "description": "Triples your chat Beans and daily cap for 1 hour.",
        "effect": apply_chat_boost,
        "cooldown": 604800,  # 7 days
        "duration": 3600,  # 1 hour
    },
    "free_insurance": {
        "name": "Barista's Protection",
        "price": "2 tokens",
        "description": "Insures every brew for free for 7 days.",
        "effect": apply_free_insurance,
        "cooldown": 604800,  # 7 days
        "duration": 604800,  # 7 days
    },
    "perfect_brew_boost": {
        "name": "Expert Barista",
        "price": "10 tokens",
        "description": "Raises your perfect brew chance from 2% to 25% for 3 days.",
        "effect": apply_perfect_brew_boost,
        "cooldown": 864000,  # 10 days
        "duration": 259200,  # 3 days
    },
    "instant_brew": {
        "name": "Express Order",
        "price": "5000 beans",
        "description": "Finishes your current brew right away.",
        "effect": apply_empty,
        "cooldown": 432000,  # 5 days
        "duration": 0,  # Instant effect
    },
    "half_brew_time": {
        "name": "Turbo Brewing",
        "price": "12 tokens",
        "description": "Halves every brew time for 7 days.",
        "effect": apply_half_brew_time,
        "cooldown": 864000,  # 10 days
        "duration": 604800,  # 7 days
    },
    "freeze_thermometer": {
        "name": "Thermometer Freezer",
        "price": "10 tokens",
        "description": "Holds the thermometer where it is for 1 hour.",
        "effect": apply_freeze_thermometer,
        "cooldown": 172800,  # 48 hours
        "duration": 3600,  # 1 hour
    },
    "burnt_to_perfect": {
        "name": "Resurrection",
        "price": "4000 beans",
        "description": "Turns your burnt brews into perfect brews for 7 days.",
        "effect": apply_burnt_to_perfect,
        "cooldown": 864000,  # 10 days
        "duration": 604800,  # 7 days
    },
    "reset_chat_cap": {
        "name": "Chat Cap Reset",
        "price": "3 tokens",
        "description": "Resets your chat Bean cap for today.",
        "effect": apply_empty,
        "cooldown": 432000,  # 5 days
        "duration": 0,  # Instant effect
    },
    "chat_bean_boost": {
        "name": "Chat Bean Boost",
        "price": "500 beans",
        "description": "Raises each chat reward from 100–200 to 150–300 Beans for 24 hours.",
        "effect": apply_chat_bean_boost,
        "cooldown": 172800,  # 48 hours
        "duration": 86400,  # 24 hours
    },
    "streak_insurance": {
        "name": "Streak Shield",
        "price": "6 tokens",
        "description": "Saves and restores your streak once if you miss a day. Lasts 30 days.",
        "effect": apply_streak_insurance,
        "cooldown": 2592000,  # 30 days
        "duration": 2592000,  # 30 days
    },
    "thermometer_boost": {
        "name": "Fuel Injection",
        "price": "3 tokens",
        "description": "Heats the thermometer by 30 points right away.",
        "effect": apply_empty,
        "cooldown": 86400,  # 24 hours
        "duration": 0,  # Instant
    },
    "sell_alarm": {
        "name": "Sell Alarm",
        "price": "3 tokens",
        "description": "Sends you a DM when a brew is ready to sell. Lasts 30 days.",
        "effect": apply_sell_alarm,
        "cooldown": 2592000,  # 30 days
        "duration": 2592000,  # 30 days
    },
    "message_pin": {
        "name": "1 Message Pin",
        "price": "10 tokens",
        "description": "Pins any one message in the server. Use it with /pin.",
        "effect": apply_message_pin,
        "cooldown": 172800,  # 2 days
        "duration": 0,  # No expiration (stackable item)
    },
    "custom_credit": {
        "name": "1 Customization Credit",
        "price": "5000 beans",
        "description": "Picks a new background for your Home card. Use it with /customize.",
        "effect": apply_custom_credit,
        "cooldown": 0,
        "duration": 0,
    },
    "star_drop": {
        "name": "Star Drop",
        "price": "500 beans",
        "description": "Holds one random reward.",
        "effect": apply_empty,
        "cooldown": 0,
        "duration": 0,
    },
    "star_drop_10": {
        "name": "10 Star Drops",
        "price": "4500 beans",
        "description": "Ten Star Drops for the price of nine.",
        "effect": apply_empty,
        "cooldown": 0,
        "duration": 0,
    },
    "mega_box": {
        "name": "Mega Box",
        "price": "3 tokens",
        "description": "Holds 5 to 10 rewards.",
        "effect": apply_empty,
        "cooldown": 0,
        "duration": 0,
    },
    "mega_box_10": {
        "name": "10 Mega Boxes",
        "price": "27 tokens",
        "description": "Ten Mega Boxes for the price of nine.",
        "effect": apply_empty,
        "cooldown": 0,
        "duration": 0,
    },
}


async def setup(bot):
    pass

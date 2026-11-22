ROAST_TYPES = {
    "light": {
        "name": "Light Roast",
        "cost": 1000,
        "time": 12 * 3600,  # 12 hours
        "payout": [0, 1, 2],
        "weights": [5, 90, 5],
        "insurance_cost": 150,
    },
    "medium": {
        "name": "Medium Roast",
        "cost": 5000,
        "time": 24 * 3600,  # 24 hours
        "payout": [0, 5, 6, 7],
        "weights": [5, 80, 10, 5],
        "insurance_cost": 750,
    },
    "dark": {
        "name": "Dark Roast",
        "cost": 10000,
        "time": 40 * 3600,  # 40 hours
        "payout": [0, 10, 11, 12, 14],
        "weights": [3, 50, 30, 10, 7],
        "insurance_cost": 1500,
    },
    "golden": {
        "name": "Golden Roast",
        "cost": 25000,
        "time": 72 * 3600,  # 72 hours
        "payout": [25, 28, 32, 35],
        "weights": [40, 30, 20, 10],
        "insurance_cost": 0,  # No insurance for golden roast
    },
}

PERFECT_BREW_CHANCE = 2  # percent

UNLOCK_REQ = 20  # for golden roast

MEGA_BOX_ITEMS = {5: 0.795, 6: 0.1725, 7: 0.015, 8: 0.01, 9: 0.005, 10: 0.0025}
MEGA_BOX_BASE = 5
MEGA_BOX_BASE_RARITY = {"rare": 0.6, "super_rare": 0.4}
MEGA_BOX_EXTRA = {5: 0.4, 10: 0.1, "effect": 0.5}
DROP_UPGRADES = 4
DROP_BONUS = {"mythic": 0.1, "legendary": 0.5, "ultra": 1.0}
EFFECT_FALLBACK_TOKENS = 5

STAR_DROP_RATES = {
    "rarity_rates": {
        "rare": 0.50,
        "super_rare": 0.25,
        "epic": 0.17,
        "mythic": 0.05,
        "legendary": 0.025,
        "ultra": 0.005,
    },
    "drops": {
        "rare": [{"type": "beans", "range": [200, 300], "weight": 1}],
        "super_rare": [{"type": "beans", "range": [350, 450], "weight": 1}],
        "epic": [
            {"type": "beans", "range": [600, 700], "weight": 50},
            {"type": "beans", "range": [700, 800], "weight": 25},
            {"type": "tokens", "amount": 1, "weight": 20},
            {"type": "tokens", "amount": 2, "weight": 5},
        ],
        "mythic": [
            {"type": "beans", "range": [1000, 1200], "weight": 40},
            {"type": "beans", "amount": 2000, "weight": 35},
            {"type": "tokens", "amount": 2, "weight": 25},
        ],
        "legendary": [
            {"type": "tokens", "amount": 3, "weight": 50},
            {"type": "tokens", "amount": 4, "weight": 50},
        ],
        "ultra": [
            {"type": "tokens", "amount": 5, "weight": 50},
            {"type": "tokens", "amount": 6, "weight": 50},
        ],
    },
}

WELCOME_BUTTON_REWARD = 250

MAX_BUTTON_WELCOMES = 10

DAILY_GAMBLING_LIMITS = {
    "coinflip": 50,
    "blackjack": 50,
}

STAMP_GOALS = {"brawl_pass": 30, "brawl_pass_plus": 45}

STAMP_PRICE_RANGES = {
    "brawl_pass": (200, 400),
    "brawl_pass_plus": (300, 500),
}

STAMP_MONTHLY_LIMIT = 5

LEGACY_STAMP_GOALS = {
    "daily_checkins": 30,
    "brew_sells": 30,
    "quests_completed": 30,
    "shop_purchases": 10,
    "boss_inspections": 10,
    "thermometer_bonuses": 10,
}

ORDER_CHAT_BEANS = 500

ORDER_STATION_TASKS = 2

ORDER_TASK_LEVELS = {
    "brew_start": 1,
    "brew_sells": 1,
    "shop_purchases": 2,
}

ORDER_FILLER = "daily_checkins"

ORDER_LABELS = {
    "chat_earnings": "Earn {goal:,} Beans from chat",
    "daily_checkins": "Clock in",
    "brew_start": "Start a brew",
    "brew_sells": "Sell a brew",
    "shop_purchases": "Buy from the shop",
}

QUEST_BEAN_REWARDS = {"daily": 200}

QUEST_BONUS_BEANS = {"daily": 400}

TABLE_QUEST_TYPES = {
    "bean_collector": {
        "name": "🫘 Bean Collector",
        "description": "Collectively earn {target:,} beans this week",
        "targets": [10000, 20000, 30000, 40000, 50000],
        "rewards": [200, 400, 600, 800, 1000],  # Per member
        "duration": 7,  # days
    }
}

BREW = "</brew:1396588612790784070>"
SELL = "</sell:1396588612790784071>"
HOME = "</balance:1393376242501157005>"
SHOP = "</shop:1393376242501157009>"
BUY = "</buy:1393376242501157010>"
CUSTOMIZE = "</customize:1486174479489957908>"
STARDROP = "</stardrop:1447676573020065996>"
MEGABOX = "</megabox:1486191980349358224>"
PIN = "</pin:1427543833792610344>"

LADDER = {
    "brewing": (1, "Brewing", f"Turn Beans into Tokens: {BREW}, wait, then {SELL}."),
    "shop": (2, "Shop", f"Spend Beans and Tokens: browse {SHOP}, then {BUY}."),
    "drops": (
        4,
        "Star Drops",
        f"Random rewards you earn or buy. Open one with {STARDROP}.",
    ),
    "boss": (
        5,
        "Boss Inspection",
        "When the boss walks into chat, press a button. "
        "Impress the boss to tick off a task of Today's Order.",
    ),
    "thermometer": (
        7,
        "Thermometer",
        "Active chat heats the cup. Hot chat drops Tokens. See `/thermometer`.",
    ),
    "tables": (
        10,
        "Tables",
        "Team up for weekly Bean goals: `/table seat` to join, `/table reserve` to host.",
    ),
    "games": (15, "Games", "Bet Beans in `/coinflip` and `/blackjack`. Optional fun."),
    "effects": (
        20,
        "Effect Items",
        f"Timed boosts for chat and brewing. Find them in {SHOP}.",
    ),
    "boxes": (25, "Mega Boxes", f"Big bundles of rewards. Open one with {MEGABOX}."),
    "style": (
        35,
        "Customize and Pin",
        f"Pick a home card background with {CUSTOMIZE} and pin messages with {PIN}.",
    ),
}

ITEM_STATIONS = {
    "sell_alarm": "brewing",
    "streak_insurance": "shop",
    "star_drop": "drops",
    "star_drop_10": "drops",
    "mega_box": "boxes",
    "mega_box_10": "boxes",
    "message_pin": "style",
    "custom_credit": "style",
}

TUTORIAL_BEANS = 500
TUTORIAL_TOKENS = 3

BACKGROUNDS = {
    "gym": "Gym",
    "skulls": "Skulls",
    "classic": "Classic",
    "hub": "Starr Park Hub",
    "new_york": "New York",
    "tokyo": "Tokyo",
    "miami": "Miami",
    "university": "University",
    "superbrawl": "Superbrawl",
    "strikers": "Strikers",
    "cosmo": "Cosmo",
    "nano": "Nano",
    "windstock": "Windstock",
    "valentines": "Valentines",
    "couple": "Couple",
    "oddities": "Oddities Shop",
    "candyland": "Candyland",
}


async def setup(bot):
    pass


# Thermometer: each row is the heat it starts at, its name, the Beans added to
# every counted message, and the Token drops it can roll (odds, amounts).
THERMOMETER_LEVELS = (
    (100, "Boiling", 6, ((0.005, (5,)), (0.015, (1, 1, 2)))),
    (75, "Hot", 4, ((0.01, (1,)),)),
    (50, "Warm", 2, ()),
    (0, "Cold", 0, ()),
)
THERMOMETER_DAILY_TOKEN_DROPS = 3

BOSS_SECONDS = 120
BOSS_ODDS = (("mega_box", 0.5), ("star_drop", 0.25), ("nothing", 0.25))

TABLE_SEATS = 10
TABLE_SEATS_NEEDED = 5
TABLE_WINNER_TOKENS = 3
TABLE_KICK_DAYS = 14

# Referral steps shown on the Invites card: (key, role, what it takes, icon, reward)
REFERRAL_TRAINEE_BEANS = 300
REFERRAL_BRIDGE_BEANS = 3000
REFERRAL_MASTER_SELLS = 3
REFERRAL_STEPS = (
    (
        "trainee_done",
        "Trainee Barista",
        "A new member you invited brews",
        "kit/bean",
        f"+{REFERRAL_TRAINEE_BEANS:,}",
    ),
    (
        "bridge_done",
        "Bridge Barista",
        "A new member you invited sells",
        "kit/bean",
        f"+{REFERRAL_BRIDGE_BEANS:,}",
    ),
    (
        "master_done",
        "Master Barista",
        f"{REFERRAL_MASTER_SELLS} sells by new members you invited",
        "kit/token",
        "+50% per brew",
    ),
)

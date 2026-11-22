import io

from PIL import Image

from brawl.Currency import rewardcard
from brawl.Currency.card import BACKGROUND
from brawl.Currency.config import ROAST_TYPES

TASKS = [("Earn 500 Beans from chat", "120 / 500", False, 0.24), ("Clock in", "Done", True, 1)]


def size(card):
    return Image.open(io.BytesIO(card.getvalue())).size


def test_reward_cards_draw_for_every_state():
    base = {"background": BACKGROUND}
    cards = [
        rewardcard.draw_clock_in(
            {**base, "beans": 2800, "tokens": 4, "notes": ["Booster bonus"], "streak": 7, "tasks": TASKS}
        ),
        rewardcard.draw_clock_in({**base, "beans": 500, "tokens": 0, "notes": [], "streak": 1, "tasks": []}),
        rewardcard.draw_order({**base, "tasks": TASKS, "beans": 200, "stamp": False}),
        rewardcard.draw_order({**base, "tasks": TASKS, "beans": 600, "stamp": True}),
        rewardcard.draw_level_up(
            {**base, "avatar": b"", "name": "sam", "level": 20, "beans": 349, "tokens": 2, "unlocks": [("New role", "Brawler")]}
        ),
        rewardcard.draw_redeemed(
            {**base, "tier": "brawl_pass_plus", "name": "Brawl Pass Plus", "stamps": 45, "cost": 600, "tokens": 5, "left": 0, "month": 5, "limit": 5}
        ),
    ]
    cards += [rewardcard.draw_shift({**base, "step": step}) for step in range(1, 5)]
    cards += [rewardcard.draw_ready({**base, "roast": roast}) for roast in ROAST_TYPES]
    assert all(size(card)[0] > 0 for card in cards)

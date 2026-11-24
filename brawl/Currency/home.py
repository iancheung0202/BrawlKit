from brawl.Currency.card import BACKGROUND
from brawl.Currency.config import BACKGROUNDS
from brawl.Currency.db import u_background


def background(user_id):
    name = u_background(user_id).get()
    return name if name in BACKGROUNDS else BACKGROUND


async def setup(bot):
    pass

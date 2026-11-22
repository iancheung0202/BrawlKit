from brawl.Currency.card import render
from brawl.Currency.config import BREW, HOME, SELL, TUTORIAL_BEANS, TUTORIAL_TOKENS
from brawl.Currency.db import u_tutorial
from brawl.Currency.helper import BEAN_EMOTE, SERVER_STORE, STAMP_EMOTE
from brawl.Currency.home import background
from brawl.Currency.rewardcard import draw_shift

CLOCK_IN, BREW_STEP, SELL_STEP, FINISHED, DONE = 1, 2, 3, 4, 6
STEPS = {"clock_in": CLOCK_IN, "brew": BREW_STEP, "sell": SELL_STEP}

STORE = f"<#{SERVER_STORE}>"
HINTS = {
    CLOCK_IN: f"**First:** press Clock In below, or in {STORE} on any other day.",
    BREW_STEP: f"**Next:** brew a Light Roast with {BREW}. Brewing opens at Level 1, a few minutes of chat.",
    SELL_STEP: f"**Next:** sell your brew with {SELL} when it is ready. That is your first Token.",
    FINISHED: f"Chat for {BEAN_EMOTE} Beans and finish Today's Order for {STAMP_EMOTE} Stamps. "
    f"New stations unlock as you level up, and {HOME} shows what is next.",
}


def step_of(user_id):
    step = u_tutorial(user_id).get()
    if not step or step >= DONE:
        return None
    return min(step, SELL_STEP)


def hint(step):
    return HINTS[step]


async def shift(step, user_id):
    """The first shift card for a step; FINISHED draws it complete."""
    state = {"step": step, "background": background(user_id)}
    return await render(draw_shift, state, name="shift")


class TutorialManager:
    def __init__(self, bot):
        self.bot = bot

    async def start(self, member):
        if economy := self.bot.get_cog("CurrencySystem"):
            await economy.add_beans(member.id, TUTORIAL_BEANS, skip_quest_check=True)
        u_tutorial(member.id).set(CLOCK_IN)
        return CLOCK_IN

    async def advance(self, user_id, action):
        """The step the member is on after this action, or None if it was not their step."""
        if step_of(user_id) != STEPS[action]:
            return None
        if action != "sell":
            u_tutorial(user_id).set(STEPS[action] + 1)
            return STEPS[action] + 1
        u_tutorial(user_id).set(DONE)
        if economy := self.bot.get_cog("CurrencySystem"):
            await economy.add_tokens(user_id, TUTORIAL_TOKENS, reason="tutorial")
        return FINISHED


async def setup(bot):
    pass

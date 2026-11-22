from brawl.Currency.card import render
from brawl.Currency.config import (
    BREW,
    HOME,
    HOW,
    SELL,
    STAMP_GOALS,
    TUTORIAL_BEANS,
    TUTORIAL_TOKENS,
)
from brawl.Currency.db import u_tutorial
from brawl.Currency.helper import BOT_COMMANDS, SERVER_STORE, STAMP_EMOTE
from brawl.Currency.home import background
from brawl.Currency.quests import clocked_in
from brawl.Currency.rewardcard import draw_shift

BREW_STEP, SELL_STEP, CLOCK_IN, DONE, FINISHED = 2, 3, 4, 6, 7
STEPS = {"brew": BREW_STEP, "sell": SELL_STEP, "clock_in": CLOCK_IN}

HINTS = {
    BREW_STEP: (
        "Step 1 of 3: brew your first coffee",
        f"Go to <#{BOT_COMMANDS}>, type {BREW} and pick Light Roast. It is free and ready right away.",
    ),
    SELL_STEP: (
        "Step 2 of 3: sell your coffee",
        f"Type {SELL} here to sell it for Tokens.",
    ),
    CLOCK_IN: (
        "Step 3 of 3: clock in",
        f"Go to <#{SERVER_STORE}> and press the Clock In button. It gives you Today's Order.",
    ),
    FINISHED: (
        "First shift done",
        f"Finish Today's Order to earn a {STAMP_EMOTE} Stamp. "
        f"{STAMP_GOALS['brawl_pass']} Stamps let you redeem a Brawl Pass. {HOME} shows your progress and {HOW} explains the whole cafe.",
    ),
}


def step_of(user_id):
    """The first-shift step a member is on. Steps saved by older tutorials still fit."""
    step = u_tutorial(user_id).get()
    if not step or step >= DONE:
        return None
    return min(max(step, BREW_STEP), CLOCK_IN)


def hint(step):
    """The title and the instruction for this step of the first shift."""
    return HINTS[step]


async def shift(step, user_id):
    """The first shift checklist with this step marked as the one to do now."""
    state = {"step": step - BREW_STEP + 1, "background": background(user_id)}
    return await render(draw_shift, state, name="shift")


class TutorialManager:
    def __init__(self, bot):
        self.bot = bot

    async def start(self, member):
        u_tutorial(member.id).set(BREW_STEP)
        return BREW_STEP

    async def advance(self, user_id, action):
        """The step the member is on after this action, or None if it was not their step."""
        if step_of(user_id) != STEPS[action]:
            return None
        if action == "brew" or (action == "sell" and not clocked_in(user_id)):
            u_tutorial(user_id).set(STEPS[action] + 1)
            return STEPS[action] + 1
        u_tutorial(user_id).set(DONE)
        if economy := self.bot.get_cog("CurrencySystem"):
            await economy.add_tokens(user_id, TUTORIAL_TOKENS, reason="tutorial")
            await economy.add_beans(user_id, TUTORIAL_BEANS, skip_quest_check=True)
        return FINISHED


async def setup(bot):
    pass

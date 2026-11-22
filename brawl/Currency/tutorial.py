import discord

from brawl.Currency.config import BREW, HOME, SELL, TUTORIAL_BEANS, TUTORIAL_TOKENS
from brawl.Currency.db import u_tutorial
from brawl.Currency.helper import BEAN_EMOTE, STAMP_EMOTE, TOKEN_EMOTE
from brawl.Utility.style import BLUE, GREEN

CLOCK_IN, BREW_STEP, SELL_STEP, DONE = 1, 2, 3, 6
STEPS = {"clock_in": CLOCK_IN, "brew": BREW_STEP, "sell": SELL_STEP}

LINES = {
    CLOCK_IN: "**Clock in** with the button below for more Beans and Today's Order.",
    BREW_STEP: f"**Brew** a Light Roast with {BREW}. Brewing opens at Level 1, a few minutes of chat.",
    SELL_STEP: f"**Sell** your brew with {SELL} when it is ready. That is your first Token.",
}


def step_of(user_id):
    step = u_tutorial(user_id).get()
    if not step or step >= DONE:
        return None
    return min(step, SELL_STEP)


def guide(step):
    lines = [
        f"{'✅' if number < step else '▶️' if number == step else '▫️'} "
        f"**Step {number} of 3:** {line}"
        for number, line in LINES.items()
    ]
    return discord.Embed(
        title="Your first shift",
        description="\n".join(lines)
        + f"\n-# Finish all three for {TOKEN_EMOTE} `{TUTORIAL_TOKENS}`. "
        f"{HOME} is your home screen.",
        color=BLUE,
    )


class TutorialManager:
    def __init__(self, bot):
        self.bot = bot

    async def start(self, member):
        if economy := self.bot.get_cog("CurrencySystem"):
            await economy.add_beans(member.id, TUTORIAL_BEANS, skip_quest_check=True)
        u_tutorial(member.id).set(CLOCK_IN)
        return guide(CLOCK_IN)

    async def advance(self, user_id, action):
        if step_of(user_id) != STEPS[action]:
            return None
        if action != "sell":
            u_tutorial(user_id).set(STEPS[action] + 1)
            return guide(STEPS[action] + 1)
        u_tutorial(user_id).set(DONE)
        if economy := self.bot.get_cog("CurrencySystem"):
            await economy.add_tokens(user_id, TUTORIAL_TOKENS, reason="tutorial")
        return discord.Embed(
            title="First shift complete!",
            description=f"You earned {TOKEN_EMOTE} `{TUTORIAL_TOKENS}` on top of your sale.\n"
            f"Chat for {BEAN_EMOTE} Beans, finish Today's Order for {STAMP_EMOTE} Stamps, "
            f"and fill your Stamp Card for a Brawl Pass.\n"
            f"-# New stations unlock as you level up. {HOME} shows what is next.",
            color=GREEN,
        )


async def setup(bot):
    pass

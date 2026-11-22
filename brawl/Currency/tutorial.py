import asyncio

import discord
from firebase_admin import db

from brawl.Currency.db import u_tutorial
from brawl.Currency.helper import BOT_COMMANDS, GENERAL_CHAT

STEP_CLAIM_DAILY = 1
STEP_BREW_LIGHT = 2
STEP_INSURE = 3
STEP_SHOP = 4
STEP_BUY_ALARM = 5
STEP_COMPLETED = 6


class TutorialManager:
    def __init__(self, bot):
        self.bot = bot

    def step(self, user_id, step=None):
        ref = u_tutorial(user_id)
        if step is None:
            return ref.get()
        ref.set(step)

    async def start(self, member: discord.Member):
        if cog := self.bot.get_cog("CurrencySystem"):
            await cog.add_beans(member.id, 500, skip_quest_check=True)
        self.step(member.id, STEP_CLAIM_DAILY)

    async def check_balance_update(self, user_id, new_balance):
        if self.step(user_id) == STEP_CLAIM_DAILY and new_balance >= 1000:
            self.step(user_id, STEP_BREW_LIGHT)
            if channel := self.bot.get_channel(BOT_COMMANDS):
                await channel.send(
                    f"<@{user_id}> Great! You now have enough beans.",
                    embed=discord.Embed(
                        description="**Step 2:** Use the </brew:1396588612790784070> command in this channel.\nSelect **Light Roast**. This converts your beans into a brew, which you can later sell for tokens!",
                        color=discord.Color.purple(),
                    ),
                )
            return True
        return False

    async def on_brew_started(self, user_id, roast_type):
        if self.step(user_id) == STEP_BREW_LIGHT and roast_type == "light":
            self.step(user_id, STEP_INSURE)
            if cog := self.bot.get_cog("CurrencySystem"):
                await cog.add_beans(user_id, 150, skip_quest_check=True)
            if channel := self.bot.get_channel(BOT_COMMANDS):
                await channel.send(
                    f"<@{user_id}> Brewing started! ☕",
                    embed=discord.Embed(
                        description="**Step 3:** You can use </balance:1393376242501157005> to view your profile and brewing status at anytime.\nI've also just given you **150 Beans** for free. Go back to the brew menu and click :shield: **Insure**!",
                        color=discord.Color.purple(),
                    ),
                )

    async def on_insured(self, user_id):
        if self.step(user_id) == STEP_INSURE:
            self.step(user_id, STEP_SHOP)
            if channel := self.bot.get_channel(BOT_COMMANDS):
                await channel.send(
                    f"<@{user_id}> Your brew is safe! 🛡️",
                    embed=discord.Embed(
                        description="**Step 4:** Now, let's check out the shop. Use </shop:1393376242501157009> to see what you can buy.\nOnce you use the </shop:1393376242501157009> command, I'll give you some free tokens as a reward",
                        color=discord.Color.purple(),
                    ),
                )

    async def on_shop_viewed(self, user_id):
        if self.step(user_id) == STEP_SHOP:
            self.step(user_id, STEP_BUY_ALARM)
            if cog := self.bot.get_cog("CurrencySystem"):
                await cog.add_tokens(user_id, 3)
            if channel := self.bot.get_channel(BOT_COMMANDS):
                await channel.send(
                    f"<@{user_id}> As you can see, there are plenty of things you can buy in the shop!",
                    embed=discord.Embed(
                        description="**Step 5:** I've just given you **3 Tokens**.\nUse </buy:1393376242501157010> and purchase the **Sell Alarm** (it costs exactly 3 tokens).\nThis item will notify you in DM when your brew is ready!",
                        color=discord.Color.purple(),
                    ),
                )

    async def on_item_bought(self, user_id, item_id):
        if self.step(user_id) == STEP_BUY_ALARM and item_id == "sell_alarm":
            self.step(user_id, STEP_COMPLETED)
            if channel := self.bot.get_channel(BOT_COMMANDS):
                await channel.send(
                    f"<@{user_id}> **Tutorial Completed!** 🎉\n",
                    embed=discord.Embed(
                        description=f"You're all set! You'll get a DM when your brew is ready to sell.\nWhen it is time, you will use </sell:1396588612790784071> to earn tokens.\nNow, head over to <#{GENERAL_CHAT}> to chat and earn more beans!",
                        color=discord.Color.green(),
                    ).set_footer(text="Welcome to the server again!"),
                )


async def setup(bot):
    pass

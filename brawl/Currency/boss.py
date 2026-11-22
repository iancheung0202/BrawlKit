import random
import time

import discord
from discord.ui import View

from brawl.Currency.card import render
from brawl.Currency.config import BOSS_ODDS, BOSS_SECONDS
from brawl.Currency.db import u_mega_boxes, u_star_drops
from brawl.Currency.helper import BOSS_INSPECTION_ACTIONS, BOSS_INSPECTION_ROLE_ID
from brawl.Currency.home import background
from brawl.Currency.ladder import locked
from brawl.Currency.quests import report, wildcard
from brawl.Currency.stationcard import (
    draw_boss,
    draw_boss_result,
    draw_boss_results,
)

# Each outcome: where the reward is kept, the line of the action to show,
# and how to use the reward.
OUTCOMES = {
    "mega_box": (
        u_mega_boxes,
        "success",
        "Open it with </megabox:1486191980349358224>.",
    ),
    "star_drop": (
        u_star_drops,
        "nothing",
        "Open it with </stardrop:1447676573020065996>.",
    ),
    "nothing": (None, "fail", None),
}


def roll():
    outcomes, odds = zip(*BOSS_ODDS)
    return random.choices(outcomes, odds)[0]


async def start_inspection(cog, channel):
    """The boss walks into a channel with three things members can do."""
    view = BossInspectionView(cog, random.sample(list(BOSS_INSPECTION_ACTIONS), 3))
    view.message = await channel.send(
        f"<@&{BOSS_INSPECTION_ROLE_ID}> The boss is here for a surprise inspection.",
        file=await render(draw_boss, background(None), name="boss"),
        view=view,
    )
    return view


class BossInspectionView(View):
    def __init__(self, cog, action_keys):
        super().__init__(timeout=BOSS_SECONDS)
        self.cog = cog
        self.participants = {}
        self.message = None
        self.start_time = time.time()
        self.ended = False
        for spot, key in enumerate(action_keys):
            button = discord.ui.Button(
                label=BOSS_INSPECTION_ACTIONS[key]["label"],
                style=discord.ButtonStyle.primary,
                custom_id=f"boss_action_{spot}",
            )
            button.callback = self.action(key)
            self.add_item(button)

    def action(self, key):
        async def callback(interaction: discord.Interaction):
            if self.ended or time.time() - self.start_time >= BOSS_SECONDS:
                await interaction.response.send_message(
                    "The boss has already left.", ephemeral=True
                )
                return await self.end_inspection()
            if await locked(interaction, "boss"):
                return
            user = interaction.user
            if user.id in self.participants:
                return await interaction.response.send_message(
                    "You already made your move this inspection.", ephemeral=True
                )
            outcome = roll()
            self.participants[user.id] = (user.display_name, outcome)
            ref, line, how = OUTCOMES[outcome]
            if ref:
                ref(user.id).set((ref(user.id).get() or 0) + 1)
            result = {
                "background": background(user.id),
                "outcome": outcome,
                "line": BOSS_INSPECTION_ACTIONS[key][line],
            }
            await interaction.response.send_message(
                how,
                file=await render(draw_boss_result, result, name="boss"),
                ephemeral=True,
            )
            await report(
                interaction,
                await wildcard(user.id, interaction.guild.id, interaction.client),
            )

        return callback

    async def end_inspection(self):
        """Swap the card for the results, once."""
        if not self.message or self.ended:
            return
        self.ended = True
        self.stop()
        results = {
            "background": background(None),
            "people": list(self.participants.values()),
        }
        try:
            await self.message.edit(
                content=None,
                attachments=[await render(draw_boss_results, results, name="boss")],
                embed=None,
                view=None,
            )
        except discord.HTTPException:
            pass

    async def on_timeout(self):
        await self.end_inspection()


async def setup(bot):
    pass

import random
import time

import discord
from discord.ui import View

from brawl.Currency.card import render
from brawl.Currency.config import (
    BOSS_GAP_HOURS,
    BOSS_HALF_VISITS,
    BOSS_ODDS,
    BOSS_SECONDS,
)
from brawl.Currency.db import u_mega_boxes, u_star_drops
from brawl.Currency.helper import BOSS_INSPECTION_ACTIONS, BOSS_INSPECTION_ROLE_ID
from brawl.Currency.home import background
from brawl.Currency.ladder import locked
from brawl.Currency.panel import notice
from brawl.Currency.quests import report, update_quest
from brawl.Currency.stationcard import draw_boss, draw_boss_result, draw_boss_results

HOUR = 3600
HALF = 12 * HOUR


def plan(midnight):
    """The day's visit times: the same number in each half of the UTC day,
    each a random gap after the one before it."""
    low, high = (hours * HOUR for hours in BOSS_GAP_HOURS)
    times = []
    for start in (midnight, midnight + HALF):
        while True:
            gaps = [random.uniform(low, high) for _ in range(BOSS_HALF_VISITS - 1)]
            first = start + random.uniform(0, HALF - sum(gaps) - 1)
            if sum(gaps) < HALF and (not times or first - times[-1] >= low):
                break
        times.append(first)
        for gap in gaps:
            times.append(times[-1] + gap)
    return [int(moment) for moment in times]


# Each outcome: where the reward is kept, the line of the action to show,
# and how to use the reward.
OUTCOMES = {
    "mega_box": (
        u_mega_boxes,
        "success",
        "Open it with /megabox",
    ),
    "star_drop": (
        u_star_drops,
        "nothing",
        "Open it with /stardrop",
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
                    embed=notice("The boss has already left."), ephemeral=True
                )
                return await self.end_inspection()
            if await locked(interaction, "boss"):
                return
            user = interaction.user
            if user.id in self.participants:
                return await interaction.response.send_message(
                    embed=notice("You already made your move this inspection."),
                    ephemeral=True,
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
                "next": how,
            }
            await interaction.response.send_message(
                file=await render(draw_boss_result, result, name="boss"),
                ephemeral=True,
            )
            await report(
                interaction,
                await update_quest(
                    user.id,
                    interaction.guild.id,
                    {"boss_inspections": 1},
                    interaction.client,
                ),
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
                content=f"<@&{BOSS_INSPECTION_ROLE_ID}> The boss has left.",
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

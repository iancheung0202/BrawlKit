import random
import time

import discord
from discord.ui import View

from brawl.Currency.db import (
    u_mega_boxes,
    u_star_drops,
)
from brawl.Currency.helper import (
    BOSS_INSPECTION_ACTIONS,
    MEGA_BOX_EMOTE,
    NO_EMOTE,
    STAR_DROP_EMOTE,
    YES_EMOTE,
)


class BossInspectionView(View):
    def __init__(self, cog, action_keys):
        super().__init__(timeout=120)
        self.cog = cog
        self.action_keys = action_keys
        self.participants = {}
        self.message = None
        self.start_time = time.time()
        self.ended = False

        for i, action_key in enumerate(action_keys):
            action_data = BOSS_INSPECTION_ACTIONS[action_key]
            button = discord.ui.Button(
                label=action_data["label"],
                style=discord.ButtonStyle.primary,
                custom_id=f"boss_action_{i}",
                row=0,
            )
            button.callback = self.create_action_callback(action_key)
            self.add_item(button)

    def create_action_callback(self, action_key):
        async def action_callback(interaction: discord.Interaction):
            if self.ended:
                return await interaction.response.send_message(
                    "⏰ This inspection has already ended!", ephemeral=True
                )

            elapsed_time = time.time() - self.start_time
            if elapsed_time >= 120:
                self.ended = True
                await self.end_inspection()
                return await interaction.response.send_message(
                    "⏰ Time's up! The inspection has already ended before you acted.",
                    ephemeral=True,
                )

            user_id = interaction.user.id
            if user_id in self.participants:
                return await interaction.response.send_message(
                    "You've already attempted to impress the boss! Chill out... 😰",
                    ephemeral=True,
                )

            action_data = BOSS_INSPECTION_ACTIONS[action_key]
            roll = random.random()

            if roll < 0.50:
                result = {
                    "outcome": "success",
                    "beans": 0,
                    "tokens": 0,
                    "message": action_data["success"],
                }

                ref = u_mega_boxes(user_id)
                current = ref.get() or 0
                ref.set(current + 1)

                title = f"{YES_EMOTE} Boss Impressed!"
                description = f"{action_data['success']}\n\n-# You earned {MEGA_BOX_EMOTE} **1 Mega Box**! Use </megabox:1486191980349358224> to open it."
                color = discord.Color.green()

            elif roll < 0.75:
                result = {
                    "outcome": "nothing",
                    "beans": 0,
                    "tokens": 0,
                    "message": action_data["nothing"],
                }

                ref = u_star_drops(user_id)
                current = ref.get() or 0
                ref.set(current + 1)

                title = "😐 Boss Neutral"
                description = f"{action_data['nothing']}\n\n-# You only got {STAR_DROP_EMOTE} **1 Star Drop**! Use </stardrop:1447676573020065996> to open it."
                color = discord.Color.yellow()

            else:
                result = {
                    "outcome": "penalty",
                    "beans": 0,
                    "tokens": 0,
                    "message": action_data["fail"],
                }

                title = f"{NO_EMOTE} Boss Unimpressed!"
                description = f"{action_data['fail']}\n\n-# You gasped for air as you almost lost your job, but at least you got the air you deserved. You're welcome."
                color = discord.Color.red()

            self.participants[user_id] = {"action_key": action_key, "result": result}

            stamp_cog = interaction.client.get_cog("StampCard")
            if stamp_cog:
                await stamp_cog.update_progress(
                    interaction.user.id, "boss_inspections", 1
                )

            await interaction.response.send_message(
                embed=discord.Embed(title=title, description=description, color=color),
                ephemeral=True,
            )

        return action_callback

    async def end_inspection(self):
        """End the inspection and show results"""
        if not self.message or self.ended:
            return

        self.ended = True

        embed = discord.Embed(
            title="⏰ Boss Inspection Complete!",
            description="The boss has finished and left the café. Here are the results:",
            color=0xE67E22,
        )

        if not self.participants:
            embed.add_field(
                name="No Participants",
                value="Nobody tried to impress the boss... 😔",
                inline=False,
            )
        else:
            # Sort participants by outcome
            success_list = []
            nothing_list = []
            penalty_list = []

            for user_id, data in self.participants.items():
                user = self.message.guild.get_member(user_id)
                username = user.mention if user else f"<@{user_id}>"
                action_key = data["action_key"]
                action_label = BOSS_INSPECTION_ACTIONS[action_key]["label"]
                result = data["result"]

                if result["outcome"] == "success":
                    reward_text = f"{MEGA_BOX_EMOTE} 1 Mega Box"
                    success_list.append(f"{username}: *{action_label}* → {reward_text}")
                elif result["outcome"] == "nothing":
                    nothing_list.append(
                        f"{username}: *{action_label}* → {STAR_DROP_EMOTE} 1 Star Drop"
                    )
                else:
                    penalty_list.append(f"{username}: *{action_label}* → Nothing")

            if success_list:
                embed.add_field(
                    name=f"{YES_EMOTE} Boss Impressed",
                    value="\n".join(success_list),
                    inline=False,
                )

            if nothing_list:
                embed.add_field(
                    name="😐 Boss Neutral", value="\n".join(nothing_list), inline=False
                )

            if penalty_list:
                embed.add_field(
                    name=f"{NO_EMOTE} Boss Unimpressed",
                    value="\n".join(penalty_list),
                    inline=False,
                )

        embed.set_footer(text="Better luck next time, employees! 👔")

        self.clear_items()
        try:
            await self.message.edit(embed=embed, view=self)
        except:
            pass

    async def on_timeout(self):
        await self.end_inspection()


async def setup(bot):
    pass

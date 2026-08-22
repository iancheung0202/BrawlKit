import discord
from discord.ext import commands
from discord.ui import Button, View
import asyncio
import os
import time
from . import guardedChannels
from firebase_admin import db

# Track last modified time for hot-reloading
last_modified_guard = os.path.getmtime("./brawl/ChannelGuard/guardedChannels.py")

def check_and_reload_guard():
    global last_modified_guard, guardedChannels
    new_modified = os.path.getmtime("./brawl/ChannelGuard/guardedChannels.py")
    if new_modified > last_modified_guard:
        with open("./brawl/ChannelGuard/guardedChannels.py", "r") as f:
            lines = f.readlines()
        for line in lines:
            if line.startswith("guarded_channels ="):
                new_guarded_channels = eval(line.split("=", 1)[1].strip())
                if new_guarded_channels != guardedChannels.guarded_channels:
                    guardedChannels.guarded_channels = new_guarded_channels
                    last_modified_guard = new_modified
                    print("guardedChannels reloaded!")
                break

class AcknowledgeButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.green, label="Got it!", custom_id="acknowledge_btn")

    async def callback(self, interaction: discord.Interaction):
        # Update permissions
        await interaction.channel.set_permissions(
            interaction.user,
            overwrite=None,
            reason="Channel Guard Acknowledged"
        )
        
        # Delete the message
        await interaction.message.delete()
        
        # Send confirmation
        await interaction.response.send_message(
            "You may now participate in this channel!",
            ephemeral=True
        )

        # Store acknowledgment
        ref = db.reference(f"Channel Guard/{interaction.channel.id}/acknowledged")
        acknowledged = ref.get() or []
        if interaction.user.id not in acknowledged:
            acknowledged.append(interaction.user.id)
            ref.set(acknowledged)

class ChannelGuardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pending = {}

    @commands.Cog.listener()
    async def on_typing(self, channel, user, when):
        # Check for file changes and reload if needed
        check_and_reload_guard()

        if channel.id not in guardedChannels.guarded_channels or user.bot:
            return

        # Check database for acknowledgment
        ref = db.reference(f"Channel Guard/{channel.id}")
        data = ref.get() or {}
        if user.id in data.get("acknowledged", []):
            return

        # Check if already pending
        if user.id in self.pending:
            return

        self.pending[user.id] = True
        
        try:
            # Restrict permissions
            await channel.set_permissions(
                user,
                send_messages=False,
                reason="Pending Channel Guard acknowledgment"
            )

            # Create embed from stored data
            embed_data = data
            color = discord.Color.blurple()
            if embed_data.get("color"):
                try:
                    color = discord.Color(int(f"0x{embed_data['color']}", 16))
                except:
                    pass

            embed = discord.Embed(
                title=embed_data.get("title", "Channel Rules"),
                description=embed_data.get("description", "Please read and acknowledge the rules"),
                color=color
            )
            if embed_data.get("image"):
                embed.set_image(url=embed_data["image"])

            # Send message with button
            view = View(timeout=60)
            view.add_item(AcknowledgeButton())
            msg = await channel.send(content=user.mention, embed=embed, view=view)

            # Schedule cleanup
            async def cleanup():
                await asyncio.sleep(60)
                try:
                    await msg.delete()
                except:
                    pass
                await channel.set_permissions(user, overwrite=None)
                del self.pending[user.id]

            self.bot.loop.create_task(cleanup())
        except Exception as e:
            del self.pending[user.id]
            raise e

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChannelGuardCog(bot))
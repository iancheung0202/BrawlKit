import discord
from discord import app_commands
from discord.ext import commands
import datetime
import os
from firebase_admin import db

class GuardModal(discord.ui.Modal, title="Channel Guard Setup"):
    title_input = discord.ui.TextInput(
        label="Embed Title",
        max_length=256,
        required=False
    )
    description = discord.ui.TextInput(
        label="Embed Description",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=False
    )
    color = discord.ui.TextInput(
        label="Embed Color (hex)",
        placeholder="#FFFFFF",
        max_length=7,
        required=False
    )
    image = discord.ui.TextInput(
        label="Image URL",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Update guarded_channels file
        channel_id = interaction.channel.id
        file_path = "./brawl/ChannelGuard/guardedChannels.py"
        
        with open(file_path, "r") as f:
            lines = f.readlines()
        
        found = False
        for i, line in enumerate(lines):
            if line.startswith("guarded_channels ="):
                channel_list = eval(line.split("=")[1].strip())
                if channel_id not in channel_list:
                    channel_list.append(channel_id)
                lines[i] = f"guarded_channels = {channel_list}\n"
                found = True
                break
        
        if not found:
            lines.append(f"\nguarded_channels = [{channel_id}]\n")
        
        with open(file_path, "w") as f:
            f.writelines(lines)

        # Save embed data to database
        embed_data = {
            "title": str(self.title_input),
            "description": str(self.description),
            "color": str(self.color).lstrip("#"),
            "image": str(self.image)
        }
        # Assuming db is Firebase Realtime Database
        ref = db.reference(f"Channel Guard/{channel_id}")
        ref.set(embed_data)

        embed = discord.Embed(
            description="✅ Channel Guard configured for this channel!",
            color=0x00FF00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.guild_only()
class ChannelGuard(commands.GroupCog, name="channelguard"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(
        name="setup",
        description="Set up Channel Guard for this channel"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GuardModal())

    @app_commands.command(
        name="disable",
        description="Disable Channel Guard in this channel"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def disable(self, interaction: discord.Interaction):
        channel_id = interaction.channel.id
        file_path = "./brawl/ChannelGuard/guardedChannels.py"
        
        with open(file_path, "r") as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines):
            if line.startswith("guarded_channels ="):
                channel_list = eval(line.split("=")[1].strip())
                if channel_id in channel_list:
                    channel_list.remove(channel_id)
                lines[i] = f"guarded_channels = {channel_list}\n"
                break
        
        with open(file_path, "w") as f:
            f.writelines(lines)

        # Remove database entry
        ref = db.reference(f"Channel Guard/{channel_id}")
        ref.delete()

        embed = discord.Embed(
            description="✅ Channel Guard disabled for this channel!",
            color=0x00FF00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChannelGuard(bot))
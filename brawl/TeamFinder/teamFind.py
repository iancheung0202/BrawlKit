import discord
import datetime
import re
import random
import requests
import urllib.parse

from firebase_admin import db
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
from brawl.Utility.apiKey import headers, brawl_tools_headers
from brawl.Utility.profile import get_ranked_tier

API_BASE = 'https://api.brawlstars.com/v1'

def fetch_profile(tag):
    if not tag.startswith('#'):
        tag = f"#{tag}"
    url = f"https://api.brawltools.net/players/{urllib.parse.quote(tag.upper())}"
    resp = requests.get(url, headers=brawl_tools_headers)
    return resp, resp.json() if resp.ok else (resp, {})

async def closeTeamFindRequest(interaction):
    match = re.search(r"<@(\d+)>", interaction.message.content)
    if match:
        userID = match.group(1)
    else:
        userID = " "
    if (
        str(userID) == str(interaction.user.id)
        or interaction.user.guild_permissions.administrator
    ):
        embed = interaction.message.embeds[0]
        content = interaction.message.content
        
        modifiedContent = re.sub(r"is requesting for.*", "no longer needs teammates. <:Yes:855024337354358794>", content)
        modifiedContent = modifiedContent.replace("**", "")
        modifiedContent = modifiedContent.replace("<a:tools:1390756351952687154>", "")
        
        view = TeamFindViewResolved()
        
        await interaction.response.edit_message(
            content=modifiedContent, embed=embed, view=view
        )
    else:
        await interaction.response.send_message(
            "<:no:1036810470860013639> Only the user who requested for teammates can perform this action.",
            ephemeral=True,
        )

class TeamFindModal(discord.ui.Modal):
    def __init__(self, title="Find Teammates", region="", player_tag_default=None):
        super().__init__(title=f"{title} - {region}", timeout=None)
        self.region = region
        
        self.player_tag = discord.ui.TextInput(
            label="Your Player Tag",
            style=discord.TextStyle.short,
            placeholder="#9L00JQRGR",
            required=True,
            default=str(player_tag_default) if player_tag_default else "",
            max_length=15
        )
        self.category = discord.ui.TextInput(
            label="Category",
            style=discord.TextStyle.short,
            placeholder="e.g. Trophies, Ranked, Challenge, etc.",
            required=True,
            max_length=20
        )
        self.game_mode = discord.ui.TextInput(
            label="Game Mode",
            style=discord.TextStyle.short,
            placeholder="e.g. Showdown, Brawl Ball, Hot Zone, etc.",
            required=True,
            max_length=20
        )
        self.team_code = discord.ui.TextInput(
            label="Team Code",
            style=discord.TextStyle.short,
            placeholder="Enter team join code",
            required=True,
            max_length=10
        )
        self.players_needed = discord.ui.TextInput(
            label="Players Needed",
            style=discord.TextStyle.short,
            placeholder="Default: 2",
            required=False,
            default="2",
            max_length=1
        )
        
        self.add_item(self.player_tag)
        self.add_item(self.category)
        self.add_item(self.game_mode)
        self.add_item(self.team_code)
        self.add_item(self.players_needed)

    async def on_submit(self, interaction: discord.Interaction):
        # Save the player tag to Firebase
        user_id = str(interaction.user.id)
        player_tag_value = self.player_tag.value.strip().replace("#", "")
        if player_tag_value:
            ref = db.reference("/Team Find Player Tag")
            ref.child(user_id).update({'Player Tag': player_tag_value})
        
        # Fetch player stats from API
        try:
            resp, data = fetch_profile(player_tag_value)
            if not resp.ok:
                await interaction.response.send_message(
                    f"<:no:1036810470860013639> Failed to fetch profile for player tag {self.player_tag.value}. Please check the tag and try again.",
                    ephemeral=True
                )
                return
                
            profile_data = data['data']
            trophies = profile_data.get('trophies', 'N/A')
            brawlers_unlocked = len(profile_data.get('brawlers', []))
            ranked_tier = profile_data.get('rankedPoints', 0)
        except Exception as e:
            print(f"API Error: {e}")
            await interaction.response.send_message(
                "<:no:1036810470860013639> Error fetching player data from Brawl Stars API. Please try again later.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        # Get server configuration
        ref = db.reference("/Team Find")
        config = ref.get()
        for key, value in config.items():
            if value["Server ID"] == interaction.guild.id:
                CHANNEL_ID = value["Channel ID"]
                NA_HELPER_ROLE_ID = value["NA Helper Role ID"]
                EU_HELPER_ROLE_ID = value["EU Helper Role ID"]
                ASIA_HELPER_ROLE_ID = value["Asia Helper Role ID"]
                SA_HELPER_ROLE_ID = value["SA Helper Role ID"]
                AU_HELPER_ROLE_ID = value["AU Helper Role ID"]
                break

        channel = interaction.client.get_channel(CHANNEL_ID)
        if channel is None:
            await interaction.followup.send(
                f"<:no:1036810470860013639> The team finder channel for this server (<#{CHANNEL_ID}>) could not be found. It may have been deleted or the bot cannot see it. Please use `/teamfind setup` to set a new one if needed.",
                ephemeral=True
            )
            return

        if "NA" in self.region:
            helperRole = interaction.guild.get_role(NA_HELPER_ROLE_ID)
            embedTitle = "North America Team Request"
            embedColor = 0x6161F9
        elif "EU" in self.region:
            helperRole = interaction.guild.get_role(EU_HELPER_ROLE_ID)
            embedTitle = "Europe Team Request"
            embedColor = 0x50C450
        elif "Asia" in self.region:
            helperRole = interaction.guild.get_role(ASIA_HELPER_ROLE_ID)
            embedTitle = "Asia Team Request"
            embedColor = 0xF96262
        elif "SA" in self.region:
            helperRole = interaction.guild.get_role(SA_HELPER_ROLE_ID)
            embedTitle = "South America Team Request"
            embedColor = 0xF7D31A
        elif "AU" in self.region:
            helperRole = interaction.guild.get_role(AU_HELPER_ROLE_ID)
            embedTitle = "Australia Team Request"
            embedColor = 0x9B59B6

        # Get players needed value
        players_needed = int(self.players_needed.value) if self.players_needed.value.isdigit() else 2
        
        # Create embed with API data
        embed = discord.Embed(
            description=f"### {embedTitle} ({players_needed} More Players Needed)\n-# - Coordinate with each other in the **thread** below\n-# - Click on **`Claim`** if you're 100% joining the team. \n-# - If you are the requester and **no longer need teammates**, press **`Close`**.",
            color=embedColor,
        )
        embed.add_field(
            name="Player Tag", 
            value=f"> [{self.player_tag.value}](https://brawlify.com/stats/profile/{player_tag_value})", 
            inline=True
        )
        
        if 'ranked' in self.category.value.lower() or 'ranked' in self.game_mode.value.lower():
            embed.add_field(name="Ranked", value=f"> {get_ranked_tier(ranked_tier)}", inline=True)
        else:
            embed.add_field(name="Trophies", value=f"> <:trophies:1341985600567251015> `{trophies}`", inline=True)
        embed.add_field(name="Brawlers Unlocked", value=f"> <a:unlocked:1390755948926079037> `{brawlers_unlocked}`", inline=True)
        embed.add_field(name="Category", value=f"> {self.category.value}", inline=True)
        embed.add_field(name="Game Mode", value=f"> {self.game_mode.value}", inline=True)
        
        team_code = self.team_code.value.strip() if self.team_code.value else ""
        if team_code:
            embed.add_field(
                name="Team Code", 
                value=f"> {team_code}", 
                inline=True
            )
        
        try:
            embed.set_footer(icon_url=interaction.guild.icon.url, text=interaction.guild.name)
        except Exception:
            embed.set_footer(text=interaction.guild.name)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)

        emote = random.choice(["<a:tools:1390756351952687154>"])
        players_needed = int(self.players_needed.value) if self.players_needed.value.isdigit() else 2
        
        # Create view
        view = TeamFindView(players_needed)
        
        msg = await channel.send(
            content=f"**{emote} {interaction.user.mention} is requesting for teammates** - {helperRole.mention}",
            embed=embed,
            view=view,
        )
        thread = await msg.create_thread(
            name=f"{interaction.user.name} - {embedTitle}", auto_archive_duration=1440
        )
        
        # Update sticky panel if exists
        ref = db.reference("/Team Find Sticky Panel")
        stickies = ref.get()
        try:
            for key, val in stickies.items():
                if val["Channel ID"] == interaction.channel.id:
                    try:
                        oldMsg = await interaction.channel.fetch_message(
                            val["Message ID"]
                        )
                        await oldMsg.delete()
                    except Exception:
                        pass
                    db.reference("/Team Find Sticky Panel").child(key).delete()
                    newMsg = await interaction.channel.send(
                        oldMsg.content,
                        embed=oldMsg.embeds[0],
                        view=TeamFindButtonViewSystem(),
                    )

                    data = {
                        interaction.channel.id: {
                            "Channel ID": interaction.channel.id,
                            "Message ID": newMsg.id,
                        }
                    }

                    for key, value in data.items():
                        ref.push().set(value)
                    break
        except Exception as e:
            print(e)
            
        await interaction.followup.send(
            f"<:yes:1036811164891480194> [Team Request Sent]({msg.jump_url})",
            ephemeral=True,
        )

class TeamFindView(discord.ui.View):
    def __init__(self, players_needed=2):
        super().__init__(timeout=None)
        self.players_needed = players_needed
        self.claimed_count = 0
        self.claims = []  # Store claimer user IDs

    @discord.ui.button(
        label="Claim", style=discord.ButtonStyle.green, custom_id="claim_team"
    )
    async def claim_team(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        match = re.search(r"<@(\d+)>", interaction.message.content)
        if match:
            userID = match.group(1)
        else:
            userID = " "
        if str(userID) == str(interaction.user.id):
            await interaction.response.send_message(
                "You want to help yourself? :joy:", ephemeral=True
            )
            return
        
        # Check if user already claimed
        if interaction.user.id in self.claims:
            await interaction.response.send_message(
                content="<:no:1036810470860013639> You've already joined this team.",
                ephemeral=True,
            )
            return
            
        # Check if team is full
        if self.claimed_count >= self.players_needed:
            await interaction.response.send_message(
                content="<:no:1036810470860013639> The team is full!",
                ephemeral=True,
            )
            return
            
        # Add claim
        self.claimed_count += 1
        self.claims.append(interaction.user.id)
        user_mention = interaction.user.mention
        
        # Update the embed
        embed = interaction.message.embeds[0]
        
        # Update title with new count
        remaining = self.players_needed - self.claimed_count
        title_str = f"({remaining} More Player{'s' if remaining != 1 else ''} Needed)" if remaining > 0 else "(Team Full!)"
        embed.description = embed.description.replace(
            re.search(r"### .*?\)", embed.description).group(0),
            f"{embed.description.split('(')[0]} {title_str}"
        )
        
        # Update claimed by field
        claim_field = "\n".join([f"- <@{user_id}>" for user_id in self.claims])
        for i, field in enumerate(embed.fields):
            if field.name.startswith("Team Code"):
                team_code = field.value.replace("> ", "").strip()
                print(team_code)
            if field.name.startswith("Claimed By"):
                embed.set_field_at(
                    i, 
                    name=f"Claimed By `({self.claimed_count}/{self.players_needed})`",
                    value=claim_field,
                    inline=False
                )
        
        # Disable claim button if team is full
        if self.claimed_count >= self.players_needed:
            button.disabled = True
        
        has_join_button = any(child.label == "Join Team" for child in self.children)
        if team_code and not has_join_button:
            self.add_item(discord.ui.Button(
                label="Join Team",
                style=discord.ButtonStyle.link,
                url=f"https://link.brawlstars.com/invite/gameroom/en/?tag={team_code}",
                row=0
            ))
        
        await interaction.message.edit(embed=embed, view=self)
        
        # Notify in thread 
        thread = await interaction.guild.fetch_channel(interaction.message.id)
        thread_msg = await thread.send(
            f"{interaction.user.mention} claimed the team request!"
        )
        
        # Send response
        await interaction.response.send_message(
            content=f"<:yes:1036811164891480194> You have claimed the team request! Discuss in {thread.mention}",
            ephemeral=True,
        )

    @discord.ui.button(
        label="Close", style=discord.ButtonStyle.red, custom_id="close_team"
    )
    async def close_team(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        match = re.search(r"<@(\d+)>", interaction.message.content)
        if match:
            userID = match.group(1)
        else:
            userID = " "
        if str(userID) != str(interaction.user.id):
            await interaction.response.send_message(
                "<:no:1036810470860013639> This is not your team request!", ephemeral=True
            )
            return
        await closeTeamFindRequest(interaction)


class TeamFindViewResolved(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Team Request Closed",
        style=discord.ButtonStyle.grey,
        custom_id="closed_team",
        disabled=True,
    )
    async def resolved(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        pass

class CoOpRepEnableView(discord.ui.View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(
        label="Enable/Edit Reputation System",
        style=discord.ButtonStyle.green,
        custom_id="enable_rep_system",
    )
    async def enable_rep_system(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        enableModal = CoOpRepEnableModal()
        await interaction.response.send_modal(enableModal)
        response = await enableModal.wait()

        if enableModal.embed is not None:
            await interaction.edit_original_response(embed=enableModal.embed)

        await enableModal.on_submit_interaction.response.send_message(
            "Updated", ephemeral=True
        )

    @discord.ui.button(
        label="Disable Reputation System",
        style=discord.ButtonStyle.red,
        custom_id="disable_rep_system",
    )
    async def disable_rep_system(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        ref = db.reference("/Team Find Reps System")
        coop = ref.get()
        found = False

        if coop:
            for key, value in coop.items():
                if value["Server ID"] == interaction.guild.id:
                    db.reference("/Team Find Reps System").child(key).delete()
                    found = True
                    break

        if found:
            embed = discord.Embed(
                title="Reputation System Disabled",
                description="The reputation system has been successfully disabled for this server.",
                color=0xFF0000,
            )
            await interaction.response.edit_message(embed=embed)
        else:
            embed = discord.Embed(
                title="Reputation System Not Enabled",
                description="This server does not have the reputation system enabled. No changes were made.",
                color=0xFF0000,
            )
            await interaction.response.edit_message(embed=embed)

    @discord.ui.button(
        label="Add Reward",
        style=discord.ButtonStyle.green,
        custom_id="addrepreward",
        row=1,
    )
    async def addrepreward(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Check if both co-op and reputation systems are enabled
        coop_ref = db.reference("/Team Find")
        coop = coop_ref.get()
        rep_ref = db.reference("/Team Find Reps System")
        rep_system = rep_ref.get()

        coop_enabled = False
        rep_enabled = False

        # Check if the co-op system is enabled for the server
        if coop:
            for key, value in coop.items():
                if value["Server ID"] == interaction.guild.id:
                    coop_enabled = True
                    break

        # Check if the reputation system is enabled for the server
        if rep_system:
            for key, value in rep_system.items():
                if value["Server ID"] == interaction.guild.id:
                    max_rep = value["Max Rep"]
                    rep_enabled = True
                    break

        if coop_enabled and rep_enabled:
            addRewardModel = AddRewardModel(title="Add a Custom Reward")
            await interaction.response.send_modal(addRewardModel)
            response = await addRewardModel.wait()
            embed = discord.Embed(
                title="Reputation System",
                description=f"The reputation system is enabled. Users can only give a maximum of `{max_rep}` reputation points at once.",
                color=discord.Color.blurple(),
            )
            shop_lines = []
            if addRewardModel.roles is not None and not isinstance(
                addRewardModel.roles, str
            ):
                for idx, (role_id, cost) in enumerate(
                    sorted(addRewardModel.roles.items(), key=lambda x: x[1]), start=1
                ):
                    line = f"{idx}. <@&{role_id}> • {cost} reps \n"
                    shop_lines.append(line)
                shop = "".join(shop_lines)
            else:
                shop = "None"
            embed.add_field(name="Roles", value=str(shop), inline=False)
            await interaction.edit_original_response(
                embed=embed, view=CoOpRepEnableView()
            )
            await addRewardModel.on_submit_interaction.response.send_message(
                embed=addRewardModel.update, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "<:no:1036810470860013639> Both team find and reputation systems must be enabled to add a reward.",
                ephemeral=True,
            )

    @discord.ui.button(
        label="Remove Reward",
        style=discord.ButtonStyle.red,
        custom_id="removerepreward",
        row=1,
    )
    async def removerepreward(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Check if both co-op and reputation systems are enabled
        coop_ref = db.reference("/Team Find")
        coop = coop_ref.get()
        rep_ref = db.reference("/Team Find Reps System")
        rep_system = rep_ref.get()

        coop_enabled = False
        rep_enabled = False

        # Check if the co-op system is enabled for the server
        if coop:
            for key, value in coop.items():
                if value["Server ID"] == interaction.guild.id:
                    coop_enabled = True
                    break

        # Check if the reputation system is enabled for the server
        if rep_system:
            for key, value in rep_system.items():
                if value["Server ID"] == interaction.guild.id:
                    rep_enabled = True
                    max_rep = value["Max Rep"]
                    break

        if coop_enabled and rep_enabled:
            removeRewardModel = RemoveRewardModel(title="Remove a Custom Reward")
            await interaction.response.send_modal(removeRewardModel)
            response = await removeRewardModel.wait()
            embed = discord.Embed(
                title="Reputation System",
                description=f"The reputation system is enabled. Users can only give a maximum of `{max_rep}` reputation points at once.",
                color=discord.Color.blurple(),
            )
            shop_lines = []
            if removeRewardModel.roles is not None and not isinstance(
                removeRewardModel.roles, str
            ):
                for idx, (role_id, cost) in enumerate(
                    sorted(removeRewardModel.roles.items(), key=lambda x: x[1]), start=1
                ):
                    line = f"{idx}. <@&{role_id}> • {cost} reps \n"
                    shop_lines.append(line)
                shop = "".join(shop_lines)
            else:
                shop = "None"
            embed.add_field(name="Roles", value=str(shop), inline=False)
            await interaction.edit_original_response(
                embed=embed, view=CoOpRepEnableView()
            )
            await removeRewardModel.on_submit_interaction.response.send_message(
                embed=removeRewardModel.update, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "<:no:1036810470860013639> Both team find and reputation systems must be enabled to remove a reward.",
                ephemeral=True,
            )


class AddRewardModel(discord.ui.Modal, title="Add a Custom Reward"):
    role_id = discord.ui.TextInput(
        label="Role ID",
        style=discord.TextStyle.short,
        placeholder="Enter the role ID",
        required=True,
        max_length=50,
    )
    cost = discord.ui.TextInput(
        label="Cost of Reward",
        style=discord.TextStyle.short,
        placeholder="Must be a reasonable integer",
        required=True,
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        ref = db.reference("/Team Find Reps System")
        coop = ref.get()
        found = False
        server_key = None
        server_roles = {}

        try:
            import json

            for key, val in coop.items():
                if str(val["Server ID"]) == str(interaction.guild.id):
                    server_key = key
                    server_roles = val.get("Roles", {})
                    if isinstance(server_roles, str):
                        try:
                            server_roles = json.loads(server_roles)
                        except json.JSONDecodeError:
                            server_roles = {}
                    found = True
                    break

        except Exception:
            pass

        if not found:
            self.update = discord.Embed(
                description="Reputation system is not enabled for this server yet. Please enable it first.",
                color=discord.Color.red(),
            )
            self.on_submit_interaction = interaction
            self.stop()
            # await interaction.response.send_message(embed=self.update, ephemeral=True)
            return

        # Validate and parse inputs
        try:
            cost = int(self.cost.value)
        except ValueError:
            self.update = discord.Embed(
                description="Cost must be a valid integer.",
                color=discord.Color.red(),
            )
            # await interaction.response.send_message(embed=self.update, ephemeral=True)
            self.on_submit_interaction = interaction
            self.stop()
            return

        role_id = self.role_id.value.strip()
        if role_id in server_roles:
            self.update = discord.Embed(
                description="This role ID already exists as a reward in this server.",
                color=discord.Color.red(),
            )
            # await interaction.response.send_message(embed=self.update, ephemeral=True)
            self.on_submit_interaction = interaction
            self.stop()
            return

        # Add and update
        server_roles[role_id] = cost
        ref.child(server_key).update({"Roles": server_roles})

        self.update = discord.Embed(
            description=f"Added reward for role ID: `{role_id}` with a cost of {cost} reputation points.",
            color=discord.Color.green(),
        )
        self.roles = server_roles
        # await interaction.response.send_message(embed=self.update, ephemeral=True)

        self.on_submit_interaction = interaction
        self.stop()


class RemoveRewardModel(discord.ui.Modal, title="Remove a Custom Reward"):
    role_id = discord.ui.TextInput(
        label="Role ID",
        style=discord.TextStyle.short,
        placeholder="Enter the role ID to remove",
        required=True,
        max_length=50,
    )

    async def on_submit(self, interaction: discord.Interaction):
        ref = db.reference("/Team Find Reps System")
        coop = ref.get()
        found = False
        server_key = None

        # Retrieve current roles and rewards from the server entry
        server_roles = {}
        try:
            import json

            for key, val in coop.items():
                if val["Server ID"] == interaction.guild.id:
                    server_roles = val.get("Roles", {})
                    if isinstance(server_roles, str):
                        try:
                            server_roles = json.loads(server_roles)
                        except json.JSONDecodeError:
                            server_roles = {}
                    server_key = key
                    found = True
                    break
        except Exception:
            pass

        if not found or not server_roles:
            self.update = discord.Embed(
                description="No rewards found for this server.",
                color=discord.Color.red(),
            )
            # await interaction.response.send_message(embed=self.update, ephemeral=True)
            self.on_submit_interaction = interaction
            self.stop()
            return

        # Check if the role ID exists in the server's roles
        role_id = str(self.role_id)
        if role_id not in server_roles:
            self.update = discord.Embed(
                description="Role ID not found as a reward.",
                color=discord.Color.red(),
            )
            # await interaction.response.send_message(embed=self.update, ephemeral=True)
            self.on_submit_interaction = interaction
            self.stop()
            return

        # Remove the reward (role ID)
        del server_roles[role_id]

        if not server_roles:
            server_roles = "None"

        ref.child(server_key).update({"Roles": server_roles})

        self.update = discord.Embed(
            description=f"Removed reward for role ID: `{role_id}`.",
            color=discord.Color.green(),
        )
        self.roles = server_roles
        # await interaction.response.send_message(embed=self.update, ephemeral=True)

        self.on_submit_interaction = interaction
        self.stop()


class CoOpRepEnableModal(discord.ui.Modal, title="Enable/Edit Reputation System"):

    maxrep = discord.ui.TextInput(
        label="Maximum Reputation Points",
        style=discord.TextStyle.short,
        placeholder="Max reps at once (default: 999)",
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if str(self.maxrep):
            try:
                max_rep = int(str(self.maxrep))
            except ValueError:
                await interaction.response.send_message(
                    "Invalid input for maximum reputation. Please enter a valid integer.",
                    ephemeral=True,
                )
                return
        else:
            max_rep = 999  # Default value

        ref = db.reference("/Team Find Reps System")
        coop = ref.get()
        found = False
        roles = "None"
        if coop:
            for key, value in coop.items():
                if value["Server ID"] == interaction.guild.id:
                    roles = value["Roles"]
                    ref.child(key).update({"Max Rep": max_rep})
                    found = True
                    embed = discord.Embed(
                        title="Reputation System Updated",
                        description=f"The reputation system is updated with a maximum of `{max_rep}` reputation points.",
                        color=discord.Color.yellow(),
                    )
                    shop_lines = []
                    if roles is not None and not isinstance(roles, str):
                        for idx, (role_id, cost) in enumerate(
                            sorted(roles.items(), key=lambda x: x[1]), start=1
                        ):
                            line = f"{idx}. <@&{role_id}> • {cost} reps \n"
                            shop_lines.append(line)
                        shop = "".join(shop_lines)
                    else:
                        shop = "None"
                    embed.add_field(name="Roles", value=str(shop), inline=False)
                    embed.add_field(name="Commands", value=(
                        "`-giverep <user> <amount>` - Give reputation points to a user\n"
                        "`-toprep` - View the reputation leaderboard\n"
                        "`-rep <user>` - Check your or another user's reputation points\n"
                    ))
                    self.embed = embed

        if not found:
            # If the server wasn't found in the system, add a new entry.
            data = {
                interaction.guild.id: {
                    "Server ID": interaction.guild.id,
                    "Max Rep": max_rep,
                    "Roles": "None",  # Defaulting to None for roles
                }
            }
            for key, value in data.items():
                ref.push().set(value)

            embed = discord.Embed(
                title="Reputation System Enabled",
                description=f"The reputation system is enabled. Users can only give a maximum of `{max_rep}` reputation points at once.",
                color=discord.Color.green(),
            )
            embed.add_field(name="Roles", value=str(roles), inline=False)
            self.embed = embed

        self.on_submit_interaction = interaction
        self.stop()
        
class TeamFindButtonViewSystem(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    async def fetch_player_tag(self, interaction):
        user_id = str(interaction.user.id)
        ref = db.reference("/Team Find Player Tag")
        try:
            player_tag = ref.child(user_id).get().get('Player Tag', None)
            return player_tag
        except Exception:
            return None

    @discord.ui.button(
        label="NA", style=discord.ButtonStyle.blurple, custom_id="na_teamfind"
    )
    async def na(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_region_request(interaction, button, "NA")

    @discord.ui.button(
        label="EU", style=discord.ButtonStyle.blurple, custom_id="eu_teamfind"
    )
    async def eu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_region_request(interaction, button, "EU")

    @discord.ui.button(
        label="Asia", style=discord.ButtonStyle.blurple, custom_id="asia_teamfind"
    )
    async def asia(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_region_request(interaction, button, "Asia")

    @discord.ui.button(
        label="SA", style=discord.ButtonStyle.blurple, custom_id="sa_teamfind"
    )
    async def sa(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_region_request(interaction, button, "SA")

    @discord.ui.button(
        label="AU", style=discord.ButtonStyle.blurple, custom_id="au_teamfind"
    )
    async def au(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_region_request(interaction, button, "AU")
        
    async def handle_region_request(self, interaction, button, region):
        ref = db.reference("/Team Find")
        config = ref.get()
        found = False
        for key, value in config.items():
            if value["Server ID"] == interaction.guild.id:
                found = True
                break
        if not found:
            embed = discord.Embed(
                title="Team Finder not enabled!",
                description=f"This server doesn't have the team finder system enabled yet. Please ask the server admin to use </teamfind setup:1254927191037317149> to setup the system!",
                colour=0xFF0000,
            )
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        player_tag = await self.fetch_player_tag(interaction)
        modal = TeamFindModal(
            title="Find Teammates",
            region=region,
            player_tag_default=player_tag
        )
        await interaction.response.send_modal(modal)

@app_commands.guild_only()
class TeamFind(commands.GroupCog, name="teamfind"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        super().__init__()

    @app_commands.command(
        name="disable", description="Disable team finder system in this server"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def teamfind_disable(self, interaction: discord.Interaction) -> None:
        config = db.reference("/Team Find").get()
        found = False
        for key, val in config.items():
            if val["Server ID"] == interaction.guild.id:
                db.reference("/Team Find").child(key).delete()
                found = True
                break
        if found:
            embed = discord.Embed(
                title="Team Finder system successfully disabled",
                description=f"You can use </teamfind setup:1254927191037317149> at anytime to setup the system again.",
                colour=0xFFFF00,
            )
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="We could not find your server",
                description=f"Maybe you have already disabled the team finder in your server, or you have never enabled it.",
                colour=0xFF0000,
            )
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    @teamfind_disable.error
    async def teamfind_disable_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    @app_commands.command(
        name="panel", description="Creates a customized team finder panel"
    )
    @app_commands.describe(
        is_sticky_panel="Want the panel to always be the last message in this channel?",
        message="The content of the message",
        title="Makes the title of the embed",
        description="Makes the description of the embed",
        color="Sets the color of the embed",
        thumbnail="Please provide a URL for the thumbnail of the embed (upper-right hand corner image)",
        image="Please provide a URL for the image of the embed (appears at the bottom of the embed)",
        footer="Sets the footer of the embed that appears at the bottom of the embed as small texts",
        footer_icon="Shows server icon in the footer of the embed? (Must have footer text first)",
        footer_time="Shows the time of the embed being sent?",
    )
    @app_commands.checks.bot_has_permissions(create_public_threads=True, send_messages_in_threads=True)
    @app_commands.checks.has_permissions(manage_messages=True, manage_guild=True)
    async def teamfind_panel(
        self,
        interaction: discord.Interaction,
        is_sticky_panel: bool,
        message: str = None,
        title: str = None,
        description: str = None,
        color: str = None,
        thumbnail: str = None,
        image: str = None,
        footer: str = None,
        footer_icon: str = None,
        footer_time: bool = None,
    ) -> None:
        # Converting color
        embed = None
        if color is not None:
            try:
                color = await commands.ColorConverter().convert(interaction, color)
            except:
                color = None
        if color is None:
            color = discord.Color.default()
        if title is not None or description is not None:
            embed = discord.Embed(color=color)
        if title is not None:
            embed.title = title
        if description is not None:
            embed.description = description
        if thumbnail is not None:
            embed.set_thumbnail(url=thumbnail)
        if image is not None:
            embed.set_image(url=image)
        if footer is not None:
            if footer_icon is not None:
                embed.set_footer(text=footer, icon_url=interaction.guild.icon.url)
            else:
                embed.set_footer(text=footer)
        if footer_time is not None or footer_time == True:
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        msgContent = ""
        if message is not None:
            msgContent = message
            
        newMsg = await interaction.channel.send(
            content=msgContent, embed=embed, view=TeamFindButtonViewSystem()
        )
        if is_sticky_panel:
            ref = db.reference("/Team Find Sticky Panel")
            stickies = ref.get()
            try:
                for key, val in stickies.items():
                    if val["Channel ID"] == interaction.channel.id:
                        try:
                            oldMsg = await interaction.channel.fetch_message(
                                val["Message ID"]
                            )
                            await oldMsg.delete()
                        except Exception:
                            pass
                        db.reference("/Team Find Sticky Panel").child(key).delete()
                        break
            except Exception:
                pass

            data = {
                interaction.channel.id: {
                    "Channel ID": interaction.channel.id,
                    "Message ID": newMsg.id,
                }
            }

            for key, value in data.items():
                ref.push().set(value)

        embed = discord.Embed(
            title="",
            description=f"**<:yes:1036811164891480194> Custom Team Finder Panel Sent!** {'This panel will now always be the last message in the channel.' if is_sticky_panel else ''} \n\n*Sent in the wrong channel? Delete the panel and use </teamfind panel:1254927191037317149> in the correct channel!*",
            colour=0x00FF00,
        )
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @teamfind_panel.error
    async def teamfind_panel_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    @app_commands.command(name="setup", description="Setup team finder system in the server")
    @app_commands.describe(
        channel="The channel for all team requests",
        na_helper_role="NA Helper role",
        eu_helper_role="EU Helper role",
        asia_helper_role="Asia Helper role",
        sa_helper_role="SA Helper role",
        au_helper_role="AU Helper role",
    )
    @app_commands.checks.bot_has_permissions(create_public_threads=True, send_messages_in_threads=True, manage_channels=True)
    @app_commands.checks.has_permissions(manage_messages=True, manage_guild=True)
    async def teamfind_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        na_helper_role: discord.Role,
        eu_helper_role: discord.Role,
        asia_helper_role: discord.Role,
        sa_helper_role: discord.Role,
        au_helper_role: discord.Role,
    ) -> None:
        ref = db.reference("/Team Find")
        config = ref.get()
        if config:
            for key, value in config.items():
                if value["Server ID"] == interaction.guild.id:
                    embed = discord.Embed(
                        title="Team Finder System already enabled!",
                        description=f'Your team finder channel is already set as <#{value["Channel ID"]}> `({value["Channel ID"]})`\n\nPlease use </teamfind panel:1254927191037317149> to create your team finder panel.\n\nIf you wish to disable the system, please use </teamfind disable:1246163431912898582>.',
                        colour=0xFF0000,
                    )
                    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

        data = {
            interaction.guild.name: {
                "Server Name": interaction.guild.name,
                "Server ID": interaction.guild.id,
                "Channel ID": channel.id,
                "NA Helper Role ID": na_helper_role.id,
                "EU Helper Role ID": eu_helper_role.id,
                "Asia Helper Role ID": asia_helper_role.id,
                "SA Helper Role ID": sa_helper_role.id,
                "AU Helper Role ID": au_helper_role.id,
            }
        }

        for key, value in data.items():
            ref.push().set(value)

        embed = discord.Embed(
            title="Team Finder System Enabled Successfully!",
            description=(
                f"- The team request channel has been set to <#{channel.id}> `({channel.id})`.\n"
                f"- **By default, all administrators can close any team requests for moderation purposes.**\n"
                f"- To create your team finder panel, please use </teamfind panel:1254927191037317149>.\n"
                f"- **Tip:** Make sure members cannot type in <#{channel.id}>. The system works best if only the bot is able to send messages in that channel."
            ),
            colour=0x00FF00,
        )
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        await interaction.response.send_message(embed=embed)
        
    @teamfind_setup.error
    async def teamfind_setup_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)
        
    @app_commands.command(
        name="reputation",
        description="Enable, manage, or disable reputation system in the server",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def teamfind_reputation(
        self,
        interaction: discord.Interaction,
    ) -> None:
        ref = db.reference("/Team Find Reps System")
        coop = ref.get()
        enabled = False
        try:
            for key, value in coop.items():
                if value["Server ID"] == interaction.guild.id:
                    enabled = [value["Max Rep"], value["Roles"]]
                    break
        except Exception:
            pass

        if enabled is not False:  # If enabled
            max_rep, roles = enabled
            embed = discord.Embed(
                title="Reputation System",
                description=f"The reputation system is enabled. Users can only give a maximum of `{max_rep}` reputation points at once.",
                color=discord.Color.blurple(),
            )
            shop_lines = []
            if roles is not None and not isinstance(roles, str):
                for idx, (role_id, cost) in enumerate(
                    sorted(roles.items(), key=lambda x: x[1]), start=1
                ):
                    line = f"{idx}. <@&{role_id}> • {cost} reps \n"
                    shop_lines.append(line)
                shop = "".join(shop_lines)
            else:
                shop = "None"
            embed.add_field(name="Roles", value=str(shop), inline=False)
            embed.add_field(name="Commands", value=(
                "`-giverep <user> <amount>` - Give reputation points to a user\n"
                "`-toprep` - View the reputation leaderboard\n"
                "`-rep <user>` - Check your or another user's reputation points\n"
            ))
            await interaction.response.send_message(
                embed=embed, view=CoOpRepEnableView(), ephemeral=True
            )
        else:
            embed = discord.Embed(
                title="Reputation System Not Enabled",
                description="This server does not have the reputation system enabled. Click the button below to enable it.",
                color=0xFF0000,
            )
            await interaction.response.send_message(
                embed=embed, view=CoOpRepEnableView(), ephemeral=True
            )
    @teamfind_reputation.error
    async def teamfind_reputation_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TeamFind(bot))
import discord
import random
import re
import requests
import urllib.parse
import json
import asyncio

from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
from firebase_admin import db

from brawl.Utility.apiKey import headers, brawl_tools_headers
from brawl.Currency.db import u_tag

API_BASE = 'https://api.brawlstars.com/v1'
BRAWLTOOLS_BASE = 'https://api.brawltools.net'
TOTAL_BRAWLERS = 97  # adjust if game adds new brawlers

CATEGORY_OPTIONS = [
    'trophy', 'ranked', 'fame',
    'wins_solo', 'wins_duo', 'wins_3v3'
]

# Autocomplete handler for category parameter
async def category_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=opt, value=opt)
        for opt in CATEGORY_OPTIONS
        if current.lower() in opt.lower()
    ]

# Fetch full profile data via BrawlTools
def fetch_profile(tag: str):
    if not tag.startswith('#'):
        tag = f"#{tag}"
    url = f"{BRAWLTOOLS_BASE}/players/{urllib.parse.quote(tag.upper())}"
    resp = requests.get(url, headers=brawl_tools_headers)
    return resp, resp.json() if resp.ok else (resp, {})

# Assign milestone roles utility
async def assign_milestone_roles(member: discord.Member, tag: str, guild: discord.Guild):
    prof_resp, prof_data = fetch_profile(tag)
    if not prof_resp.ok or 'data' not in prof_data:
        return
    stats = prof_data['data']

    cfg = db.reference(f'Brawl Milestone Roles/{guild.id}').get() or {}

    async def process(roles_cfg, value):
        for entry in sorted(roles_cfg, key=lambda e: e['threshold'], reverse=True):
            if value >= entry['threshold']:
                role = guild.get_role(int(entry['role_id']))
                if role and role not in member.roles:
                    await member.add_roles(role)
                # remove lower roles
                for other in roles_cfg:
                    if other['role_id'] == entry['role_id']:
                        continue
                    r = guild.get_role(int(other['role_id']))
                    if r and r in member.roles:
                        await member.remove_roles(r)
                break

    await process(cfg.get('trophy', []), stats.get('trophies', 0))
    await process(cfg.get('ranked', []), stats.get('highestRankedPoints', 0))
    await process(cfg.get('fame', []), stats.get('famePoints', 0))
    wins = cfg.get('wins', {})
    await process(wins.get('solo', []), stats.get('soloVictories', 0))
    await process(wins.get('duo', []), stats.get('duoVictories', 0))
    await process(wins.get('3v3', []), stats.get('3vs3Victories', 0))
    

class VerifyButton(Button):
    def __init__(self):
        super().__init__(
            label="Verify",
            emoji="<a:verify:1391195109302861904>",
            style=discord.ButtonStyle.blurple,
            custom_id="verify_button"
        )

    async def callback(self, interaction: discord.Interaction):
        ref = u_tag(interaction.user.id)
        data = ref.get()
        if data and 'tag' in data:
            tag = data['tag']
            if not tag.startswith('#'):
                tag = f"#{tag}"
            url = f"{API_BASE}/players/{urllib.parse.quote(tag.upper())}"
            resp = requests.get(url, headers=headers)
            data = resp.json()
            name = data['name']
            raw_color = data.get('nameColor','0xFFFFFF')
            try: color = int(raw_color,16)&0xFFFFFF
            except: color = 0xFFFFFF
            emb = discord.Embed(title=f"<a:warning:1391215594430402742> Account Already Linked", description=f"> You have previously linked **{name}** to your Discord account. **Do you wish to unlink?**", color=color)
            emb.set_footer(text="You will lose all your linked roles")
            emb.set_thumbnail(url=f"https://cdn.brawlify.com/profile-icons/regular/{data['icon']['id']}.png")
            emb.add_field(name="Account Tag", value=f"<a:tools:1390756351952687154> `{tag}`",inline=True)
            emb.add_field(name="Current Account Trophies", value=f"<:trophies:1341985600567251015> `{data['trophies']}`",inline=True)
            await interaction.response.send_message(embed=emb, ephemeral=True, view=UnlinkAccountView())
        else:
            await interaction.response.send_modal(VerifyModal())

# Button to update roles
class UpdateRolesButton(Button):
    def __init__(self):
        super().__init__(label="Update Roles", emoji="<:refresh:1048779043287351408>", style=discord.ButtonStyle.grey, custom_id="update_roles")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        user_ref = u_tag(interaction.user.id)
        data = user_ref.get() or {}
        tag = data.get('tag')
        if not tag:
            return await interaction.followup.send("<:No:855023143743651860> You must verify and link your Brawl Stars account first.", ephemeral=True)
        await assign_milestone_roles(interaction.user, tag, interaction.guild)
        prof_resp, prof_data = fetch_profile(tag)
        stats = prof_data['data']
        cfg = db.reference(f'Brawl Milestone Roles/{interaction.guild.id}').get() or {}
        embed = discord.Embed(title="Milestone roles updated! <:Yes:855024337354358794> ", color=0xfcca50)
        def section(title, entries, value):
            lines = []
            for e in sorted(entries, key=lambda x: x['threshold']):
                if value >= e['threshold']:
                    lines = f"> <:Yes:855024337354358794> <@&{e['role_id']}>: `{value}/{e['threshold']}` ({e['emoji']} {e['name']})"
            if lines:
                embed.add_field(name=title, value=lines, inline=False)
        section('<:trophies:1341985600567251015> Trophies', cfg.get('trophy', []), stats.get('trophies', 0))
        section('<a:ranked:1393007596872532139> Ranked (Highest)', cfg.get('ranked', []), stats.get('highestRankedPoints', 0))
        section('<a:global:1392272416797098045> Fame', cfg.get('fame', []), stats.get('famePoints', 0))
        wins = cfg.get('wins', {})
        section('<:solo:1341985978067451988> Solo Wins', wins.get('solo', []), stats.get('soloVictories', 0))
        section('<:duo:1341985494657142885> Duo Wins', wins.get('duo', []), stats.get('duoVictories', 0))
        section('<:3v3:1341985474595655703> 3v3 Wins', wins.get('3v3', []), stats.get('3vs3Victories', 0))
        await interaction.followup.send(embed=embed, ephemeral=True)

# Verification view
class VerificationEmbedView(View):
    def __init__(self, *, timeout=None):
        super().__init__(timeout=timeout)
        self.add_item(VerifyButton())  # Your existing verify button
        self.add_item(UpdateRolesButton())

class VerifyModal(Modal):
    def __init__(self):
        super().__init__(title="Link your Brawl Stars Account")

        self.tag_input = TextInput(
            label="Your Brawl Stars Account Tag",
            required=True,
            placeholder="Example: #9L00JQRGR"
        )
        self.add_item(self.tag_input)

    async def on_submit(self, interaction: discord.Interaction):
        tag = self.tag_input.value.strip().upper()
        if not tag.startswith('#'):
            tag = f"#{tag}"
        url = f"{API_BASE}/players/{urllib.parse.quote(tag.upper())}"
        resp = requests.get(url, headers=headers)
        data = resp.json()
        try:
            name = data['name']
        except Exception as e:
            print(e)
            await interaction.response.send_message(embed=discord.Embed(description="<:No:855023143743651860> Invalid player tag. Please try again!"), ephemeral=True)
        icon_id = None
        random_brawler_name = None
        while True:
            print(data)
            print(data.get('brawlers'))
            random_brawler = random.choice(data.get('brawlers'))
            print(random_brawler["name"].title())
            brawltools_response = requests.get(f"https://api.brawltools.net/brawlers/{random_brawler['id']}")
            brawltools_data = brawltools_response.json()
            icon_id = brawltools_data["data"][0]["iconId"]
            if icon_id != data['icon']['id']:
                random_brawler_name = random_brawler["name"].title()
                break
        raw_color = data.get('nameColor','0xFFFFFF')
        try: color = int(raw_color,16)&0xFFFFFF
        except: color = 0xFFFFFF
        emb = discord.Embed(title=f"One more step left...", description=f"> To verify that you own the account **{name}**, please **change your player icon** in Brawl Stars <:fastforward:1351972114433048719> `{random_brawler_name}`.\n\n-# <:info:1037445870469267638> Once you are done, click the button below!", color=color)
        emb.set_footer(text="You can always change your icon back afterward")
        emb.set_thumbnail(url=f"https://cdn.brawlify.com/profile-icons/regular/{icon_id}.png")
        emb.add_field(name="Account Tag", value=f"<a:tools:1390756351952687154> `{tag}`",inline=True)
        emb.add_field(name="Current Account Trophies", value=f"<:trophies:1341985600567251015> `{data['trophies']}`",inline=True)
        await interaction.response.send_message(embed=emb, ephemeral=True, view=IconChangeView())

class Verify(commands.GroupCog, name="verify"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Updated remove-partner command
    @app_commands.command(name="embed", description="Sends the verification embed")
    @app_commands.checks.has_permissions(administrator=True)
    async def verify_embed(
        self,
        interaction: discord.Interaction,
    ):
        embed = discord.Embed(description="# <a:brawlstars:1393743461030694962> Exclusive Self Roles!\nLink your **Brawl Stars account** with your Discord to **unlock exclusive roles** based on your <:trophies:1341985600567251015> trophies, <a:ranked:1393007596872532139> Ranked, <:3v3:1341985474595655703> victories, and even <a:global:1392272416797098045> fame!\n\n<a:pikachucool:855023776398573608> **You can flex your highest in-game achievements**! \n-# <:reply:1036792837821435976> *Use </milestone mine:1392998294732410990> to **view** the server milestones once linked.*", color=0xfcca50)
        embed.set_footer(text="We verify by checking a temporary icon change — never your password.")
        embed.set_image(url='https://media.discordapp.net/attachments/791906307158048771/854639322765721600/En20201112_BS_2ndBday_Longimage.jpeg?ex=687417a4&is=6872c624&hm=43972185501ff389d021e9cb128c4397b27a1e3ce6efa65ad1184c810f0a0b71&')
        await interaction.channel.send(embed=embed, view=VerificationEmbedView())
    @verify_embed.error
    async def verify_embed_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)


class IconChangeView(discord.ui.View):
    def __init__(
        self,
        *,
        timeout=None,
    ):
        super().__init__(timeout=timeout)
        self.add_item(IconChangeButton())


class IconChangeButton(Button):
    def __init__(self):
        super().__init__(
            emoji="<:Yes:855024337354358794>",
            style=discord.ButtonStyle.grey,
            custom_id="icon_change_button"
        )

    async def callback(self, interaction: discord.Interaction):
        # Extract the tag from embed fields
        tag = None
        for field in interaction.message.embeds[0].fields:
            if field.name.startswith("Account Tag"):
                tag = field.value.split("`")[1].strip()
                break

        # Extract requested icon id from thumbnail url
        match = re.search(r'/(\d+)\.png$', interaction.message.embeds[0].thumbnail.url)
        requested_icon_id = int(match.group(1))

        url = f"{API_BASE}/players/{urllib.parse.quote(tag.upper())}"

        # Send initial ephemeral response without changing your original message
        await interaction.response.edit_message(embed=interaction.message.embeds[0], view=None)
        message = await interaction.followup.send(
            embed=discord.Embed(
                description="Verifying your account. Please wait patiently  <a:loading:1026905298088243240>",
                color=discord.Color.blurple()
            ),
            ephemeral=True
        )

        max_retries = 30  # 5 minutes max (30 * 10s)

        for attempt in range(1, max_retries + 1):

            resp = requests.get(url, headers=headers)
            if resp.status_code != 200:
                continue  # Skip this try silently

            data = resp.json()
            current_icon_id = data['icon']['id']

            if current_icon_id == requested_icon_id:
                # Success! Update DB and inform user
                ref = u_tag(interaction.user.id)
                ref.update({'tag': tag})
                
                # give them their milestone roles immediately
                await assign_milestone_roles(interaction.user, tag, interaction.guild)
                
                prof_resp, prof_data = fetch_profile(tag)
                stats = prof_data['data']
                cfg = db.reference(f'Brawl Milestone Roles/{interaction.guild.id}').get() or {}
                
                embed = discord.Embed(
                    description="<:Yes:855024337354358794> Verification successful. Your Brawl Stars Account is now linked and milestone roles are granted!",
                    color=discord.Color.green()
                )
                def section(title, entries, value):
                    lines = []
                    for e in sorted(entries, key=lambda x: x['threshold']):
                        if value >= e['threshold']:
                            lines = f"> <:Yes:855024337354358794> <@&{e['role_id']}>: `{value}/{e['threshold']}` ({e['emoji']} {e['name']})"
                    if lines:
                        embed.add_field(name=title, value=lines, inline=False)
                section('<:trophies:1341985600567251015> Trophies', cfg.get('trophy', []), stats.get('trophies', 0))
                section('<a:ranked:1393007596872532139> Ranked (Highest)', cfg.get('ranked', []), stats.get('highestRankedPoints', 0))
                section('<a:global:1392272416797098045> Fame', cfg.get('fame', []), stats.get('famePoints', 0))
                wins = cfg.get('wins', {})
                section('<:solo:1341985978067451988> Solo Wins', wins.get('solo', []), stats.get('soloVictories', 0))
                section('<:duo:1341985494657142885> Duo Wins', wins.get('duo', []), stats.get('duoVictories', 0))
                section('<:3v3:1341985474595655703> 3v3 Wins', wins.get('3v3', []), stats.get('3vs3Victories', 0))

                # then notify them
                await message.edit(
                    embed=embed
                )
                
                break
            else:
                # Optionally, update ephemeral message with attempt count
                embed = discord.Embed(
                    description=f"<a:loading:1026905298088243240>  Attempt **`{attempt}`**: Icon not updated yet, checking again in `10` seconds...",
                    color=discord.Color.blurple()
                )
                embed.set_footer(text="It can take up to 5 attempts for Brawl Stars API to update")
                await message.edit(
                    embed=embed
                )
            await asyncio.sleep(10)
        else:
            # Timeout reached
            await message.edit(
                embed=discord.Embed(
                    description="❌ Timed out after 5 minutes. Please try again later.",
                    color=discord.Color.red()
                )
            )


class UnlinkAccountView(discord.ui.View):
    def __init__(
        self,
        *,
        timeout=None,
    ):
        super().__init__(timeout=timeout)
        self.add_item(UnlinkAccountButton())

class UnlinkAccountButton(Button):
    def __init__(self):
        super().__init__(
            emoji="<a:warning:1391215594430402742>",
            label="Unlink",
            style=discord.ButtonStyle.red,
            custom_id="unlink_account_button"
        )

    async def callback(self, interaction: discord.Interaction):
        ref = u_tag(interaction.user.id)
        ref.delete()
        embed = discord.Embed(
            title="<:Yes:855024337354358794> Account Unlinked",
            description="Your Brawl Stars account has been successfully unlinked.",
            color=discord.Color.red()
        )
        embed.set_footer(text="You can relink anytime using the panel.")
        embed.set_thumbnail(url="https://cdn.brawlify.com/profile-icons/regular/28000000.png")  # Optional

        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=None
        )

class MilestoneRolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    milestone = app_commands.Group(
        name="milestone",
        description="Manage Brawl Stars milestone roles"
    )

    @milestone.command(name="add", description="Add a milestone role")
    @app_commands.describe(category="Select a category to add milestone", threshold="The number at which the milestone role is given", role="The milestone role to give", name="A descriptive name of this milestone", emoji="An emoji for this milestone")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(category=category_autocomplete)
    async def add(
        self,
        interaction: discord.Interaction,
        category: str,
        threshold: int,
        role: discord.Role,
        name: str,
        emoji: str
    ):
        if category.startswith('wins_'):
            cat, sub = 'wins', category.split('_')[1]
        else:
            cat, sub = category, None
        ref = db.reference(f'Brawl Milestone Roles/{interaction.guild.id}')
        cfg = ref.get() or {}
        if sub:
            cfg.setdefault('wins', {}).setdefault(sub, []).append({
                "threshold": threshold,
                "role_id": str(role.id),
                "name": name,
                "emoji": emoji
            })
        else:
            cfg.setdefault(cat, []).append({
                "threshold": threshold,
                "role_id": str(role.id),
                "name": name,
                "emoji": emoji
            })
        ref.set(cfg)
        await interaction.response.send_message(f"<:Yes:855024337354358794> Added {role.mention} ({emoji} {name}) to **{category}**.", ephemeral=True)

    @milestone.command(name="remove", description="Remove a milestone by name")
    @app_commands.describe(category="Select a category of the milestone", name="The descriptive name of the milestone to be removed")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(category=category_autocomplete)
    async def remove(
        self,
        interaction: discord.Interaction,
        category: str,
        name: str
    ):
        if category.startswith('wins_'):
            cat, sub = 'wins', category.split('_')[1]
        else:
            cat, sub = category, None
        ref = db.reference(f'Brawl Milestone Roles/{interaction.guild.id}')
        cfg = ref.get() or {}
        lst = cfg.get(cat, {}).get(sub, []) if sub else cfg.get(cat, [])
        new = [e for e in lst if e['name'] != name]
        if len(new) == len(lst):
            return await interaction.response.send_message(f"<:No:855023143743651860> No milestone named {name} in **{category}**.", ephemeral=True)
        if sub:
            cfg['wins'][sub] = new
        else:
            cfg[cat] = new
        ref.set(cfg)
        await interaction.response.send_message(f"<:Yes:855024337354358794> Removed {name} from **{category}**.", ephemeral=True)

    @milestone.command(name="list", description="List milestone roles in a category")
    @app_commands.describe(category="Select a milestone category to view")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(category=category_autocomplete)
    async def list(
        self,
        interaction: discord.Interaction,
        category: str
    ):
        if category.startswith('wins_'):
            cat, sub = 'wins', category.split('_')[1]
        else:
            cat, sub = category, None
        cfg = db.reference(f'Brawl Milestone Roles/{interaction.guild.id}').get() or {}
        items = cfg.get(cat, {}).get(sub, []) if sub else cfg.get(cat, [])
        if not items:
            return await interaction.response.send_message(f"No milestones in {category}.", ephemeral=True)
        msg = "\n".join([f"<@&{e['role_id']}>: `{e['threshold']}` ({e['emoji']} {e['name']})" for e in items])
        await interaction.response.send_message(msg, ephemeral=True)

    @milestone.command(name="mine", description="Show your milestone progress")
    async def mine(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        user_ref = u_tag(interaction.user.id)
        data = user_ref.get() or {}
        tag = data.get('tag')
        if not tag:
            return await interaction.followup.send("<:No:855023143743651860> You must verify and link your Brawl Stars account first.")
        await assign_milestone_roles(interaction.user, tag, interaction.guild)
        prof_resp, prof_data = fetch_profile(tag)
        if not prof_resp.ok or 'data' not in prof_data:
            return await interaction.followup.send("<a:warning:1391215594430402742> Something went wrong.", ephemeral=True)
        stats = prof_data['data']
        cfg = db.reference(f'Brawl Milestone Roles/{interaction.guild.id}').get() or {}
        embed = discord.Embed(title=f"{stats['name']}'s Server Milestone Progress", color=0xfcca50)
        def section(title, entries, value):
            lines = []
            unlocked = [e for e in sorted(entries, key=lambda x: x['threshold']) if value >= e['threshold']]
            highlight_id = unlocked[-1]['role_id'] if unlocked else None

            for e in sorted(entries, key=lambda x: x['threshold']):
                if value >= e['threshold']:
                    status = "<:Yes:855024337354358794>" if e['role_id'] == highlight_id else "<a:Yes_dimmed:1393015472676540436>"
                else:
                    status = "<:No:855023143743651860>"
                lines.append(f"> {status} <@&{e['role_id']}>: `{value}/{e['threshold']}` ({e['emoji']} {e['name']})")
            if lines:
                embed.add_field(name=title, value="\n".join(lines), inline=False)
        section('<:trophies:1341985600567251015> Trophies', cfg.get('trophy', []), stats.get('trophies', 0))
        section('<a:ranked:1393007596872532139> Ranked (Highest)', cfg.get('ranked', []), stats.get('highestRankedPoints', 0))
        section('<a:global:1392272416797098045> Fame', cfg.get('fame', []), stats.get('famePoints', 0))
        wins = cfg.get('wins', {})
        section('<:solo:1341985978067451988> Solo Wins', wins.get('solo', []), stats.get('soloVictories', 0))
        section('<:duo:1341985494657142885> Duo Wins', wins.get('duo', []), stats.get('duoVictories', 0))
        section('<:3v3:1341985474595655703> 3v3 Wins', wins.get('3v3', []), stats.get('3vs3Victories', 0))
        await interaction.followup.send(embed=embed)
        
async def setup(bot: commands.Bot):
    await bot.add_cog(Verify(bot))
    await bot.add_cog(MilestoneRolesCog(bot))
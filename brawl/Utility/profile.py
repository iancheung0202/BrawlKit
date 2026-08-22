import discord
import requests
import urllib.parse
import aiohttp
import io

from discord import app_commands
from discord.ext import commands
from firebase_admin import db

from brawl.Utility.apiKey import headers, brawl_tools_headers
from brawl.Currency.db import u_tag

TIER_EMOJIS = [
    "<:wood:1486153028338716714>",
    "<:bronze:1486153004305350877>",
    "<:silver:1486153072953528500>",
    "<:gold:1486153104754741309>",
    "<:prestige1:1486153143636197396>",
    "<:prestige2:1486153190268207196>",
    "<:prestige3:1486153236443300022>"
]

TROPHY_EMOJI = "<:trophy:1486156047357051033>"
PRESTIGE_TROPHY_EMOJI = "<:prestigetrophy:1486155952146092242>"
HIGH_TROPHY_EMOJI = "<:high_trophies:1341985587241943090>"
GADGET_EMOJI = "<:gadgets:1343354483429740604>"
STARPOWER_EMOJI = "<:star_powers:1343354502769807372>"
GEAR_EMOJI = "<:gears:1343354528715636857>"
THREE_V_THREE_EMOJI = "<:3v3:1341985474595655703>"
SOLO_EMOJI = "<:solo:1341985978067451988>"
DUO_EMOJI = "<:duo:1341985494657142885>"
POWER_POINT_EMOJI = "<a:powerpoints:1390474378898309271>"
TOTAL_PRESTIGE_EMOJI = "<:totalprestige:1486155908693098626>"

API_BASE = 'https://api.brawlstars.com/v1'
TOTAL_BRAWLERS = 101 # ADJUST CONSTANTLY

def get_tier_emoji(trophies):
    if trophies >= 3000: return TIER_EMOJIS[6]
    if trophies >= 2000: return TIER_EMOJIS[5]
    if trophies >= 1000: return TIER_EMOJIS[4]
    if trophies >= 750:  return TIER_EMOJIS[3]
    if trophies >= 500:  return TIER_EMOJIS[2]
    if trophies >= 250:  return TIER_EMOJIS[1]
    return TIER_EMOJIS[0]

def fetch_profile(tag):
    if not tag.startswith('#'):
        tag = f"#{tag}"
    url = f"https://api.brawltools.net/players/{urllib.parse.quote(tag.upper())}"
    resp = requests.get(url, headers=brawl_tools_headers)
    return resp, resp.json() if resp.ok else (resp, {})

def fetch_battlelog(tag):
    if not tag.startswith('#'):
        tag = f"#{tag}"
    url = f"{API_BASE}/players/{urllib.parse.quote(tag.upper())}/battlelog"
    resp = requests.get(url, headers=headers)
    return resp, resp.json() if resp.ok else (resp, {})

def get_fame_rank(points: int) -> str:
    fame_levels = [
        ("Global", 2000, "<a:global:1392272416797098045>"),
        ("Lunar", 3200, "<a:lunar:1392272419170816100>"),
        ("Martian", 4500, "<a:martian:1392272421070962698>"),
        ("Saturnian", 8000, "<a:saturnian:1392272426477424812>"),
        ("Solar", 12000, "<a:solar:1392272428289233069>"),
        ("Meteoric", 20000, "<a:meteoric:1392272424145522850>"),
        ("Alien", 50000, "<a:alien:1392272414347497754>")
    ]

    if points < 1:
        return "No Fame"

    current_index = 0
    local_points = points
    while current_index < len(fame_levels):
        name, cap, emote = fame_levels[current_index]
        total_level_points = cap * 3
        if local_points < total_level_points:
            level = local_points // cap + 1
            return f"{emote} {name} `{['I', 'II', 'III'][level - 1]}`"
        local_points -= total_level_points
        current_index += 1

    return f"{fame_levels[-1][2]} Alien `III`"

def get_ranked_tier(points: int) -> str:
    rank_thresholds = [
        (0, "<a:bronze:1392279963637518407>", "I"),
        (250, "<a:bronze:1392279963637518407>", "II"),
        (500, "<a:bronze:1392279963637518407>", "III"),
        (750, "<a:silver:1392280041634664560>", "I"),
        (1000, "<a:silver:1392280041634664560>", "II"),
        (1250, "<a:silver:1392280041634664560>", "III"),
        (1500, "<a:gold:1392279968410636299>", "I"),
        (2000, "<a:gold:1392279968410636299>", "II"),
        (2500, "<a:gold:1392279968410636299>", "III"),
        (3000, "<a:diamond:1392279966334587022>", "I"),
        (3500, "<a:diamond:1392279966334587022>", "II"),
        (4000, "<a:diamond:1392279966334587022>", "III"),
        (4500, "<a:mythic:1392280035368501359>", "I"),
        (5000, "<a:mythic:1392280035368501359>", "II"),
        (5500, "<a:mythic:1392280035368501359>", "III"),
        (6000, "<a:legendary:1392279971023556849>", "I"),
        (6750, "<a:legendary:1392279971023556849>", "II"),
        (7500, "<a:legendary:1392279971023556849>", "III"),
        (8250, "<a:masters:1392280030972739594>", "I"),
        (9250, "<a:masters:1392280030972739594>", "II"),
        (10250, "<a:masters:1392280030972739594>", "III"),
        (11250, "<a:pro:1392280038677680272>", ""), 
    ]

    for i in range(len(rank_thresholds) - 1, -1, -1):
        threshold, emote, level = rank_thresholds[i]
        if points >= threshold:
            if level == "":
                return f"{emote}"
            return f"{emote} `{level}`"

    return "<a:bronze:1392279963637518407> `I`" 

def get_record_tier(record: int) -> str:
    emotes = {
        0: "<a:0_:1392287284497350736>",
        1: "<a:1_:1392287286082932848>",
        2: "<a:2_:1392287287240556686>",
        3: "<a:3_:1392287288935055492>",
        4: "<a:4_:1392287290411319486>",
        5: "<a:5_:1392287291845640202>",
        6: "<a:6_:1392287293313908767>",
        7: "<a:7_:1392287296123961405>",
        8: "<a:8_:1392287298120318996>",
        9: "<a:9_:1392287299277946880>",
        10: "<a:10_:1392287356303970447>",
        11: "<a:11_:1392287395264860400>",
        12: "<a:12_:1392287406585024562>",
    }

    roman = {
        1: "I", 2: "II", 3: "III", 4: "IV", 5: "V",
        6: "VI", 7: "VII", 8: "VIII", 9: "IX",
        10: "X", 11: "XI", 12: "XII"
    }

    if record not in emotes:
        record = 0 

    emote = emotes[record]
    if record == 0:
        return f"{emote} `0`"
    return f"{emote} `{roman[record]}`"

async def make_home(data, color):
    tag = data['tag']
    data = data['data']
    name = data['name']
    unlocked = len(data.get('brawlers', []))
    pct = int((unlocked / TOTAL_BRAWLERS) * 20)
    bar = '━' * pct + '-' * (20 - pct)
    emb = discord.Embed(title=f"{name} ({tag})", color=color)
    emb.set_thumbnail(url=f"https://cdn.brawlify.com/profile-icons/regular/{data['icon']['id']}.png")
    emb.add_field(name="Trophies", value=f"{TROPHY_EMOJI} `{data['trophies']:,}` / `{data['highestTrophies']:,}` {HIGH_TROPHY_EMOJI}",inline=False)
    emb.add_field(name="Ranked", value=f"{get_ranked_tier(data['rankedPoints'])} (`{data['rankedPoints']:,}`) / {get_ranked_tier(data['highestRankedPoints'])} (`{data['highestRankedPoints']:,}`)",inline=False)
    emb.add_field(name="Victories", value=f"{THREE_V_THREE_EMOJI} `{data['3vs3Victories']:,}` / {SOLO_EMOJI} `{data['soloVictories']:,}` / {DUO_EMOJI} `{data['duoVictories']:,}` / <a:max_streak:1371655286049214672> `{data['highestWinStreak']:,}`",inline=False)
    emb.add_field(name="Records", value=f"{get_record_tier(data['recordRank'])} (`{data['recordPoints']:,}`)",inline=True)
    emb.add_field(name="Fame", value=f"{get_fame_rank(data['famePoints'])}",inline=True)
    emb.add_field(name="Total Prestige", value=f"{TOTAL_PRESTIGE_EMOJI} `{data['totalPrestigeLevel']:,}`", inline=True)
    emb.add_field(name="Brawlers Unlocked", value=f"`{bar} {unlocked:,}/{TOTAL_BRAWLERS:,}`", inline=False)
    url = f"https://share.brawlify.com/player/{tag.replace('#', '').upper()}/default"
    emb.set_image(url=url)
    return emb


async def make_brawlers(data, color):
    pages=[]
    tag = data['tag']
    data = data['data']
    brawlers=data.get('brawlers',[])
    LIMIT_PER_PAGE = 18
    total_pages = (len(brawlers) + LIMIT_PER_PAGE - 1) // LIMIT_PER_PAGE  
                
    for i in range(0, len(brawlers), LIMIT_PER_PAGE):
        emb = discord.Embed(title=f"{data['name']} ({tag}) - Brawlers", color=color)
        for b in brawlers[i:i+LIMIT_PER_PAGE]:
            emb.add_field(
                name=f"{get_tier_emoji(b['highestTrophies'])} {b['name'].title()}",
                value=(
                    f"{TROPHY_EMOJI if b['trophies'] < 1000 else PRESTIGE_TROPHY_EMOJI} **`{b['trophies']:,}`** ㆍ {POWER_POINT_EMOJI} `{b['power']}`\n"
                    f"-# {GADGET_EMOJI} `{len(b.get('gadgets',[]))}` ㆍ {STARPOWER_EMOJI} `{len(b.get('starPowers',[]))}` ㆍ {GEAR_EMOJI} `{len(b.get('gears',[]))}`"
                ), inline=True)
                
        page_num = i//LIMIT_PER_PAGE + 1
        emb.set_footer(text=f"Page {page_num} of {total_pages}")
        pages.append((emb, None))
    return pages


from datetime import datetime
import re

def format_mode(raw: str) -> str:
    """Converts camelCase or PascalCase to spaced & titled format"""
    return re.sub(r'(?<!^)(?=[A-Z])', ' ', raw).title()

async def make_matches(battlelog_data, player_tag, color):
    log = battlelog_data.get("items", [])[:25]
    pages = []
    total_matches = len(log)
    
    clean_player_tag = player_tag.replace('#', '').upper()
    
    for idx, match in enumerate(log):
        battle = match.get("battle", {})
        event = match.get("event", {})
        mode = format_mode(event.get("mode", "Unknown"))
        map_name = event.get("map", "Unknown")

        result = battle.get("result", "unknown").title()
        duration = battle.get("duration", 0)
        trophy_change = battle.get("trophyChange", 0)
        raw_type = battle.get("type", "unknown").lower()
        if raw_type == "ranked":
            type_ = "Ladder"
        elif raw_type == "soloranked":
            type_ = "Ranked"
        else:
            type_ = raw_type.title()

        battle_time_str = match.get("battleTime")
        try:
            dt = datetime.strptime(battle_time_str, "%Y%m%dT%H%M%S.%fZ")
            unix_ts = int(dt.timestamp())
            timestamp_str = f"<t:{unix_ts}:R>"
        except Exception:
            timestamp_str = "Unknown"

        star_player = battle.get("starPlayer", {})
        try:
            sp_name = star_player.get("name", "Unknown")
            sp_brawler = star_player.get("brawler", {}).get("name", "Unknown")
            star_player_str = f"\n-# ⭐ **Star Player:** {sp_name} → **{sp_brawler.title()}**" if sp_name != "Unknown" else ""
        except Exception:
            sp_name = "Unknown"
            sp_brawler = "Unknown"
            star_player_str = ""

        embed = discord.Embed(
            title=f"{mode} @ {map_name}",
            description=f"__**{type_}**__ • 🕒 `{duration}s` • {timestamp_str}{star_player_str}",
            color=color,
        )
        embed.set_footer(text=f"Page {idx+1} of {total_matches}")

        result_emoji = "🏆" if result.lower() == "victory" else "💀"
        change_emoji = "🔺" if trophy_change >= 0 else "🔻"
        result != "Unknown" and embed.add_field(name="Result", value=f"{result_emoji} {result}", inline=True)
        type_ == "Ladder" and embed.add_field(name="Trophy Change", value=f"{change_emoji} {trophy_change}", inline=True)

        teams = battle.get("teams", [])
        player_team_index = None
        
        for team_idx, team in enumerate(teams):
            for player in team:
                if player.get('tag', '').replace('#', '').upper() == clean_player_tag:
                    player_team_index = team_idx
                    break
            if player_team_index is not None:
                break
                
        team_labels = []
        if player_team_index is not None:
            team_labels.append("Your Team")
            for i in range(len(teams)):
                if len(teams) == 2:
                    team_labels.append(f"Enemy Team")
                    break
                if i != player_team_index:
                    team_labels.append(f"Enemy Team {i+1}")
        else:
            team_labels = [f"Team {i+1}" for i in range(len(teams))]
        
        for idx, team in enumerate(teams):
            if player_team_index is not None:
                if idx == player_team_index:
                    display_idx = 0
                else:
                    display_idx = idx + 1 if idx < player_team_index else idx
            else:
                display_idx = idx
                
            if display_idx >= len(team_labels):
                continue
                
            team_str = ""
            for player in team:
                p_name = player.get("name", "Unknown")
                brawler = player.get("brawler", {})
                b_name = brawler.get("name", "??")
                b_power = brawler.get("power", "?")
                b_trophies = brawler.get("trophies", "?")
                if raw_type == "ranked":
                    team_str += f"-# - {p_name} → **{b_name.title()}** ({TROPHY_EMOJI} `{b_trophies:,}`, {POWER_POINT_EMOJI} `{b_power}`)\n"
                elif raw_type == "soloranked":
                    team_str += f"-# - {p_name} → **{b_name.title()}** ({POWER_POINT_EMOJI} `{b_power}`)\n"
                    embed.set_thumbnail(url=f"https://cdn-misc.brawlify.com/league/{b_trophies}.png")
                else:
                    team_str += f"-# - {p_name} → **{b_name.title()}** (<:info:1037445870469267638> `{b_trophies:,}`, {POWER_POINT_EMOJI} `{b_power}`)\n"
                    
            embed.add_field(name=team_labels[display_idx], value=team_str, inline=False)
        pages.append((embed, None))

    return pages


def sort_brawlers_data(data, color, sort_type='default'):
    tag = data['tag']
    prof = data['data']
    brawlers = prof.get('brawlers',[])[:] 

    if sort_type == 'alpha_asc':
        brawlers.sort(key=lambda b: b['name'])
    elif sort_type == 'alpha_desc':
        brawlers.sort(key=lambda b: b['name'], reverse=True)
    elif sort_type == 'trophy_high':
        brawlers.sort(key=lambda b: b['trophies'], reverse=True)
    elif sort_type == 'trophy_low':
        brawlers.sort(key=lambda b: b['trophies'])
    elif sort_type == 'power_high':
        brawlers.sort(key=lambda b: b['power'], reverse=True)
    elif sort_type == 'power_low':
        brawlers.sort(key=lambda b: b['power'])

    pages = []
    LIMIT_PER_PAGE = 18
    total_pages = max(1, (len(brawlers) + LIMIT_PER_PAGE - 1) // LIMIT_PER_PAGE)

    for i in range(0, max(1, len(brawlers)), LIMIT_PER_PAGE):
        emb = discord.Embed(title=f"{prof['name']} ({tag}) - Brawlers", color=color)
        for b in brawlers[i:i+LIMIT_PER_PAGE]:
            emb.add_field(
                name=f"{get_tier_emoji(b['highestTrophies'])} {b['name'].title()}",
                value=(
                    f"{TROPHY_EMOJI if b['trophies'] < 1000 else PRESTIGE_TROPHY_EMOJI} **`{b['trophies']:,}`** ㆍ {POWER_POINT_EMOJI} Power `{b['power']}`\n"
                    f"-# {GADGET_EMOJI} `{len(b.get('gadgets',[]))}` ㆍ {STARPOWER_EMOJI} `{len(b.get('starPowers',[]))}` ㆍ {GEAR_EMOJI} `{len(b.get('gears',[]))}`"
                ), inline=True)
        page_num = i//LIMIT_PER_PAGE + 1
        emb.set_footer(text=f"Page {page_num} of {total_pages}")
        pages.append((emb, None))
    return pages


class SectionView(discord.ui.View):
    def __init__(self, pages, author_id, prof_data=None, color=None):
        super().__init__(timeout=180)
        self.pages = pages
        self.section = 'home'
        self.idx = 0
        self.author = author_id
        self.prof_data = prof_data
        self.color = color
        self.message = None
        self._update_buttons()

    def _update_buttons(self):
        self.home_btn.disabled = False
        self.brawl_btn.disabled = len(self.pages.get('brawlers',[])) == 0
        self.match_btn.disabled = len(self.pages.get('matches',[])) == 0
        
        pgs = self.pages[self.section]
        self.first_btn.disabled = self.idx == 0
        self.prev_btn.disabled = self.idx == 0
        self.next_btn.disabled = self.idx == len(pgs)-1
        self.last_btn.disabled = self.idx == len(pgs)-1
        
        if hasattr(self, 'sort_select_menu'):
            self.sort_select_menu.disabled = self.section != 'brawlers'


    async def on_timeout(self):
        for b in self.children: b.disabled = True
        try: await self.message.edit(view=self)
        except: pass

    async def interaction_check(self, inter):
        if inter.user.id != self.author:
            await inter.response.send_message("Only the author can interact.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Home", style=discord.ButtonStyle.green)
    async def home_btn(self, inter, btn):
        self.section = 'home'
        self.idx = 0
        self._update_buttons()
        await inter.response.edit_message(embed=self.pages['home'][0], view=self)

    @discord.ui.button(label="Brawlers", style=discord.ButtonStyle.blurple)
    async def brawl_btn(self, inter, btn):
        if not self.pages.get('brawlers'): return
        self.section = 'brawlers'
        self.idx = 0
        self._update_buttons()
        await inter.response.edit_message(embed=self.pages['brawlers'][0][0], view=self)

    @discord.ui.button(label="Matches", style=discord.ButtonStyle.blurple)
    async def match_btn(self, inter, btn):
        if not self.pages.get('matches'):
            await inter.response.send_message("No recent matches.", ephemeral=True)
            return
        self.section = 'matches'
        self.idx = 0
        self._update_buttons()
        await inter.response.edit_message(embed=self.pages['matches'][0][0], view=self)

    @discord.ui.button(emoji="<:fastbackward:1351972112696479824>", style=discord.ButtonStyle.grey, row=1)
    async def first_btn(self, inter, btn):
        pgs = self.pages[self.section]
        self.idx = 0
        self._update_buttons()
        await inter.response.edit_message(embed=pgs[self.idx][0], view=self)

    @discord.ui.button(emoji="<:backarrow:1351972111010369618>", style=discord.ButtonStyle.grey, row=1)
    async def prev_btn(self, inter, btn):
        pgs = self.pages[self.section]
        self.idx = max(self.idx-1, 0)
        self._update_buttons()
        await inter.response.edit_message(embed=pgs[self.idx][0], view=self)

    @discord.ui.button(emoji="<:rightarrow:1351972116819480616>", style=discord.ButtonStyle.grey, row=1)
    async def next_btn(self, inter, btn):
        pgs = self.pages[self.section]
        self.idx = min(self.idx+1, len(pgs)-1)
        self._update_buttons()
        await inter.response.edit_message(embed=pgs[self.idx][0], view=self)

    @discord.ui.button(emoji="<:fastforward:1351972114433048719>", style=discord.ButtonStyle.grey, row=1)
    async def last_btn(self, inter, btn):
        pgs = self.pages[self.section]
        self.idx = len(pgs)-1
        self._update_buttons()
        await inter.response.edit_message(embed=pgs[self.idx][0], view=self)

    @discord.ui.select(
        placeholder="Sort Brawlers...",
        options=[
            discord.SelectOption(label="Default (Release)", value="default", description="Sort by release order"),
            discord.SelectOption(label="Alphabetical (A-Z)", value="alpha_asc", description="Sort from A to Z"),
            discord.SelectOption(label="Alphabetical (Z-A)", value="alpha_desc", description="Sort from Z to A"),
            discord.SelectOption(label="Highest Trophies", value="trophy_high", description="Sort by highest current trophies"),
            discord.SelectOption(label="Lowest Trophies", value="trophy_low", description="Sort by lowest current trophies"),
            discord.SelectOption(label="Highest Power", value="power_high", description="Sort by highest power level"),
            discord.SelectOption(label="Lowest Power", value="power_low", description="Sort by lowest power level"),
        ],
        row=2,
        disabled=True
    )
    async def sort_select_menu(self, inter: discord.Interaction, select: discord.ui.Select):
        if self.section != 'brawlers' or not self.prof_data:
            return await inter.response.defer()
            
        sort_type = select.values[0]
        self.pages['brawlers'] = sort_brawlers_data(self.prof_data, self.color, sort_type)
        self.idx = 0
        self._update_buttons()
        await inter.response.edit_message(embed=self.pages['brawlers'][0][0], view=self)

class Profile(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="profile", description="Display Brawl Stars profile data, brawlers, and recent matches")
    @app_commands.describe(tag="Specify a player tag (e.g. #9L00JQRGR)", user="Specify a Discord user who has linked their profile")
    async def profile(self, interaction: discord.Interaction, tag: str = None, user: discord.Member = None):
        if tag is not None and user is not None:
            return await interaction.response.send_message(f"Please either specify a player tag or a Discord user. Not both!", ephemeral=True)
        if user is None:
            user = interaction.user
        if tag is None:
            ref = u_tag(user.id)
            data = ref.get()
            if data and 'tag' in data:
                tag = data['tag']
        if tag is None: 
            if user == interaction.user:
                return await interaction.response.send_message(f"You haven't linked your profile yet. Please specify a profile tag or another Discord user.", ephemeral=True)
            else:
                return await interaction.response.send_message(f"{user.mention} hasn't linked their profile yet. Please specify a profile tag or another Discord user.", ephemeral=True)
        prof_resp, prof_data = fetch_profile(tag)
        match_resp, match_data = fetch_battlelog(tag)
        if not prof_resp.ok:
            return await interaction.response.send_message(f"Error fetching profile: {prof_resp.status_code}", ephemeral=True)
        
        await interaction.response.defer(thinking=True)
        raw_color = prof_data.get('nameColor','0xFFFFFF')
        try: color = int(raw_color,16)&0xFFFFFF
        except: color = 0xFFFFFF
        
        home_embed = await make_home(prof_data, color)
        pages = {
            'home': [home_embed],
            'brawlers': await make_brawlers(prof_data, color)
        }
        
        if match_resp.ok:
            pages['matches'] = await make_matches(match_data, tag, color)
        else:
            pages['matches'] = []
            
        view = SectionView(pages, interaction.user.id, prof_data, color)
        await interaction.followup.send(embed=pages['home'][0], view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(Profile(bot))

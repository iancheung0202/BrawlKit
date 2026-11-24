import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from brawl.Currency.card import BACKGROUND, render
from brawl.Currency.db import u_tag
from brawl.Currency.helper import NO_EMOTE
from brawl.Currency.panel import notice
from brawl.Utility import api
from brawl.Utility.playercard import (
    BATTLES_PER_PAGE,
    BRAWLERS_PER_PAGE,
    brawler_art,
    draw_battles,
    draw_brawlers,
    draw_profile,
    face,
    league_art,
    mode_art,
    sides,
)

# Sort: (name in the menu, what it sorts by, highest first)
SORTS = {
    "default": ("Release order", None, False),
    "trophy_high": ("Most trophies", lambda brawler: brawler["trophies"], True),
    "trophy_low": ("Fewest trophies", lambda brawler: brawler["trophies"], False),
    "power_high": ("Highest power", lambda brawler: brawler["power"], True),
    "power_low": ("Lowest power", lambda brawler: brawler["power"], False),
    "alpha_asc": ("A to Z", lambda brawler: brawler["name"], False),
    "alpha_desc": ("Z to A", lambda brawler: brawler["name"], True),
}
PER_PAGE = {"brawlers": BRAWLERS_PER_PAGE, "battles": BATTLES_PER_PAGE}
STATS = (
    "trophies",
    "highestRankedPoints",
    "famePoints",
    "soloVictories",
    "duoVictories",
    "3vs3Victories",
)


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


def linked(user_id):
    data = u_tag(user_id).get()
    return api.clean_tag(data["tag"]) if data and "tag" in data else None


def keep_stats(user_id, stats):
    """Saves the six numbers the in-game leaderboards rank a linked member by."""
    u_tag(user_id).update({"stats": {stat: stats.get(stat, 0) for stat in STATS}})


def sorted_brawlers(brawlers, sort):
    _, key, reverse = SORTS[sort]
    return sorted(brawlers, key=key, reverse=reverse) if key else list(brawlers)


class ProfileView(discord.ui.View):
    """Profile, brawlers and battles of one player. A page is drawn when it is opened."""

    def __init__(self, author_id, profile, battles):
        super().__init__(timeout=180)
        self.author_id, self.profile, self.battles = author_id, profile, battles
        self.section, self.page, self.sort = "profile", 0, "default"
        self.message = None
        self.sort_menu.options = [
            discord.SelectOption(label=name, value=value)
            for value, (name, *_) in SORTS.items()
        ]
        self.refresh()

    def rows(self):
        if self.section == "brawlers":
            return sorted_brawlers(self.profile["stats"].get("brawlers", []), self.sort)
        return self.battles if self.section == "battles" else []

    def pages(self):
        return max(-(-len(self.rows()) // PER_PAGE.get(self.section, 1)), 1)

    def refresh(self):
        stats = self.profile["stats"]
        self.brawlers_button.disabled = not stats.get("brawlers")
        self.battles_button.disabled = not self.battles
        last = self.pages() - 1
        self.first_button.disabled = self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.last_button.disabled = self.page >= last
        self.sort_menu.disabled = self.section != "brawlers"

    async def file(self):
        shared = {
            "player": self.profile["player"],
            "background": self.profile["background"],
            "page": self.page + 1,
            "pages": self.pages(),
        }
        if self.section == "profile":
            return await render(draw_profile, self.profile, name="profile")
        size = PER_PAGE[self.section]
        rows = self.rows()[self.page * size : (self.page + 1) * size]
        if self.section == "brawlers":
            art = await api.images(brawler_art(brawler["id"]) for brawler in rows)
            count = len(self.rows())
            page = {
                **shared,
                "brawlers": rows,
                "art": art,
                "sort": SORTS[self.sort][0],
                "total": f"{count} brawler{'s' * (count != 1)}",
            }
            return await render(draw_brawlers, page, name="brawlers")
        paths = []
        for item in rows:
            if item.get("event", {}).get("modeId") is not None:
                paths.append(mode_art(item["event"]))
            for side in sides(item.get("battle", {}), shared["player"]["tag"]):
                paths += [brawler_art(player["brawler"]["id"]) for player in side]
        page = {**shared, "battles": rows, "art": await api.images(paths)}
        return await render(draw_battles, page, name="battles")

    async def show(self, interaction, section=None, page=0):
        self.section, self.page = section or self.section, page
        self.refresh()
        await interaction.response.defer()
        await interaction.edit_original_response(
            attachments=[await self.file()], view=self
        )

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} Only the member who ran this can use it.", "bad"
                ),
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except (discord.HTTPException, AttributeError):
            pass

    @discord.ui.button(label="Profile", style=discord.ButtonStyle.green)
    async def profile_button(self, interaction, button):
        await self.show(interaction, "profile")

    @discord.ui.button(label="Brawlers", style=discord.ButtonStyle.blurple)
    async def brawlers_button(self, interaction, button):
        await self.show(interaction, "brawlers")

    @discord.ui.button(label="Battles", style=discord.ButtonStyle.blurple)
    async def battles_button(self, interaction, button):
        await self.show(interaction, "battles")

    @discord.ui.button(
        emoji="<:fastbackward:1351972112696479824>",
        style=discord.ButtonStyle.grey,
        row=1,
    )
    async def first_button(self, interaction, button):
        await self.show(interaction)

    @discord.ui.button(
        emoji="<:backarrow:1351972111010369618>", style=discord.ButtonStyle.grey, row=1
    )
    async def prev_button(self, interaction, button):
        await self.show(interaction, page=max(self.page - 1, 0))

    @discord.ui.button(
        emoji="<:rightarrow:1351972116819480616>", style=discord.ButtonStyle.grey, row=1
    )
    async def next_button(self, interaction, button):
        await self.show(interaction, page=min(self.page + 1, self.pages() - 1))

    @discord.ui.button(
        emoji="<:fastforward:1351972114433048719>",
        style=discord.ButtonStyle.grey,
        row=1,
    )
    async def last_button(self, interaction, button):
        await self.show(interaction, page=self.pages() - 1)

    @discord.ui.select(placeholder="Sort brawlers", row=2)
    async def sort_menu(self, interaction, select):
        self.sort = select.values[0]
        await self.show(interaction, "brawlers")


async def show_profile(interaction, tag, owner=None, ephemeral=False):
    """Sends a player's profile cards as the follow-up to a deferred interaction."""
    stats, battles, total = await asyncio.gather(
        api.get_stats(tag), api.get_battles(tag), api.brawler_count()
    )
    if not stats:
        return await interaction.followup.send(
            embed=notice(
                f"{NO_EMOTE} No player found for `{api.clean_tag(tag)}`. "
                "Check the tag and try again.",
                "bad",
            ),
            ephemeral=ephemeral,
        )
    if owner:
        keep_stats(owner.id, stats)
    ranks = [stats.get("ranked", 0), stats.get("highestRanked", 0)]
    player, art = await asyncio.gather(
        face(tag, stats), api.images(league_art(rank) for rank in ranks)
    )
    profile = {
        "stats": stats,
        "art": art,
        "player": player,
        "brawlers": total,
        "background": BACKGROUND,
    }
    view = ProfileView(interaction.user.id, profile, battles[:25])
    view.message = await interaction.followup.send(
        file=await view.file(), view=view, ephemeral=ephemeral
    )


class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="profile",
        description="See a Brawl Stars profile, its brawlers and recent battles",
    )
    @app_commands.describe(
        tag="A player tag, for example #9L00JQRGR",
        user="A member who has linked their account",
    )
    async def profile(
        self,
        interaction: discord.Interaction,
        tag: str = None,
        user: discord.Member = None,
    ):
        async def refuse(text):
            await interaction.response.send_message(
                embed=notice(f"{NO_EMOTE} {text}", "bad"), ephemeral=True
            )

        if tag and user:
            return await refuse("Give a player tag or a member, not both.")
        owner = None if tag else user or interaction.user
        if owner:
            tag = linked(owner.id)
        if not tag and owner == interaction.user:
            return await refuse(
                "You have not linked an account yet. Give a player tag or a member."
            )
        if not tag:
            return await refuse(
                f"{owner.mention} has not linked an account yet. Give a player tag."
            )
        await interaction.response.defer(thinking=True)
        await show_profile(interaction, tag, owner)


async def setup(bot):
    await bot.add_cog(Profile(bot))

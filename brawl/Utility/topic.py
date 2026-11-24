import random

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View
from firebase_admin import db

from brawl.Currency import wallet
from brawl.Currency.config import TOPIC_BEANS
from brawl.Currency.helper import BEAN_EMOTE, MAIN_GUILD_ID, TOPIC_REVIEW
from brawl.Currency.panel import notice
from brawl.Currency.rewardcard import draw_topic
from brawl.Utility.style import BLUE, GOLD, GREEN, NO, RED, YES

PENDING = "/Cafe Topics/Pending"
APPROVED = "/Cafe Topics/Approved"

ICEBREAKERS = [
    "What's your favorite Brawl Stars brawler and why?",
    "If you could create a new game mode for Brawl Stars, what would it be?",
    "What's the most memorable moment you've had in Brawl Stars?",
    "Which brawler do you think needs a buff or nerf?",
    "What's your favorite map to play on?",
    "If you could team up with any professional Brawl Stars player, who would it be?",
    "What's your go-to strategy in Gem Grab?",
    "Which brawler has the best skins in your opinion?",
    "What's the funniest thing that's happened to you in a match?",
    "If you could add any crossover character to Brawl Stars, who would it be?",
    "Which event mode do you enjoy the most?",
    "What's your highest trophy count ever?",
    "If you could design a skin for any brawler, what would it look like?",
    "Which Supercell game (Clash, Clash Royale, etc.) should get a Brawl Stars crossover?",
    "Who is the most underrated brawler right now?",
    "What's the best gadget in the game?",
    "Which star power completely changes how you play a brawler?",
    "Who do you usually pick for Solo Showdown?",
    "What's the best duo partner combo?",
    "What was the first legendary brawler you unlocked?",
    "If you could swap abilities between two brawlers, which ones would you switch?",
    "What's your least favorite map and why?",
    "Which brawler has the funniest voice lines?",
    "What's your favorite limited-time mode?",
    "Who do you think has the coolest super?",
    "What's the most clutch play you’ve ever made?",
    "If you could buff one gadget, which one would it be?",
    "Which skin do you regret not buying?",
    "What's the first skin you ever bought?",
    "Which brawler is the hardest to master?",
    "Which brawler is the easiest to play?",
    "Who’s your favorite healer?",
    "What’s your go-to strategy in Brawl Ball?",
    "Who’s your favorite support-type brawler?",
    "What’s your favorite special event (like Robo Rumble or Big Game)?",
    "Have you ever maxed out a brawler before anyone else?",
    "Which season of Brawl Pass was your favorite?",
    "What's the most gems you've ever saved up?",
    "Who do you think has the best base attack animation?",
    "What’s your least favorite game mode?",
    "Which brawler do you love but struggle to play well?",
    "If you could create a custom emote, what would it be?",
    "What's the rarest skin you own?",
    "What's the rarest skin you wish you owned?",
    "Who’s your favorite chromatic brawler?",
    "Which chromatic skin looks the best?",
    "Who has the best voice acting?",
    "Which super is the most satisfying to use?",
    "What’s your favorite loading screen art?",
    "If you could bring back an old map permanently, which one would it be?",
    "Who do you always ban in Power League?",
    "Which brawler do you wish you unlocked earlier?",
    "What’s the most annoying brawler to face?",
    "What's your highest rank in Power League?",
    "What's your favorite emote?",
    "Which brawler should get a rework?",
    "What’s your favorite trio (bandits, pirates, etc.)?",
    "Which duo comp is unbeatable?",
    "What’s your go-to strategy in Heist?",
    "If you could make a Brawl Stars movie, who would be the main character?",
    "Which brawler feels the most fun to play?",
    "What’s the most overpowered brawler in history?",
    "Who’s your favorite mythic brawler?",
    "Who’s your favorite epic brawler?",
    "Who’s your favorite rare brawler?",
    "Which game mode do you find the most competitive?",
    "What’s the funniest gadget in the game?",
    "If you could remove one gadget, which would it be?",
    "Who’s the best assassin brawler?",
    "What’s your favorite Brawl Stars update?",
    "Which seasonal environment is your favorite?",
    "Which skin line is the coolest (gold, mecha, etc.)?",
    "What’s your favorite Brawl Stars meme?",
    "Who’s the most stylish brawler?",
    "Which brawler has the best winning animation?",
    "Which brawler has the best losing animation?",
    "What’s the biggest comeback you’ve seen?",
    "Which super do you fear the most?",
    "Which game mode do you push trophies in most?",
    "What’s your favorite skin line (like Lunar New Year, Halloween, etc.)?",
    "Who’s your least favorite legendary?",
    "Which map is the most chaotic?",
    "What’s your highest win streak?",
    "Which brawler looks the funniest when they die?",
    "If you could design a map, what theme would it have?",
    "Which brawler is best in Brawl Ball?",
    "Which brawler is best in Heist?",
    "Which brawler is best in Knockout?",
    "Which brawler is best in Hot Zone?",
    "Who do you always pick for Siege?",
    "What’s the most gems you’ve spent at once?",
    "Which skin has the best effects?",
    "What’s your favorite background music theme?",
    "Who’s the cutest brawler?",
    "Who’s the scariest brawler?",
    "Which brawler is best in Big Game?",
    "Which brawler is best in Robo Rumble?",
    "Which brawler is best in Boss Fight?",
    "Who’s your favorite duo showdown partner?",
    "Which super takes the most skill?",
    "Who’s the best long-range brawler?",
    "Who’s the best close-range brawler?",
    "Which map has the best design?",
    "What’s your favorite Brawl Stars esports moment?",
    "Who’s your favorite esports team?",
    "Which brawler would you want as a real-life friend?",
    "If you could voice act a brawler, who would it be?",
    "What’s the most toxic comp you’ve seen?",
    "Which gadget makes you laugh every time?",
    "Which star power should be reworked?",
    "Who’s your dream brawler team of three?",
    "What’s your most embarrassing match?",
    "If you could add a new rarity, what would it be?",
    "What’s your favorite thing about Brawl Stars?",
]


def draw():
    """A random topic and the member who sent it in, if a member did."""
    sent = list((db.reference(APPROVED).get() or {}).values())
    spot = random.randrange(len(ICEBREAKERS) + len(sent))
    if spot < len(ICEBREAKERS):
        return ICEBREAKERS[spot], None
    topic = sent[spot - len(ICEBREAKERS)]
    return topic["text"], topic["user"]


def approved_by(user_id: int) -> int:
    """How many of this member's topics were approved."""
    topics = (db.reference(APPROVED).get() or {}).values()
    return sum(topic.get("user") == user_id for topic in topics)


def topic_embed():
    text, user_id = draw()
    embed = discord.Embed(title=text, color=GOLD)
    if user_id:
        embed.description = f"-# Asked by <@{user_id}>"
    return embed


class AddModal(Modal, title="Suggest a topic"):
    text = TextInput(
        label=f"Your question ({TOPIC_BEANS} Beans if approved)",
        placeholder="Which brawler would run the best cafe?",
        min_length=10,
        max_length=150,
    )

    async def on_submit(self, interaction: discord.Interaction):
        waiting = (db.reference(PENDING).get() or {}).values()
        if any(topic["user"] == interaction.user.id for topic in waiting):
            await interaction.response.send_message(
                embed=notice(
                    f"{NO} Staff are still looking at your last topic. "
                    "Suggest another once they are done.",
                    "bad",
                ),
                ephemeral=True,
            )
            return
        text = self.text.value.strip()
        review = discord.Embed(title=text, color=BLUE)
        review.description = f"Topic suggested by {interaction.user.mention}"
        sent = await interaction.guild.get_channel(TOPIC_REVIEW).send(
            embed=review, view=ReviewView()
        )
        db.reference(PENDING).child(str(sent.id)).set(
            {"user": interaction.user.id, "text": text}
        )
        await interaction.response.send_message(
            embed=notice(
                f"{YES} Sent to staff. If they approve it, it joins `/topic` with "
                f"your name and you get {BEAN_EMOTE} `{TOPIC_BEANS}`.",
                "good",
            ),
            ephemeral=True,
        )


class EditModal(Modal, title="Edit the topic"):
    """Staff fix the wording of a suggestion before they approve it."""

    def __init__(self, text: str):
        super().__init__()
        self.text = TextInput(
            label="Question", default=text, min_length=10, max_length=150
        )
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        ref = db.reference(PENDING).child(str(interaction.message.id))
        if not ref.get():
            await interaction.response.edit_message(view=None)
            return
        text = self.text.value.strip()
        ref.update({"text": text})
        embed = interaction.message.embeds[0]
        embed.title = text
        await interaction.response.edit_message(embed=embed)


async def tell(interaction: discord.Interaction, topic: dict, approved: bool):
    """DM the member how their suggestion went. Closed DMs are skipped."""
    card = draw_topic(
        {"approved": approved, "text": topic["text"], "beans": TOPIC_BEANS}
    )
    guild = interaction.guild
    try:
        # Members are not cached at startup, so one the bot has not seen is fetched.
        member = guild.get_member(topic["user"]) or await guild.fetch_member(
            topic["user"]
        )
        await member.send(file=discord.File(card, "topic.jpg"))
    except discord.HTTPException:
        pass


class ReviewView(View):
    """Staff approve a member's topic, which pays the member, or turn it down."""

    def __init__(self):
        super().__init__(timeout=None)

    async def settle(self, interaction: discord.Interaction, approved: bool):
        ref = db.reference(PENDING).child(str(interaction.message.id))
        topic = ref.get()
        if not topic:
            await interaction.response.edit_message(view=None)
            return
        ref.delete()
        embed = interaction.message.embeds[0]
        embed.color = GREEN if approved else RED
        if approved:
            db.reference(APPROVED).push().set(topic)
            await wallet.change(topic["user"], beans=TOPIC_BEANS, reason="topic")
            embed.description += (
                f"\n{YES} Approved by {interaction.user.mention}, "
                f"paid {BEAN_EMOTE} `{TOPIC_BEANS}`"
            )
        else:
            embed.description += f"\n{NO} Turned down by {interaction.user.mention}"
        await interaction.response.edit_message(embed=embed, view=None)
        await tell(interaction, topic, approved)

    @discord.ui.button(
        label="Approve", style=discord.ButtonStyle.green, custom_id="topic_approve"
    )
    async def approve(self, interaction: discord.Interaction, button: Button):
        await self.settle(interaction, True)

    @discord.ui.button(
        label="Edit", style=discord.ButtonStyle.grey, custom_id="topic_edit"
    )
    async def edit(self, interaction: discord.Interaction, button: Button):
        topic = db.reference(PENDING).child(str(interaction.message.id)).get()
        if not topic:
            await interaction.response.edit_message(view=None)
            return
        await interaction.response.send_modal(EditModal(topic["text"]))

    @discord.ui.button(
        label="Turn down", style=discord.ButtonStyle.red, custom_id="topic_reject"
    )
    async def reject(self, interaction: discord.Interaction, button: Button):
        await self.settle(interaction, False)


class TopicView(View):
    def __init__(self, cafe: bool):
        super().__init__(timeout=600)
        self.message = None
        if not cafe:
            self.remove_item(self.add)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Another topic", style=discord.ButtonStyle.blurple)
    async def another(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(embed=topic_embed())

    @discord.ui.button(label="Suggest a topic", style=discord.ButtonStyle.grey)
    async def add(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AddModal())


class Topic(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="topic", description="Get something to talk about")
    @app_commands.guild_only()
    async def topic(self, interaction: discord.Interaction) -> None:
        view = TopicView(interaction.guild.id == MAIN_GUILD_ID)
        await interaction.response.send_message(embed=topic_embed(), view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    bot.add_view(ReviewView())
    await bot.add_cog(Topic(bot))

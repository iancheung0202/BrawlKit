"""Today's poll: one topic a day, as a Discord poll with a thread under it.

A topic is picked a day early and Devin researches the game to write its
answers, which staff approve or edit in the topic review channel. At midnight
UTC it is posted, approved or not. Voting and then sending an effortful message
in its thread finishes the "Answer today's poll" task. A topic that got no
answers is posted as an open question, and the thread message alone finishes
the task.

The very first poll does not wait for midnight: it goes to staff at once and
is posted when they approve it, FIRST_WAIT seconds later at the earliest. Left
unapproved, it is posted at midnight like any other.
"""

import asyncio
import json
import random
import secrets
import time
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from discord.ui import Button, Modal, TextInput, View
from firebase_admin import db

from brawl.Currency.card import render
from brawl.Currency.chat import effortful, face, paid
from brawl.Currency.guide import guide
from brawl.Currency.helper import MAIN_GUILD_ID, POLL_CHANNEL, POLL_ROLE, TOPIC_REVIEW
from brawl.Currency.quests import order_guide, update_quest
from brawl.Currency.rewardcard import draw_paid
from brawl.Utility import api, topicmatch
from brawl.Utility.style import BLUE, GOLD, GREEN, NO, YES
from brawl.Utility.topic import APPROVED, ICEBREAKERS

ROOT = "/Cafe Topics/Poll"
WRITER = "/Cafe Topics/Poll Writer"
PROMPT = (
    "You write the answers for a daily poll in Brawl Cafe, a Discord server "
    "for Brawl Stars players, many of them young. Each message gives you one "
    "poll topic. Your knowledge of the game is out of date, so look up the "
    "game as it is today before every answer, and never use a name you have "
    "not just checked. Do not ask questions and do not write code. Reply only "
    "in the JSON form each message asks for."
)
RESEARCH_WAIT, RESEARCH_EVERY = 1800, 30
FIRST_WAIT = 1800
QUESTION, ANSWER, MOST = 300, 55, 10
TASK = "topic_polls"
ASK = (
    "Tomorrow's poll topic: {topic}\n\n"
    "Brawlers in the game right now: {brawlers}\n"
    "Game modes playing today: {modes}\n\n"
    "Research first. Search the web for the current state of Brawl Stars "
    "(official release notes, the Brawl Stars wiki, recent news) and check "
    "every name you plan to use. Take as long as you need. Then write 3 to 6 "
    "answers members can vote for.\n"
    "- Every brawler, skin, gadget, star power, mode, map or event must exist "
    "in the game today, spelled as the game spells it. Never invent one.\n"
    "- Nothing removed, renamed or out of date. If the topic itself is out of "
    "date, fix the question with as small a change as you can.\n"
    "- Each answer is at most 40 characters. The question is at most 150.\n"
    "- When the choices cannot cover everyone, end with 'Someone else' or "
    "'Something else'.\n"
    "- Safe for young members. No links.\n"
    "Answer with one line of JSON and nothing else: "
    '{{"id": "{tag}", "question": "<the topic>", "answers": ["<answer>"], '
    '"checked": "<what you checked and where, at most 25 words>"}}'
)
running = set()  # research in progress, held so it is not dropped half way


def day(ahead=0):
    return (datetime.now(timezone.utc) + timedelta(days=ahead)).strftime("%Y-%m-%d")


def midnight(date):
    return int(
        datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    )


def pick(avoid=()):
    """A topic no poll has used yet, with the member who sent it in if one did.
    Once every topic has been used, they all come round again."""
    sent = (db.reference(APPROVED).get() or {}).values()
    pool = [(text, None) for text in ICEBREAKERS]
    pool += [(topic["text"], topic["user"]) for topic in sent]
    used = set((db.reference(ROOT).child("used").get() or {}).values())
    fresh = [topic for topic in pool if topic[0] not in used | set(avoid)]
    if not fresh:
        db.reference(ROOT).child("used").delete()
        fresh = [topic for topic in pool if topic[0] not in avoid] or pool
    return random.choice(fresh)


def tidy(answers):
    """Up to MOST different answers, each short enough for a poll."""
    kept = []
    for answer in answers if isinstance(answers, list) else []:
        answer = " ".join(str(answer).split())[:ANSWER]
        if answer and answer.lower() not in [one.lower() for one in kept]:
            kept.append(answer)
    return kept[:MOST] if len(kept) >= 2 else []


def written(messages, tag):
    """The question, answers and research note Devin sent back, or None so far."""
    for found in topicmatch.replies(messages, tag):
        answers = tidy(found.get("answers"))
        if not answers:
            continue
        question = " ".join(str(found.get("question") or "").split())[:QUESTION]
        note = " ".join(str(found.get("checked") or "").split())[:200]
        return question, answers, note
    return None


async def research(topic):
    """Devin's poll for this topic, after it has looked the game up."""
    tag = secrets.token_hex(4)
    asked = ASK.format(
        topic=json.dumps(topic),
        brawlers=", ".join(await api.brawler_names()) or "look them up",
        modes=", ".join((await api.modes()).values()),
        tag=tag,
    )
    return await topicmatch.reply(
        asked,
        lambda messages: written(messages, tag),
        kept_at=WRITER,
        prompt=PROMPT,
        title="BrawlKit daily poll",
        wait=RESEARCH_WAIT,
        every=RESEARCH_EVERY,
    )


def review_embed(plan):
    """What staff see: tomorrow's poll and where its answers stand."""
    embed = discord.Embed(
        title=plan["text"], color=GREEN if plan.get("approved") else BLUE
    )
    embed.description = f"Poll for <t:{int(plan['at'])}:f>"
    if plan.get("user"):
        embed.description += f", asked by <@{plan['user']}>"
    answers = plan.get("answers")
    if answers:
        listed = "\n".join(
            f"{spot}. {answer}" for spot, answer in enumerate(answers, 1)
        )
    elif plan.get("tried"):
        listed = "-# None. Add them with Edit, or it posts as an open question."
    else:
        listed = "-# Researching the game"
    embed.add_field(name="Answers", value=listed, inline=False)
    if plan.get("note"):
        embed.add_field(name="Checked", value=plan["note"], inline=False)
    if plan.get("approved"):
        embed.description += f"\n{YES} Approved by <@{plan['approved']}>"
    elif plan.get("posted"):
        embed.description += "\n-# Auto posted, no staff approved it"
    elif plan.get("first"):
        embed.description += "\n-# Posts once approved, or by itself at midnight UTC"
    else:
        embed.description += "\n-# Posts by itself if no staff approve it"
    return embed


def planned(interaction):
    """Tomorrow's poll, if this is still its review message."""
    plan = db.reference(ROOT).child("next").get() or {}
    return plan if plan.get("review") == interaction.message.id else None


class EditModal(Modal, title="Edit the poll"):
    def __init__(self, plan):
        super().__init__()
        self.text = TextInput(
            label="Question", default=plan["text"], min_length=10, max_length=QUESTION
        )
        self.answers = TextInput(
            label=f"Answers, one on each line (2 to {MOST})",
            style=discord.TextStyle.paragraph,
            default="\n".join(plan.get("answers") or []),
            max_length=MOST * (ANSWER + 1),
        )
        self.add_item(self.text)
        self.add_item(self.answers)

    async def on_submit(self, interaction: discord.Interaction):
        plan = planned(interaction)
        if not plan:
            await interaction.response.edit_message(view=None)
            return
        answers = tidy(self.answers.value.split("\n"))
        if not answers:
            await interaction.response.send_message(
                f"{NO} A poll needs at least 2 different answers.", ephemeral=True
            )
            return
        plan.update(text=self.text.value.strip(), answers=answers, tried=True)
        db.reference(ROOT).child("next").set(plan)
        await interaction.response.edit_message(embed=review_embed(plan))


class ReviewView(View):
    """Staff approve tomorrow's poll, fix its wording, or ask for another topic."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Approve", style=discord.ButtonStyle.green, custom_id="poll_approve"
    )
    async def approve(self, interaction: discord.Interaction, button: Button):
        plan = planned(interaction)
        if not plan:
            await interaction.response.edit_message(view=None)
            return
        if not plan.get("answers"):
            await interaction.response.send_message(
                f"{NO} There are no answers yet. Add them with Edit.", ephemeral=True
            )
            return
        plan["approved"] = interaction.user.id
        db.reference(ROOT).child("next").set(plan)
        await interaction.response.edit_message(embed=review_embed(plan))

    @discord.ui.button(
        label="Edit", style=discord.ButtonStyle.grey, custom_id="poll_edit"
    )
    async def edit(self, interaction: discord.Interaction, button: Button):
        plan = planned(interaction)
        if not plan:
            await interaction.response.edit_message(view=None)
            return
        await interaction.response.send_modal(EditModal(plan))

    @discord.ui.button(
        label="Another topic", style=discord.ButtonStyle.grey, custom_id="poll_swap"
    )
    async def swap(self, interaction: discord.Interaction, button: Button):
        plan = planned(interaction)
        polls = interaction.client.get_cog("Polls")
        if not plan or not polls:
            await interaction.response.edit_message(view=None)
            return
        text, user = pick(avoid=[plan["text"]])
        plan = {
            key: plan[key] for key in ("day", "at", "review", "first") if key in plan
        }
        plan.update(text=text, user=user)
        db.reference(ROOT).child("next").set(plan)
        await interaction.response.edit_message(embed=review_embed(plan))
        polls.write(plan)


class Polls(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ref = db.reference(ROOT)
        self.live = self.ref.child("live").get() or {}
        self.task = bot.loop.create_task(self.loop())

    def cog_unload(self):
        self.task.cancel()

    async def loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self.tick()
            except Exception as e:
                print(f"Daily poll failed: {e}")
            await asyncio.sleep(60)

    async def tick(self):
        """Posts today's poll once, then gets tomorrow's ready for staff."""
        plan = self.ref.child("next").get() or {}
        if not self.live and not plan:
            return await self.plan(day(), time.time() + FIRST_WAIT, first=True)
        if self.live.get("day") != day():
            due = plan.get("day", "9") <= day()  # an unapproved first poll may be older
            early = plan.get("day") == day() and plan.get("first")
            waits = early and not plan.get("approved")
            if not waits and time.time() >= (plan["at"] if due else 0):
                await self.post(plan if due else {})
        elif plan.get("day") != day(1):
            return await self.plan(day(1), midnight(day(1)))
        if not plan.get("tried") and not running and plan.get("review"):
            self.write(plan)  # the bot restarted while Devin was researching

    async def plan(self, date, at, **more):
        """Picks a topic, shows it to staff, and starts the research."""
        channel = self.bot.get_channel(TOPIC_REVIEW)
        if channel is None:
            return
        text, user = pick()
        plan = {"day": date, "at": at, "text": text, "user": user, **more}
        sent = await channel.send(embed=review_embed(plan), view=ReviewView())
        plan["review"] = sent.id
        self.ref.child("next").set(plan)
        self.write(plan)

    def write(self, plan):
        task = asyncio.create_task(self.answers(plan))
        running.add(task)
        task.add_done_callback(running.discard)

    async def answers(self, plan):
        """Fills in the review once Devin has answered, unless staff moved on."""
        try:
            found = await research(plan["text"])
        except topicmatch.Unavailable:
            found = None
        now = self.ref.child("next").get() or {}
        same = (now.get("review"), now.get("text")) == (plan["review"], plan["text"])
        if not same or now.get("answers"):
            return
        now["tried"] = True
        if found:
            question, now["answers"], now["note"] = found
            now["text"] = question or now["text"]
        self.ref.child("next").set(now)
        try:
            channel = self.bot.get_channel(TOPIC_REVIEW)
            message = channel.get_partial_message(plan["review"])
            await message.edit(embed=review_embed(now))
        except (discord.HTTPException, AttributeError):
            pass

    async def post(self, plan):
        """Today's poll and its thread, and the review marked as posted."""
        channel = self.bot.get_channel(POLL_CHANNEL)
        if channel is None:
            return
        if not plan:
            text, user = pick()
            plan = {"text": text, "user": user}
        answers = plan.get("answers")
        asked = f"\n-# Asked by <@{plan['user']}>" if plan.get("user") else ""
        more = {
            "content": f"<@&{POLL_ROLE}>{asked}",
            "allowed_mentions": discord.AllowedMentions(roles=True, users=False),
        }
        if answers:
            poll = discord.Poll(question=plan["text"], duration=timedelta(hours=24))
            for answer in answers:
                poll.add_answer(text=answer)
            sent = await channel.send(poll=poll, **more)
        else:
            sent = await channel.send(
                embed=discord.Embed(title=plan["text"], color=GOLD), **more
            )
        old, self.live = self.live, {
            "day": day(),
            "message": sent.id,
            "poll": bool(answers),
        }
        self.ref.child("live").set(self.live)
        self.ref.child("used").push().set(plan["text"])
        if plan.get("review"):
            plan["posted"] = True
            await self.close(
                TOPIC_REVIEW, plan["review"], embed=review_embed(plan), view=None
            )
        thread = await sent.create_thread(
            name=plan["text"][:100], auto_archive_duration=1440
        )
        await thread.send(
            "Vote, then tell us why here." if answers else "Tell us your answer here.",
            view=guide("order"),
        )
        if old.get("message"):
            await self.close(old["message"], old["message"], locked=True, archived=True)

    async def close(self, channel_id, message_id, **changes):
        """Locks yesterday's thread, or takes the buttons off a posted review."""
        try:
            channel = self.bot.get_channel(channel_id)
            if "view" in changes:
                await channel.get_partial_message(message_id).edit(**changes)
            elif channel:
                await channel.edit(**changes)
        except (discord.HTTPException, AttributeError):
            pass

    def did(self, part, user_id):
        self.live.setdefault(part, {})[str(user_id)] = True
        self.ref.child("live").child(part).child(str(user_id)).set(True)

    def has(self, part, user_id):
        return str(user_id) in self.live.get(part, {})

    async def finish(self, user_id):
        """Moves the member's order once they have voted and said why."""
        voted = self.has("voted", user_id) or not self.live.get("poll")
        if not voted or not self.has("replied", user_id) or self.has("done", user_id):
            return
        self.did("done", user_id)
        order = await update_quest(user_id, MAIN_GUILD_ID, {TASK: 1}, self.bot)
        thread = self.bot.get_channel(self.live["message"])
        guild = self.bot.get_guild(MAIN_GUILD_ID)
        member = guild and guild.get_member(user_id)
        if not order or not thread or not member:
            return
        strip = await render(
            draw_paid,
            {
                "name": member.display_name,
                "avatar": await face(member),
                **paid(order),
            },
            name="order",
        )
        await thread.send(file=strip, view=order_guide(order))

    @commands.Cog.listener()
    async def on_raw_poll_vote_add(self, payload):
        if payload.message_id == self.live.get("message"):
            self.did("voted", payload.user_id)
            await self.finish(payload.user_id)

    @commands.Cog.listener()
    async def on_message(self, message):
        # A thread made from a message has that message's id.
        if (
            message.author.bot
            or message.channel.id != self.live.get("message")
            or self.has("replied", message.author.id)
            or not effortful(self.bot, message)
        ):
            return
        self.did("replied", message.author.id)
        await self.finish(message.author.id)


async def setup(bot: commands.Bot) -> None:
    bot.add_view(ReviewView())
    await bot.add_cog(Polls(bot))

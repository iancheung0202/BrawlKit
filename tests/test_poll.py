import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from brawl.Currency.db import u_quests
from brawl.Utility import poll, topicmatch

MEMBER, STAFF, REVIEW, POST = 1, 2, 55, 77


@pytest.fixture
def polls(cafe, monkeypatch):
    """The cog with its channels mocked; research answers at once."""
    review, public = MagicMock(), MagicMock()
    review.send = AsyncMock(return_value=MagicMock(id=REVIEW))
    review.get_partial_message.return_value.edit = AsyncMock()
    sent = MagicMock(id=POST)
    sent.create_thread = AsyncMock()
    public.send = AsyncMock(return_value=sent)
    public.edit = AsyncMock()
    channels = {poll.TOPIC_REVIEW: review, poll.POLL_CHANNEL: public, POST: public}
    cafe.bot.get_channel = channels.get
    cog = poll.Polls(cafe.bot)
    cog.review, cog.public, cog.cafe = review, public, cafe
    monkeypatch.setattr(poll, "render", AsyncMock(return_value="strip"))
    cog.found = ("Who is the best tank?", ["Bull", "Frank", "Someone else"], "Wiki")
    cog.starts = []

    async def research(topic):
        if isinstance(cog.found, Exception):
            raise cog.found
        return cog.found

    monkeypatch.setattr(poll, "research", research)
    monkeypatch.setattr(cog, "write", lambda plan: cog.starts.append(plan))
    return cog


def run(coroutine):
    return asyncio.run(coroutine)


def plan(polls):
    return polls.ref.child("next").get() or {}


def researched(polls):
    run(polls.answers(polls.starts[-1]))


def press(polls, button, user=STAFF, message=REVIEW):
    interaction = polls.cafe.interaction(user)
    interaction.message.id = message
    polls.cafe.cogs["Polls"] = polls

    async def go():
        await getattr(poll.ReviewView(), button).callback(interaction)

    run(go())
    return interaction


def started(polls):
    """A cog whose first poll is planned, researched and approved."""
    run(polls.tick())
    researched(polls)
    press(polls, "approve")
    return polls


def posted(polls):
    """A live poll today."""
    started(polls)
    polls.ref.child("next").child("at").set(time.time() - 1)
    run(polls.tick())
    return polls


def message(polls, content="Frank because he is so tanky", channel=POST, user=MEMBER):
    sent = MagicMock(content=content)
    sent.author.bot, sent.author.id, sent.channel.id = False, user, channel
    run(polls.on_message(sent))


def vote(polls, user=MEMBER, message_id=POST):
    run(polls.on_raw_poll_vote_add(MagicMock(message_id=message_id, user_id=user)))


def task(polls, user=MEMBER):
    u_quests(user).child("daily").set(
        {
            "quests": {poll.TASK: {"current": 0, "goal": 1}},
            "end_time": time.time() + 3600,
            "completed": {},
        }
    )


def done(user=MEMBER):
    return poll.TASK in (u_quests(user).child("daily/completed").get() or {})


def test_the_first_poll_goes_to_staff_at_once_and_waits(polls):
    run(polls.tick())
    first = plan(polls)
    assert first["first"] and first["day"] == poll.day() and first["review"] == REVIEW
    assert first["at"] - time.time() > poll.FIRST_WAIT - 5
    assert polls.review.send.await_count == 1 and len(polls.starts) == 1
    run(polls.tick())
    assert polls.review.send.await_count == 1 and not polls.public.send.called


def test_the_first_poll_needs_approval_and_its_wait(polls):
    run(polls.tick())
    researched(polls)
    polls.ref.child("next").child("at").set(time.time() - 1)
    run(polls.tick())
    assert not polls.public.send.called  # not approved
    press(polls, "approve")
    polls.ref.child("next").child("at").set(time.time() + 60)
    run(polls.tick())
    assert not polls.public.send.called  # too early
    polls.ref.child("next").child("at").set(time.time() - 1)
    run(polls.tick())
    sent = polls.public.send.call_args.kwargs
    assert sent["poll"].question == "Who is the best tank?"
    assert [answer.text for answer in sent["poll"].answers] == polls.found[1]
    assert str(poll.POLL_ROLE) in sent["content"]
    assert polls.live["poll"] and polls.live["message"] == POST


def test_research_fills_the_review(polls):
    run(polls.tick())
    assert "Researching" in poll.review_embed(plan(polls)).fields[0].value
    researched(polls)
    now = plan(polls)
    assert now["answers"] == polls.found[1] and now["note"] == "Wiki" and now["tried"]
    assert polls.review.get_partial_message.return_value.edit.await_count == 1


def test_research_that_fails_leaves_it_to_staff(polls):
    polls.found = topicmatch.Unavailable("down")
    run(polls.tick())
    researched(polls)
    now = plan(polls)
    assert now["tried"] and "answers" not in now
    assert "Edit" in poll.review_embed(now).fields[0].value
    refused = press(polls, "approve").response.send_message.call_args
    assert "no answers" in refused.args[0] and "approved" not in plan(polls)


def test_research_for_a_swapped_topic_is_dropped(polls):
    run(polls.tick())
    old = polls.starts[-1]
    press(polls, "swap")
    assert plan(polls)["text"] != old["text"] and len(polls.starts) == 2
    run(polls.answers(old))
    assert "answers" not in plan(polls)


def test_an_old_review_message_loses_its_buttons(polls):
    run(polls.tick())
    gone = press(polls, "approve", message=999).response.edit_message.call_args
    assert gone.kwargs == {"view": None}


def test_edit_changes_question_and_answers(polls):
    run(polls.tick())
    interaction = polls.cafe.interaction(STAFF)
    interaction.message.id = REVIEW

    async def go(lines):
        modal = poll.EditModal(plan(polls))
        modal.text._value, modal.answers._value = "Which tank is best?", lines
        await modal.on_submit(interaction)

    run(go("Bull"))
    assert "answers" not in plan(polls)  # one answer is not a poll
    run(go("Bull\nbull\n\nFrank\n" + "x" * 90))
    assert plan(polls)["text"] == "Which tank is best?"
    assert plan(polls)["answers"] == ["Bull", "Frank", "x" * poll.ANSWER]


def test_tomorrow_is_planned_after_today_posts(polls):
    posted(polls)
    run(polls.tick())
    tomorrow = plan(polls)
    assert tomorrow["day"] == poll.day(1) and "first" not in tomorrow
    assert tomorrow["at"] == poll.midnight(poll.day(1))
    run(polls.tick())
    assert polls.review.send.await_count == 2 and polls.public.send.await_count == 1


def test_a_new_day_posts_approved_answers_and_locks_the_old_thread(polls):
    posted(polls)
    run(polls.tick())
    researched(polls)
    press(polls, "approve")
    polls.live["day"] = "2000-01-01"
    polls.ref.child("next").update({"day": poll.day(), "at": time.time() - 1})
    run(polls.tick())
    assert polls.public.send.await_count == 2
    assert "poll" in polls.public.send.call_args.kwargs
    assert polls.public.edit.call_args.kwargs == {"locked": True, "archived": True}


def test_unapproved_answers_post_at_midnight_and_the_review_says_so(polls):
    posted(polls)
    run(polls.tick())
    researched(polls)
    polls.live["day"] = "2000-01-01"
    polls.ref.child("next").update({"day": poll.day(), "at": time.time() - 1})
    run(polls.tick())
    assert "poll" in polls.public.send.call_args.kwargs and polls.live["poll"]
    marked = polls.review.get_partial_message.return_value.edit.call_args.kwargs
    assert "Auto posted" in marked["embed"].description and marked["view"] is None


def test_an_unapproved_first_poll_posts_at_the_next_midnight(polls):
    run(polls.tick())
    researched(polls)
    polls.ref.child("next").update({"day": "2000-01-01", "at": 1})
    run(polls.tick())
    assert "poll" in polls.public.send.call_args.kwargs
    run(polls.tick())
    assert plan(polls)["day"] == poll.day(1)


def test_a_topic_without_answers_posts_as_an_open_question(polls):
    polls.found = topicmatch.Unavailable("down")
    posted_before = polls.public.send.await_count
    run(polls.tick())
    researched(polls)
    polls.ref.child("next").update({"day": "2000-01-01", "at": 1})
    run(polls.tick())
    sent = polls.public.send.call_args.kwargs
    assert polls.public.send.await_count == posted_before + 1
    assert "poll" not in sent and sent["embed"].title and polls.live["poll"] is False


def test_a_day_with_no_plan_still_posts_a_topic(polls):
    posted(polls)
    polls.live["day"] = "2000-01-01"
    polls.ref.child("next").delete()
    run(polls.tick())
    assert polls.public.send.await_count == 2 and polls.live["day"] == poll.day()


def test_topics_are_not_repeated_until_all_are_used(polls, monkeypatch):
    monkeypatch.setattr(poll, "ICEBREAKERS", ["one?", "two?"])
    polls.ref.child("used").push().set("one?")
    assert {poll.pick()[0] for _ in range(20)} == {"two?"}
    polls.ref.child("used").push().set("two?")
    assert poll.pick(avoid=["one?"])[0] == "two?"
    assert not polls.ref.child("used").get()


def test_vote_then_reply_finishes_the_task(polls):
    posted(polls)
    task(polls)
    vote(polls)
    assert not done()
    message(polls)
    assert done()


def test_reply_then_vote_finishes_the_task(polls):
    posted(polls)
    task(polls)
    message(polls)
    assert not done()
    vote(polls)
    assert done()


def test_only_effort_in_the_poll_thread_counts(polls):
    posted(polls)
    task(polls)
    vote(polls, message_id=5)
    vote(polls)
    message(polls, "lol")
    message(polls, channel=5)
    assert not done()


def test_an_open_question_needs_only_the_reply(polls):
    posted(polls)
    polls.live["poll"] = False
    task(polls)
    message(polls)
    assert done()


def test_the_task_is_paid_once_and_votes_survive_a_restart(polls):
    posted(polls)
    task(polls)
    vote(polls)
    again = poll.Polls(polls.cafe.bot)
    assert again.has("voted", MEMBER)
    polls.live = again.live
    message(polls)
    paid = u_quests(MEMBER).child("daily/quests").get()[poll.TASK]["current"]
    message(polls, "Another long answer about Bull")
    vote(polls)
    assert u_quests(MEMBER).child("daily/quests").get()[poll.TASK]["current"] == paid


def test_devin_answers_are_cleaned(polls):
    messages = [
        {"source": "user", "message": '{"id": "ab", "answers": ["x", "y"]}'},
        {
            "source": "devin",
            "message": 'ok {"id": "ab", "question": " Best  tank? ", '
            '"answers": ["Bull", "bull", 7, "", "Frank"], "checked": "wiki"}',
        },
    ]
    assert poll.written(messages, "ab") == ("Best tank?", ["Bull", "7", "Frank"], "wiki")
    assert poll.written(messages, "zz") is None
    assert poll.written([{"source": "devin", "message": '{"id": "ab"}'}], "ab") is None

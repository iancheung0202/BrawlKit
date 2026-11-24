# AGENTS.md

This is for AI agents working on BrawlKit, and for any person who wants the full picture before changing something. Please read it first. The [README](README.md) covers what the bot is, and [CONTRIBUTING.md](CONTRIBUTING.md) covers how a pull request gets merged.

I'm Ian. I own the bot and the server it runs in, so "I" and "me" below mean me.

## What you're working on

BrawlKit is a game that happens to live in a Discord bot. It has an economy, levels, stations, events and community tools, all for one server, Brawl Stars Cafe.

A lot of it was written by hand before AI tools existed, and some by AI tools when they were still rough. The job since then has been cleanup: making the code easy to maintain while keeping everything it does. Keep that in mind when a file looks bigger than you'd like. The complexity members can see is the product. The mess they can't see is what we're fixing.

## How I want you to work

1. Ask before anything goes live. Don't deploy, restart the bot, push to `main` or merge until I've approved that specific change. Build it, test it, show me, then ask.
2. Show me before you ship. If members will see it, render it and send me the picture first.
3. Clean up the server when you're done. Every patch, bundle, scratch script and picture you put there gets deleted once the deploy is finished.
4. Keep secrets secret. Never print, log, commit or paste a token, key or credentials file. They live in `.env` and in git-ignored files under `assets/`.
5. Use only BrawlKit's own keys. Other bots share the server, and their keys are not ours to borrow. If one of ours is missing or broken, stop and tell me.
6. Treat live data as real, because it is. Change the live database only when I ask, change only what I asked for, and read the value back afterwards to confirm it.
7. Check, don't guess. Look up command names, IDs and numbers in the code before you use them or tell me about them. When you report back, say what you verified and what you couldn't, like anything that needs a button pressed in Discord.

## Rules for the code

1. Don't cut features. Reorganize, rename internals, simplify how something is written, but don't remove what it does, rename a command or change a number unless that is the task I gave you.
2. Copy the pattern that's already there. Before you add something, find the closest existing thing and build yours the same way.
3. Give everything one home. Each system has its own file. Numbers go in `brawl/Currency/config.py`, channel, role and emote IDs in `brawl/Currency/helper.py`, and colors plus the yes and no emotes in `brawl/Utility/style.py`. Write a value once and import it. If the same logic is needed twice, move it somewhere both can reach.
4. Keep it small and plain. Short functions, plain names, and a one-line docstring saying what the function does or gives back. Leave out comments that describe your edit. Delete dead code, unused helpers and commented-out blocks; don't leave them for later.
5. Move money through the wallet. Beans and Tokens only change through `brawl/Currency/wallet.py`, always with a `reason`. That is how the ledger knows what each system paid, which keeps the weekly `/economy` report right.
6. Let systems talk through events. When one system has to react to another (an order was finished, a wallet changed), use `brawl/Currency/events.py`. A system that reaches into another one's internals is hard to change later.
7. Build an event as one file I can delete. A limited-time event gets a single file under `brawl/Currency/`, with its settings at the top and its own commands, cards and listeners, plus its own test file. When the event ends I delete those two files and nothing else should break. `goldenbean.py` is the one to copy.
8. Write tests with every change, and get the tests and pre-commit passing before you ask me to look.

## Rules for what members see

These cover cards, strips, embeds, buttons and any text the bot sends.

1. Show it. If a picture, an icon or a number can say something, don't spend a sentence on it.
2. Keep text off the cards. A card or strip carries names, numbers and icons. The explaining goes in the embed around it or on a `/how` page.
3. Stay in the cafe. Beans, Tokens, Stamps, stations, orders, brewing, the boss. A new feature gets a name that belongs with those.
4. Only mention commands that exist. Find the command in the code before you put it in front of a member.
5. Be consistent. The same thing gets the same label, layout and wording wherever it appears. If you reword one strip, go and check the others. I care about this more than about any single clever line.
6. Tell members what to do next. Every strip notification ends with `guide(page, label)` from `brawl/Currency/guide.py`. That adds an info button, which opens the matching `/how` page, and a grey disabled button naming the one command to run next, worded `Use /command to ...`. Drop the label only when there's no next command.
7. Don't join things with dot symbols. Use a comma, a slash, a new line or separate fields.
8. Write for a kid. A lot of our members are young. Use short words and short sentences, one idea per line.
9. Keep chat clean. If only one member needs the answer, make it ephemeral. If a notice repeats, follow how the existing ones avoid stacking up.
10. Use what Discord offers before reaching for a line of plain text: the custom emotes the bot already has, embed fields, buttons, Components V2 layouts.

## Running things

You don't need a bot token, a database or a server. The work happens against the test suite and by drawing cards.

```bash
pip install -r requirements.txt pytest pre-commit
pytest                      # whole suite
pytest tests/test_shop.py   # one file
pre-commit run --all-files  # black, isort, file checks
```

Use Python 3.10. That's what CI and production run.

### Tests

`tests/conftest.py` replaces Firebase with an in-memory tree and builds the cogs around a mocked bot. Reach for the `cafe` fixture whenever a test reads or writes data. One thing that trips people up: Discord views have to be created inside a running event loop (`asyncio.run`), otherwise they raise.

### Drawing a card

Every card comes from a plain function that takes a dict and returns the image, either as bytes or as a `BytesIO`. Call it with sample data, save the result and open it:

```python
from brawl.Currency.howcard import PAGES
open("beans.jpg", "wb").write(PAGES["beans"][1]())
```

Then actually look at it, in every state the card can be in: empty, full, locked, a very long name. One happy-path render isn't enough.

### Running the bot

You can't, outside production. The Firebase project and the server IDs are fixed in the code, and the ticket, welcome and booster features are loaded from another bot's shared folder that sits next to this repo on the server. Please don't try to work around that. Test with the suite and with renders, and I'll test live.

### How a deploy works

Production runs in Docker Compose, with the repo mounted into the container.

- For a code-only change, get the new code onto the server and run `docker compose restart`.
- If `requirements.txt` or the `Dockerfile` changed, run `docker compose up -d --build`.
- Slash commands sync when the bot starts. A new one can take a little while to show up in Discord.
- After a restart, read the log for errors and make sure the bot connected.
- Anything that has to survive a restart belongs in the database. Memory is wiped.

I've left the server address, login and paths out of this file on purpose, since the repo is public.

## Map of the code

`brawlkit.py` starts the bot, connects Firebase, loads every `.py` under `brawl/` as an extension and registers the views that have to keep working after a restart. Because every file gets loaded as an extension, each one ends with `async def setup(bot)`, even when it has nothing to set up.

Files ending in `card.py` only draw. They take data and return a picture, and they never read the database or talk to Discord. The file next to them holds the commands and the data, so `brewing.py` goes with `brewcard.py` and `shop.py` with `shopcard.py`.

### brawl/Currency: foundations

| File | Holds |
|---|---|
| `config.py` | Every number: rewards, prices, odds, limits, the level ladder, command mentions |
| `helper.py` | Channel, role and emote IDs, the built-in shop items, date helpers |
| `db.py` | One function per database path (`u_...` for a member, `g_...` for the server) |
| `wallet.py` | Read, change and spend Beans and Tokens |
| `events.py` | The small bus systems use to react to each other |
| `ledger.py` | Counts what every system pays, by week; `/economy` |
| `card.py` | The `Card` drawing class, fonts, icons, `render` |
| `panel.py` | Embed helpers: `notice`, `framed`, `panel` |
| `guide.py` | The info button and grey next-command label under strips |
| `ladder.py` | Which level unlocks which station, and the locked message |

### brawl/Currency: earning

| File | Holds |
|---|---|
| `currency.py` | The chat listener that ties earning together; `/thermometer`; the admin add command |
| `chat.py` | Chat Beans, the daily limit, the effortful-message filter |
| `levels.py` | XP, levels and level-up rewards (Postgres); `/xp` admin commands |
| `daily.py` | Clock In, the store panel, admin dash commands |
| `quests.py` | Today's Order: building it, tracking tasks, paying it |
| `stampcard.py` | Stamps, Mega Boxes on every fifth Stamp, `/redeem` |
| `rewardcard.py` | Cards for Clock In, Today's Order, the first shift, a redeemed pass |
| `tutorial.py` | The first-shift steps for new members |
| `heat.py`, `stationcard.py` | Thermometer levels, Token drops, and their cards |
| `boss.py` | Boss visit times, the inspection buttons and outcomes |
| `brewing.py`, `brewcard.py` | `/brew`, `/sell`, insurance, brew strips |

### brawl/Currency: spending and playing

| File | Holds |
|---|---|
| `shop.py`, `shopcard.py` | `/shop`, `/buy`, `/pin`, the purchase queue, server rewards |
| `bag.py`, `itemcard.py`, `effects.py` | Effect items: holding, starting with `/use`, timers and cooldowns |
| `gacha.py`, `dropcard.py` | `/stardrop`, `/megabox`, rolls and reward cards |
| `gambling.py`, `gamecard.py` | `/coinflip`, `/blackjack` |
| `tables.py`, `tablecard.py` | `/table` commands, the weekly quest, paying the top table |
| `invitetracker.py`, `invitecard.py` | Invite tracking, the welcome button, invitee progress |

### brawl/Currency: showing

| File | Holds |
|---|---|
| `balance.py`, `balancecard.py` | `/balance` and its four pages: Counter, Chat, Inventory, Community |
| `how.py`, `howcard.py` | `/how` and every explainer page |
| `pagination.py`, `boardcard.py` | `/leaderboard` |
| `staff.py` | Staff application panel |
| `goldenbean.py` | The Golden Bean event, complete in one file |

### Other folders

| File | Holds |
|---|---|
| `Utility/api.py` | Brawl Stars API calls and cached art |
| `Utility/profile.py`, `Utility/playercard.py` | `/profile` and its cards |
| `Utility/topic.py` | `/topic`, suggestions, staff review, cooldown |
| `Utility/topicmatch.py` | The similar-topics check, through one long-lived Devin session |
| `Utility/style.py` | Shared colors and the yes and no emotes |
| `Utility/emotes.py`, `Utility/effortful.py` | Emote list command; owner tool to test the effort filter |
| `TeamFinder/teamFind.py` | Team finder panel and requests |
| `TeamFinder/reputationSystem.py` | Rep, rep roles, Tokens for rep |
| `Milestone/milestone.py` | Account linking and milestone roles |
| `Partnership/partnershipSystem.py` | Partner servers, panels and threads |
| `scripts/` | One-off maintenance scripts, run by hand |

### Where data lives

Almost everything is in the Firebase Realtime Database. The paths are built in `brawl/Currency/db.py`, though a few systems (topics, team finder, the Golden Bean) name their own root at the top of their file. Keys made by `push()` carry the time they were created, and the topic review counts depend on that.

Levels are the exception. They sit in a Postgres `levels` table and are read through the `Leveling` cog.

Memory is for short-lived state only. If it has to survive a restart, save it.

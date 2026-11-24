# BrawlKit

BrawlKit is the Discord bot behind Brawl Stars Cafe. It turns the server into a small game: members earn currency by chatting, spend it on real Brawl Stars rewards and server perks, and unlock more of the cafe as they level up.

I'm Ian, and I wrote this README for people working on the code. If you're a member and just want to know how the cafe works, run `/how` in the server. It explains every system, numbers included, and does it better than this page.

Two other files are worth knowing about:

- [AGENTS.md](AGENTS.md) has the rules I want followed and a map of the code. It's written for AI agents, but it's the best place for a person to start too.
- [CONTRIBUTING.md](CONTRIBUTING.md) explains how to send me a change.

## Tech

- Python 3.10 and [discord.py](https://discordpy.readthedocs.io) 2.6 (slash commands, buttons, Components V2 layouts)
- Firebase Realtime Database for almost all data
- Postgres for levels and XP
- Pillow for every card and strip the bot posts as a picture
- The Brawl Stars API for player profiles and milestone roles
- Docker Compose in production
- pytest, black, isort and pre-commit, run by CI on every pull request

## Systems

Here is what each system does. I've left the numbers out because they change often; rewards, prices, odds and limits all live in `brawl/Currency/config.py`.

### Beans

Beans are the everyday currency. Members earn them by chatting with effortful messages, up to a daily limit that is higher for boosters. Clocking in each day pays Beans too, and a streak pays more.

### Tokens

Tokens are the rare one. They come from brewing, thermometer drops, streaks, reputation and winning tables, and they pay for the most valuable shop items and for passes.

### Today's Order and Stamps

Clocking in gives a member Today's Order: a short list of tasks drawn from the stations they have unlocked. Finishing the order earns a Stamp. Stamps fill a Stamp Card, pay Mega Boxes along the way, and are redeemed with `/redeem` for a Brawl Pass or Brawl Pass Plus, with a monthly limit for the whole server.

### Levels and stations

Chatting earns XP. Levels 1 to 10 each unlock one station (brewing, shop, Star Drops, Mega Boxes, boss, thermometer, tables, games, effect items, message pin), so a new member meets one system at a time. A first-shift tutorial walks them through the start.

### Brewing

`/brew` spends Beans on a roast that takes hours to finish, and `/sell` turns the finished brew into Tokens. Roasts differ in cost, time and payout odds, and insurance covers a bad batch.

### Thermometer and boss

Active chat heats a shared thermometer. Hotter chat pays extra Beans and drops Tokens. A few times a day the boss walks into chat, and members who press a button in time can get a Mega Box or Star Drop.

### Star Drops and Mega Boxes

`/stardrop` and `/megabox` open random rewards with rarities and upgrade rolls, drawn as cards.

### Shop and effect items

`/shop` lists built-in items and server rewards, each with a price button. Effect items are timed boosts for chat and brewing; they wait in the bag until started with `/use`.

### Games

`/coinflip` and `/blackjack` bet Beans, with daily limits.

### Tables

Members sit together at a table (`/table`), share a weekly Bean quest, and the top table of the week is paid.

### Invites

The bot tracks who invited whom, rewards inviters, and shows them how far each member they invited has got. Members who welcome a newcomer earn Beans.

### Topics

`/topic` posts a conversation starter. Members can suggest topics, staff approve or turn them down, and a similarity check lists existing topics with the same meaning before staff decide.

### Team finder and reputation

Members post requests for teammates from a panel. Hosts can thank teammates with rep, which earns roles and a few Tokens a day.

### Profiles and milestones

`/profile` draws a linked Brawl Stars account, its brawlers and recent battles. Milestone roles follow a linked account's trophies and ranks.

### Partnerships and staff tools

The bot also manages partner servers with their panels and request threads, runs staff applications, and gives admins an `/economy` report of what each system paid in a week.

### Events

Now and then we run a limited-time community event, like the Golden Bean. Each one lives in a single file, so when it's over I can delete that file and the event is gone.

## Layout

```
brawlkit.py          starts the bot and loads every file under brawl/ as an extension
brawl/Currency/      the cafe: economy, progression, stations, cards
brawl/Utility/       Brawl Stars API, profiles, topics, shared styles
brawl/TeamFinder/    team finder and reputation
brawl/Milestone/     milestone roles from linked accounts
brawl/Partnership/   partner servers
assets/              pictures and the font the cards are drawn with
tests/               pytest suite, run against an in-memory database
```

The file-by-file map is in [AGENTS.md](AGENTS.md#map-of-the-code).

## Working on it

You don't need a bot token, a database or a server to work on BrawlKit. You write the change, run the tests, and draw the cards to pictures to see how they look.

```bash
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest pre-commit
pre-commit install

pytest                      # the whole suite
pre-commit run --all-files  # formatting and file checks
```

To look at a card, call the function that draws it and save what comes back:

```bash
python -c "
from brawl.Currency.howcard import PAGES
open('beans.jpg', 'wb').write(PAGES['beans'][1]())
"
```

You can't run your own copy of the bot, sorry. It's tied to the cafe's database and server IDs, and it loads some shared code that isn't in this repository. I test changes live after I merge them.

## Configuration

Secrets come from a `.env` file that is never committed. `.env.example` lists the names the bot needs:

| Name | Used for |
|---|---|
| `BOT_TOKEN` | Discord bot login |
| `BRAWL_STARS_API_KEY` | Player profiles and milestones |
| `DATABASE_URL` | Postgres, for levels |
| `TOPICS_DEVIN_API_KEY`, `TOPICS_DEVIN_PROMPT` | Optional. The similar-topics check; without them it is left out |

## License

All rights reserved. The code is public so people can read it and send pull requests, but please don't run, copy or reuse it without asking me first. The details are in [LICENSE](LICENSE). The Brawl Stars art under `assets/` belongs to Supercell, and this project is unofficial and not endorsed by Supercell.

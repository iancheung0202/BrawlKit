# Contributing to BrawlKit

Thanks for wanting to help. I'm Ian, the creator and sole developer of BrawlKit. If you're a member of the cafe and want to contribute, you're more than welcome to. The process is short.

## How a change gets in

1. Fork the repo and make your change in your fork.
2. Add tests for it.
3. Run `pytest` and `pre-commit run --all-files`. Both have to pass, and CI will run them again on the pull request anyway.
4. Open a pull request against `main`. Tell me what changes for members and why. If you touched a card or a strip, attach a before and after picture.
5. I review it and merge it.
6. I deploy it and test it in the server. Only I have access to the server the bot runs on, so that part is always mine.

## Setting up

You don't need a bot token or a database. You work with the test suite and with pictures of the cards, and the commands for both are in the [README](README.md#working-on-it).

The tests swap the real database for one that lives in memory (`tests/conftest.py`), so you can't break anyone's Beans by running them.

There is no test bot to run. I know that's unusual. The bot is wired to the cafe's own database and server, so I do the live testing after a merge.

## What I look for in a pull request

A lot of this codebase was written by hand before AI tools existed, and some of it by AI tools when they were still rough. It has taken a long cleanup to make it maintainable. These are the things that keep it from sliding back.

### Don't cut anything

BrawlKit has a lot of systems on purpose. It's a game. If something looks overcomplicated, tidy how it's written, but leave what it does alone. That means no removed features, no renamed commands and no changed numbers, unless that is the whole point of your pull request.

### Keep the code small and plain

- Write short functions, each with a one-line docstring saying what it does or gives back.
- Skip comments like "moved this" or "new version". Git already knows. Comment the things the code can't say for itself.
- Delete what you stop using. No dead code, no leftover helpers, no commented-out blocks.

### Give everything one home

Each system has its own file, and the map in [AGENTS.md](AGENTS.md#map-of-the-code) shows which is which. Look there before you add a new file.

Shared values are written once and imported:

- numbers (rewards, prices, odds, limits) in `brawl/Currency/config.py`
- channel, role and emote IDs in `brawl/Currency/helper.py`
- colors in `brawl/Utility/style.py`

If you catch yourself pasting the same logic into a second place, move it somewhere both can import it from.

### Test it

Every change comes with tests in `tests/`. For a bug fix, write the test that fails without your fix.

### Show me the picture

Cards are the part members actually see, and a diff can't tell me whether one looks right. So any change to a card or strip needs a before and after picture in the pull request.

### Write for the members

A lot of our members are young, so anything the bot says should be easy for a kid to follow.

- Only mention commands that exist. Look them up in the code. A message that tells a member to run a command we don't have is worse than no message.
- Call the same thing by the same name everywhere.
- Cafe terms are always spelled the same way: Beans, Tokens, Stamps, Stamp Card, Today's Order, Clock In, Star Drop, Mega Box, Brew Station, Thermometer.
- Keep the text on a card short. The card shows it, and the embed around the card can explain it.

The full list of design rules is in [AGENTS.md](AGENTS.md#rules-for-what-members-see).

## Secrets

Never commit a token, a key or a credentials file, and never paste one into a pull request, an issue or a chat. `.env` and the credential files under `assets/` are ignored by git for this reason. If you think one got out, tell me straight away so I can replace it.

## License

BrawlKit is not open source; see [LICENSE](LICENSE). By opening a pull request you agree that your contribution becomes part of the project under that notice.

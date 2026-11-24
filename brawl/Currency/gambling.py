import random
import time

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View

from brawl.Currency import wallet
from brawl.Currency.card import BACKGROUND, render
from brawl.Currency.db import u_gambling_limits
from brawl.Currency.gamecard import DECK, draw_blackjack, draw_coinflip, total
from brawl.Currency.helper import (
    BEAN_EMOTE,
    DAILY_GAMBLING_LIMITS,
    MAIN_GUILD_ID,
    NO_EMOTE,
    ULTRA_TIER_ROLE_ID,
    get_current_date_key,
)
from brawl.Currency.ladder import locked
from brawl.Currency.panel import notice

MIN_BET, MAX_BET, ULTRA_MAX_BET = 100, 1000, 2000
TURN_SECONDS = 30
NAMES = {"blackjack": "blackjack", "coinflip": "coin flip"}
RULES = (
    "## How blackjack works\n"
    "Get closer to 21 than the dealer without going over.\n"
    "### Cards\n"
    "- 2 to 10 are worth their number. J, Q and K are worth 10.\n"
    "- An Ace is worth 11, or 1 if 11 would put you over 21.\n"
    "### Your turn\n"
    "- **Hit** takes another card. Over 21 is a bust and you lose.\n"
    "- **Stand** keeps your hand. The dealer then draws until they have 17 or more.\n"
    "- **Double Down** doubles your bet, takes one card, then stands.\n"
    "- **Surrender** ends the game and returns half your bet.\n"
    "### Payouts\n"
    "- A win pays your bet. A tie returns it.\n"
    "- 21 on your first two cards pays one and a half times your bet.\n"
    f"You have {TURN_SECONDS} seconds for each choice."
)
WARNING = (
    "Games are for fun, not a way to earn. The odds favor the house, "
    "so over time you lose more than you win.\n\n"
    "You can play {limit} games of {game} a day.\n"
    "If gambling is a problem for you or someone you know, please seek help."
)


def beans_of(amount):
    return f"{amount:,} Beans"


class Game(View):
    """What both games share: one player, one bet, one card that redraws."""

    name = ""

    def __init__(self, cog, user_id, bet):
        super().__init__(timeout=TURN_SECONDS)
        self.cog, self.user_id, self.bet = cog, user_id, bet
        self.over, self.message = False, None

    async def interaction_check(self, interaction):
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            embed=notice(f"{NO_EMOTE} This is not your game.", "bad"), ephemeral=True
        )
        return False

    def state(self, tone, headline, line):
        return {
            "background": BACKGROUND,
            "bet": self.bet,
            "beans": wallet.balance(self.user_id)[0],
            "tone": tone,
            "headline": headline,
            "line": line,
        }

    async def file(self, tone, headline, line):
        return await render(self.draw, self.state(tone, headline, line), name=self.name)

    async def finish(self, interaction, tone, headline, line, payout=0):
        """Pays out, shows the result and offers another round at the same bet."""
        self.over = True
        self.stop()
        if payout:
            await wallet.change(self.user_id, beans=payout, reason="games")
        view = PlayAgain(self.cog, self.user_id, self.name, self.bet)
        await interaction.response.edit_message(
            attachments=[await self.file(tone, headline, line)], view=view
        )
        view.message = await interaction.original_response()

    async def warn(self, interaction):
        limit = DAILY_GAMBLING_LIMITS[self.name]
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Play responsibly",
                description=WARNING.format(limit=limit, game=NAMES[self.name]),
                color=0x2B2D31,
            ),
            ephemeral=True,
        )

    async def on_timeout(self):
        if self.over or not self.message:
            return
        self.over = True
        file = await self.file(
            "bad", "Time ran out", f"You did not choose and lost {beans_of(self.bet)}."
        )
        try:
            await self.message.edit(attachments=[file], view=None)
        except discord.HTTPException:
            pass


class PlayAgain(View):
    def __init__(self, cog, user_id, name, bet):
        super().__init__(timeout=60)
        self.cog, self.user_id, self.name, self.bet = cog, user_id, name, bet
        self.message = None

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.grey, emoji="🔁")
    async def again(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                embed=notice(f"{NO_EMOTE} This is not your game.", "bad"),
                ephemeral=True,
            )
        self.stop()
        await getattr(self.cog, self.name).callback(self.cog, interaction, self.bet)
        await self.message.edit(view=None)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class Blackjack(Game):
    name = "blackjack"
    draw = staticmethod(draw_blackjack)

    def __init__(self, cog, user_id, bet):
        super().__init__(cog, user_id, bet)
        cards = random.sample(DECK, 4)
        self.dealer, self.player = cards[:2], cards[2:]

    def state(self, tone, headline, line):
        hands = {"dealer": self.dealer, "player": self.player}
        return {**super().state(tone, headline, line), **hands}

    def deal(self, hand):
        hand.append(
            random.choice([c for c in DECK if c not in self.dealer + self.player])
        )

    def opening(self):
        """A 21 on the first two cards ends the game before the player chooses."""
        player, dealer = total(self.player) == 21, total(self.dealer) == 21
        if player and dealer:
            return "even", "Tie", "You both have 21. Your bet is returned.", self.bet
        if player:
            won = int(self.bet * 1.5)
            line = f"21 on your first two cards. You won {beans_of(won)}."
            return "good", "Blackjack!", line, self.bet + won
        if dealer:
            line = f"The dealer has 21. You lost {beans_of(self.bet)}."
            return "bad", "You lose", line, 0

    def settle(self):
        """The dealer draws to 17, then the higher hand wins."""
        while total(self.dealer) < 17:
            self.deal(self.dealer)
        dealer, player = total(self.dealer), total(self.player)
        won, lost = beans_of(self.bet), f"You lost {beans_of(self.bet)}."
        if dealer > 21:
            line = f"The dealer went over 21. You won {won}."
            return "good", "You win", line, self.bet * 2
        if player > dealer:
            line = f"Your {player} beats the dealer's {dealer}. You won {won}."
            return "good", "You win", line, self.bet * 2
        if dealer > player:
            line = f"The dealer's {dealer} beats your {player}. {lost}"
            return "bad", "You lose", line, 0
        return "even", "Tie", f"You both have {player}. Your bet is returned.", self.bet

    async def bust(self, interaction):
        line = f"You went over 21 and lost {beans_of(self.bet)}."
        await self.finish(interaction, "bad", "Bust", line)

    @discord.ui.button(
        label="Hit", style=discord.ButtonStyle.primary, emoji="🎯", row=0
    )
    async def hit(self, interaction: discord.Interaction, button):
        self.deal(self.player)
        if total(self.player) > 21:
            return await self.bust(interaction)
        if total(self.player) == 21:
            return await self.finish(interaction, *self.settle())
        file = await self.file(
            "play", "Hit or stand?", f"You have {TURN_SECONDS} seconds to choose."
        )
        await interaction.response.edit_message(attachments=[file], view=self)

    @discord.ui.button(
        label="Stand", style=discord.ButtonStyle.green, emoji="✋", row=0
    )
    async def stand(self, interaction: discord.Interaction, button):
        await self.finish(interaction, *self.settle())

    @discord.ui.button(
        label="Double Down", style=discord.ButtonStyle.red, emoji="💵", row=0
    )
    async def double_down(self, interaction: discord.Interaction, button):
        if not await wallet.pay(self.user_id, beans=self.bet, reason="games"):
            return await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} Doubling down costs {BEAN_EMOTE} `{self.bet:,}` more, "
                    "and you do not have that.",
                    "bad",
                ),
                ephemeral=True,
            )
        self.bet *= 2
        self.deal(self.player)
        if total(self.player) > 21:
            return await self.bust(interaction)
        await self.finish(interaction, *self.settle())

    @discord.ui.button(
        label="Surrender", style=discord.ButtonStyle.grey, emoji="🏳️", row=1
    )
    async def surrender(self, interaction: discord.Interaction, button):
        back = self.bet // 2
        line = f"You gave up and got {beans_of(back)} back, half your bet."
        await self.finish(interaction, "even", "Surrendered", line, back)

    @discord.ui.button(
        emoji="<:info:1037445870469267638>", style=discord.ButtonStyle.grey, row=1
    )
    async def rules(self, interaction: discord.Interaction, button):
        await interaction.response.send_message(
            embed=discord.Embed(description=RULES, color=0x2B2D31), ephemeral=True
        )

    @discord.ui.button(
        emoji="<a:warning:1391215594430402742>", style=discord.ButtonStyle.grey, row=1
    )
    async def warning(self, interaction: discord.Interaction, button):
        await self.warn(interaction)


class Coinflip(Game):
    name = "coinflip"
    draw = staticmethod(draw_coinflip)
    side = "?"

    def state(self, tone, headline, line):
        return {**super().state(tone, headline, line), "side": self.side}

    async def flip(self, interaction, call):
        self.side = random.choice(["heads", "tails"])
        won = call == self.side
        headline = f"{self.side.title()}. You {'win' if won else 'lose'}"
        line = f"You called {call} and {'won' if won else 'lost'} {beans_of(self.bet)}."
        await self.finish(
            interaction, "good" if won else "bad", headline, line, self.bet * 2 * won
        )

    @discord.ui.button(label="Heads", style=discord.ButtonStyle.blurple, emoji="🪙")
    async def heads(self, interaction: discord.Interaction, button):
        await self.flip(interaction, "heads")

    @discord.ui.button(label="Tails", style=discord.ButtonStyle.blurple, emoji="🪙")
    async def tails(self, interaction: discord.Interaction, button):
        await self.flip(interaction, "tails")

    @discord.ui.button(
        emoji="<a:warning:1391215594430402742>", style=discord.ButtonStyle.grey
    )
    async def warning(self, interaction: discord.Interaction, button):
        await self.warn(interaction)


class Gambling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def is_ultra(self, member):
        return any(role.id == ULTRA_TIER_ROLE_ID for role in member.roles)

    async def place(self, interaction, game, bet):
        """Runs every check a bet has to pass, then takes it. True when the game can start."""
        if interaction.guild.id != MAIN_GUILD_ID:
            line = f"{NO_EMOTE} You do not have permission to use this command."
            await interaction.followup.send(embed=notice(line, "bad"), ephemeral=True)
            return False
        if await locked(interaction, "games"):
            return False
        user_id, ultra = interaction.user.id, self.is_ultra(interaction.user)
        plays = u_gambling_limits(user_id, get_current_date_key())
        played = (plays.get() or {}).get(game, 0)
        limit = DAILY_GAMBLING_LIMITS[game] * (2 if ultra else 1)
        highest = ULTRA_MAX_BET if ultra else MAX_BET
        beans = wallet.balance(user_id)[0]
        if played >= limit:
            resets = int(time.time() // 86400 * 86400 + 86400)
            line = (
                f"You have played all `{limit}` games of {NAMES[game]} for today. "
                f"You can play again <t:{resets}:R>."
            )
        elif bet < MIN_BET:
            line = f"The lowest bet is {BEAN_EMOTE} `{MIN_BET:,}`."
        elif bet > highest:
            line = f"The highest bet is {BEAN_EMOTE} `{highest:,}`."
        elif beans < bet:
            line = (
                f"You don't have enough Beans. "
                f"You have {BEAN_EMOTE} `{beans:,}` and the bet is `{bet:,}`."
            )
        else:
            await wallet.pay(user_id, beans=bet, reason="games")
            plays.update({game: played + 1})
            return True
        await interaction.followup.send(
            embed=notice(f"{NO_EMOTE} {line}", "bad"), ephemeral=True
        )
        return False

    @app_commands.command(
        name="blackjack", description="Bet Beans on a hand of blackjack"
    )
    @app_commands.describe(bet="Beans to bet, from 100 to 1,000")
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        await interaction.response.defer(thinking=True)
        if not await self.place(interaction, "blackjack", bet):
            return
        game = Blackjack(self, interaction.user.id, bet)
        result = game.opening()
        if result:
            *words, payout = result
            if payout:
                await wallet.change(game.user_id, beans=payout, reason="games")
            game.over = True
            view = PlayAgain(self, game.user_id, "blackjack", bet)
            view.message = await interaction.followup.send(
                file=await game.file(*words), view=view, wait=True
            )
            return
        file = await game.file(
            "play", "Hit or stand?", f"You have {TURN_SECONDS} seconds to choose."
        )
        game.message = await interaction.followup.send(file=file, view=game, wait=True)

    @app_commands.command(name="coinflip", description="Bet Beans on a coin flip")
    @app_commands.describe(bet="Beans to bet, from 100 to 1,000")
    @app_commands.checks.cooldown(rate=1, per=5.0)
    async def coinflip(self, interaction: discord.Interaction, bet: int):
        await interaction.response.defer(thinking=True)
        if not await self.place(interaction, "coinflip", bet):
            return
        game = Coinflip(self, interaction.user.id, bet)
        file = await game.file(
            "play",
            "Heads or tails?",
            f"Call it right to win {beans_of(bet)}. You have {TURN_SECONDS} seconds.",
        )
        game.message = await interaction.followup.send(file=file, view=game, wait=True)

    @blackjack.error
    @coinflip.error
    async def on_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                embed=notice(
                    f"{NO_EMOTE} Wait `{error.retry_after:.0f}` seconds before the next game.",
                    "bad",
                ),
                ephemeral=True,
            )


async def setup(bot):
    await bot.add_cog(Gambling(bot))

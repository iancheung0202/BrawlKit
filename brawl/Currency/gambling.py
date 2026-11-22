import random
import time

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View

from brawl.Currency.db import (
    u_gambling_limits,
)
from brawl.Currency.helper import (
    BEAN_EMOTE,
    DAILY_GAMBLING_LIMITS,
    MAIN_GUILD_ID,
    NO_EMOTE,
    ULTRA_TIER_ROLE_ID,
    get_current_date_key,
)


class PlayAgainView(View):
    def __init__(self, cog, user_id, command_name: str, bet_amount: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.command_name = command_name
        self.bet_amount = bet_amount

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.grey, emoji="🔁")
    async def play_again_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your game!", ephemeral=True
            )

        cmd_attr = getattr(self.cog, self.command_name, None)
        if cmd_attr is None:
            return await interaction.response.send_message(
                "Unable to start the game. Contact the bot developer.", ephemeral=True
            )

        try:
            if isinstance(cmd_attr, app_commands.Command):
                func = cmd_attr.callback
                bound = func.__get__(self.cog, type(self.cog))
                await bound(interaction, self.bet_amount)
                self.clear_items()
                await self.message.edit(view=self)
                return
        except Exception:
            pass

        if callable(cmd_attr):
            await cmd_attr(interaction, self.bet_amount)
            self.clear_items()
            await self.message.edit(view=self)
            return

        cls_attr = getattr(type(self.cog), self.command_name, None)
        if callable(cls_attr):
            bound = cls_attr.__get__(self.cog, type(self.cog))
            await bound(interaction, self.bet_amount)
            self.clear_items()
            await self.message.edit(view=self)
            return

        return await interaction.response.send_message(
            "Unable to start the game. Unknown error.", ephemeral=True
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)


class BlackjackView(View):
    def __init__(self, cog, user_id, bet_amount, dealer_cards, player_cards):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.dealer_cards = dealer_cards
        self.player_cards = player_cards
        self.game_over = False
        self.message = None

    def calculate_hand_value(self, cards):
        value = 0
        aces = 0
        for card in cards:
            if card[0] in ["J", "Q", "K"]:
                value += 10
            elif card[0] == "A":
                aces += 1
                value += 11
            else:
                value += int(card[0]) if card[0] != "10" else 10

        while value > 21 and aces:
            value -= 10
            aces -= 1

        return value

    def format_cards(self, cards, hide_first=False):
        card_emojis = {"♠": "♠️", "♥": "♥️", "♦": "♦️", "♣": "♣️"}
        formatted = []
        for i, (rank, suit) in enumerate(cards):
            if hide_first and i == 0:
                formatted.append("`??`")
            else:
                formatted.append(f"`{rank}{card_emojis[suit]}`")
        return " ".join(formatted)

    def create_embed(self, title, description, color):
        embed = discord.Embed(title=title, description=description, color=color)

        dealer_value = self.calculate_hand_value(self.dealer_cards)
        player_value = self.calculate_hand_value(self.player_cards)

        if self.game_over:
            embed.add_field(
                name="🎩 Dealer",
                value=f"{self.format_cards(self.dealer_cards)} (Value: {dealer_value})",
                inline=False,
            )
        else:
            embed.add_field(
                name="🎩 Dealer",
                value=f"{self.format_cards(self.dealer_cards, hide_first=True)} (Value: ?)",
                inline=False,
            )

        embed.add_field(
            name="🎲 Your Hand",
            value=f"{self.format_cards(self.player_cards)} (Value: {player_value})",
            inline=False,
        )
        embed.add_field(
            name="💰 Bet", value=f"{BEAN_EMOTE} {self.bet_amount:,}", inline=False
        )
        return embed

    @discord.ui.button(
        label="Hit", style=discord.ButtonStyle.primary, emoji="🎯", row=0
    )
    async def hit_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your game!", ephemeral=True
            )

        deck = [
            (rank, suit)
            for rank in [
                "A",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "10",
                "J",
                "Q",
                "K",
            ]
            for suit in ["♠", "♥", "♦", "♣"]
        ]
        used_cards = self.dealer_cards + self.player_cards
        available_cards = [card for card in deck if card not in used_cards]
        new_card = random.choice(available_cards)
        self.player_cards.append(new_card)

        player_value = self.calculate_hand_value(self.player_cards)

        if player_value > 21:
            self.game_over = True
            embed = self.create_embed(
                "💥 Bust!",
                f"You went over 21! You lose {BEAN_EMOTE} {self.bet_amount:,}",
                discord.Color.red(),
            )
            self.clear_items()
            view = PlayAgainView(self.cog, self.user_id, "blackjack", self.bet_amount)
            await interaction.response.edit_message(embed=embed, view=view)
            view.message = await interaction.original_response()
        elif player_value == 21:
            await self._stand_logic(interaction)
        else:
            embed = self.create_embed(
                "🎲 Blackjack", f"Your turn! Hit or Stand?", discord.Color.blue()
            )
            embed.set_footer(text="You have 30 seconds to make your choice.")
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="Stand", style=discord.ButtonStyle.green, emoji="✋", row=0
    )
    async def stand_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your game!", ephemeral=True
            )

        await self._stand_logic(interaction)

    async def _stand_logic(self, interaction):
        self.game_over = True

        deck = [
            (rank, suit)
            for rank in [
                "A",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "10",
                "J",
                "Q",
                "K",
            ]
            for suit in ["♠", "♥", "♦", "♣"]
        ]
        used_cards = self.dealer_cards + self.player_cards

        while self.calculate_hand_value(self.dealer_cards) < 17:
            available_cards = [card for card in deck if card not in used_cards]
            new_card = random.choice(available_cards)
            self.dealer_cards.append(new_card)
            used_cards.append(new_card)

        dealer_value = self.calculate_hand_value(self.dealer_cards)
        player_value = self.calculate_hand_value(self.player_cards)

        if dealer_value > 21:
            winnings = self.bet_amount * 2
            title = "🎉 You Win!"
            description = f"Dealer busted! You win {BEAN_EMOTE} {self.bet_amount:,}"
            color = discord.Color.green()
            beans, tokens = await self.cog.economy.get_balance(self.user_id)
            await self.cog.economy.update_balance(self.user_id, beans + winnings)
        elif player_value > dealer_value:
            winnings = self.bet_amount * 2
            title = "🎉 You Win!"
            description = (
                f"You beat the dealer! You win {BEAN_EMOTE} {self.bet_amount:,}"
            )
            color = discord.Color.green()
            beans, tokens = await self.cog.economy.get_balance(self.user_id)
            await self.cog.economy.update_balance(self.user_id, beans + winnings)
        elif dealer_value > player_value:
            title = "💔 You Lose!"
            description = f"Dealer wins! You lose {BEAN_EMOTE} {self.bet_amount:,}"
            color = discord.Color.red()
        else:
            title = "🤝 Push!"
            description = (
                f"It's a tie! Your {BEAN_EMOTE} {self.bet_amount:,} bet is returned"
            )
            color = discord.Color.yellow()
            beans, tokens = await self.cog.economy.get_balance(self.user_id)
            await self.cog.economy.update_balance(self.user_id, beans + self.bet_amount)

        embed = self.create_embed(title, description, color)
        self.clear_items()
        view = PlayAgainView(self.cog, self.user_id, "blackjack", self.bet_amount)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(
        label="Double Down", style=discord.ButtonStyle.red, emoji="💵", row=0
    )
    async def double_down_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your game!", ephemeral=True
            )

        beans, tokens = await self.cog.economy.get_balance(self.user_id)
        if beans < self.bet_amount:
            return await interaction.response.send_message(
                f"{NO_EMOTE} You don't have enough {BEAN_EMOTE} to double down!",
                ephemeral=True,
            )

        self.bet_amount *= 2
        await self.cog.economy.update_balance(
            self.user_id, beans - (self.bet_amount // 2)
        )

        deck = [
            (rank, suit)
            for rank in [
                "A",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "10",
                "J",
                "Q",
                "K",
            ]
            for suit in ["♠", "♥", "♦", "♣"]
        ]
        used_cards = self.dealer_cards + self.player_cards
        available_cards = [card for card in deck if card not in used_cards]
        new_card = random.choice(available_cards)
        self.player_cards.append(new_card)

        player_value = self.calculate_hand_value(self.player_cards)

        if player_value > 21:
            self.game_over = True
            embed = self.create_embed(
                "💥 Bust!",
                f"You went over 21! You lose {BEAN_EMOTE} {self.bet_amount:,}",
                discord.Color.red(),
            )
            self.clear_items()
            view = PlayAgainView(self.cog, self.user_id, "blackjack", self.bet_amount)
            await interaction.response.edit_message(embed=embed, view=view)
            view.message = await interaction.original_response()
        else:
            await self._stand_logic(interaction)

    @discord.ui.button(
        label="Surrender", style=discord.ButtonStyle.grey, emoji="🏳️", row=1
    )
    async def surrender_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your game!", ephemeral=True
            )

        self.game_over = True
        refund = self.bet_amount // 2
        embed = self.create_embed(
            "🏳️ Surrendered",
            f"You surrendered! You get back {BEAN_EMOTE} {refund:,} (half of your bet)",
            discord.Color.orange(),
        )
        self.clear_items()
        beans, tokens = await self.cog.economy.get_balance(self.user_id)
        await self.cog.economy.update_balance(self.user_id, beans + refund)
        view = PlayAgainView(self.cog, self.user_id, "blackjack", self.bet_amount)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(
        emoji="<:info:1037445870469267638>", style=discord.ButtonStyle.grey, row=1
    )
    async def blackjack_info_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your game!", ephemeral=True
            )

        embed = discord.Embed(
            description=(
                "## How to Play Blackjack\n"
                "-# Blackjack is a classic card game where the goal is to have a hand value as close to 21 as possible without going over. Here are the basic rules:\n"
                "### **Card Values:**\n"
                "-# - Number cards (2-10) are worth their face value.\n"
                "-# - Face cards (J, Q, K) are worth 10.\n"
                "-# - Aces can be worth 1 or 11, depending on what benefits your hand more.\n"
                "### **Gameplay:**\n"
                "-# 1. You and the dealer are each dealt two cards. Your cards are both face up, while the dealer has one card face up and one face down.\n"
                "-# 2. You can choose to `'Hit'` to draw another card or `'Stand'` to keep your current hand.\n"
                "-# 3. If your hand exceeds 21, you bust and lose the game.\n"
                "-# 4. Once you stand, the dealer reveals their hidden card and must hit until their hand is at least 17.\n"
                "-# 5. The winner is determined by who has the higher hand value without busting. If both hands are equal, it's a push (tie).\n"
                "### **Special Options:**\n"
                "-# - **Double Down:** You can double your initial bet and receive only one more card before standing.\n"
                "-# - **Surrender:** You can forfeit half your bet and end the game immediately.\n"
                "### **Payouts:**\n"
                "-# If you win, you receive a payout of 1:1 on your bet. However, if you hit blackjack with an Ace and a 10-value card, the payout is 3:2.\n"
            ),
            color=0x2B2D31,
        ).set_footer(
            text='Type "-blackjack" to send this to your DMs! Your 30-second countdown timer is ticking! ⚠️'
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        emoji="<a:warning:1391215594430402742>", style=discord.ButtonStyle.grey, row=1
    )
    async def gambling_warning_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your game!", ephemeral=True
            )

        embed = discord.Embed(
            title="Our Stance on Gambling",
            description=(
                "It is important to remember that gambling is not a way to make money, real or fake. It is a form of entertainment and should be treated as such. If you or someone you know is struggling with gambling addiction, please seek help.\n\n"
                "Additionally, please remember that the odds are always slightly in favor of the house. The house always wins in the long run.\n\n"
                f"We've implemented daily limits (**{DAILY_GAMBLING_LIMITS['blackjack']}** blackjack games per day) to promote responsible gambling. Use `/balance` to check your usage.\n\n"
                "-# Please gamble responsibly.\n"
            ),
            color=0x2B2D31,
        ).set_thumbnail(
            url="https://images.emojiterra.com/twitter/v13.1/512px/26a0.png"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        if not self.game_over and self.message:
            self.game_over = True
            embed = discord.Embed(
                title="⏰ Game Timeout!",
                description=f"You took too long to make a decision! You lose your bet of {BEAN_EMOTE} {self.bet_amount:,}",
                color=discord.Color.red(),
            )
            embed.add_field(
                name="🎩 Dealer",
                value=f"{self.format_cards(self.dealer_cards)} (Value: {self.calculate_hand_value(self.dealer_cards)})",
                inline=False,
            )
            embed.add_field(
                name="🎲 Your Hand",
                value=f"{self.format_cards(self.player_cards)} (Value: {self.calculate_hand_value(self.player_cards)})",
                inline=False,
            )
            self.clear_items()
            try:
                await self.message.edit(embed=embed, view=self)
            except:
                pass


class CoinflipView(View):
    def __init__(self, cog, user_id, bet_amount):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.game_over = False
        self.message = None

    @discord.ui.button(
        label="Heads", style=discord.ButtonStyle.blurple, emoji="🪙", row=0
    )
    async def heads_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your coinflip!", ephemeral=True
            )

        await self._flip_coin(interaction, "heads")

    @discord.ui.button(
        label="Tails", style=discord.ButtonStyle.blurple, emoji="🪙", row=0
    )
    async def tails_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your coinflip!", ephemeral=True
            )

        await self._flip_coin(interaction, "tails")

    @discord.ui.button(
        emoji="<a:warning:1391215594430402742>", style=discord.ButtonStyle.grey, row=0
    )
    async def gambling_warning_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(
                "This isn't your coinflip!", ephemeral=True
            )

        embed = discord.Embed(
            title="Our Stance on Gambling",
            description=(
                "It is important to remember that gambling is not a way to make money, real or fake. It is a form of entertainment and should be treated as such. If you or someone you know is struggling with gambling addiction, please seek help.\n\n"
                f"We've implemented daily limits (**{DAILY_GAMBLING_LIMITS['coinflip']}** coinflips per day) to promote responsible gambling. Use `/balance` to check your usage.\n\n"
                "-# Even though this game is truly a 50/50 chance, please gamble responsibly.\n"
            ),
            color=0x2B2D31,
        ).set_thumbnail(
            url="https://images.emojiterra.com/twitter/v13.1/512px/26a0.png"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _flip_coin(self, interaction, choice):
        self.game_over = True
        result = random.choice(["heads", "tails"])

        embed = discord.Embed(title="🪙 Coin Flip Result", color=discord.Color.blue())
        embed.add_field(name="Your Choice", value=choice.capitalize(), inline=True)
        embed.add_field(name="Result", value=result.capitalize(), inline=True)
        embed.add_field(
            name="Bet Amount", value=f"{BEAN_EMOTE} {self.bet_amount:,}", inline=True
        )

        if choice == result:
            winnings = self.bet_amount * 2
            embed.description = (
                f"🎉 **You Win!** You earn {BEAN_EMOTE} {self.bet_amount:,}"
            )
            embed.color = discord.Color.green()
            beans, tokens = await self.cog.economy.get_balance(self.user_id)
            await self.cog.economy.update_balance(self.user_id, beans + winnings)
        else:
            embed.description = (
                f"💔 **You Lose!** You lose {BEAN_EMOTE} {self.bet_amount:,}"
            )
            embed.color = discord.Color.red()

        self.clear_items()
        view = PlayAgainView(self.cog, self.user_id, "coinflip", self.bet_amount)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def on_timeout(self):
        if not self.game_over and self.message:
            embed = discord.Embed(
                title="⏰ Coinflip Timeout!",
                description=f"You took too long to choose! You lose your bet of {BEAN_EMOTE} {self.bet_amount:,}",
                color=discord.Color.red(),
            )
            embed.add_field(
                name="Bet Amount",
                value=f"{BEAN_EMOTE} {self.bet_amount:,}",
                inline=True,
            )
            embed.add_field(
                name="Result", value="Game canceled due to timeout", inline=True
            )
            self.clear_items()
            try:
                await self.message.edit(embed=embed, view=self)
            except:
                pass


class Gambling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def economy(self):
        return self.bot.get_cog("CurrencySystem")

    async def check_gambling_limit(self, user_id: int, game_type: str):
        """Check if user has reached their daily gambling limit for a specific game."""
        if game_type not in DAILY_GAMBLING_LIMITS:
            return True, 0

        date_key = get_current_date_key()
        ref = u_gambling_limits(user_id, date_key)
        data = ref.get() or {}
        current_usage = data.get(game_type, 0)
        limit = DAILY_GAMBLING_LIMITS[game_type]

        guild = self.bot.get_guild(MAIN_GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            ultra_role = guild.get_role(ULTRA_TIER_ROLE_ID)
            if member and ultra_role and ultra_role in member.roles:
                limit *= 2

        return current_usage < limit, current_usage

    async def increment_gambling_usage(self, user_id: int, game_type: str):
        """Increment the user's daily gambling usage for a specific game."""
        if game_type not in DAILY_GAMBLING_LIMITS:
            return

        date_key = get_current_date_key()
        ref = u_gambling_limits(user_id, date_key)
        data = ref.get() or {}
        current_usage = data.get(game_type, 0)
        data[game_type] = current_usage + 1
        ref.set(data)

    @app_commands.command(
        name="blackjack", description="Play blackjack with your Starr Beans"
    )
    @app_commands.describe(bet="Amount of Starr Beans to bet (min 100, max 1000)")
    @app_commands.checks.cooldown(rate=1, per=10.0)
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        await interaction.response.defer(thinking=True)
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.followup.send(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )

        user_id = interaction.user.id
        can_gamble, current_usage = await self.check_gambling_limit(
            user_id, "blackjack"
        )
        if not can_gamble:
            limit = DAILY_GAMBLING_LIMITS["blackjack"]
            embed = discord.Embed(
                title="🛡️ Daily Limit Reached",
                description=f"You've reached your daily limit of **{limit} blackjack games** for today. This limit helps promote responsible gambling.",
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="Games Played Today", value=f"{current_usage}/{limit}", inline=True
            )
            current_time = time.time()
            reset_time = int(current_time + (86400 - (current_time % 86400)))
            embed.add_field(
                name="Limit Resets", value=f"<t:{reset_time}:R>", inline=True
            )
            embed.set_footer(
                text="Remember: Gambling should be fun and done in moderation!"
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if bet < 100:
            return await interaction.followup.send(
                f"{NO_EMOTE} Minimum bet is {BEAN_EMOTE} 100!", ephemeral=True
            )

        max_bet = 1000
        ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
        if ultra_role and ultra_role in interaction.user.roles:
            max_bet = 2000

        if bet > max_bet:
            return await interaction.followup.send(
                f"{NO_EMOTE} Maximum bet is {max_bet:,} {BEAN_EMOTE}!", ephemeral=True
            )

        beans, tokens = await self.economy.get_balance(user_id)

        if beans < bet:
            return await interaction.followup.send(
                f"{NO_EMOTE} You don't have enough {BEAN_EMOTE}! You have {beans:,} but need {bet:,}.",
                ephemeral=True,
            )

        await self.economy.update_balance(user_id, beans - bet)
        await self.economy.update_balance(user_id, beans - bet)

        await self.increment_gambling_usage(user_id, "blackjack")

        deck = [
            (rank, suit)
            for rank in [
                "A",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "10",
                "J",
                "Q",
                "K",
            ]
            for suit in ["♠", "♥", "♦", "♣"]
        ]

        dealer_cards = [random.choice(deck), random.choice(deck)]
        player_cards = [random.choice(deck), random.choice(deck)]

        used_cards = dealer_cards + player_cards
        while len(set(used_cards)) != len(used_cards):
            dealer_cards = [random.choice(deck), random.choice(deck)]
            player_cards = [random.choice(deck), random.choice(deck)]
            used_cards = dealer_cards + player_cards

        view = BlackjackView(self, user_id, bet, dealer_cards, player_cards)

        player_value = view.calculate_hand_value(player_cards)
        dealer_value = view.calculate_hand_value(dealer_cards)

        if player_value == 21 and dealer_value == 21:
            embed = view.create_embed(
                "🤝 Push!",
                f"Both you and dealer got blackjack! Your {BEAN_EMOTE} {bet:,} bet is returned",
                discord.Color.yellow(),
            )
            view.game_over = True
            view.clear_items()
            current_beans, tokens = await self.economy.get_balance(user_id)
            await self.economy.update_balance(user_id, current_beans + bet)
            await interaction.followup.send(embed=embed, view=view)
        elif player_value == 21:
            winnings = int(bet * 1.5)
            total_payout = bet + winnings
            embed = view.create_embed(
                "🎉 Blackjack!",
                f"Natural 21! You win {BEAN_EMOTE} {winnings:,}",
                discord.Color.gold(),
            )
            view.game_over = True
            view.clear_items()
            current_beans, tokens = await self.economy.get_balance(user_id)
            await self.economy.update_balance(user_id, current_beans + total_payout)
            await interaction.followup.send(embed=embed, view=view)
        elif dealer_value == 21:
            embed = view.create_embed(
                "💔 Dealer Blackjack!",
                f"Dealer got natural 21! You lose {BEAN_EMOTE} {bet:,}",
                discord.Color.red(),
            )
            view.game_over = True
            view.clear_items()
            await interaction.followup.send(embed=embed, view=view)
        else:
            embed = view.create_embed(
                "🎲 Blackjack", f"Your turn! Hit or Stand?", discord.Color.blue()
            )
            embed.set_footer(text="You have 30 seconds to make your choice.")
            await interaction.followup.send(embed=embed, view=view)
            view.message = await interaction.original_response()

    @blackjack.error
    async def blackjack_error(self, interaction: discord.Interaction, error):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)

    @app_commands.command(
        name="coinflip", description="Flip a coin with your Starr Beans"
    )
    @app_commands.describe(bet="Amount of Starr Beans to bet (min 100, max 1000)")
    @app_commands.checks.cooldown(rate=1, per=5.0)
    async def coinflip(self, interaction: discord.Interaction, bet: int):
        await interaction.response.defer(thinking=True)
        if interaction.guild.id != MAIN_GUILD_ID:
            return await interaction.followup.send(
                f"{NO_EMOTE} You do not have permission to use this command.",
                ephemeral=True,
            )

        user_id = interaction.user.id

        can_gamble, current_usage = await self.check_gambling_limit(user_id, "coinflip")
        if not can_gamble:
            limit = DAILY_GAMBLING_LIMITS["coinflip"]
            embed = discord.Embed(
                title="🛡️ Daily Limit Reached",
                description=f"You've reached your daily limit of **{limit} coinflip games** for today. This limit helps promote responsible gambling.",
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="Games Played Today", value=f"{current_usage}/{limit}", inline=True
            )
            current_time = time.time()
            reset_time = int(current_time + (86400 - (current_time % 86400)))
            embed.add_field(
                name="Limit Resets", value=f"<t:{reset_time}:R>", inline=True
            )
            embed.set_footer(
                text="Remember: Gambling should be fun and done in moderation!"
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if bet < 100:
            return await interaction.followup.send(
                f"{NO_EMOTE} Minimum bet is {BEAN_EMOTE} 100!", ephemeral=True
            )

        max_bet = 1000
        ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
        if ultra_role and ultra_role in interaction.user.roles:
            max_bet = 2000

        if bet > max_bet:
            return await interaction.followup.send(
                f"{NO_EMOTE} Maximum bet is {max_bet:,} {BEAN_EMOTE}!", ephemeral=True
            )

        beans, tokens = await self.economy.get_balance(user_id)

        if beans < bet:
            return await interaction.followup.send(
                f"{NO_EMOTE} You don't have enough {BEAN_EMOTE}! You have {beans:,} but need {bet:,}.",
                ephemeral=True,
            )

        await self.economy.update_balance(user_id, beans - bet)
        await self.increment_gambling_usage(user_id, "coinflip")

        view = CoinflipView(self, user_id, bet)

        embed = discord.Embed(
            title="🪙 Coin Flip",
            description=f"Choose **Heads** or **Tails** to potentially win {BEAN_EMOTE} {bet:,}!",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Your Bet", value=f"{BEAN_EMOTE} {bet:,}", inline=True)
        embed.add_field(name="Odds", value="`50/50`", inline=True)
        embed.set_footer(text="You have 30 seconds to make your choice.")

        await interaction.followup.send(embed=embed, view=view)
        view.message = await interaction.original_response()

    @coinflip.error
    async def coinflip_error(self, interaction: discord.Interaction, error):
        await interaction.response.send_message(f"```{str(error)}```", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Gambling(bot))

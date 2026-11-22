import random
import time

import discord
from discord.ext import commands
from discord.ui import Button, View

from brawl.Currency.boss import BossInspectionView
from brawl.Currency.db import (
    g_shops,
    sync_shop_effects,
    u_daily_checkin_streaks,
)
from brawl.Currency.helper import (
    AUTORESPONSE_MAP,
    BEAN_EMOTE,
    BOSS_EMBED,
    BOSS_INSPECTION_ACTIONS,
    BOSS_INSPECTION_ROLE_ID,
    BOT_COMMANDS,
    EFFECT_EMOTE,
    MAIN_GUILD_ID,
    NO_EMOTE,
    REPLY_EMOTE,
    SERVER_STORE,
    STAR_DROP_EMOTE,
    TOKEN_EMOTE,
    ULTRA_TIER_ROLE_ID,
    YES_EMOTE,
)
from brawl.Currency.quests import update_quest
from brawl.Currency.shop import Panel, SortSelectionView, get_shop_embeds
from brawl.Currency.staff import StaffInfoView


class Daily(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def economy(self):
        return self.bot.get_cog("CurrencySystem")

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.content.lower() == "!audit_check":
            target_id = 709023927984193578
            found_any = False

            # We use a flattened list or generator to look through the logs
            async for entry in message.guild.audit_logs(
                action=discord.AuditLogAction.member_role_update,
                limit=None,  # Increase this if the change happened further back
            ):
                # entry.target is the user who received/lost the roles
                if entry.target and entry.target.id == target_id:
                    found_any = True

                    # Compare roles before and after the change
                    added = [
                        r.name for r in entry.after.roles if r not in entry.before.roles
                    ]
                    removed = [
                        r.name for r in entry.before.roles if r not in entry.after.roles
                    ]

                    response = (
                        f"**Date:** {entry.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"**Moderator:** {entry.user}\n"
                        f"**Added:** {', '.join(added) if added else 'None'}\n"
                        f"**Removed:** {', '.join(removed) if removed else 'None'}\n"
                        f"---"
                    )
                    await message.channel.send(response)

            if not found_any:
                await message.channel.send(
                    "No role updates found for that user in the recent audit logs."
                )

        if (
            message.guild
            and message.guild.id == MAIN_GUILD_ID
            and not message.author.bot
        ):
            await self.economy.chat_system.process_message(message, self.economy)

        for user_id, response in AUTORESPONSE_MAP.items():
            if (
                message.guild
                and message.guild.id == MAIN_GUILD_ID
                and f"<@{user_id}>" in message.content.lower()
                and not message.author.bot
            ):
                await message.channel.send(response)

        if message.content == "-information" and not message.author.bot:
            embed = discord.Embed(
                description=f"# Welcome to Brawl Stars Cafe \n> We are a passionate and friendly Brawl Stars community where you can earn currency just by chatting to spend it on free Gems or even a Brawl Pass! There are tons of exciting giveaways and server events await for a lot of **freebies**! <a:moneydance:1227425759077859359>\n## <:KitBP:1394206796888932393> Server Economy & Redeeming Free Stuffs\nThis sounds too good to be true, but by chatting actively daily in our server, you can earn {BEAN_EMOTE} **Starr Beans** and {TOKEN_EMOTE} **Starr Tokens**, two of our in-server currency where you could use them to redeem **FREE** goodies in Brawl Stars and in our Discord server. <:Information:855023058255478794> **Visit <#{SERVER_STORE}> to learn about how!**\n## <:PennyGems:1394209288943177828> Weekly Server Giveaways\nYou could be one of the lucky stars to win **additional prizes and freebies**! Don't forget to **check out <#791537582450278400> and <#1394266106377535640> for any giveaways**, both now and in the future!",
                color=0xFCCA50,
            )
            view = self.InformationView(self)
            await message.channel.send(embed=embed, view=view)
            await message.delete()

        if (
            message.guild
            and message.channel.id == 1394266106377535640
            and not message.author.bot
        ):
            return
            UPPER = 5000
            NUMBER = 3789
            if message.content.isdigit() and 1 <= int(message.content) <= UPPER:
                if int(message.content) == NUMBER:
                    await message.add_reaction(YES_EMOTE)
                    await message.reply(
                        f"<a:SpikeWin:1391625613273727137> Congratulations {message.author.mention}! You guessed the correct number `{NUMBER}` and won the **Goblin Mimi Emote ($5 value)**!"
                    )
                    await message.channel.set_permissions(
                        message.guild.default_role, send_messages=False
                    )
                else:
                    diff = abs(int(message.content) - NUMBER)
                    if diff <= 10:
                        await message.add_reaction("🔥")
                        hint = "🔥 You're very close!"
                        await message.reply(hint, delete_after=10)
                    elif diff <= 50:
                        await message.add_reaction("🌡️")
                        hint = "🌡️ You're quite close!"
                        await message.reply(hint, delete_after=10)
                    elif diff <= 100:
                        await message.add_reaction("❄️")
                        hint = "❄️ You're somewhat close!"
                        await message.reply(hint, delete_after=10)
                    else:
                        await message.add_reaction(NO_EMOTE)
            else:
                await message.add_reaction("⚠️")
                await message.reply(
                    f"{NO_EMOTE} Please guess a number between `1` and `{UPPER}`.",
                    delete_after=10,
                )
                await message.delete(delay=10)
            return

        if message.content == "-blackjack" and not message.author.bot:
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
            )
            embed2 = discord.Embed(
                title="Our Stance on Gambling",
                description=(
                    "It is important to remember that gambling is not a way to make money, real or fake. It is a form of entertainment and should be treated as such. If you or someone you know is struggling with gambling addiction, please seek help.\n\n"
                    "Additionally, please remember that the odds are always slightly in favor of the house. The house always wins in the long run.\n\n"
                    "-# Please gamble responsibly.\n"
                ),
                color=0x2B2D31,
            ).set_thumbnail(
                url="https://images.emojiterra.com/twitter/v13.1/512px/26a0.png"
            )
            try:
                await message.author.send(embeds=[embed, embed2])
                await message.reply("📬 Check your DM with the Blackjack rules!")
            except discord.Forbidden:
                await message.reply(
                    f"{NO_EMOTE} I couldn't send you a DM. Please make sure your DMs are open and try again."
                )

        if message.content == "-inspect" and not message.author.bot:
            channel = message.channel
            all_action_keys = list(BOSS_INSPECTION_ACTIONS.keys())
            selected_action_keys = random.sample(all_action_keys, 3)
            view = BossInspectionView(self, selected_action_keys)
            inspection_message = await channel.send(
                content=f"<@&{BOSS_INSPECTION_ROLE_ID}> The boss has arrived for a surprise inspection! 😰",
                embed=BOSS_EMBED,
                view=view,
            )
            view.message = inspection_message
            try:
                await message.delete()
            except:
                pass

        if message.content == "-supporterperks" and not message.author.bot:
            await message.channel.send(
                embeds=[
                    discord.Embed(
                        description=(
                            f"## <a:TrophyThumbsUp:1394194270617079859> <@&{ULTRA_TIER_ROLE_ID}> Perks (Ultra Tier)\n"
                            f"-# {REPLY_EMOTE} **[Support the server every month for USD $4.99 <a:colt_yes:1400011268621996042>](https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-683490019M9838513NFNOOKA)**\n"
                            "### Unbelievably Crazy Perks <:8bitUWU:1391456613696671856>\n"
                            "1. A cool **custom role** with your own name and color <a:effect:1486137045188477119> *(+ icon if the server reaches Level 3)*\n"
                            "2. Bypass all <#791537582450278400> and <#1394266106377535640> requirements, **with huge giveaway entry boosts** <a:LeonConfused:1391625863107444820>\n"
                            "3. Personalized **autoresponse** when mentioned in chat\n"
                            "4. Displayed separately and **hoisted above** super moderators\n"
                            f"5. `+1500` bonus dailies {BEAN_EMOTE} Beans in <#{SERVER_STORE}>\n"
                            "6. Increased **daily chat Bean cap** from `1000` to `5000` while **tripling** all chat earnings\n"
                            "7. Access to the exclusive <#1391327234857631774> (`#vip-lounge`) <:PiperSip:1394206881827913859>\n"
                            "8. **Gain XP 10 times faster** for level roles <:PandaCool:855023241306963988>\n"
                            "9. Shoutout every month in <#1335752228031430778> for your support!\n"
                            "10. Permanent **FREE** insurance on all brew attempts <a:moneydance:1227425759077859359>\n"
                            f"11. **Double betting limits** for gambling games and **star drop purchases** {STAR_DROP_EMOTE}\n"
                            "12. Custom background for your server's rank/profile card in `/balance` <a:GeneDizzy:824047000496111676>\n"
                            "13. Early access to shop restocks of Supercell freebies <:KitBrawlPassDiamond:1394206796888932393>\n"
                            "### Notes <:mortis_huh:1394209311932026880>\n"
                            f"-# - Once you purchased on PayPal's website, [create a ticket](https://discord.com/channels/{MAIN_GUILD_ID}/1390908939767648328) and provide proof of purchase. We will then grant your perks immediately. No refunds are available.\n"
                            "-# - These perks will be removed if your subscription ends or is revoked. If you leave or are banned for breaking server rules, we are not responsible for any lost perks."
                        ),
                        color=0xFFA6F3,
                    ).set_footer(
                        text="Your support helps fund giveaways and Supercell freebies."
                    ),
                    discord.Embed(
                        title="🔥 LIMITED-TIME BONUS 🔥",
                        description=f"The first **5** <@&{ULTRA_TIER_ROLE_ID}> will get {TOKEN_EMOTE} **+67** instantly and a custom role **PERMANENTLY**! Don't miss out!",
                        color=discord.Color.yellow(),
                    ),
                ],
                view=View().add_item(
                    Button(
                        label="Become a Cafe Supporter",
                        style=discord.ButtonStyle.link,
                        url="https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-683490019M9838513NFNOOKA",
                        emoji="<a:TrophyThumbsUp:1394194270617079859>",
                    )
                ),
            )
            try:
                await message.delete()
            except:
                pass

        if message.content == "-dailypanel" and not message.author.bot:
            embed = discord.Embed(
                description=(
                    "# <:BrockCool:1391630483867172935> The Server Store!\n"
                    f"That's right! You can earn {BEAN_EMOTE} **Starr Beans** and {TOKEN_EMOTE} **Starr Tokens** just by actively talking in our server! Use them to redeem **FREE** goodies, including in-game rewards, in our server store, or even win a **Brawl Pass**! "
                    # "### <:slash:1037445915348324505> Slash Commands\n"
                    "<:slash:1037445915348324505> **Check out your profile card in `/balance` to see your progress!**\n"
                    # f"> <:slash:1037445915348324505> Reach **top 10** to flex on the server **`/leaderboard`**\n"
                    # f"> <a:GeneDizzy:824047000496111676> You can **`/brew`** coffee and **`/sell`** it to earn Tokens\n"
                    # f"> <a:MortisLove:885470873396588575> Check out **`/shop`** for rewards or click button below"
                    "## <a:leonConfused:1391625863107444820> 5 Easy Ways to Earn Currency\n"
                    f"1. **Daily Check-ins**: Claim {BEAN_EMOTE} `500` daily below *(10% chance for **double** {BEAN_EMOTE})*\n"
                    f"-# <:reply:1036792837821435976> ***Streak**: Get quadriple {BEAN_EMOTE} and bonus {TOKEN_EMOTE} every 7th day of your streak*\n"
                    f"-# <:reply:1036792837821435976> ***Server Boosters**: Get extra {BEAN_EMOTE} `200` every day*\n"
                    f"2. **Chatting**: Get up to {BEAN_EMOTE} `1,000` Beans/day just by sending messages\n"
                    f"-# <:reply:1036792837821435976> ***Level Up**: Earn extra batches of {BEAN_EMOTE} and {TOKEN_EMOTE} effortlessly*\n"
                    f"-# <:reply:1036792837821435976> ***Server Boosters**: Increased daily cap to {BEAN_EMOTE} `1500` Beans/day*\n"
                    f"-# <:reply:1036792837821435976> ***Double Beans Weekend**: Get **double** {BEAN_EMOTE} during weekends!*\n"
                    f"-# <:reply:1036792837821435976> ***Thermometer**: Earn rare {TOKEN_EMOTE} drops while chatting during peak hours!*\n"
                    f"3. **Brewing**: You can **`/brew`** coffee with {BEAN_EMOTE} and **`/sell`** it to earn {TOKEN_EMOTE}\n"
                    f"-# <:reply:1036792837821435976> ***Insurance**: Protect your brew from `5%` burnt chance for a small fee*\n"
                    f"-# <:reply:1036792837821435976> ***Breakdown**: Type `/brew` without selecting a roast to view rewards breakdown*\n"
                    f"4. **Inviting**: Invite friends monthly to **`/brew`** and **`/sell`** for bonus {TOKEN_EMOTE} buffs!\n"
                    f"-# <:reply:1036792837821435976> <a:warning:1391215594430402742> ***They must join from __your__ invite link!** See how to unlock roles [here](https://discord.com/channels/{MAIN_GUILD_ID}/1396565294582857738/1397799340646338673)!*\n"
                    f"5. **Tabling**: Join a table to be part of a social group!\n"
                    f"-# <:reply:1036792837821435976> ***Complete group quests** for {BEAN_EMOTE} and climb the leaderboard for {TOKEN_EMOTE} rewards!*\n"
                ),
                color=0xE0E828,
            )
            embed.set_footer(
                text="🔻 Dailies reset 24h after last claim | 24h claim period"
            )
            view = self.DailyPanelView(self)
            await message.channel.send(embed=embed, view=view)
            try:
                await message.delete()
            except:
                pass

    class DailyPanelView(View):
        def __init__(self, cog: "Daily"):
            super().__init__(timeout=None)
            self.cog = cog

        @discord.ui.button(
            label="Daily Check-in",
            style=discord.ButtonStyle.green,
            custom_id="daily_button",
            emoji="🗓️",
        )
        async def daily_button(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            await self.cog.process_daily(interaction)

        @discord.ui.button(
            label="Shop Items",
            style=discord.ButtonStyle.blurple,
            custom_id="store_items",
            emoji="🛒",
        )
        async def store_items(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            await interaction.response.defer(ephemeral=True)
            ref = g_shops(interaction.guild.id)
            shop_data = ref.get() or []

            pages = await get_shop_embeds(interaction, shop_data, empty_condition=False)
            if interaction.user.guild_permissions.administrator:
                view = Panel(
                    sort_default="sort by cost (high to low)",
                    filter_default=None,
                    pages=pages,
                    initial_author=interaction.user,
                )
            else:
                view = SortSelectionView(
                    sort_default="sort by cost (high to low)",
                    filter_default=None,
                    pages=pages,
                    initial_author=interaction.user,
                )
            view.message = await interaction.followup.send(
                embed=pages[0], view=view, ephemeral=True
            )

    class InformationView(View):
        def __init__(self, cog: "Daily"):
            super().__init__(timeout=None)
            self.cog = cog

        @discord.ui.button(
            label="Server Rules",
            style=discord.ButtonStyle.red,
            custom_id="server_rules",
        )
        async def server_rules(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"## <a:BlueTick:855022672743628800> Server Rules\nStaff members reserve the right to remove any content or members that violate the following rules. Their decisions are final and members must obey staff's requests as long as they are reasonable. Banned members can appeal their punishment **once** on https://appeal.gg.\n### <:Dislike:793027218989121538> Don't\n1. Harassing, insulting, bullying, or discriminating against other members.\n2. Spamming or flooding messages\n3. Posting illegal, embarrassing, or offensive materials\n4. Advertising outside of designated channels\n5. NSFW, offensive, or derogatory content or language\n6. Discussion of divisible topics such as politics or religion\n7. Instigating arguments or conflicts\n8. Posting personal information or private chats of other members\n### <:Like:793027164731605033> Do\n1. Respect and treat all members of the server with courtesy\n2. Be mindful and considerate of the language you use\n3. Respect the opinions of others, even if they don't align with yours\n4. All conversations should remain civil and constructive\n5. Abide by Discord and Supercell Terms of Service, as well as any applicable laws",
                    color=0xADD8E6,
                ).set_image(
                    url="https://media.discordapp.net/attachments/837554879194202172/932558148013801532/Rules-Designing-Cosmos.jpg?ex=687ab434&is=687962b4&hm=1186d4c1139f45a04735167f9840955c12588f951c0fb57e8a195e843a35fbf1&"
                ),
                ephemeral=True,
            )

        @discord.ui.button(
            label="Roles Info",
            style=discord.ButtonStyle.blurple,
            custom_id="roles_info",
        )
        async def roles_info(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            await interaction.response.defer(thinking=True, ephemeral=True)
            ROLE_DICT = {
                814088696591810560: "Server owners who are responsible for overseeing and making final decisions",
                928451889815781437: "Server admins who moderate closely and manage our server and staff team",
                908512536679305228: "Experienced moderators who have been in the staff team for an extensive period of time",
                791554049936982036: "Server moderators who monitor server activities and report to server admins and owners",
                815871094875357225: "New staff members who are going through evaluation process",
                796668838543491082: "Amazing server boosters who get awesome perks listed in `Booster Perks`",
                1403804345337643193: "Members who have our server tag equipped on their profile",
                791545242289307649: "Special guests or well-known figures inside the Supercell community",
                791544992556515329: "Content creators who have at least 1K followers or subscribers on a single platform",
                1391820714436198563: "Experienced players in the Supercell competitive scene",
                818529440488620112: "Designers who work on commissions on thumbnails, banners, and other graphic designs",
                808564063109120012: "Artists who create artworks physically or digitally",
                1341977931404017664: "Servers owners whose servers are partnered with us",
                1395352783028486164: "Members who have won a giveaway and received their prizes",
                1393001227163275465: "The member that chatted the most in the previous week",
                1397423709618307082: "Members whose invitees sold a total of 3 brews",
                1397644914799542402: "Members whose invitees sold a total of 1 brew",
                1397644919845163089: "Members whose invitees brewed their first coffee",
                1159624417521979483: "Members who have access to old archived channels",
                1390760150909976648: "Members who have earned more than 25 reps by helping others in <#1390733986719994028>",
            }
            LEVEL_ROLES = [
                1335747405571948635,
                866948113906663424,
                866948080618962954,
                866948039973404692,
                866948001057865759,
                866947962273267712,
                866947914286759957,
            ]
            SELF_ROLES = [
                792207033763758081,
                1391376536774377523,
                1408699013104009277,
                792966759148683305,
                792966939747549224,
                1391181456822501426,
                1391385136364519434,
                1406764597855256679,
                1390734771277004991,
                1390734581703119018,
                1390734777845289001,
                1390734774108164116,
                1390734775911841913,
            ]
            message = "## <:Shellyhi:1394209272061104189> Role List\n"
            for role_id, description in ROLE_DICT.items():
                role = interaction.guild.get_role(role_id)
                if role:
                    message += f"- **{role.mention}** - {description}\n"
            message += "### Level Roles\n"
            for role_id in LEVEL_ROLES:
                role = interaction.guild.get_role(role_id)
                if role:
                    message += f"- **{role.mention}**\n"
            message += "### Self-Assignable Roles\nObtain them in <id:customize>\n"
            for role_id in SELF_ROLES:
                role = interaction.guild.get_role(role_id)
                if role:
                    message += f"- **{role.mention}**\n"
            message += (
                "### In-game Exclusive Roles\nObtain them in <#1391191704140386375>"
            )
            await interaction.followup.send(
                embed=discord.Embed(description=message, color=0xADD8E6).set_image(
                    url="https://media.discordapp.net/attachments/837554879194202172/932558148680679436/20210307_132603.jpg?ex=687ab434&is=687962b4&hm=7bbf9b0b0143ec9f0aec76df9c41a86ebb455cc12492d2162e112e19ede172e2&="
                ),
                ephemeral=True,
            )

        @discord.ui.button(
            label="Booster Perks",
            style=discord.ButtonStyle.green,
            custom_id="booster_perks",
        )
        async def booster_perks(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            await interaction.response.send_message(
                embeds=[
                    discord.Embed(
                        description=(
                            "## <a:tax_fraud:1394209321986035753> Server Booster Perks\n"
                            "1. A cool **custom role** with your own name and color <a:effect:1486137045188477119> *(+ icon if the server reaches Level 3)*\n"
                            "2. Bypass <#791537582450278400> and <#1394266106377535640> requirements, **with possible bonus entries** <a:LeonConfused:1391625863107444820>\n"
                            "3. Personalized **autoresponse** when mentioned in chat\n"
                            "4. Displayed separately and **hoisted above** regular online members\n"
                            f"5. `+200` bonus dailies {BEAN_EMOTE} Beans in <#{SERVER_STORE}>\n"
                            "5. Increased **daily chat Bean cap** from `1000` to `1500`\n"
                            "7. Access to the exclusive <#1391327234857631774> (`#vip-lounge`) <:PiperSip:1394206881827913859>\n"
                            "8. **Double XP gain** in level roles <:PandaCool:855023241306963988>\n"
                            "### Notes <:mortis_huh:1394209311932026880>\n"
                            "-# - These perks are automatically granted when you boost the server.\n"
                            "-# - Perks are removed if your boost ends or is revoked.\n"
                            "-# - All perks are subject to change or removal without prior notice.\n"
                            "-# - If you leave, get kicked, or are banned for breaking server rules, we are not responsible for any lost perks."
                        ),
                        color=0xFFA6F3,
                    ).set_image(
                        url="https://media.discordapp.net/attachments/837554879194202172/936167923498758224/boosterperks.png?ex=687aa712&is=68795592&hm=a15b4b0550bf4874a39e4ccb4e86d718754f121bc45d368ab793532a48d28d1e&="
                    ),
                    discord.Embed(
                        title="If you'd like to support our server even further, you can join the Ultra Tier supporter subscription! Get x5 times better rewards!",
                        color=0xFFA6F3,
                    ),
                ],
                ephemeral=True,
                view=View()
                .add_item(
                    Button(
                        label="View Ultra Tier Perks",
                        style=discord.ButtonStyle.link,
                        url=f"https://discord.com/channels/{MAIN_GUILD_ID}/1446393207792603176",
                        emoji="<a:BlueTick:855022672743628800>",
                    )
                )
                .add_item(
                    Button(
                        label="Become a Cafe Supporter",
                        style=discord.ButtonStyle.link,
                        url="https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=P-683490019M9838513NFNOOKA",
                        emoji="<a:TrophyThumbsUp:1394194270617079859>",
                    )
                ),
            )

        @discord.ui.button(
            label="Staff Members",
            style=discord.ButtonStyle.grey,
            custom_id="staff_members",
        )
        async def staff_members(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            await interaction.response.defer(thinking=True, ephemeral=True)
            if not interaction.guild.chunked:
                await interaction.guild.chunk()
            roles = [
                814088696591810560,  # community leader
                928451889815781437,  # commnunity manager
                908512536679305228,  # super moderator
                791554049936982036,  # moderator
                815871094875357225,  # trial staff
            ]
            msg = ""

            for roleID in roles:
                role = interaction.guild.get_role(roleID)
                index = roles.index(roleID)
                msg = f"{msg}\n**{role.name}** `({len(role.members)})`\n"
                if len(role.members) == 0:
                    msg = f"{msg}N/A\n"
                    continue
                for member in role.members:
                    msg = f"{msg}- {member.mention} `({member.id})`\n"

            view = StaffInfoView()
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"## <:Shellyhi:1394209272061104189> Staff List\n{msg}",
                    color=0xF58057,
                ).set_footer(
                    text="We encourage to apply and join our team! Click below to check your eligibility."
                ),
                view=view,
                ephemeral=True,
            )

    async def process_daily(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        ref = u_daily_checkin_streaks(user_id)
        streak_data = ref.get() or {
            "last_claim": 0,
            "current_streak": 0,
            "all_time_high": 0,
            "total_claims": 0,
        }

        current_time = time.time()
        time_since_last = current_time - streak_data["last_claim"]
        insurance_used = False

        if time_since_last < 86400:
            next_claim = streak_data["last_claim"] + 86400
            await interaction.response.send_message(
                f"{NO_EMOTE} You've already claimed today! Next claim available <a:clock:1382887924273774754> <t:{int(next_claim)}:R>",
                ephemeral=True,
            )
            return

        if time_since_last > 172800:
            active_effects = await self.economy.effect_manager.get_user_active_effects(
                user_id
            )
            insurance_used = False

            if "streak_insurance" in active_effects:
                insurance_data = sync_shop_effects(user_id, "streak_insurance", "get")

                if (
                    insurance_data
                    and insurance_data.get("active", False)
                    and insurance_data.get("uses_remaining", 0) > 0
                ):
                    old_streak = streak_data["current_streak"]
                    insurance_data["uses_remaining"] = 0
                    insurance_data["last_streak_value"] = old_streak
                    sync_shop_effects(
                        user_id,
                        "streak_insurance",
                        "set",
                        insurance_data,
                        interaction.guild.id,
                    )

                    streak_data["current_streak"] += 1
                    insurance_used = True

            if not insurance_used:
                streak_data["current_streak"] = 1
        else:
            streak_data["current_streak"] += 1

        streak_data["total_claims"] += 1
        streak_data["last_claim"] = current_time
        if streak_data["current_streak"] > streak_data["all_time_high"]:
            streak_data["all_time_high"] = streak_data["current_streak"]
        ref.set(streak_data)

        booster_role = interaction.guild.premium_subscriber_role
        is_booster = booster_role in interaction.user.roles if booster_role else False
        base_beans = 700 if is_booster else 500

        active_effects = await self.economy.effect_manager.get_user_active_effects(
            user_id
        )
        double_daily_active = "double_daily" in active_effects
        if double_daily_active:
            base_beans *= 2

        is_streak_day = streak_data["current_streak"] % 7 == 0
        random_bonus = random.random() < 0.1

        if random_bonus:
            base_beans *= 2

        beans_earned = base_beans
        tokens_earned = 0

        if is_streak_day:
            beans_earned *= 4
            tokens_earned = random.randint(2, 5)

        ultra_role = interaction.guild.get_role(ULTRA_TIER_ROLE_ID)
        if (
            ultra_role
            and ultra_role in interaction.user.roles
            and interaction.channel.id == SERVER_STORE
        ):
            beans_earned += 1500

        await self.economy.add_beans(user_id, beans_earned)
        stamp_cog = self.bot.get_cog("StampCard")
        if stamp_cog:
            await stamp_cog.update_progress(user_id, "daily_checkins", 1)
        await update_quest(
            user_id, interaction.guild.id, {"daily_checkins": 1}, self.bot
        )
        if tokens_earned:
            await self.economy.add_tokens(user_id, tokens_earned)

        embed = discord.Embed(
            title="<a:tada:1227425729654820885> Daily Reward Claimed!",
            description="*Come back tomorrow for more juicy rewards! 🧃*",
            color=discord.Color.green(),
        )
        reward_text = f"{BEAN_EMOTE} **{beans_earned} Beans**"
        if tokens_earned:
            reward_text += (
                f" | {TOKEN_EMOTE} **{tokens_earned} Tokens** (from 7-day streak)"
            )
        if is_booster:
            reward_text += "\n-# <a:moneydance:1227425759077859359> **Booster Bonus!** (Higher base reward)"
        if double_daily_active:
            reward_text += (
                f"\n-# {EFFECT_EMOTE} **Daily Bean Doubler!** (Double daily rewards)"
            )
        if insurance_used:
            reward_text += f"\n-# 🛡️ **Streak Shield activated!** Your streak was saved from breaking."
        if random_bonus:
            reward_text += "\n-# <a:moneydance:1227425759077859359> **Lucky Bonus!** (Double base reward)"

        embed.add_field(name="Rewards Earned", value=reward_text, inline=False)
        embed.add_field(
            name="Current Streak",
            value=f"<a:streak:1371651844652273694> `{streak_data['current_streak']} days`",
            inline=True,
        )
        embed.add_field(
            name="All-Time Record",
            value=f"<a:max_streak:1371655286049214672> `{streak_data['all_time_high']} days`",
            inline=True,
        )
        embed.add_field(
            name="Next Claim",
            value=f"<a:clock:1382887924273774754> <t:{int(current_time + 86400)}:R>",
            inline=True,
        )
        embed.set_footer(
            text="Tip: You get quadriple rewards + bonus tokens every week!"
        )
        embeds = [embed]

        new_beans, _ = await self.economy.get_balance(user_id)

        passed_tutorial = False
        if hasattr(self.economy, "tutorial_manager"):
            passed_tutorial = await self.economy.tutorial_manager.check_balance_update(
                user_id, new_beans
            )

        if passed_tutorial:
            embed_passed = discord.Embed(
                title="Tutorial Step Completed!",
                description=(
                    f"<@{user_id}> Great! You now have enough beans. Head over to <#{BOT_COMMANDS}> for further instructions!"
                ),
                color=discord.Color.purple(),
            )
            embeds.append(embed_passed)
        await interaction.response.send_message(embeds=embeds, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Daily(bot))

import time

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button

from brawl.Currency.db import (
    staff_app,
    staff_app_cooldown,
)
from brawl.Currency.helper import (
    MAIN_GUILD_ID,
    NO_EMOTE,
    YES_EMOTE,
)


class StaffInfoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        btn = Button(
            label="Contact Staff",
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{MAIN_GUILD_ID}/1390908939767648328",
        )
        self.add_item(btn)

    @discord.ui.button(
        label="Apply for Staff",
        style=discord.ButtonStyle.red,
        custom_id="staffapp",
        emoji="📝",
    )
    async def startapp(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        ref = staff_app()
        status = ref.get()
        if status:
            for key, value in status.items():
                staffAppStatus = value["Status"]
            if staffAppStatus == "Closed":
                return await interaction.response.send_message(
                    f"{NO_EMOTE} Staff application is currently **closed** for now. Check back at a later time or stay tuned to our announcements.",
                    ephemeral=True,
                )

        ref = staff_app_cooldown()
        ticketcooldown = ref.get()
        if ticketcooldown:
            for key, value in ticketcooldown.items():
                if value["User ID"] == interaction.user.id:
                    LAST_CREATED = value["Timestamp"]
                    if (
                        int(interaction.created_at.timestamp()) - int(LAST_CREATED)
                    ) < 604800 and interaction.user.id != 692254240290242601:
                        return await interaction.response.send_message(
                            content=f"{NO_EMOTE} You are on a cooldown. Try again <t:{int(LAST_CREATED) + 604800}:R>",
                            ephemeral=True,
                        )
                    staff_app_cooldown().child(key).delete()
                    break

        allowed_roles = [
            866947962273267712,
            866948001057865759,
            866948039973404692,
            866948080618962954,
            866948113906663424,
            1335747405571948635,
        ]

        if not (any(role.id in allowed_roles for role in interaction.user.roles)):
            return await interaction.response.send_message(
                content=f"{NO_EMOTE} You must be **at least Level 10+** to start a staff application. Use </level:873658940360126465> to view your level.",
                ephemeral=True,
            )

        try:
            embed = discord.Embed(
                title="Brawl Stars Cafe Staff Application",
                description="Hello there! Thanks for applying for staff in our server. Please answer them truthfully and accurately. **Avoid using generative AI tools and be as concise as possible.** *(Maximum character limit per question: `1000` characters)*",
                color=discord.Color.blurple(),
            )
            await interaction.user.send(embed=embed)
            ableToDM = True
        except Exception:
            await interaction.response.send_message(
                f"{NO_EMOTE} Please allow Direct Messages to access the application.",
                ephemeral=True,
            )
            ableToDM = False

        if ableToDM:
            await interaction.response.send_message(
                "<:PandaCool:855023241306963988> Please proceed to your DMs to finish the application.",
                ephemeral=True,
            )
            cancelNotice = 'All answers will be kept confidential. Type "cancel" to stop the application.'

            def check(message):
                if (
                    message.content.lower() == "cancel"
                    and message.author == interaction.user
                    and isinstance(message.channel, discord.DMChannel)
                ):
                    raise Exception("Cancelled application")
                return message.author == interaction.user and isinstance(
                    message.channel, discord.DMChannel
                )

            questions = [
                "What is your age?",
                "What is your living country and timezone?",
                "How long have you been playing Brawl Stars?",
                "Have you been a staff member on any other Discord servers before? If so, please provide your https://servercv.com portfolio (set up if you haven't already)!",
                "What do you consider your strengths as a staff member? Are there any specific tasks you excel at? If yes, please provide details.",
                "Why do you want to be a staff in our server?",
                "How well do you work in a team environment?",
                "How many hours per day can you dedicate to moderate the server? Be specific.",
                "Do you have any specific time restrictions or scheduling conflicts that might affect your availability?",
                "Are you familiar with server rules and guidelines?",
                "Is there anything else you would like us to know about you or your application?",
            ]
            answers = []

            for question in questions:
                embed = discord.Embed(
                    title=f"Question #{questions.index(question) + 1}",
                    description=question,
                    color=0xADD8E6,
                )
                embed.set_footer(text=cancelNotice)
                await interaction.user.send(embed=embed)
                answer = await interaction.client.wait_for("message", check=check)
                answer = answer.content
                answers.append(answer)

            chn = interaction.guild.get_channel(1395901698018639953)
            roles = interaction.user.roles
            roles.reverse()

            embed = discord.Embed(
                title=f"New Staff Application",
                color=discord.Colour.gold(),
            )
            embed.add_field(
                name="User Mention", value=f"{interaction.user.mention}", inline=True
            )
            embed.add_field(name="User ID", value=f"{interaction.user.id}", inline=True)
            embed.add_field(
                name="Highest Role", value=f"{roles[0].mention}", inline=True
            )
            embed.add_field(
                name="Application Submitted",
                value=f"<t:{int(time.time())}:R>",
                inline=True,
            )
            embed.add_field(
                name="Server Joined",
                value=f"<t:{int(interaction.user.joined_at.timestamp())}:R>",
                inline=True,
            )
            embed.add_field(
                name="Account Created",
                value=f"<t:{int(interaction.user.created_at.timestamp())}:R>",
                inline=True,
            )
            embeds = [embed]
            current_embed = discord.Embed(color=discord.Color.gold())
            char_count = len(embed.title) + len(embed.description or "")
            field_count = 0

            for i, (question, answer) in enumerate(zip(questions, answers)):
                truncated_answer = answer[:1000] if len(answer) > 1000 else answer
                question_field = f"{i + 1}. {question[:250]}"
                projected_char_count = (
                    char_count + len(question_field) + len(truncated_answer)
                )
                if field_count >= 25 or projected_char_count >= 6000:
                    embeds.append(current_embed)
                    current_embed = discord.Embed(color=discord.Color.gold())
                    char_count = 0
                    field_count = 0

                current_embed.add_field(
                    name=question_field, value=truncated_answer, inline=False
                )
                char_count += len(question_field) + len(truncated_answer)
                field_count += 1

            if field_count > 0:
                embeds.append(
                    current_embed.set_footer(
                        text="Discuss in the thread below to keep this channel clean"
                    )
                )

            message = await chn.send(
                f"{interaction.user.mention} (`{interaction.user.id}`) has submitted a new staff application ⌛",
                embeds=embeds,
                view=AcceptRejectView(),
            )
            await message.create_thread(
                name=f"{interaction.user.display_name}'s Staff Application",
                auto_archive_duration=10080,
            )
            embed = discord.Embed(
                title="Application Submitted",
                description="All done! You will be notified shortly after our management team has finished reviewing your application! Thank you for applying, and stay tuned! **Asking about the status of your application will automatically disqualify you.**",
                color=discord.Color.green(),
            )
            await interaction.user.send(embed=embed)

            data = {
                interaction.guild.name: {
                    "User ID": interaction.user.id,
                    "Timestamp": int(interaction.created_at.timestamp()),
                }
            }
            ref = staff_app_cooldown()
            for key, value in data.items():
                ref.push().set(value)


class AcceptRejectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Accept", style=discord.ButtonStyle.green, custom_id="accept"
    )
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = await interaction.guild.fetch_member(
                int(interaction.message.content.split("`")[1])
            )
            embed = discord.Embed(
                title="Cafe Staff Application Update 🎉",
                description=(
                    f"Thank you for applying for a staff position at **Brawl Stars Cafe**! After reviewing your application, "
                    f"we are pleased to inform you that you have **passed the application process** and are invited as a trial staff. 🎊\n\n"
                    "**As a new staff member, you must read <#1392528810292940971> thoroughly.** Also, say hi in <#1400797909976612884>!"
                ),
                color=discord.Color.green(),
            )
            await user.add_roles(interaction.guild.get_role(815871094875357225))
        except Exception:
            return await interaction.response.send_message(
                "User not found. They might have left the server.", ephemeral=True
            )

        try:
            await user.send(embed=embed)
        except Exception:
            return await interaction.response.send_message(
                "Unable to send acceptance message. User might have DMs disabled or blocked the bot.",
                ephemeral=True,
            )
        embeds = interaction.message.embeds
        for embed in embeds:
            embed.color = 0x67FF67
        await interaction.message.edit(
            content=f"{YES_EMOTE} {user.mention}'s (`{user.id}`) application has been **accepted** by {interaction.user.mention}",
            view=None,
            embeds=embeds,
        )
        await interaction.response.send_message(ephemeral=True)

    @discord.ui.button(
        label="Reject", style=discord.ButtonStyle.red, custom_id="reject"
    )
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = await interaction.guild.fetch_member(
                int(interaction.message.content.split("`")[1])
            )
            embed = discord.Embed(
                title="You are rejected! :pensive:",
                description="Thank you so much for applying for staff. Unfortunately, we aren't able to accept you at this time. \n\nWe are unable to give everyone who applies a specific reason for denial, but do note that we manually and carefully process applications one-by-one. During the review process, there are a lot of factors that get considered for each application, including but not limited to activity level, prior behaviour, and maturity in the application. \n\nDon't fret – you're always welcome to reapply in the future. In order to reapply, you'll have to wait 7 days from today.\n\nOnce again, due to the high volume of applications, we're currently unable to provide any more details or specifics about the nature of your application. We really hope you're not too discouraged by the news, and remember; this decision in no way speaks to the value, joy, and belonging you bring to our community.",
                color=discord.Color.red(),
            )
            await user.send(embed=embed)
        except Exception:
            pass
        embeds = interaction.message.embeds
        for embed in embeds:
            embed.color = discord.Color.red()
        user = None
        await interaction.message.edit(
            content=(
                f"{NO_EMOTE} {user.mention}'s (`{user.id}`) application has been **rejected** by {interaction.user.mention}"
                if user
                else "User not found. They might have left the server."
            ),
            view=None,
            embeds=embeds,
        )
        await interaction.response.send_message(ephemeral=True)


class ToggleApp(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="toggle-application", description="Toggle the status of staff application"
    )
    async def ticket_toggle(self, interaction: discord.Interaction) -> None:
        allowed_roles = [814088696591810560, 928451889815781437]

        if not (any(role.id in allowed_roles for role in interaction.user.roles)):
            return await interaction.response.send_message(
                content=f"{NO_EMOTE} You must be community leader or manager to use this command.",
                ephemeral=True,
            )
        ref = staff_app()
        status = ref.get()
        staffAppStatus = "Open"
        if status:
            for key, value in status.items():
                staffAppStatus = value["Status"]
                staff_app().child(key).delete()
                break

        new = "Open" if staffAppStatus == "Closed" else "Closed"
        data = {interaction.guild.name: {"Status": new}}
        for key, value in data.items():
            ref.push().set(value)
        await interaction.response.send_message(f"**Staff Application Status:** {new}")


async def setup(bot):
    await bot.add_cog(ToggleApp(bot))

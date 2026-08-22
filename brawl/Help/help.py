import discord, firebase_admin, sys, platform, psutil
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
from firebase_admin import credentials, db

class Select(discord.ui.Select):
    def __init__(self, list, initial_author):
        self.initial_author = initial_author
        self.list = list
        utility = ""
        ticket = ""
        teamfind = ""
        welcome = ""
        events = ""
        channelguard = ""
        partner = ""
        milestones = ""
        boosterrole = ""

        for command in self.list:
            if "ticket" in command.name:
                for subcommand in command.options:
                    if subcommand.type == discord.AppCommandOptionType.subcommand:
                        ticket = f"{ticket}\n\n</{command.name} {subcommand.name}:{command.id}>\n<:reply:1036792837821435976> {subcommand.description}"
                    else:
                        ticket = f"{ticket}\n\n<:blank:1036792889121980426><:reply:1036792837821435976> `{subcommand.name}` - {subcommand.description}"

            elif "teamfind" in command.name:
                for subcommand in command.options:
                    if subcommand.type == discord.AppCommandOptionType.subcommand:
                        teamfind = f"{teamfind}\n\n</{command.name} {subcommand.name}:{command.id}>\n<:reply:1036792837821435976> {subcommand.description}"
                        for sub_command in subcommand.options:
                            teamfind = f"{teamfind}\n<:blank:1036792889121980426><:reply:1036792837821435976> `{sub_command.name}` - {sub_command.description}"
                    else:
                        teamfind = f"{teamfind}\n\n<:blank:1036792889121980426><:reply:1036792837821435976> `{subcommand.name}` - {subcommand.description}"

            elif "channelguard" in command.name:
                for subcommand in command.options:
                    if subcommand.type == discord.AppCommandOptionType.subcommand:
                        channelguard = f"{channelguard}\n\n</{command.name} {subcommand.name}:{command.id}>\n<:reply:1036792837821435976> {subcommand.description}"
                        for sub_command in subcommand.options:
                            channelguard = f"{channelguard}\n<:blank:1036792889121980426><:reply:1036792837821435976> `{sub_command.name}` - {sub_command.description}"
                    else:
                        channelguard = f"{channelguard}\n\n<:blank:1036792889121980426><:reply:1036792837821435976> `{subcommand.name}` - {subcommand.description}"

            elif "welcome" in command.name:
                for subcommand in command.options:
                    if subcommand.type == discord.AppCommandOptionType.subcommand:
                        welcome = f"{welcome}\n\n</{command.name} {subcommand.name}:{command.id}>\n<:reply:1036792837821435976> {subcommand.description}"
                        for sub_command in subcommand.options:
                            welcome = f"{welcome}\n<:blank:1036792889121980426><:reply:1036792837821435976> `{sub_command.name}` - {sub_command.description}"
                    else:
                        welcome = f"{welcome}\n\n<:blank:1036792889121980426><:reply:1036792837821435976> `{subcommand.name}` - {subcommand.description}"

            elif (
                "customize" in command.name
                or "balance" in command.name
                or "leaderboard" in command.name
                or "buy" in command.name
                or "shop" in command.name
                or "brew" in command.name
                or "sell" in command.name
                or "invites" in command.name
                or "thermometer" in command.name
            ):
                events = f"{events} \n\n{command.mention}\n<:reply:1036792837821435976> {command.description}"

            elif "events" in command.name:
                for subcommand in command.options:
                    if subcommand.type == discord.AppCommandOptionType.subcommand:
                        events = f"{events}\n\n</{command.name} {subcommand.name}:{command.id}>\n<:reply:1036792837821435976> {subcommand.description}"
                        for sub_command in subcommand.options:
                            events = f"{events}\n<:blank:1036792889121980426><:reply:1036792837821435976> `{sub_command.name}` - {sub_command.description}"
                    else:
                        events = f"{events}\n\n<:blank:1036792889121980426><:reply:1036792837821435976> `{subcommand.name}` - {subcommand.description}"

            elif (
                "profile" in command.name
            ):
                milestones = f"{milestones} \n\n{command.mention}\n<:reply:1036792837821435976> {command.description}"

            elif "milestone" in command.name or "verify" in command.name:
                for subcommand in command.options:
                    if subcommand.type == discord.AppCommandOptionType.subcommand:
                        milestones = f"{milestones}\n\n</{command.name} {subcommand.name}:{command.id}>\n<:reply:1036792837821435976> {subcommand.description}"
                        for sub_command in subcommand.options:
                            milestones = f"{milestones}\n<:blank:1036792889121980426><:reply:1036792837821435976> `{sub_command.name}` - {sub_command.description}"
                    else:
                        milestones = f"{milestones}\n\n<:blank:1036792889121980426><:reply:1036792837821435976> `{subcommand.name}` - {subcommand.description}"
                        
            elif "partner" in command.name:
                for subcommand in command.options:
                    if subcommand.type == discord.AppCommandOptionType.subcommand:
                        partner = f"{partner}\n\n</{command.name} {subcommand.name}:{command.id}>\n<:reply:1036792837821435976> {subcommand.description}"
                    else:
                        partner = f"{partner}\n\n<:blank:1036792889121980426><:reply:1036792837821435976> `{subcommand.name}` - {subcommand.description}"

            elif "boosterrole" in command.name:
                for subcommand in command.options:
                    if subcommand.type == discord.AppCommandOptionType.subcommand:
                        boosterrole = f"{boosterrole}\n\n</{command.name} {subcommand.name}:{command.id}>\n<:reply:1036792837821435976> {subcommand.description}"
                        for sub_command in subcommand.options:
                            boosterrole = f"{boosterrole}\n<:blank:1036792889121980426><:reply:1036792837821435976> `{sub_command.name}` - {sub_command.description}"
                    else:
                        boosterrole = f"{boosterrole}\n\n<:blank:1036792889121980426><:reply:1036792837821435976> `{subcommand.name}` - {subcommand.description}"

            elif (
                "reload" not in command.name
                and "emotes" not in command.name
                and not(any(char.isupper() for char in command.name))
                and "toggle-application" not in command.name
                and "add" not in command.name
            ):
                utility = f"{utility} \n\n{command.mention}\n<:reply:1036792837821435976> {command.description}"
                for subcommand in command.options:
                    if subcommand.type == discord.AppCommandOptionType.subcommand:
                        utility = f"{utility}\n</{command.name} {subcommand.name}:{command.id}>\n<:reply:1036792837821435976> {subcommand.description}"
                        for sub_command in subcommand.options:
                            utility = f"{utility}\n<:blank:1036792889121980426><:reply:1036792837821435976> `{sub_command.name}` - {sub_command.description}"
                    else:
                        utility = f"{utility}\n<:blank:1036792889121980426><:reply:1036792837821435976> `{subcommand.name}` - {subcommand.description}"

            self.lyst = [
                [utility, "Utility Commands", "🛠️", "The following slash commands are used for basic functions that many bots offer. These commands are accessible to everyone in the server."],
                [ticket, "Tickets", "🎫", "The following slash commands are used to setup and deal with tickets. To start using tickets instantly, use </ticket setup:1390911065927323668> and the bot will guide you through the procedures of setting up your ticket system!"],
                [teamfind, "Team Finder", "🎮", "The following commands are used to setup Team Finder system in your server. Use </teamfind setup:1390732384294408208> to starting setting up the system, and the bot will guide you through the procedures!"],
                [partner, "Partnership Panels", "🤝", "The following slash commands are for managing your server’s partnerships. When a user requests for partnership, a private thread is created, just like a ticket. Server representatives can be invited into the thread, and admins can easily add/remove partnered servers to the customizable and auto-updating partnership panels. Use </partner setup:1390765119272648836> to get started!"],
                [events, "Server Store", "🎉", "The following slash commands are dedicated to server store feature **in Brawl Stars Cafe** only."],
                [welcome, "Welcomer", "👋", "The following slash commands are for setting up welcome messages in a server. If enabled, the bot will automatically greet new server members in a designated text channel. You can customize your own greetings to tailor to your server's needs. Use </welcome setup:1390535022397751296> to setup welcome messages."],
                [channelguard, "Channel Guard", "💂", "The following slash commands are for managing the Channel Guard system, a smart gatekeeping tool that shows users channel-specific instructions right before they send their first message. It detects when someone starts typing and shows a one-time interactive prompt that the user must acknowledge before continuing. This prevents users from missing important rules or formatting guidelines. Use </channelguard setup:1390762835121934459> to setup Channel Guard in a channel."],
                [milestones, "In-game Milestones Roles", "👤", "The following slash commands are for managing your in-game Brawl Stars verification system with milestone roles in your server. "],
                [boosterrole, "Booster Roles", "💎", "The following slash commands are for rewarding your server boosters with customizable roles and thank-you messages. When a member boosts the server, the bot will automatically send a personalized thank-you message in a designated channel, and the booster can create a custom role. Use </boosterrole setup:1395560580391112785> to setup booster roles in your server."],
            ]
            options = []
            for item in self.lyst:
                options.append(discord.SelectOption(label=item[1], emoji=item[2]))
            super().__init__(
                placeholder="Browse All Commands",
                max_values=1,
                min_values=1,
                options=options,
                custom_id="browsecommands",
            )

    async def callback(self, interaction: discord.Interaction):
        if self.initial_author != interaction.user:
            await interaction.response.send_message("<:no:1036810470860013639> You are not the author of this command", ephemeral=True)
            return
        for item in self.lyst:
            if self.values[0] == item[1]:
                intro = discord.Embed(
                    title=f"{item[2]} {item[1]}", description=item[3], color=0xFFFF00
                )
                embed = discord.Embed(
                    description=item[0], color=discord.Color.blurple()
                )
                await interaction.response.edit_message(
                    embeds=[intro, embed], view=HelpPanel(self.list, self.initial_author)
                )
                break


class HelpPanel(discord.ui.View):
    def __init__(self, list=None, initial_author=None):
        self.list = list
        self.initial_author = initial_author
        super().__init__(timeout=300)
        inviteButton = Button(
            label="Invite",
            style=discord.ButtonStyle.link,
            url="https://discord.com/oauth2/authorize?client_id=1341929399913680968",
            # row=1,
            emoji="<a:robot:1366940845697400935>"
        )
        self.add_item(inviteButton)
        serverButton = Button(
            label="Support Server",
            style=discord.ButtonStyle.link,
            url="https://discord.gg/6sHxJBaszx",
            # row=1,
            emoji="<a:join:1366940843088543775>"
        )
        self.add_item(serverButton)
        self.add_item(Select(self.list, self.initial_author))
        
    async def on_timeout(self) -> None:
        # Disable all components
        for child in self.children:
            if isinstance(child, Button) and child.style == discord.ButtonStyle.link:
                continue
            child.disabled = True
            if isinstance(child, Select):
                child.add_option(label="Disabled due to timeout", value="X", emoji="<:no:1036810470860013639>", default=True)
                # child.placeholder = "<:no:1036810470860013639> Disabled due to timeout"
        # Update the message if it exists
        if hasattr(self, 'message'):
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass  # Message was deleted
        self.stop()


    @discord.ui.button(
        label="Overview", style=discord.ButtonStyle.blurple, custom_id="overview", row=0, emoji="<a:memo:1366940844300701714>"
    )
    async def overview(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.initial_author != interaction.user:
            await interaction.response.send_message("<:no:1036810470860013639> You are not the author of this command", ephemeral=True)
            return
        embed = discord.Embed(
            title="BrawlKit Help",
            description=f"> <a:tools:1390756351952687154> BrawlKit is a powerful utility Discord bot **designed with all Brawl Stars communities in mind**, including **easy-to-use systems** like tickets, team finder, partnerships, welcomer, and in-game milestone roles.",
            color=0x1DBCEB,
        )
        embed.add_field(
            name="<:dev:1037445830749204624> Support Server",
            value=f"Head over to our **[support server](https://discord.gg/6sHxJBaszx)** if you have any suggestions, questions or bug reports! :writing_hand:",
            inline=True,
        )
        embed.add_field(
            name="<:slash:1037445915348324505> Command Usage",
            value=f"This bot uses [slash commands](https://discord.com/blog/welcome-to-the-new-era-of-discord-apps). Type `/` or **select a category** below to see the list of available bot commands.",
            inline=True,
        )

        await interaction.response.edit_message(
            embed=embed, view=HelpPanel(self.list, self.initial_author)
        )

    @discord.ui.button(
        label="Statistics",
        style=discord.ButtonStyle.blurple,
        custom_id="statistics",
        row=0,
        emoji="<a:server:1366940847093841961>"
    )
    async def statistics(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.initial_author != interaction.user:
            await interaction.response.send_message("<:no:1036810470860013639> You are not the author of this command", ephemeral=True)
            return
        embed = discord.Embed(title="BrawlKit Discord Bot Statistics <a:server:1366940847093841961>", color=0x1DBCEB)
        mem_usage = psutil.virtual_memory()
        embed.add_field(
            name="<:info:1037445870469267638> Package Info",
            value=f"```OS - {platform.system()}\nPython - {platform.python_version()}\ndiscord.py - {discord.__version__}\nGoogle Firebase - {firebase_admin.__version__}```",
            inline=False,
        )
        ref = db.reference("/Vanity Uptime")
        status = ref.get()
        for key, value in status.items():
            uptime = value["Vanity Uptime"]
            break
        embed.add_field(
            name="<:dev:1037445830749204624>  Bot Metadata",
            value=f"""> App ID: `{interaction.client.application_id}`
> Last Reboot: <t:{uptime}:R>
> Servers Count: `{len(interaction.client.guilds)}`
> API/Bot Latency: `{int(round(interaction.client.latency * 1000, 1))}ms`""",
            inline=True,
        )
        embed.add_field(
            name="📊  Bot Process Data",
            value=f"> CPU Usage: `{psutil.cpu_percent(0.1)}%`\n> RAM Usage: `{psutil.virtual_memory()[3]/1000000000:.2f} GB`\n> Memory:  `{mem_usage.used/(1024**3):.2f}/{mem_usage.total/(1024**3):.2f} GB ({(100-mem_usage.percent):.2f}%)`",
            inline=True,
        )
        # embed.add_field(
        #     name="<:servers:1194042063369552013>  Bot Host",
        #     value=f"This bot is proudly hosted by **[MystiCraft](https://discord.gg/gADreNeYKT)** servers 24/7.",
        #     inline=False,
        # )

        await interaction.response.edit_message(embed=embed, view=HelpPanel(self.list, self.initial_author))


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="View all the bot's commands")
    @app_commands.guild_only()
    async def help(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        list = await self.bot.tree.fetch_commands()

        embed = discord.Embed(
            title="BrawlKit Help",
            description=f"> <a:tools:1390756351952687154> BrawlKit is a powerful utility Discord bot **designed with all Brawl Stars communities in mind**, including **easy-to-use systems** like tickets, team finder, partnerships, welcomer, and in-game milestone roles.",
            color=0x1DBCEB,
        )
        embed.add_field(
            name="<:dev:1037445830749204624> Support Server",
            value=f"Head over to our **[support server](https://discord.gg/6sHxJBaszx)** if you have any suggestions, questions or bug reports! :writing_hand:",
            inline=True,
        )
        embed.add_field(
            name="<:slash:1037445915348324505> Command Usage",
            value=f"This bot uses [slash commands](https://discord.com/blog/welcome-to-the-new-era-of-discord-apps). Type `/` or **select a category** below to see the list of available bot commands.",
            inline=True,
        )

        view = HelpPanel(list, interaction.user)
        message = await interaction.followup.send(embed=embed, view=view)
        view.message = message


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))

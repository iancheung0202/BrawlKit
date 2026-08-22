import discord
import os
import firebase_admin
import datetime
import time
import asyncio
import sys
import importlib
import logging
import pytz

from discord.ext import commands
from firebase_admin import credentials, db
from dotenv import load_dotenv
load_dotenv()

from brawl.TeamFinder.teamFind import TeamFindView, TeamFindButtonViewSystem
from brawl.Partnership.partnershipSystem import PartnerRequestButtonView
from brawl.Verify.verify import VerificationEmbedView, IconChangeView
from brawl.Currency.currency import StaffInfoView, AcceptRejectView, ReloadView
from brawl.Currency.levels import LevelRewardInfoView

def import_from_parent(module_name, path):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    file_path = os.path.join(parent_dir, path)
    
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

cred = credentials.Certificate("./assets/fischl-beta-firebase-adminsdk-pir1k-798a85c249.json")
default_app = firebase_admin.initialize_app(cred, {"databaseURL": "https://fischl-beta-default-rtdb.firebaseio.com"})

class BrawlProfile(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        intents.presences = False
        super().__init__(
            command_prefix="b!",
            intents=intents,
            application_id=1341929399913680968,
            help_command=None,
            member_cache_flags=discord.MemberCacheFlags.none(),
            chunk_guilds_at_startup=False,
        )

    async def setup_hook(self):
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        for directory in ["brawl", "../Fischl/shared/Utility", "../Fischl/shared/Tickets", "../Fischl/shared/Boosters", "../Fischl/shared/Welcome"]:
            for path, _, files in os.walk(directory):
                for name in files:
                    if name.endswith(".py"):
                        full_path = os.path.join(path, name)
                        normalized_path = os.path.normpath(full_path)
                        extension = normalized_path.replace(os.sep, ".")[:-3]
                        extension = extension.lstrip(".")
                        await self.load_extension(extension)
                        print(f"Loaded {extension} for {self.user}")
        await brawl.tree.sync()

        ticket = import_from_parent("tickets", "Fischl/shared/Tickets/tickets.py")

        currency_cog = self.get_cog('CurrencySystem')
        if currency_cog:
            self.add_view(currency_cog.DailyPanelView(currency_cog))
            self.add_view(currency_cog.InformationView(currency_cog))
            self.add_view(currency_cog.InsuranceView(currency_cog))

        all_views = [
            TeamFindView, 
            TeamFindButtonViewSystem, 
            PartnerRequestButtonView, 
            VerificationEmbedView, 
            IconChangeView, 
            StaffInfoView, 
            AcceptRejectView,
            LevelRewardInfoView,
            ticket.CloseTicketButton, 
            ticket.TicketAdminButtons, 
            ticket.ConfirmCloseTicketButtons, 
            ticket.CreateTicketButtonView, 
            ticket.SelectView
        ]
        for view in all_views: 
            self.add_view(view())
        
        self.add_view(ReloadView(self.get_cog('MegaPass') or self.get_cog('megapass')))

    async def logging(self):
        def pacific_time_converter(*args):
            utc_dt = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=pytz.utc)
            pacific_dt = utc_dt.astimezone(pytz.timezone("America/Los_Angeles"))
            return pacific_dt.timetuple()

        logging.Formatter.converter = pacific_time_converter
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        file_handler = logging.FileHandler("console_output.log")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])

        class PrintLogger:
            def __init__(self):
                self.stdout = sys.stdout

            def write(self, message):
                if message.strip():
                    logging.info(message.strip())

            def flush(self):
                pass

        sys.stdout = PrintLogger()

        def log_uncaught_exceptions(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                # Don't log keyboard interruptions
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

        sys.excepthook = log_uncaught_exceptions

    async def status_task(self):
        timeout = 5
        while True:
            await asyncio.sleep(timeout)
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.Activity(
                    type=discord.ActivityType.playing, name="Brawl Stars"
                ),
            )
            await asyncio.sleep(timeout)
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.Activity(
                    type=discord.ActivityType.listening, name="Bad Randoms"
                ),
            )

    async def on_ready(self):
        print(f"{self.user} has connected to Discord! ({self.user.id})")
        self.loop.create_task(self.status_task())

        chn = self.get_channel(1036314355169513482)
        ref = db.reference("/Vanity Uptime")
        status = ref.get()
        if status:
            for key, value in status.items():
                db.reference("/Vanity Uptime").child(key).delete()
                break
        new = int(float(time.mktime(datetime.datetime.now().timetuple())))
        data = {
            "Vanity Uptime": {
                "Vanity Uptime": new,
            }
        }
        for key, value in data.items():
            ref.push().set(value)
        embed = discord.Embed(
            title="<a:online:1417419326582947860> Bot Online",
            description=f"**Date:** <t:{new}:D>\n**Time:** <t:{new}:t>\n\n**Servers in:** {len(self.guilds)}\n**Discord Version:** {discord.__version__}",
            colour=0x7BE81B,
        )
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        await chn.send(embed=embed)

brawl = BrawlProfile()

# loop = asyncio.get_event_loop()
# task1 = loop.create_task(
#     bot.start(
#         ""
#     )
# )
# task2 = loop.create_task(
#     brawl.start(
#         ""
#     )
# )
# gathered = asyncio.gather(task1, task2)
# loop.run_until_complete(gathered)

brawl.run(os.environ.get("BOT_TOKEN"))

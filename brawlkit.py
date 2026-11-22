import asyncio
import datetime
import importlib
import os
import sys
import time

import discord
import firebase_admin
from discord.ext import commands
from dotenv import load_dotenv
from firebase_admin import credentials, db

load_dotenv()

from brawl.Currency.levels import LevelRewardInfoView
from brawl.Currency.staff import AcceptRejectView, StaffInfoView
from brawl.Partnership.partnershipSystem import RequestView as PartnerRequestView
from brawl.TeamFinder.teamFind import PanelView, RequestView
from brawl.Verify.verify import IconChangeView, VerificationEmbedView


def import_from_parent(module_name, path):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    file_path = os.path.join(parent_dir, path)

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cred = credentials.Certificate(
    "./assets/fischl-beta-firebase-adminsdk-pir1k-798a85c249.json"
)
default_app = firebase_admin.initialize_app(
    cred, {"databaseURL": "https://fischl-beta-default-rtdb.firebaseio.com"}
)


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

        for directory in [
            "brawl",
            "../Fischl/shared/Utility",
            "../Fischl/shared/Tickets",
            "../Fischl/shared/Boosters",
            "../Fischl/shared/Welcome",
        ]:
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

        daily = self.get_cog("Daily")
        brewing = self.get_cog("Brewing")
        self.add_view(daily.DailyPanelView(daily))
        self.add_view(daily.InformationView(daily))
        self.add_view(brewing.InsuranceView(brewing))

        all_views = [
            RequestView,
            PanelView,
            PartnerRequestView,
            VerificationEmbedView,
            IconChangeView,
            StaffInfoView,
            AcceptRejectView,
            LevelRewardInfoView,
            ticket.CloseTicketButton,
            ticket.TicketAdminButtons,
            ticket.ConfirmCloseTicketButtons,
            ticket.CreateTicketButtonView,
            ticket.SelectView,
        ]
        for view in all_views:
            self.add_view(view())

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

brawl.run(os.environ.get("BOT_TOKEN"))

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.update(
    BRAWL_STARS_API_KEY="test",
    DATABASE_URL="postgres://test",
)


class Ref:
    def __init__(self, tree, path):
        self.tree, self.path = tree, path.strip("/")

    def child(self, key):
        return Ref(self.tree, f"{self.path}/{key}")

    def get(self):
        prefix = self.path + "/"
        if self.path in self.tree:
            return self.tree[self.path]
        found = {}
        for path, value in self.tree.items():
            if path.startswith(prefix):
                node = found
                *parents, leaf = path[len(prefix) :].split("/")
                for parent in parents:
                    node = node.setdefault(parent, {})
                node[leaf] = value
        return found or None

    def set(self, value):
        self.delete()
        if isinstance(value, dict):
            for key, item in value.items():
                self.child(key).set(item)
        elif value is not None:
            self.tree[self.path] = value

    def update(self, value):
        for key, item in value.items():
            self.child(key).set(item)

    def delete(self):
        for path in list(self.tree):
            if path == self.path or path.startswith(self.path + "/"):
                del self.tree[path]

    def push(self):
        return self.child(f"key{len(self.tree)}")


COGS = {
    "currency": "CurrencySystem",
    "balance": "Balance",
    "pagination": "Leaderboard",
    "brewing": "Brewing",
    "shop": "Shop",
    "gambling": "Gambling",
    "daily": "Daily",
    "quests": "QuestAdmin",
    "stampcard": "StampCard",
    "gacha": "Gacha",
    "factions": "TableSystem",
}


class Cafe:
    def __init__(self, tree):
        import importlib

        self.tree = tree
        self.cogs = {}
        self.bot = MagicMock()
        self.bot.get_cog = self.cogs.get
        self.bot.loop.create_task = lambda coroutine: coroutine.close()
        for module, name in COGS.items():
            cog = getattr(importlib.import_module(f"brawl.Currency.{module}"), name)
            self.cogs[name] = cog(self.bot)
        self.cogs["Leveling"] = MagicMock(level_of=AsyncMock(return_value=99))
        self.cogs["Leveling"].pool = None

    def ref(self, path):
        return Ref(self.tree, path)

    def interaction(self, user_id=1):
        from brawl.Currency.helper import MAIN_GUILD_ID

        interaction = MagicMock()
        interaction.client = self.bot
        interaction.response = AsyncMock()
        interaction.response.is_done = MagicMock(return_value=False)
        interaction.followup = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        interaction.original_response = AsyncMock()
        interaction.guild.id = MAIN_GUILD_ID
        interaction.guild.get_role.return_value = None
        interaction.user.id = user_id
        interaction.user.roles = []
        return interaction


def chat_quests(duration, level=0):
    return {"chat_earnings": {"current": 0, "goal": 100000}}


@pytest.fixture
def cafe():
    tree = {}
    with (
        patch("firebase_admin.db.reference", lambda path="": Ref(tree, path)),
        patch("brawl.Currency.quests.generate_quests", chat_quests),
    ):
        yield Cafe(tree)


@pytest.fixture(autouse=True)
def clocked_in(request, monkeypatch):
    """Most tests start after clock in; mark a test `before_clock_in` to start earlier."""
    if not request.node.get_closest_marker("before_clock_in"):
        from brawl.Currency import quests

        monkeypatch.setattr(quests, "clocked_in", lambda user_id: True)


def pytest_configure(config):
    config.addinivalue_line("markers", "before_clock_in: the member has not clocked in")

from unittest.mock import MagicMock

import pytest

from brawl.Currency.currency import CurrencySystem
from brawl.Currency.invitetracker import InviteTracker
from brawl.Currency.levels import LevelingAdmin
from brawl.Currency.quests import QuestAdmin

COMMANDS = [
    CurrencySystem.add,
    QuestAdmin.update_quest_cmd,
    InviteTracker.add_invites,
    LevelingAdmin(MagicMock()).app_command,
]


@pytest.mark.parametrize("command", COMMANDS, ids=lambda command: command.name)
def test_admin_commands_are_hidden_from_members(command):
    assert command.default_permissions.administrator

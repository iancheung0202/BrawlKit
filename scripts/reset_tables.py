"""One-off: start every table's week again without paying the top table."""

import json
import sys
import time

sys.path.insert(0, ".")
import brawlkit  # noqa: F401, E402
from brawl.Currency.db import g_table_reset, g_tables  # noqa: E402
from brawl.Currency.helper import MAIN_GUILD_ID  # noqa: E402

tables = g_tables(MAIN_GUILD_ID).get() or {}
print(json.dumps(tables))
if "--apply" in sys.argv:
    g_table_reset(MAIN_GUILD_ID).set(time.time())
    for name in tables:
        g_tables(MAIN_GUILD_ID, name).update(
            {
                "weekly_beans": 0,
                "user_contributions": {},
                "quest": {
                    "type": "bean_collector",
                    "current_tier": 0,
                    "completed_tiers": [],
                    "progress": 0,
                    "start_time": time.time(),
                },
            }
        )
print(
    f"{len(tables)} tables {'reset' if '--apply' in sys.argv else 'found'}",
    file=sys.stderr,
)

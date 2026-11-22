import sys

from firebase_admin import db

sys.path.insert(0, ".")
import brawlkit  # noqa: F401, E402

users = db.reference("Cafe Economy").get() or {}
marked = 0
for user_id, data in users.items():
    brews = (data.get("inventory") or {}).get("brews") or {}
    if (brews.get("stats") or {}).get("total_brews", 0) < 1:
        continue
    if "--apply" in sys.argv:
        db.reference(f"Cafe Economy/{user_id}/progress/veteran").set(True)
    marked += 1
print(f"{marked} of {len(users)} members have brewed before")

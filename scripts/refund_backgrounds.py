import os
import sys

from firebase_admin import db

sys.path.insert(0, ".")
import brawlkit  # noqa: F401, E402

FOLDER = "assets/Balance Backgrounds"
refunded = 0
for name in sorted(os.listdir(FOLDER)):
    user_id = name.removesuffix(".png")
    if not user_id.isdigit():
        continue
    ref = db.reference(f"Cafe Economy/{user_id}/settings/customization")
    data = ref.get() or {}
    if data.get("refunded"):
        continue
    if "--apply" in sys.argv:
        ref.update({"credits": data.get("credits", 0) + 1, "refunded": True})
    refunded += 1
print(f"{refunded} members get 1 Customization Credit back")

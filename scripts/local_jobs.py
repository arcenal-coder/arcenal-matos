"""Run local beta reminders without configuring a system-wide service."""
import os
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if os.environ.get("MATOS_DEBUG") != "1" or os.environ.get("MATOS_DEV_LOGIN") != "1":
    raise RuntimeError("Ce worker est réservé à la bêta locale.")
while True:
    result = subprocess.run([str(root / ".venv/bin/python"), "manage.py", "run_jobs"], cwd=root, check=False)
    if result.returncode:
        print("Travaux locaux en échec ; nouvelle tentative dans cinq minutes.", flush=True)
    time.sleep(300)

"""Stop only the local beta processes recorded by this project."""
import os
import signal
import subprocess
from pathlib import Path

runtime = Path(__file__).resolve().parent.parent / ".local"
for file, signature in (("beta.pid", "matos.asgi:application --host 127.0.0.1 --port 8765"),
                        ("jobs.pid", "scripts/local_jobs.py")):
    path = runtime / file
    if not path.exists():
        continue
    pid = int(path.read_text())
    process = subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True)
    if process.returncode == 0 and signature in process.stdout:
        os.kill(pid, signal.SIGTERM)
        print(f"Processus local arrêté : {file}.")
    elif process.returncode == 0:
        raise RuntimeError(f"Le PID de {file} correspond à un autre processus ; arrêt refusé.")

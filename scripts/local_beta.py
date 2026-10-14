#!/usr/bin/env python3
"""Start the loopback-only preview using isolated development credentials."""
import json
import os
import runpy
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent.parent
runtime = root / ".local"
runtime.mkdir(exist_ok=True)
credentials_path = runtime / "credentials.json"
if not credentials_path.exists():
    descriptor = os.open(credentials_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"secret_key": secrets.token_urlsafe(48), "mcp_token": secrets.token_urlsafe(48)}, handle)
credentials = json.loads(credentials_path.read_text())
env = os.environ | {"MATOS_DEBUG": "1", "MATOS_DEV_LOGIN": "1",
                    "MATOS_YNH_PORTAL_URL": "https://onyx-ingenierie.com",
                    "MATOS_TRUST_YNH_HEADERS": "0", "MATOS_SECRET_KEY": credentials["secret_key"],
                    "MATOS_MCP_TOKEN": credentials["mcp_token"], "MATOS_PUBLIC_URL": "http://127.0.0.1:8765"}
python = root / ".venv" / "bin" / "python"
for command in (["migrate", "--noinput"], ["init_local"], ["refresh_branding"], ["collectstatic", "--noinput"]):
    subprocess.run([str(python), "manage.py", *command], cwd=root, env=env, check=True)
with socket.socket() as sock:
    if sock.connect_ex(("127.0.0.1", 8765)) == 0:
        print("Le port 8765 est déjà actif ; aucun second serveur lancé.")
        sys.exit(0)
with (runtime / "beta.log").open("ab") as log:
    process = subprocess.Popen([str(python), "-m", "uvicorn", "matos.asgi:application", "--host", "127.0.0.1", "--port", "8765"],
                               cwd=root, env=env, stdout=log, stderr=log, start_new_session=True)
(runtime / "beta.pid").write_text(str(process.pid))
for _ in range(100):
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 8765)) == 0:
            break
    if process.poll() is not None:
        raise RuntimeError("Le serveur n'a pas démarré ; consulter .local/beta.log.")
    time.sleep(0.1)
else:
    process.terminate()
    raise RuntimeError("Le serveur n'est pas devenu disponible dans le délai prévu.")
with (runtime / "jobs.log").open("ab") as log:
    worker = subprocess.Popen([str(python), "scripts/local_jobs.py"], cwd=root, env=env,
                              stdout=log, stderr=log, start_new_session=True)
(runtime / "jobs.pid").write_text(str(worker.pid))
version = runpy.run_path(str(root / "matos/version.py"))["VERSION"]
print(f"Version locale {version} : http://127.0.0.1:8765/ · profils d'essai sur la page de connexion.")
print("Identifiants MCP locaux : .local/credentials.json (hors Git).")

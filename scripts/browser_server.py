#!/usr/bin/env python3
"""Run browser acceptance on a separate, disposable local database."""
import os
import secrets
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql

root = Path(__file__).resolve().parent.parent
database = "arcenal_matos_browser"
env = os.environ | {"PGDATABASE": database, "MATOS_DEBUG": "1", "MATOS_DEV_LOGIN": "1",
                    "MATOS_TRUST_YNH_HEADERS": "0", "MATOS_SECRET_KEY": secrets.token_urlsafe(48),
                    "MATOS_MCP_TOKEN": secrets.token_urlsafe(48), "MATOS_PUBLIC_URL": "http://127.0.0.1:8766"}
with psycopg.connect(dbname="postgres", user=env.get("PGUSER", env["USER"]), host=env.get("PGHOST", "127.0.0.1"),
                     port=env.get("PGPORT", "55432"), autocommit=True) as connection:
    if not connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", [database]).fetchone():
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
python = root / ".venv/bin/python"
for command in (["migrate", "--noinput"], ["flush", "--noinput"], ["init_local"], ["collectstatic", "--noinput"]):
    subprocess.run([str(python), "manage.py", *command], cwd=root, env=env, check=True)
os.chdir(root)
os.execve(str(python), [str(python), "-m", "uvicorn", "matos.asgi:application", "--host", "127.0.0.1", "--port", "8766"], env)

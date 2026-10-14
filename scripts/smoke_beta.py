"""Verify the running local beta without adding equipment or revealing credentials."""
import asyncio
import json
import re
import runpy
from pathlib import Path

import httpx
import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

root = Path(__file__).resolve().parent.parent
version = runpy.run_path(str(root / "matos/version.py"))["VERSION"]
url = "http://127.0.0.1:8765"
with httpx.Client(base_url=url, follow_redirects=True) as client:
    page = client.get("/login/")
    page.raise_for_status()
    selected = re.search(r'<option value="(\d+)">Administrateur', page.text)
    if not selected:
        raise RuntimeError("Profil d'essai administrateur absent")
    client.post("/login/", data={"user": selected.group(1), "csrfmiddlewaretoken": client.cookies["csrftoken"]}).raise_for_status()
    assert client.cookies.get("sessionid")
    assert "Tableau de bord" in client.get("/").text
    assert version in client.get("/").text
    for path in ("/", "/inventory/", "/settings/", "/integration/", "/scan/", "/static/scan.bundle.js", "/static/theme.js", "/static/fonts/inter-latin-400-normal.woff2"):
        response = client.get(path)
        response.raise_for_status()
        if "Connexion" in response.text[:300] and path != "/static/scan.bundle.js":
            raise RuntimeError(f"Session absente pour {path}")
    config = yaml.safe_load(client.get("/integration/?download=1").content)
    assert config["mcp"]["endpoint"] == url + "/mcp"
    assert "token" not in config["mcp"]["authentication"]
    assert client.get("/reports/?format=pdf").content.startswith(b"%PDF")
    print(f"HTTP {version} : connexion d'essai, écrans, Gratitude/Inter, scan embarqué, YAML et PDF vérifiés.")


async def mcp_smoke():
    credential = json.loads((root / ".local/credentials.json").read_text())["mcp_token"]
    async with httpx.AsyncClient(headers={"Authorization": "Bearer " + credential}) as client:
        async with streamable_http_client(url + "/mcp", http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                negotiated = await session.initialize()
                tools = (await session.list_tools()).tools
                result = await session.call_tool("list_assets", {})
                assert not result.isError
                print(f"MCP {version} : initialisation {negotiated.protocolVersion}, {len(tools)} outils, lecture authentifiée vérifiée.")


asyncio.run(mcp_smoke())

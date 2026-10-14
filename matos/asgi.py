import os
import secrets
from contextlib import asynccontextmanager

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "matos.settings")
from django.core.asgi import get_asgi_application  # noqa: E402

django_app = get_asgi_application()
from django.conf import settings  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.responses import JSONResponse  # noqa: E402
from starlette.routing import Mount  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from core.mcp_server import build_server  # noqa: E402

mcp_server = build_server(settings.MCP_ALLOWED_HOSTS, settings.MCP_ALLOWED_ORIGINS)
mcp_http = mcp_server.streamable_http_app()


@asynccontextmanager
async def lifespan(app):
    async with mcp_server.session_manager.run():
        yield


web = Starlette(routes=[
    Mount("/static", StaticFiles(directory=settings.STATIC_ROOT if settings.STATIC_ROOT.exists() else settings.BASE_DIR / "static")),
    Mount("/", django_app),
], lifespan=lifespan)


async def application(scope, receive, send):
    if scope["type"] == "http" and scope["path"].rstrip("/") == "/mcp":
        headers = dict(scope["headers"])
        authorization = headers.get(b"authorization", b"")
        expected = ("Bearer " + settings.MCP_TOKEN).encode("utf-8")
        if not settings.MCP_TOKEN:
            await JSONResponse({"error": "MCP non configuré"}, status_code=503)(scope, receive, send)
        elif not secrets.compare_digest(authorization, expected):
            await JSONResponse({"error": "Authentification de l'agent requise"}, status_code=401,
                               headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
        else:
            await mcp_http(scope, receive, send)
    else:
        await web(scope, receive, send)

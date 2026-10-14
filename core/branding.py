"""Cache the public YunoHost portal identity; never cache portal credentials."""
import io
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from PIL import Image


def directory():
    return Path(settings.MEDIA_ROOT) / "branding"


def has_logo():
    return (directory() / "logo.png").is_file()


def refresh(force=False):
    origin = settings.YNH_PORTAL_URL.rstrip("/")
    if not origin:
        return False
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/"):
        raise ValueError("MATOS_YNH_PORTAL_URL doit être une origine HTTPS sans identifiant.")
    cache = directory()
    marker = cache / "public.json"
    if not force and marker.exists() and time.time() - marker.stat().st_mtime < 3600:
        return has_logo()

    def read(url, limit):
        request = Request(url, headers={"User-Agent": "ARCenal-Matos-branding/1"})
        with urlopen(request, timeout=10) as response:
            if urlsplit(response.url).hostname != parsed.hostname:
                raise ValueError("Redirection du portail vers une autre origine refusée.")
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError("La personnalisation YunoHost dépasse la taille autorisée.")
            return data

    public = json.loads(read(origin + "/yunohost/portalapi/public", 262144))
    filename = public.get("portal_logo")
    if filename and not re.fullmatch(r"[a-zA-Z0-9_-]{1,160}\.(png|jpe?g|webp|gif)", filename, re.IGNORECASE):
        raise ValueError("Format du logo YunoHost non pris en charge.")
    cache.mkdir(parents=True, exist_ok=True)
    if filename:
        raw = read(origin + "/yunohost/sso/customassets/" + filename, 2 * 1024 * 1024)
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 4000000:
                raise ValueError("Dimensions du logo excessives.")
            output = io.BytesIO()
            image.convert("RGBA").save(output, format="PNG")
        temporary = cache / "logo.tmp"
        temporary.write_bytes(output.getvalue())
        temporary.replace(cache / "logo.png")
    elif (cache / "logo.png").exists():
        (cache / "logo.png").unlink()
    temporary = cache / "public.tmp"
    temporary.write_text(json.dumps({"portal_title": str(public.get("portal_title", ""))[:200],
                                     "portal_logo": filename, "origin": origin}))
    temporary.replace(marker)
    return has_logo()

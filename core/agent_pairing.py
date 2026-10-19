"""Client of the co-hosted assistance v1 contract; no business action transport."""
import hmac
import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError

from .models import AssistanceSettings, User


class PairingUnavailable(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def configuration():
    from .agent_links import validate_destination
    try:
        config = json.loads((settings.BASE_DIR / ".assistance.json").read_text())
        if set(config) != {"application", "key", "service_url", "sso_url"} or config["application"] != "arcenal-matos" or len(config["key"]) < 43:
            return None
        for name in ("service_url", "sso_url"):
            validate_destination(config[name])
            if not config[name].startswith("https://"):
                return None
        return config
    except (OSError, ValueError, TypeError, ValidationError):
        return None


def exchange(operation, **values):
    config = configuration()
    if not config:
        raise PairingUnavailable("ARCenal Agent compatible non détecté sur ce serveur.")
    data = {"application": config["application"], "operation": operation, **values}
    request = Request(config["service_url"], json.dumps(data).encode(),
        {"Authorization": "Bearer " + config["key"], "Content-Type": "application/json"})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=3) as response:
            result = json.loads(response.read(4097))
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (URLError, OSError, ValueError):
        raise PairingUnavailable("La liaison n’a pas pu être vérifiée. Réessayez lorsque les deux applications sont disponibles.") from None


def local_pair():
    return AssistanceSettings.objects.filter(pk=1).values_list("pair_id", flat=True).first() or ""


def management_url():
    config, pair = configuration(), local_pair()
    return config["sso_url"] + "?" + urlencode({"pair": pair}) if config and pair else ""


def status():
    if not configuration():
        return "unavailable"
    pair = local_pair()
    if not pair:
        return "disconnected"
    try:
        state = exchange("status", pair_id=pair).get("state")
        return state if state in ("active", "pending", "revoked", "expired") else "unavailable"
    except PairingUnavailable:
        return "unavailable"


def pair():
    result = exchange("pair")
    pair_id = result.get("pair_id", "")
    if result.get("state") != "pending" or not isinstance(pair_id, str) or len(pair_id) != 43:
        raise PairingUnavailable("Réponse d’appariement invalide.")
    AssistanceSettings.objects.update_or_create(pk=1, defaults={"pair_id": pair_id})
    return configuration()["sso_url"] + "?" + urlencode({"pair": pair_id})


def revoke():
    pair_id = local_pair()
    # Local revocation is immediate even if the central service is offline.
    AssistanceSettings.objects.filter(pk=1).update(pair_id="")
    if pair_id:
        exchange("revoke", pair_id=pair_id)


def open_assistance(user, agent):
    from .agent_links import context_for
    context_for(user, agent)
    if status() != "active":
        raise PairingUnavailable("La liaison doit être validée dans les deux applications.")
    pair_id = local_pair()
    ticket = signing.dumps({"user": user.username, "module": agent, "pair_id": pair_id}, salt="assistance-v1")
    result = exchange("request", pair_id=pair_id, user=user.username, ticket=ticket)
    reference = result.get("reference", "")
    if not isinstance(reference, str) or len(reference) != 43 or not all(c.isalnum() or c in "-_" for c in reference):
        raise PairingUnavailable("Référence d’assistance invalide.")
    return configuration()["sso_url"] + "?" + urlencode({"reference": reference})


def verify(authorization, payload):
    from .agent_links import context_for
    config = configuration()
    if not config or not hmac.compare_digest(authorization, "Bearer " + config["key"]):
        raise PermissionDenied
    if not isinstance(payload, dict) or set(payload) != {"ticket", "user", "pair_id"}:
        raise PermissionDenied
    try:
        data = signing.loads(payload["ticket"], salt="assistance-v1", max_age=60)
        if data["pair_id"] != local_pair() or data["pair_id"] != payload["pair_id"] or data["user"] != payload["user"]:
            raise PermissionDenied
        user = User.objects.get(username=data["user"], is_active=True)
        context = context_for(user, data["module"])
        return {"application": context.application, "user": user.username, "intention": context.intention,
            "resource_type": context.resource_type, "resource_id": context.resource_id}
    except (signing.BadSignature, KeyError, TypeError, ValueError, User.DoesNotExist):
        raise PermissionDenied from None

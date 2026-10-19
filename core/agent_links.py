"""Read-only SSO navigation; no central action connector or context exchange."""
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from .models import AssistanceSettings
from .modules import preferences
from .permissions import require

AGENTS = {
    "materiel": {"title": "Matériel", "module": None, "summary": "Demander de l’aide pour comprendre l’inventaire et ses parcours."},
    "epi": {"title": "EPI", "module": "epi", "summary": "Demander de l’aide pour comprendre les stocks, dotations et validités EPI."},
    "dosimetres": {"title": "Dosimètres passifs", "module": "dosimeters", "summary": "Demander de l’aide pour la logistique des badges et périodes de port."},
}


def validate_destination(value):
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) > 500 or any(character.isspace() or ord(character) < 32 for character in value) or any(character in value for character in "\\%?#"):
        raise ValidationError("Indiquez l’entrée publique SSO, sans paramètre, fragment ou donnée de connexion.")
    try:
        parsed = urlsplit(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError
        if value.startswith("/") and not value.startswith("//") and not parsed.netloc and not parsed.scheme:
            return value
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError
        URLValidator(schemes=["https"])(value)
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ValueError
        try:
            loopback = ip_address(hostname).is_loopback
        except ValueError:
            loopback = False
        if loopback:
            raise ValueError
    except (ValueError, ValidationError):
        raise ValidationError("Utilisez un chemin SSO publié sous le même domaine ou une URL HTTPS publique, pas localhost dans le navigateur.") from None
    return value


def destination():
    from . import agent_pairing
    automatic = agent_pairing.configuration()
    if automatic:
        return automatic["sso_url"] if agent_pairing.status() == "active" else ""
    config = AssistanceSettings.objects.filter(pk=1).first()
    try:
        return validate_destination(config.sso_url if config else "")
    except ValidationError:
        return ""


def agent_cards():
    config, target = preferences(), destination()
    return [{"id": key, "title": item["title"], "summary": item["summary"],
             "module_enabled": item["module"] is None or bool(getattr(config, f'{item["module"]}_enabled')),
             "ready": bool(target)} for key, item in AGENTS.items()]


@dataclass(frozen=True)
class AssistanceContext:
    application: str
    user_id: int
    intention: str
    resource_type: str
    resource_id: str


def context_for(user, agent_id):
    require(user, ("admin", "manager", "member"))
    card = AGENTS.get(agent_id)
    if not card or (card["module"] and not getattr(preferences(), f'{card["module"]}_enabled')):
        raise KeyError(agent_id)
    return AssistanceContext("arcenal-matos", user.pk, "read_only_help", "module", agent_id)

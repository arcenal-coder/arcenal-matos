from django.core.exceptions import ValidationError

from .models import ModuleSettings


def preferences():
    return ModuleSettings.objects.filter(pk=1).first() or ModuleSettings(pk=1)


def enabled(module):
    if module not in ("epi", "dosimeters"):
        return False
    return bool(getattr(preferences(), f"{module}_enabled"))


def require_enabled(module):
    if not enabled(module):
        raise ValidationError("Ce module est désactivé dans Paramètres → Modules.")

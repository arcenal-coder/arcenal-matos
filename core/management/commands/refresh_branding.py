from django.core.management.base import BaseCommand

from core import branding


class Command(BaseCommand):
    help = "Mettre en cache le logo public de l'organisation configuré dans YunoHost."

    def handle(self, *args, **options):
        try:
            available = branding.refresh(force=True)
        except (OSError, ValueError):
            self.stdout.write("Personnalisation YunoHost temporairement indisponible ; cache/logo de secours conservé.")
            return
        if available:
            self.stdout.write("Logo public YunoHost mis en cache.")
        else:
            self.stdout.write("Logo ARCenal de secours actif.")

from django.core.management.base import BaseCommand

from core import branding
from core.mcp_server import agent
from core.services import reminders, send_outbox


class Command(BaseCommand):
    help = "Produire les rappels et expédier les messages validés/en attente."

    def handle(self, *args, **options):
        try:
            branding.refresh()
        except (OSError, ValueError):
            self.stderr.write("Personnalisation YunoHost temporairement indisponible ; cache conservé.")
        reminders(agent())
        self.stdout.write(f"{send_outbox()} message(s) accepté(s) par le transport e-mail.")

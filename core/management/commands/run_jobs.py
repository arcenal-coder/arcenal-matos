from django.core.management.base import BaseCommand

from core import branding
from core.mcp_server import agent
from core.services import reminders, send_outbox
from dosimetry.services import reminders as dosimetry_reminders
from epi.services import reminders as epi_reminders


class Command(BaseCommand):
    help = "Produire les rappels et expédier les messages validés/en attente."

    def handle(self, *args, **options):
        try:
            branding.refresh()
        except (OSError, ValueError):
            self.stderr.write("Personnalisation YunoHost temporairement indisponible ; cache conservé.")
        reminders(agent())
        epi_reminders()
        dosimetry_reminders()
        self.stdout.write(f"{send_outbox()} message(s) accepté(s) par le transport e-mail.")

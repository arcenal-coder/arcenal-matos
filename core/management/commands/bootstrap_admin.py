from django.core.management.base import BaseCommand, CommandError

from core.models import User


class Command(BaseCommand):
    help = "Attribuer l'administration à une identité YunoHost choisie à l'installation."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        username = options["username"]
        if not username or username.startswith("__"):
            raise CommandError("Identité humaine invalide")
        user, _ = User.objects.get_or_create(username=username)
        if user.role == "agent":
            raise CommandError("L'identité technique ne peut être administrateur")
        user.role = "admin"
        user.save()
        self.stdout.write("Administrateur YunoHost configuré, sans mot de passe local.")

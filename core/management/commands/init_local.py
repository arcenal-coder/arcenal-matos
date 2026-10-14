from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Category, Site, User


class Command(BaseCommand):
    help = "Créer uniquement les profils/sites fictifs de l'environnement local ; inventaire vide."

    def handle(self, *args, **options):
        if not settings.DEBUG or not settings.DEV_LOGIN:
            raise CommandError("Cette commande est réservée à l'environnement local d'essai.")
        headquarters, _ = Site.objects.get_or_create(name="Siège (essai)")
        workshop, _ = Site.objects.get_or_create(name="Atelier (essai)")
        Category.objects.get_or_create(name="Matériel général", defaults={"interval_days": 365})
        for username, label, role, site in [
            ("admin", "Administrateur d'essai", "admin", headquarters),
            ("gestionnaire", "Gestionnaire Siège", "manager", headquarters),
            ("gestionnaire_atelier", "Gestionnaire Atelier", "manager", workshop),
            ("collaborateur", "Collaborateur d'essai", "member", headquarters),
        ]:
            user, created = User.objects.get_or_create(username=username, defaults={
                "first_name": label, "role": role, "site": site, "email": f"{username}@example.invalid"})
            if created and role == "manager":
                user.managed_sites.add(site)
        self.stdout.write("Profils fictifs disponibles ; aucun matériel ajouté automatiquement.")

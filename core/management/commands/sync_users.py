import os

from django.core.management.base import BaseCommand, CommandError
from ldap3 import Connection, Server
from ldap3.utils.conv import escape_filter_chars

from core.models import User


class Command(BaseCommand):
    help = "Synchroniser les références d'identités autorisées depuis le LDAP local YunoHost."

    def handle(self, *args, **options):
        app = os.environ.get("MATOS_YNH_APP")
        if not app:
            raise CommandError("MATOS_YNH_APP doit contenir l'identifiant de l'application YunoHost.")
        connection = Connection(Server("127.0.0.1", port=389), auto_bind=True)
        try:
            permission = escape_filter_chars(f"cn={app}.main,ou=permission,dc=yunohost,dc=org")
            if not connection.search("ou=users,dc=yunohost,dc=org",
                                     f"(&(objectClass=posixAccount)(permission={permission}))",
                                     attributes=["uid", "displayName", "mail"]):
                if connection.result.get("result") != 0:
                    raise CommandError("La recherche LDAP a échoué ; aucune désactivation effectuée.")
            seen = []
            for entry in connection.entries:
                username = str(entry.uid)
                seen.append(username)
                user, _ = User.objects.get_or_create(username=username)
                user.first_name = str(entry.displayName)[:150]
                user.email = str(entry.mail.values[0]) if entry.mail.values else ""
                user.is_active = True
                user.save()
            User.objects.exclude(role="agent").exclude(username__in=seen).update(is_active=False)
            self.stdout.write(f"{len(seen)} identité(s) YunoHost synchronisée(s).")
        finally:
            connection.unbind()

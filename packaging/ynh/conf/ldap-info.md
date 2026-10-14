# Intégration LDAP/SSO réelle

core/management/commands/sync_users.py lit le LDAP local sur 127.0.0.1:389,
base ou=users,dc=yunohost,dc=org, attributs uid/displayName/mail et permission
cn=<app>.main,ou=permission,dc=yunohost,dc=org. Les références sont synchronisées
à l'installation et par le timer. Aucun mot de passe applicatif n'est créé.

core/auth.py utilise l'identité YNH_USER injectée par SSOwat après nettoyage
des en-têtes clients. Nginx accède au socket Unix du service ; les utilisateurs
hors du groupe de proxy ne peuvent accéder directement au processus web.

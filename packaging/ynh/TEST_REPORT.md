# ARCenal Matos 0.1.1~ynh1 — preview

- RÉUSSI : application, 61 tests locaux et 16 parcours Chromium.
- RÉUSSI : SSO/identité de proxy et refus d'accès testés ; données PostgreSQL locales.
- RÉUSSI : logo du portail YunoHost public réel téléchargé ; absence du logo dans le paquet distribué.
- RÉUSSI : syntaxe des scripts ; analyse statique de la candidate finalisée à effectuer avant publication.
- HISTORIQUE : run 38596598439, linter et installation 0.1.0~ynh3 réussis sur YunoHost 12.1.41.2 amd64 ; contrôle web anonyme en échec (401 attendu par l'application, 200 attendu par le test implicite).
- À REVALIDER : candidate 0.1.1~ynh1 avec tests SSO/anonyme explicites et fallback branding sans traceback ; cycle de vie complet à qualifier.
- NON_EXÉCUTÉ : connexion utilisateur réelle YunoHost et délivrance SMTP sur le serveur cible ; SSH port 22 inaccessible dans cette session.
- NON_EXÉCUTÉ : profil Hermès réel et téléphones/étiquettes physiques.

Le canal preview est une distribution de recette. Il ne constitue pas une
preuve de mise en service métier ou de qualification stable.

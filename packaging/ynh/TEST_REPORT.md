# ARCenal Matos 0.1.2~ynh1 — preview qualifiée

- Application : évolutions Paramètres/saisie, identifiants automatiques et migrations 0005/0006.
- RÉUSSI : package_check 38850600554, six scénarios dont mise à jour depuis la version publiée 0.1.1~ynh5 ; paquet figé à 3d882348b212835d9adc61c54416ad72a6185c04.
- Cause du message défectueux : niveau 0 publié dans le catalogue ARCenal ; YunoHost exige un niveau >= 5 pour annoncer une mise à jour. Correction publiée avec qualification technique ARCenal 5, distincte du résultat officiel original 0 conservé dans les preuves.
- RÉUSSI : cinq tests du vérificateur, 18 tests catalogue ; PR #16 fusionnée, flux brut et Pages vérifiés en 0.1.2~ynh1/niveau 5/working.

## Preuves historiques 0.1.1~ynh5

- RÉUSSI : application, 62 tests locaux et 16 parcours Chromium.
- RÉUSSI : SSO/identité de proxy et refus d'accès testés ; données PostgreSQL locales.
- RÉUSSI : logo du portail YunoHost public réel téléchargé ; absence du logo dans le paquet distribué.
- RÉUSSI : syntaxe des scripts et analyse de la candidate par le linter officiel dans package_check.
- RÉUSSI : package_check officiel, run 38622713770 sur YunoHost 12.1.41.2 amd64, paquet b8ef047930d7c64944b83a485c2c8f13dd414794.
- RÉUSSI : linter, installation/retrait/réinstallation, SSO et refus anonyme, assets, sauvegarde/restauration après retrait et sur système vierge, upgrade même version et changement de domaine.
- Niveau communautaire conservé à 0 : paquet hors catalogue officiel YunoHost ; aucune équivalence avec une note 8 revendiquée.
- NON_EXÉCUTÉ : connexion utilisateur réelle YunoHost et délivrance SMTP sur le serveur cible ; SSH port 22 inaccessible dans cette session.
- NON_EXÉCUTÉ : profil Hermès réel et téléphones/étiquettes physiques.

Le canal preview est une distribution de recette. Il ne constitue pas une
preuve de mise en service métier ou de qualification stable.

# Rapport de contrôle — ARCenal Matos 0.1.0 preview

Statut : distribution preview, SSO/branding de production configurés ; recette réelle de plateforme à effectuer.
Date : 2026-10-14.

## Contrôles locaux

| Contrôle | Résultat | Preuve |
| --- | --- | --- |
| Linter Python | RÉUSSI | ruff check . |
| Compilation Python | RÉUSSI | compileall sur core, matos et scripts |
| Configuration Django | RÉUSSI | manage.py check ; aucun changement de migration en attente |
| Dépendances Python | RÉUSSI | pip check : aucun conflit |
| Tests applicatifs | RÉUSSI | 60 tests PostgreSQL/Django/structure, incluant branding/cache, signature, nominal, limites/refus et versions |
| Concurrence de prêts | RÉUSSI | Deux validations concurrentes : un seul gagnant |
| Autres écritures concurrentes | RÉUSSI | Import CSV concurrent : un identifiant unique ; annulation/sortie concurrentes : état cohérent |
| Remise en service humaine | RÉUSSI | Une modification de date/périodicité ne débloque pas implicitement un contrôle déjà expiré |
| Jeu 300 utilisateurs / 1 500 équipements | RÉUSSI | Catalogue intersite < 25 requêtes SQL et export CSV de 1 500 équipements ; pas une mesure de 300 utilisateurs simultanés |
| Client MCP officiel | RÉUSSI | Initialisation 2025-11-25, lecture/écriture, refus de champ protégé, authentification obligatoire, pas d'outil de validation humaine |
| Construction du scanner embarqué | RÉUSSI | npm run build, esbuild, dépendances servies localement et licences conservées |
| Parcours navigateur Chromium | RÉUSSI | 16 scénarios Playwright : 5 parcours métier conservés et 11 contrôles Gratitude/RC |
| Gratitude clair / sombre | RÉUSSI | Captures à 1440, 1024 et 390px, tokens, contrastes texte >= 4,5:1 et bordures interactives >= 3:1 ; aucun texte fonctionnel testé sous 12px |
| Préférence d'apparence | RÉUSSI | Système suit le navigateur en temps réel ; choix manuel prioritaire et conservé après rechargement |
| Accessibilité automatisée | RÉUSSI | Axe sans violation sur les écrans inventaire et formulaires en erreur testés, tags WCAG 2/2.1/2.2 A/AA ; ne vaut pas certification exhaustive |
| Clavier / compact / reflow | RÉUSSI | Focus 3px, Menu/Échap, cibles >= 44px, mouvements réduits, viewport équivalent à zoom 200 % sur écran 1440px |
| Confirmation d'annulation | RÉUSSI | Fermer le dialogue conserve la demande ; confirmer applique l'annulation et conserve le journal métier |
| Syntaxe Bash et structure TOML du paquet | RÉUSSI | Tests structuraux ; ne remplacent pas package_linter/package_check |
| Archives locales | RÉUSSI | Sources/mentions tierces, absence de runtime et secrets locaux, scripts du modèle exécutables ; fixture de finalisation conservant le SHA256 et échappant le TOML |
| RC réellement démarrée | RÉUSSI | smoke_beta.py : version RC visible, session d'essai, écrans, Gratitude/Inter locaux, YAML/PDF et MCP avec 14 outils sur port 8765 |
| Données locales au redémarrage | RÉUSSI | Aucune migration ; compteurs matériel/réservations/prêts/licences identiques avant/après ; aucun inventaire de tests injecté |

Les régressions de bêta, y compris coûts décimaux MCP et jeu 300 humains + 1 agent, ont été rejouées dans les 57 tests RC. Aucun test de caméra/NFC physique n'est assimilé à ces contrôles. Le premier contrôle Gratitude a détecté 4,469:1 pour le texte secondaire clair ; teinte corrigée à #5D6C80, puis tests rejoués avec succès.

## Paquet et services réels

| Scénario | Résultat | Motif / suite |
| --- | --- | --- |
| package_linter officiel | NON_EXÉCUTÉ | Modèle de manifest à finaliser : URL de source distribuée et licence à déclarer |
| package_check / environnement Incus | NON_EXÉCUTÉ | Aucune instance Linux/YunoHost d'essai fournie ou provisionnée |
| Installation YunoHost | NON_EXÉCUTÉ | Sources et paquet préparés localement ; aucune installation sur serveur réel |
| Retrait / réinstallation | NON_EXÉCUTÉ | À vérifier sur YunoHost d'essai |
| Mise à jour | NON_EXÉCUTÉ | À vérifier avec une version précédente et une sauvegarde complète |
| Sauvegarde / restauration YunoHost | NON_EXÉCUTÉ | Scripts préparés ; restauration réelle et cohérence documents/base à démontrer |
| SSO/LDAP réels | NON_EXÉCUTÉ | Middleware et refus testés ; identité de proxy simulée dans les tests, profils fictifs dans la bêta locale |
| SMTP réel / réception fournisseur | NON_EXÉCUTÉ | Déduplication, validation et gestion d'erreur testées ; transport local console et tests avec transport simulé |
| Connexion du profil Hermès réel | NON_EXÉCUTÉ | Serveur MCP testé avec client officiel ; export YAML ARCenal, import natif Hermès non démontré |
| Catalogue ARCenal Store | NON_EXÉCUTÉ | Contrat de catalogue et dépôt de distribution absents ; aucune promotion réalisée |
| Caméra sur téléphone physique | NON_EXÉCUTÉ | Décodeur QR vérifié sur image et viewport mobile ; permissions/caméra réelles à tester |
| Étiquettes NFC iPhone/Android | NON_EXÉCUTÉ | Parcours URL validé fonctionnellement ; appareils/étiquettes physiques non disponibles |
| Application native / RFID distant | NON_APPLICABLE_JUSTIFIÉ | Hors périmètre V1 confirmé |

## Recette proposée au client

Ouvrir la bêta locale, choisir successivement Administrateur, Gestionnaire et Collaborateur. Créer/importer du matériel, demander et valider un prêt, effectuer sortie/retour, préparer une intervention et une demande fournisseur, puis exporter rapports et YAML. Les données de tests automatisés sont isolées de l'inventaire de la bêta.

La recette cliente, la publication et le déploiement restent des étapes distinctes des contrôles locaux.

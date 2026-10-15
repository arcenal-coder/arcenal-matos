# Rapport de contrôle — ARCenal Matos 0.1.1 preview

Statut : distribution preview, SSO/branding de production configurés ; recette réelle de plateforme à effectuer.
Date : 2026-10-15.

## Contrôles locaux

| Contrôle | Résultat | Preuve |
| --- | --- | --- |
| Linter Python | RÉUSSI | ruff check . |
| Compilation Python | RÉUSSI | compileall sur core, matos et scripts |
| Configuration Django | RÉUSSI | manage.py check ; aucun changement de migration en attente |
| Dépendances Python | RÉUSSI | pip check : aucun conflit |
| Tests applicatifs | RÉUSSI | 62 tests PostgreSQL/Django/structure, incluant identité SSO via ASGI, branding/cache, fallback TLS sans traceback, signature, nominal, limites/refus et versions |
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
| package_linter officiel | RÉUSSI dans package_check | Run 38622713770 ; avertissements licence personnalisée/README ; aucune qualification communautaire officielle revendiquée |
| package_check / environnement Incus | RÉUSSI | 0.1.1~ynh5, révision b8ef047930d7c64944b83a485c2c8f13dd414794 ; YunoHost 12.1.41.2 amd64 ; cinq scénarios réussis |
| Installation YunoHost | RÉUSSI (Incus) | Run 38622713770 ; serveur cible non installé, SSH refusé |
| Retrait / réinstallation | RÉUSSI (Incus) | Scénario install.root, accès web vérifié après réinstallation |
| Mise à jour | RÉUSSI (Incus, même version) | Scénario upgrade ; migration depuis une future version métier distincte à recetter |
| Sauvegarde / restauration YunoHost | RÉUSSI (Incus) | Restauration après retrait et sur système vierge ; accès SSO et assets contrôlés ; données métier réelles et politique d'exploitation cible à recetter |
| SSO/LDAP réels | RÉUSSI (Incus) | Compte LDAP et connexion au portail réels, tableau de bord connecté 200, anonyme refusé 401 ; serveur cible non recetté |
| Changement de domaine | RÉUSSI (Incus) | Scénario change_url et configuration SSO/origines régénérée |
| SMTP réel / réception fournisseur | NON_EXÉCUTÉ | Déduplication, validation et gestion d'erreur testées ; transport local console et tests avec transport simulé |
| Connexion du profil Hermès réel | NON_EXÉCUTÉ | Serveur MCP testé avec client officiel ; export YAML ARCenal, import natif Hermès non démontré |
| Catalogue ARCenal Store | RÉUSSI (publication) | PR #11 fusionnée ; workflow 38688794615 réussi ; flux brut et Pages vérifiés avec la révision qualifiée ; parcours Store sur le serveur cible NON_EXÉCUTÉ |
| Caméra sur téléphone physique | NON_EXÉCUTÉ | Décodeur QR vérifié sur image et viewport mobile ; permissions/caméra réelles à tester |
| Étiquettes NFC iPhone/Android | NON_EXÉCUTÉ | Parcours URL validé fonctionnellement ; appareils/étiquettes physiques non disponibles |
| Application native / RFID distant | NON_APPLICABLE_JUSTIFIÉ | Hors périmètre V1 confirmé |

## Recette proposée au client

Ouvrir la bêta locale, choisir successivement Administrateur, Gestionnaire et Collaborateur. Créer/importer du matériel, demander et valider un prêt, effectuer sortie/retour, préparer une intervention et une demande fournisseur, puis exporter rapports et YAML. Les données de tests automatisés sont isolées de l'inventaire de la bêta.

La recette cliente, la publication et le déploiement restent des étapes distinctes des contrôles locaux.

## Preuves de distribution

- Source immuable : https://github.com/arcenal-coder/arcenal-matos/releases/tag/v0.1.1 ; SHA256 `ff063e8fc5cbf811b6261d4d4f0b3b69e9a88fa36fb7144131343827b7540f24`.
- CI application Linux : https://github.com/arcenal-coder/arcenal-matos/actions/runs/38616759680 (61 tests à cette révision ; régression ASGI ajoutée ensuite, 62 tests locaux réussis).
- Paquet qualifié : https://github.com/arcenal-coder/arcenal-matos_ynh/actions/runs/38622713770.
- Catalogue : https://github.com/arcenal-coder/arcenal-systeme-catalogue/pull/11 ; publication https://github.com/arcenal-coder/arcenal-systeme-catalogue/actions/runs/38688794615 ; Matos présent en preview et absent du canal stable.
- RÉUSSI : redémarrage local 0.1.1 sans migration, logo société téléchargé, smoke HTTP/YAML/PDF/MCP avec 14 outils sur http://127.0.0.1:8765/.
- NON_EXÉCUTÉ : installation arm64 (compatibilité déclarée, qualification exécutée uniquement en amd64).
- Le niveau communautaire retourné reste 0 (hors catalogue officiel YunoHost) malgré les cinq scénarios réussis ; le catalogue ARCenal conserve ce niveau, sans le convertir en note 8.
- Correctifs prouvés : lecture EOF current_host, branding optionnel avec TLS strict, tests SSO explicites, normalisation YNH-USER pour Django ASGI et réactivation systemd/permissions privées après restauration.

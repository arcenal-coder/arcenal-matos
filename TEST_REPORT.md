# Rapport de contrôle — ARCenal Matos 0.1.2 preview

Statut : distribution preview, SSO/branding de production configurés ; recette réelle de plateforme à effectuer.
Date : 2026-10-16.

## Publication corrective 0.1.2

- Cause prouvée du blocage : catalogue ARCenal avec `level=0`, alors que YunoHost exige un entier >= 5 et `state=working` pour annoncer une mise à jour (`app_upgrade_bad_quality`). Le statut 0 ne signifie pas simplement absence de qualification communautaire : sa publication précédente était incorrecte pour le catalogue client.
- Les cinq scénarios package_check de 0.1.1~ynh5 avaient réussi ; son niveau officiel restait 0 à cause des contrôles d'inscription/état dans le catalogue officiel YunoHost. Ces messages ne sont pas des échecs d'installation ou de cycle de vie.
- Source immuable 0.1.2 et paquet 0.1.2~ynh1 publiés, incluant les améliorations de saisie et migrations additives 0005/0006.
- RÉUSSI : 72 tests backend et 19 parcours Chromium sur 0.1.2 ; migration du schéma 0.1.1 vers 0.1.2 avec conservation de la clé, série, champs historiques, références marque/modèle et contenu d'un document privé ; ruff, build scanner et cohérence des migrations.
- RÉUSSI : six scénarios package_check, dont mise à jour réelle depuis b8ef047930d7c64944b83a485c2c8f13dd414794, run 38850600554 ; qualification technique ARCenal 5 et résultat officiel original 0 conservés séparément dans l'artefact public `arcenal-qualification.json` de la release v0.1.2.
- RÉUSSI : cinq tests du vérificateur (échec si cycle de vie manquant/en échec ou vrai défaut du linter), 18 tests catalogue avec régression du blocage `level < 5`, promotion sélective 38851575297, PR #16 fusionnée et publication 38851729049.
- RÉUSSI : flux brut et Pages répondent `0.1.2~ynh1`, révision 3d882348b212835d9adc61c54416ad72a6185c04, niveau 5 et état working ; SHA256 de l'archive distante vérifié. Le rafraîchissement du catalogue local du serveur client reste nécessaire.
- Publication source/paquet et correction du catalogue preview explicitement autorisées par le client le 16 octobre 2026.

## Contrôles locaux

### Historique : lot saisie simplifiée / Paramètres du 15 octobre 2026

- RÉUSSI : **71 tests backend**, dont identifiant automatique, clés conservées à l'édition, deux créations concurrentes sans doublon, références marque/modèle, alerte « filips / Philips », droits des rôles, demandes privées et orientation EXIF des photos.
- RÉUSSI : **19 parcours Chromium** sur une exécution complète ; après adaptation du logo au sombre, les 11 scénarios impactés ont été rejoués avec succès (thèmes/accessibilité, paramètres, références et assistance).
- RÉUSSI : client MCP officiel → demande de saisie → lecture du contexte et image PNG → réponse série/périodicité persistée, sans créer/modifier de fiche à la place de l'humain. Le retour agent dans le navigateur est simulé ; le transport MCP est exercé réellement dans les tests backend.
- RÉUSSI : logo téléversable par l'administrateur, transparence conservée, logo au-dessus du titre et lisible en sombre ; boutons espacés, retour inventaire pour Enregistrer/Annuler et absence de JSON dans le formulaire.
- RÉUSSI : ruff, syntaxe JS, compilation Python, Django check et cohérence des migrations.
- RÉUSSI : migrations additives 0005/0006 appliquées localement après sauvegarde hors Git ; inventaire avant/après identique (0 fiche), anciens libellés conservés par la migration de référentiels.
- RÉUSSI : aperçu local redémarré, smoke HTTP/YAML/PDF/MCP, 17 outils MCP ; médias des tests navigateur isolés de l'instance locale.
- NON_EXÉCUTÉ : agent Hermès réel/vision réelle et validation métier des périodicités suggérées. Installation/upgrade des nouvelles migrations ensuite qualifiés le 16 octobre pour 0.1.2.
- Modifications ensuite publiées dans 0.1.2 ; aucune connexion au serveur client effectuée.

### Correctif local prioritaire du 15 octobre 2026 (après publication)

- Portée cliente : application prévue pour LDAP/SSO YunoHost et saisie/suivi du matériel ; aucun raccordement distant demandé.
- RÉUSSI : 21 tests ciblés branding/écrans ; identité SSO via ASGI → création persistée/journalisée d'une fiche → consultation, accès sans identité refusé.
- RÉUSSI : 17 parcours Chromium ; géométrie de « Par ARCenal » au bas droit des pages courtes et longues, ordinateur/mobile ; création et suivi matériel conservés.
- RÉUSSI : logo société transparent sans cadre sur connexion et pages authentifiées ; redémarrage local sans migration et smoke HTTP/MCP.
- Aperçu local actualisé ; ces corrections ne sont pas incluses dans l'archive immuable v0.1.1 déjà publiée. Authentification réelle LDAP/SSO prévue pour l'installation YunoHost ; profils d'essai dans l'aperçu local.

| Contrôle | Résultat | Preuve |
| --- | --- | --- |
| Linter Python | RÉUSSI | ruff check . |
| Compilation Python | RÉUSSI | compileall sur core, matos et scripts |
| Configuration Django | RÉUSSI | manage.py check ; aucun changement de migration en attente |
| Dépendances Python | RÉUSSI | pip check : aucun conflit |
| Tests applicatifs | RÉUSSI | 72 tests PostgreSQL/Django/structure, incluant identité SSO, saisie simplifiée, concurrence des identifiants, migration avec document privé et versions |
| Concurrence de prêts | RÉUSSI | Deux validations concurrentes : un seul gagnant |
| Autres écritures concurrentes | RÉUSSI | Import CSV concurrent : un identifiant unique ; annulation/sortie concurrentes : état cohérent |
| Remise en service humaine | RÉUSSI | Une modification de date/périodicité ne débloque pas implicitement un contrôle déjà expiré |
| Jeu 300 utilisateurs / 1 500 équipements | RÉUSSI | Catalogue intersite < 25 requêtes SQL et export CSV de 1 500 équipements ; pas une mesure de 300 utilisateurs simultanés |
| Client MCP officiel | RÉUSSI | Initialisation 2025-11-25, lecture/écriture, refus de champ protégé, authentification obligatoire, pas d'outil de validation humaine |
| Construction du scanner embarqué | RÉUSSI | npm run build, esbuild, dépendances servies localement et licences conservées |
| Parcours navigateur Chromium | RÉUSSI | 19 scénarios Playwright : métier, Paramètres/saisie, assistance conditionnelle, logo et Gratitude |
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
| package_linter officiel | RÉUSSI dans package_check | Run 38850600554 ; seuls AppCatalog.state_is_working et AppCatalog.is_in_catalog concernent le catalogue officiel, aucune erreur applicative/packaging ; avertissements conservés |
| package_check / environnement Incus | RÉUSSI | 0.1.2~ynh1, révision 3d882348b212835d9adc61c54416ad72a6185c04 ; YunoHost 12.1.41.2 amd64 ; six scénarios réussis |
| Installation YunoHost | RÉUSSI (Incus) | Run 38850600554 ; aucune connexion au serveur client |
| Retrait / réinstallation | RÉUSSI (Incus) | Scénario install.root, accès web vérifié après réinstallation |
| Mise à jour | RÉUSSI (Incus) | Même version et depuis la version publiée 0.1.1~ynh5 |
| Sauvegarde / restauration YunoHost | RÉUSSI (Incus) | Restauration après retrait et sur système vierge ; accès SSO et assets contrôlés ; données métier réelles et politique d'exploitation cible à recetter |
| SSO/LDAP réels | RÉUSSI (Incus) | Compte LDAP et connexion au portail réels, tableau de bord connecté 200, anonyme refusé 401 ; serveur cible non recetté |
| Changement de domaine | RÉUSSI (Incus) | Scénario change_url et configuration SSO/origines régénérée |
| SMTP réel / réception fournisseur | NON_EXÉCUTÉ | Déduplication, validation et gestion d'erreur testées ; transport local console et tests avec transport simulé |
| Connexion du profil Hermès réel | NON_EXÉCUTÉ | Serveur MCP testé avec client officiel ; export YAML ARCenal, import natif Hermès non démontré |
| Catalogue ARCenal Store | RÉUSSI (publication) | PR #16 fusionnée ; workflow 38851729049 réussi ; flux brut et Pages vérifiés avec niveau 5 et révision qualifiée ; cache du serveur client à actualiser |
| Caméra sur téléphone physique | NON_EXÉCUTÉ | Décodeur QR vérifié sur image et viewport mobile ; permissions/caméra réelles à tester |
| Étiquettes NFC iPhone/Android | NON_EXÉCUTÉ | Parcours URL validé fonctionnellement ; appareils/étiquettes physiques non disponibles |
| Application native / RFID distant | NON_APPLICABLE_JUSTIFIÉ | Hors périmètre V1 confirmé |

## Recette proposée au client

Ouvrir la bêta locale, choisir successivement Administrateur, Gestionnaire et Collaborateur. Créer/importer du matériel, demander et valider un prêt, effectuer sortie/retour, préparer une intervention et une demande fournisseur, puis exporter rapports et YAML. Les données de tests automatisés sont isolées de l'inventaire de la bêta.

La recette cliente, la publication et le déploiement restent des étapes distinctes des contrôles locaux.

## Preuves de distribution

- Source immuable : https://github.com/arcenal-coder/arcenal-matos/releases/tag/v0.1.2 ; SHA256 `04dcf13b27f3a998c9aabde98d297ed67df5b2b41155605f6253e327164f0a65`.
- CI application Linux : https://github.com/arcenal-coder/arcenal-matos/actions/runs/38849521398 (72 tests backend et 19 parcours navigateur).
- Paquet qualifié : https://github.com/arcenal-coder/arcenal-matos_ynh/actions/runs/38850600554.
- Catalogue : https://github.com/arcenal-coder/arcenal-systeme-catalogue/pull/16 ; publication https://github.com/arcenal-coder/arcenal-systeme-catalogue/actions/runs/38851729049 ; Matos présent en preview et absent du canal stable.
- RÉUSSI : redémarrage local 0.1.1 sans migration, logo société téléchargé, smoke HTTP/YAML/PDF/MCP avec 14 outils sur http://127.0.0.1:8765/.
- NON_EXÉCUTÉ : installation arm64 (compatibilité déclarée, qualification exécutée uniquement en amd64).
- Résultat communautaire original 0 conservé dans les preuves, distinct de la qualification technique ARCenal 5 du catalogue client. Copier le 0 dans ce dernier bloquait à tort la mise à jour ; les deux constats officiels restants sont exclusivement liés à son propre catalogue.
- Correctifs prouvés : lecture EOF current_host, branding optionnel avec TLS strict, tests SSO explicites, normalisation YNH-USER pour Django ASGI et réactivation systemd/permissions privées après restauration.

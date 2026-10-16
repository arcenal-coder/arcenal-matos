# Rapport de contrôle — ARCenal Matos 0.2.0 preview

Statut : 0.2.0 finalisée, qualifiée et publiée en preview ; recette métier et mise à jour sur le serveur client distinctes.
Date : 2026-10-16.

## Finalisation 0.2.0

- Le client confirme « Oui, finaliser et publier » : source immuable, paquet, qualification puis catalogue preview autorisés.
- Versions application/JavaScript/manifest synchronisées ; notes de version et procédure de sauvegarde/restauration fournies.
- RÉUSSI sur 0.2.0 : ruff, compilation, Django check/migrations, pip check, 119 tests backend et 25 parcours Chromium, build scanner ; CI Linux 38885647848, source c782bf8.
- Tests de paquet enrichis avec le module EPI actif, la page Modules, et le refus d'accès Dosimètres lorsqu'il est inactif initialement.
- RÉUSSI : package_check 38885952601, paquet 0.2.0~ynh1 figé à 37f06d73a9d2562b26fa0dc07d1447eeedb153e9 ; sept scénarios sur YunoHost 12.1.41.2 amd64, dont upgrades depuis 0.1.1 et 0.1.2.
- RÉUSSI : 18 tests catalogue, promotion sélective 38887649483, PR #22 fusionnée, publication 38887936074 et flux brut/Pages vérifiés en 0.2.0~ynh1/niveau 5/working. Changement concurrent ARCenal Store conservé ; diff final limité à Matos.
- Source immuable : https://github.com/arcenal-coder/arcenal-matos/releases/tag/v0.2.0 ; SHA256 8c717f8b984eed15197bc6be3f1cb325f8e795df7d2473b5ed4e57f0e3ebfaab vérifié à distance. Preuve structurée : `arcenal-qualification.json` jointe à la release, résultat officiel original et grade technique ARCenal conservés séparément.

## Dosimètres passifs et activation des modules

- Périmètre client validé : badges passifs, logistique seulement, témoins, périodes, réception, préaffectation/distribution, collecte, envoi, perte/remplacement, assistance IA ; dosimètres opérationnels dans le matériel général.
- RÉUSSI : **119 tests backend** (95 précédents + 5 d'activation et 19 dosimètres) ; droits par rôle/site, numéros par période, séquence des dates, badges témoins/non portés, historique et absence de résultats de dose.
- RÉUSSI : activation indépendante et désactivation simultanée, pages et mutations bloquées, données EPI/badges conservées à réactivation, rappels suspendus et YAML limité aux modules actifs ; lecture MCP Dosimètres bloquée après désactivation pendant une vraie session SDK.
- RÉUSSI : PostgreSQL concurrent sur double réception d'un numéro, double remise et double expédition ; un seul badge / mouvement / colis confirmé.
- RÉUSSI : agent MCP officiel → lecture du contexte → préparation de préaffectation persistée sans mouvement physique ; confirmation humaine distincte. Préparation d'envoi revalidée à confirmation ; réponses visant un autre site ou des badges inéligibles refusées.
- RÉUSSI : **25 parcours navigateur**, dont interrupteurs, conservation des références EPI, réception/distribution/collecte/envoi/perte/remplacement, vue personnelle, témoin, assistance en attente et axe clair/ordinateur + sombre/mobile.
- RÉUSSI : ruff, syntaxe JavaScript, compilation, Django check et cohérence des migrations ; migration locale core.0007 + dosimetry.0001 après sauvegarde, empreintes du matériel et des EPI identiques avant/après ; aucun badge fictif ajouté.
- Réglages initiaux : EPI actif et Dosimètres inactif, activation réservée à l'administrateur. 23 outils MCP enregistrés, gardes dynamiques sur les fonctions des modules désactivés.
- NON_EXÉCUTÉ : agent Hermès réel, flux avec un laboratoire réel et recette métier cliente. Cycle de vie YunoHost qualifié et publication 0.2.0 réalisée après autorisation.

## Module EPI — développement local vérifié

- Périmètre validé par le client : module séparé, suivi mixte, péremption fabricant et durée après mise en service, demandes, distributions, destructions, prix HT privés et propositions de validité IA.
- RÉUSSI : **95 tests backend**, dont 23 tests EPI : séparation de l'inventaire général, 20 paires reçues / 3 remises / 17 en stock, remises partielles, coûts historiques, quantités détruites et droits par rôle/site.
- RÉUSSI : concurrence réelle PostgreSQL sur remises, réception de deux exemplaires individuels, double remise du même exemplaire et conflit remise/destruction ; aucun stock négatif ni double attribution.
- RÉUSSI : dates fabricant/durée première mise en service, refus d'une remise expirée et dates futures incohérentes, reprise de remises anciennes, date initiale non réinitialisable et notifications internes dédupliquées.
- RÉUSSI : transport MCP officiel → contexte EPI → réponse source/date/durée → proposition persistée sans modifier le stock → application humaine par HTTP. Date dépassant la limite fabricant ou dépourvue de point de départ refusée ; réponse inconnue non transformée en validité inventée.
- RÉUSSI : **22 scénarios navigateur**, incluant lots/demandes/remise/destruction/prix privés, exemplaires/série/expiration/remise passée, validité manuelle, demande IA en attente et contrôle axe sur les écrans EPI en clair/ordinateur et sombre/mobile.
- RÉUSSI : ruff, compilation, cohérence des migrations, génération/vérification d'une archive de développement incluant l'app `epi` et sa migration.
- RÉUSSI : sauvegarde locale avant migration `epi.0001_initial`, migration additive, empreinte d'inventaire général avant/après identique et aucun EPI fictif ajouté. Version distincte 0.2.0-dev.1 pour préserver les archives publiées 0.1.2.
- NON_EXÉCUTÉ : inférence par un agent Hermès réel, validation des sources fabricant sur les EPI réels du client et recette métier cliente. Cycle de vie incluant EPI qualifié dans 0.2.0.
- Modules ensuite publiés dans 0.2.0~ynh1 ; aucune connexion au serveur client effectuée.

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

## Historique : paquet et services réels 0.1.2

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

## Historique : preuves de distribution 0.1.2

- Source immuable : https://github.com/arcenal-coder/arcenal-matos/releases/tag/v0.1.2 ; SHA256 `04dcf13b27f3a998c9aabde98d297ed67df5b2b41155605f6253e327164f0a65`.
- CI application Linux : https://github.com/arcenal-coder/arcenal-matos/actions/runs/38849521398 (72 tests backend et 19 parcours navigateur).
- Paquet qualifié : https://github.com/arcenal-coder/arcenal-matos_ynh/actions/runs/38850600554.
- Catalogue : https://github.com/arcenal-coder/arcenal-systeme-catalogue/pull/16 ; publication https://github.com/arcenal-coder/arcenal-systeme-catalogue/actions/runs/38851729049 ; Matos présent en preview et absent du canal stable.
- RÉUSSI : redémarrage local 0.1.1 sans migration, logo société téléchargé, smoke HTTP/YAML/PDF/MCP avec 14 outils sur http://127.0.0.1:8765/.
- NON_EXÉCUTÉ : installation arm64 (compatibilité déclarée, qualification exécutée uniquement en amd64).
- Résultat communautaire original 0 conservé dans les preuves, distinct de la qualification technique ARCenal 5 du catalogue client. Copier le 0 dans ce dernier bloquait à tort la mise à jour ; les deux constats officiels restants sont exclusivement liés à son propre catalogue.
- Correctifs prouvés : lecture EOF current_host, branding optionnel avec TLS strict, tests SSO explicites, normalisation YNH-USER pour Django ASGI et réactivation systemd/permissions privées après restauration.

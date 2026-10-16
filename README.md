# ARCenal Matos · 0.1.2 — preview

Application web responsive de gestion interne des actifs, Django/PostgreSQL, MCP intégré et liaison YAML pour un agent logisticien créé dans Hermès.

Logiciel propriétaire — conditions dans LICENSE. Distribution destinée au canal preview d'ARCenal Store avant qualification sur chaque serveur client.

## Installation YunoHost

Paquet : https://github.com/arcenal-coder/arcenal-matos_ynh/tree/preview. L'installation choisit le domaine, le groupe YunoHost autorisé et le compte administrateur ; aucun compte ou mot de passe applicatif à créer. Le processus web utilise un socket Unix réservé à l'application et Nginx, les identités proviennent de SSOwat, les rôles/sites se configurent dans Matos.

Matos est référencé en **preview** dans le catalogue canonique ARCenal : `https://raw.githubusercontent.com/arcenal-coder/arcenal-systeme-catalogue/main/preview`. Paquet figé `0.1.1~ynh5`, révision `b8ef047930d7c64944b83a485c2c8f13dd414794`. La publication a été vérifiée sur le flux brut et son miroir GitHub Pages ; PR catalogue [#11](https://github.com/arcenal-coder/arcenal-systeme-catalogue/pull/11).

Le logo est récupéré depuis le portail public YunoHost de l'instance, mis en cache localement et actualisé périodiquement. Le logo ARCenal est conservé si aucun logo d'organisation n'est disponible. La signature « Par ARCenal » apparaît au bas de toutes les pages et des rapports PDF.

Les paramètres secrets restent sur le serveur. L'export YAML ne contient pas le jeton MCP ; sa liaison au profil Hermès se configure séparément.

## Aperçu local de la version distribuée

Après préparation de l'environnement local :

```sh
.venv/bin/python scripts/local_beta.py
```

Ouvrir **http://127.0.0.1:8765/**. Choisir un profil fictif sur la page de connexion : Administrateur, Gestionnaire Siège, Gestionnaire Atelier ou Collaborateur. Aucun mot de passe local ; ce sélecteur existe uniquement en mode d'essai activé explicitement et sur loopback. En production, l'identité provient exclusivement de YunoHost/SSOwat.

Le thème **Gratitude amélioré** reprend les références communes ARCenal : crème/ivoire, accent terre cuite et variables CSS sémantiques. Le sélecteur **Apparence** propose Clair, Sombre et Système ; le choix manuel persiste dans ce navigateur. La police Inter et les dépendances du scanner sont servies localement. Navigation compacte, focus clavier, cibles tactiles et tableaux défilants sont intégrés.

La version de l'application et des archives provient de `matos/version.py`. Les manifests JavaScript et YunoHost sont contrôlés pour rester cohérents. Les anciennes archives sont conservées dans `dist/` ; les nouvelles archives portent `0.1.2`.

L'inventaire démarre vide. L'administrateur définit sites et catégories ; un gestionnaire ajoute une fiche ou télécharge le modèle CSV. Le collaborateur demande un prêt ; le gestionnaire le valide puis enregistre sortie et retour. Utiliser l'écran des intégrations comme administrateur pour télécharger le YAML du logisticien.

Python isolé dans `.venv/`, PostgreSQL 17 dans `.local/postgres`, port **55432**. Les secrets locaux restent dans `.local/credentials.json` (hors Git, accès restreint). Logs : `.local/beta.log` et `.local/jobs.log`. Un worker local produit automatiquement les rappels toutes les cinq minutes. Le mode local utilise le transport e-mail console : aucun message n'est délivré à un fournisseur réel.

Pour arrêter le serveur et le worker : `.venv/bin/python scripts/stop_local.py`. PostgreSQL local peut être arrêté avec `/opt/homebrew/opt/postgresql@17/bin/pg_ctl -D .local/postgres stop` sur ce Mac. Aucun service global de démarrage automatique n'est configuré.

## Capacités de la preview

La candidate 0.1.2 regroupe les évolutions de saisie et Paramètres poussées après 0.1.1. Sa publication corrige aussi la qualification du catalogue ARCenal : YunoHost ne propose pas de mise à jour lorsque le niveau est inférieur à 5, même si `state` vaut `working`. Les preuves techniques ARCenal et le résultat du catalogue communautaire officiel sont distincts ; la qualification 0.1.2 est en cours avant promotion du catalogue.

### Saisie simplifiée

La version 0.1.2 ajoute un menu **Paramètres** avec Agent & MCP, Gestion des utilisateurs, Sites et Catégories & périodicités. Ces changements ne font pas partie de l'ancienne archive immuable v0.1.1.

- **Inventaire → Ajouter** : identifiant automatique par type/catégorie et séquence verrouillée ; les clés déjà attribuées restent stables.
- Catégories, marques et modèles ajoutables sur place. Marques/modèles mémorisés, variantes de casse réutilisées et noms proches proposés pour éviter les erreurs de frappe. Les modèles sont rattachés à leur marque.
- Aucun champ JSON dans la saisie humaine ; les données historiques et leur compatibilité CSV/MCP sont conservées.
- Enregistrer ou Annuler ramènent à l'inventaire ; achat et contrôles sont regroupés dans une section facultative.
- Logo société repris du portail ou téléversé dans **Paramètres → Sites** ; fichier transparent prioritaire, affiché au-dessus d'ARCenal Matos, avec adaptation du texte sombre pour le thème sombre.

L'assistance est activable dans **Paramètres → Agent & MCP** après configuration du secret MCP. Elle ne lance pas Hermès : l'agent connecté doit traiter les demandes via `list_intake_requests`, lire contexte/photo avec `read_intake_request`, puis répondre par `complete_intake_request`. Le YAML exporté contient ces instructions. Une photo nécessite un modèle capable de vision ; une périodicité inconnue reste vide, une justification est requise. Les images restent privées dans les médias de l'instance et sont exposées à l'agent authentifié via MCP.

Le formulaire attend la réponse et recopie série/périodicité sans remplacer une saisie modifiée entre-temps. L'enregistrement final de la fiche reste humain. Aucun fournisseur d'IA externe n'est appelé directement par Matos.

- Rôles et rattachements multisites, droits contrôlés côté serveur et documents privés.
- Inventaire matériel, champs personnalisés, affectations, QR/Code128 et scan caméra embarqué sans CDN.
- Prêts internes avec validation humaine, demandes intersites si équivalent local indisponible, état/photos à la sortie et au retour, transferts.
- Maintenance avec prestataire/coût/documents, périodicités par catégorie ajustables, blocage des prêts et remise en service humaine.
- Logiciels et abonnements, places et affectations, échéances.
- Import CSV atomique à colonnes prédéfinies, PDF/CSV d'inventaire/audit.
- Notifications internes, rappels dédupliqués et file d'envoi e-mail ; validation humaine des demandes fournisseur.
- Journal distinguant humains et agent, MCP Streamable HTTP authentifié et commandes d'agent idempotentes.

## Connexion MCP

Endpoint : `/mcp`. SDK MCP **1.30.0**, révision **2025-11-25**. Fournir `Authorization: Bearer <valeur privée MATOS_MCP_TOKEN>` à chaque requête. Sans configuration, le serveur MCP est fermé. L'export YAML ne contient pas cette valeur et ne modifie pas les droits serveur.

Le schéma `arcenal-agent-link` décrit profil, endpoint, transport, référence d'authentification et missions. Il sert à configurer le profil dédié ; l'import automatique natif dans Hermès et sa connexion réelle restent à vérifier. Un client MCP officiel est utilisé dans les tests.

L'agent peut gérer fiches/affectations, sorties après validation humaine, retours, transferts, interventions, brouillons fournisseur, rappels et rapports. Les validations de réservations et de demandes fournisseur, ainsi que les remises en service, restent humaines.

## Contrôles de développement

```sh
.venv/bin/ruff check .
MATOS_DEBUG=1 .venv/bin/python -m compileall -q core matos scripts
MATOS_DEBUG=1 .venv/bin/python manage.py check
MATOS_DEBUG=1 .venv/bin/python manage.py test core.tests --noinput
npm run build
npm run test:browser
```

Pour reconstruire l'environnement Python : `python3 -m venv .venv`, puis `.venv/bin/pip install -r requirements-dev.txt`. Installer les dépendances JavaScript par `npm ci`. Le code de scan est construit avec esbuild à partir de `@zxing/browser` ; sa licence et celles de ses dépendances restent dans node_modules, et les mentions légales du bundle sont générées avec celui-ci.

## Paquet YunoHost candidat

`packaging/ynh/` suit le format v2/helpers 2.1 : manifest, scripts install/remove/upgrade/backup/restore/change_url, PostgreSQL, SSO/LDAP, SMTP et timer de rappels. Domaine dédié, cible YunoHost >= 12.1.17. Les profils/sites de démonstration ne sont pas créés à l'installation YunoHost.

```sh
.venv/bin/python scripts/build_beta.py
```

Cette commande produit une archive de sources et un **modèle de paquet** dans `dist/`. Le manifest doit être finalisé avec l'URL de l'archive distribuée, sa somme de contrôle et la licence déclarée avant installation. Le script accepte `--source-url` et `--license` pour assembler cette candidate ; il ne publie rien. Lors de cette finalisation, il conserve l'archive de sources déjà construite pour que la somme corresponde exactement au fichier distribué.

## Vérifications restant à effectuer sur infrastructure réelle

- Sur le serveur cible : installation, contrôle des groupes/sites et du logo, SSO/LDAP, SMTP avec réception réelle, politique de sauvegarde et restauration de données métier. Le SSH du serveur cible reste inaccessible dans cette session.
- Parcours d'installation depuis ARCenal Store sur le serveur cible. Le catalogue est publié ; son affichage et le clic d'installation sur cette instance restent à recetter.
- Scan caméra et étiquettes NFC sur iPhone/Android physiques. Le NFC ouvre une URL sur appareils compatibles ; il ne réalise pas un inventaire à distance. Les URL de la bêta loopback sont accessibles uniquement sur le Mac.
- Profil Hermès réel et import de sa configuration ; recette fonctionnelle par le client.

Les états et preuves détaillés de la bêta sont conservés dans `.arcenal/`. Une bêta locale n'est pas une validation du déploiement YunoHost ou Store.

La qualification isolée est réussie sur YunoHost 12.1.41.2 **amd64** : installation/retrait/réinstallation, connexion SSO réelle et refus anonyme, assets, upgrade même version, sauvegarde/restauration et changement de domaine ([preuve](https://github.com/arcenal-coder/arcenal-matos_ynh/actions/runs/38622713770)). `arm64` est déclaré compatible mais son installation n'a pas été exécutée. Le niveau communautaire reste 0 car le paquet ne figure pas au catalogue officiel YunoHost ; les preuves techniques ARCenal sont tracées séparément dans `TEST_REPORT.md`.

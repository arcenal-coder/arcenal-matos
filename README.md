# ARCenal Matos · 0.2.0 — preview

Application web responsive de gestion interne des actifs, Django/PostgreSQL, MCP intégré et liaison YAML pour un agent logisticien créé dans Hermès.

Logiciel propriétaire — conditions dans LICENSE. Distribution destinée au canal preview d'ARCenal Store avant qualification sur chaque serveur client.

La version 0.2.0 est publiée en preview avec les modules EPI et Dosimètres passifs, activables indépendamment. La mise à jour depuis **0.1.2~ynh1** et le cycle de vie YunoHost ont été qualifiés. Les nouveautés, premières étapes et procédure de retour arrière sont dans [RELEASE_NOTES.md](RELEASE_NOTES.md).

## Paramètres → Modules

L'administrateur choisit **Activer le module EPI** et **Activer le module Dosimètres passifs**. EPI est actif par défaut pour conserver le comportement existant ; Dosimètres est initialement désactivé.

Désactiver un module masque ses menus et bloque ses accès directs, mutations, fonctions MCP et nouveaux rappels. Les données, stocks, dotations, badges, historiques et notifications déjà reçues restent conservés. La réactivation retrouve les mêmes données et reprend les fonctions et rappels ; l'autre module et l'inventaire matériel ne sont pas affectés.

## Module Dosimètres passifs

Ce module gère **la logistique uniquement**. Les dosimètres opérationnels restent dans l'inventaire matériel ; aucun résultat de dose n'est enregistré ou calculé.

1. Activer Dosimètres dans **Paramètres → Modules**. L'administrateur configure ensuite les **Laboratoires** et **Périodes de port** (début, fin, échéance de retour). Le calendrier n'est pas limité à une fréquence fixe.
2. Le gestionnaire réceptionne les badges du site et de la période, avec un numéro par ligne. Un numéro est unique dans sa période/laboratoire et peut être réutilisé sur une autre période. Badges personnels et témoins sont distingués.
3. Préaffecter et distribuer les badges personnels aux équipiers éligibles du site ; une préaffectation existante n'est pas remplacée par une remise à une autre personne. Un témoin reste lié au site et n'a pas de bénéficiaire individuel.
4. Enregistrer les collectes/restitutions, puis les envois groupés au laboratoire par site et période avec date réelle et référence de suivi. Les badges restés en stock peuvent être collectés et retournés en étant signalés **non portés**.
5. Déclarer pertes ou annulations avec motif ; un remplacement possède un autre numéro et reste lié au badge d'origine. Les remises, collectes et envois peuvent être repris à leurs dates passées réelles, dans l'ordre chronologique.
6. L'équipier consulte uniquement **Mes badges**, leurs périodes, échéances et retours. Les gestionnaires ne gèrent que leurs sites. Les retards et badges collectés à expédier produisent des notifications internes dédupliquées.

### Rôle de l'agent IA

Après activation de l'assistance dans **Agent & MCP** et connexion de l'agent, le gestionnaire demande une aide dans **Dosimètres → Assistant IA** : faire le point, proposer des préaffectations, préparer une collecte ou un envoi.

L'agent utilise `list_dosimetry_assistance`, `read_dosimetry_assistance` et `propose_dosimetry_logistics`. Il dispose du contexte du site/période, des badges et équipiers éligibles, sans résultat de dose. Les propositions sont persistées mais ne distribuent, collectent ou expédient rien. Le gestionnaire confirme les préaffectations, ou utilise les listes précochées dans les formulaires d'opération réelle. Chaque préparation est revérifiée au moment de la confirmation. L'agent ne peut pas déclarer une perte/annulation ni inventer une correspondance numéro/porteur manquante.

## Module EPI séparé

Le menu **EPI** ouvre son propre catalogue, stock, demandes, dotations, destructions et historique. Les comptes LDAP/SSO et les sites de Matos sont partagés ; les EPI ne sont pas des fiches de l'inventaire matériel général.

### Commencer

1. Gestionnaire ou administrateur : **EPI → Catalogue EPI → Ajouter une référence EPI**. Renseigner type, taille/pointure, unité (pièce, paire ou boîte) et suivi par quantités/lots ou exemplaires individuels. La durée après première mise en service est facultative et doit correspondre aux indications du fabricant.
2. **Stock & validités → Réceptionner des EPI** : choisir site, lot, quantité, date de réception, limite fabricant et prix d'achat unitaire HT. Un prix inconnu reste vide. Les identifiants individuels sont automatiques ; les numéros de série peuvent être ajoutés à la réception ou sur l'exemplaire.
3. L'équipier utilise **Mes demandes** pour demander une référence/taille/quantité. Le gestionnaire accepte ou refuse, puis enregistre la remise physique, totale ou partielle. L'acceptation seule ne retire rien du stock.
4. **Distribués** présente les remises et les quantités encore détenues. **Mes EPI** expose seulement les dotations personnelles. Les coûts et le stock des autres sites restent protégés côté serveur.
5. Une destruction s'enregistre depuis un lot ou une dotation, avec date, quantité/exemplaire et motif. Elle est définitive et journalisée ; les EPI détruits ne retournent pas au stock.

Pour reprendre des équipements déjà distribués, enregistrer la réception d'origine (quantité et date réelles), puis les remises à leurs dates réelles. Le stock final correspond alors aux quantités encore disponibles ; aucun stock fictif n'est ajouté automatiquement.

### Validité, prix et agent

- La validité est la plus proche des limites renseignées : date fabricant, date retenue et durée d'usage après première mise en service. La date de première mise en service d'un exemplaire n'est pas réinitialisable par une remise. Les EPI expirés à la date de remise sont bloqués ; une validité inconnue est explicitement indiquée.
- Les dates/durées peuvent être complétées dans le lot ou sur un exemplaire, sans modifier son identifiant, son stock, son prix historique ou sa première mise en service. Les modifications sont tracées.
- Les prix d'achat HT sont mémorisés à la remise et à la destruction. La vue d'ensemble distingue valorisation du stock, coûts historiques des remises et des destructions ; les prix inconnus ne sont pas assimilés à des achats à 0 €.
- Le traitement périodique produit des notifications **internes**, dédupliquées, pour les échéances à moins de 30 jours et les EPI expirés. Aucun envoi e-mail EPI supplémentaire n'est créé.
- Après activation de l'assistance dans **Paramètres → Agent & MCP**, demander une proposition depuis un lot, un exemplaire ou **Validités IA**. L'agent lit le type d'EPI et ses informations fabricant via `list_epi_validity_requests` / `read_epi_validity_request`, puis répond par `propose_epi_validity` avec source et explication. Les informations manquantes sont signalées ; aucune date précise n'est admise sans point de départ connu.
- Le gestionnaire applique ou écarte la proposition sur son lot/exemplaire. La durée commune d'une référence est modifiable uniquement par l'administrateur. Une proposition ne prolonge jamais la limite fabricant connue ; l'agent ne peut ni valider une demande, ni distribuer, ni détruire un EPI.

La V1 n'inclut pas le reconditionnement/retour d'EPI usagés, les transferts intersites, les achats/comptabilité complète ou la signature électronique de remise. La proposition IA n'est pas une certification réglementaire.

## Installation YunoHost

Paquet : https://github.com/arcenal-coder/arcenal-matos_ynh/tree/preview. L'installation choisit le domaine, le groupe YunoHost autorisé et le compte administrateur ; aucun compte ou mot de passe applicatif à créer. Le processus web utilise un socket Unix réservé à l'application et Nginx, les identités proviennent de SSOwat, les rôles/sites se configurent dans Matos.

Matos est référencé en **preview** dans le catalogue canonique ARCenal : `https://raw.githubusercontent.com/arcenal-coder/arcenal-systeme-catalogue/main/preview`. Paquet figé `0.2.0~ynh1`, révision `37f06d73a9d2562b26fa0dc07d1447eeedb153e9`, niveau technique ARCenal **5**, état `working`. Publication vérifiée sur le flux brut et son miroir GitHub Pages ; [PR catalogue nº 22](https://github.com/arcenal-coder/arcenal-systeme-catalogue/pull/22).

Si YunoHost affiche encore une ancienne version ou l'avertissement « défectueuse », actualiser son catalogue d'applications puis rouvrir les mises à jour. Le serveur doit avoir récupéré l'entrée `0.2.0~ynh1` ; le déploiement n'est pas réalisé automatiquement par cette publication.

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

La version 0.2.0 reprend la saisie simplifiée de 0.1.2 et ajoute les deux modules. Le niveau technique ARCenal 5 est maintenu : YunoHost ne propose pas de mise à jour lorsque le niveau est inférieur à 5. Le résultat communautaire officiel original reste conservé séparément. La [preuve de qualification](https://github.com/arcenal-coder/arcenal-matos/releases/download/v0.2.0/arcenal-qualification.json) détaille les sept scénarios, dont les mises à jour depuis 0.1.1~ynh5 et 0.1.2~ynh1.

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

## Assistance ARCenal Agent par SSO — ajout local après 0.2.0

Demande qualifiée par le client : **assistance SSO, sans écriture**, selon la skill `arcenal-agent-link`. Les nouveaux exports dédiés non publiés ont été remplacés par le bouton accessible exactement nommé **Demander à ARCenal Agent**, dans l'inventaire, les modules EPI/Dosimètres et Paramètres → Agent & MCP.

L'appariement automatique est développé côté Matos **0.2.1** et dans le paquet natif ARCenal Agent **0.22.2~ynh4**. Il conserve le dashboard Hermes actuel et ne réinstalle aucun ancien broker/service de contrôle. Les deux paquets compatibles préparent côté serveur les adresses publiées YunoHost et un secret applicatif dédié ; aucune adresse ni clé à copier. Dans **Paramètres → Agent & MCP**, confirmer la lecture seule et cliquer **Lier ARCenal Agent**, valider dans l'Agent, puis revenir sur **Vérifier la liaison**. **Liaison active** n'apparaît qu'après vérification centrale et accord local. Une indisponibilité ne vaut jamais validation. L'accord expire après 90 jours et peut être révoqué dans chaque application. L'ancien réglage SSO manuel reste dans un volet technique séparé.

Le POST Matos contrôle session, rôle et activation du module. Le contrat central d'assistance v1 fournit une référence aléatoire à usage unique, valable 60 secondes. Le navigateur ne transporte que cette référence. À réception, l'Agent exige la même identité SSO, une liaison active et une revalidation serveur des droits/rôle/module auprès de Matos. Le contexte minimal (application, utilisateur SSO, intention lecture seule, module) circule exclusivement entre serveurs, sans fiche ou document. L'accueil confirme le contexte autorisé ; aucune inférence IA ou connexion du chat administratif n'est revendiquée.

L'ouverture se fait dans une fenêtre isolée, sans référent vers le destinataire ; le journal ne conserve que les catégories techniques de demande. Les contextes/actions fournis par le navigateur sont refusés. Les modules désactivés restent bloqués, y compris entre émission et réception. Aucun connecteur central d'actions ni MCP supplémentaire n'est créé. Le nouveau service et le secret applicatif servent uniquement au contrat d'assistance vérifié localement. Une future intégration d'écriture exige un connecteur central réellement disponible et une confirmation humaine dans Matos avant chaque envoi.

Cette candidate preview ne modifie aucune archive de release existante. Les nouveaux paquets, leur SSOwat et leur cycle de vie restent à qualifier sur une instance YunoHost jetable. Test inter-dépôts : `.venv/bin/python scripts/verify_agent_pairing.py <répertoire-paquet-natif-ARCenal-Agent>` ; seuls les transports HTTP y sont remplacés, pas les implémentations ni la revalidation.

### Configuration MCP préexistante de 0.2.0

La configuration publiée avant cette qualification est conservée dans le volet technique replié **Configuration MCP existante**. Elle n'est pas utilisée par le bouton SSO et n'est pas présentée comme un connecteur central vérifié.

Endpoint : `/mcp`. SDK MCP **1.30.0**, révision **2025-11-25**. Fournir `Authorization: Bearer <valeur privée MATOS_MCP_TOKEN>` à chaque requête. Sans configuration, le serveur MCP est fermé. L'export YAML ne contient pas cette valeur et ne modifie pas les droits serveur.

Le YAML technique historique décrit profil, endpoint, transport, référence d'authentification et missions. Son import natif et sa connexion réelle restent à vérifier. Ce contrat historique est distinct du nouveau lien d'assistance SSO ; un client MCP officiel est utilisé dans les tests des fonctions déjà publiées.

L'agent peut gérer fiches/affectations, sorties après validation humaine, retours, transferts, interventions, brouillons fournisseur, rappels et rapports. Les validations de réservations et de demandes fournisseur, ainsi que les remises en service, restent humaines.

## Contrôles de développement

```sh
.venv/bin/ruff check .
MATOS_DEBUG=1 .venv/bin/python -m compileall -q core epi dosimetry matos scripts
MATOS_DEBUG=1 .venv/bin/python manage.py check
MATOS_DEBUG=1 .venv/bin/python manage.py test core.tests epi.tests dosimetry.tests --noinput
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

La qualification isolée 0.2.0 est réussie sur YunoHost 12.1.41.2 **amd64** : installation/retrait/réinstallation, connexion SSO réelle et refus anonyme, assets, EPI et Paramètres → Modules, Dosimètres inactif refusé, upgrades même version et depuis 0.1.1/0.1.2, sauvegarde/restauration et changement de domaine ([preuve](https://github.com/arcenal-coder/arcenal-matos_ynh/actions/runs/38885952601)). `arm64` est déclaré compatible mais son installation n'a pas été exécutée. Les seuls constats critiques/d'erreur du linter officiel concernent l'inscription et l'état dans son catalogue officiel ; ils ne sont pas présentés comme une note communautaire 5. Le catalogue client ARCenal porte sa qualification technique 5, documentée séparément dans `TEST_REPORT.md`.

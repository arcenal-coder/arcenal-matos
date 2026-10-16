# ARCenal Matos 0.2.0 — preview

## Contenu

- Inventaire multisite, prêts, transferts, maintenances, imports et rapports conservés.
- Module **EPI** séparé : quantités/lots ou exemplaires, validités fabricant/première mise en service, demandes et remises partielles, dotations, destructions, coûts HT historiques réservés aux gestionnaires et administrateurs.
- Module **Dosimètres passifs** séparé : périodes/laboratoires, badges personnels et témoins, préaffectations, distribution, collecte, retours non portés, envois, pertes et remplacements. Aucun résultat de dose ; les appareils opérationnels restent dans le matériel général.
- **Paramètres → Modules** : activation indépendante, conservation des données, blocage réel des vues, opérations, rappels et fonctions MCP quand le module est désactivé.
- Agent IA via le MCP existant : propositions de validité EPI et préparations logistiques des badges. Les décisions de validation et les opérations physiques restent humaines.
- Comptes humains LDAP/SSO YunoHost, logo société transparent au-dessus du nom de l'application, thèmes clair/sombre/système et signature en pied de page.

## Première utilisation après mise à jour

1. Les rôles et sites existants sont conservés. L'administrateur vérifie les utilisateurs dans Paramètres.
2. EPI reste actif par défaut. Pour les dosimètres, ouvrir **Paramètres → Modules**, activer Dosimètres passifs et enregistrer.
3. Configurer les références EPI puis les réceptions ; pour les badges, configurer le laboratoire et la période avant réception/distribution.
4. Pour l'assistance, activer **Agent & MCP** et connecter l'agent avec le YAML actualisé et son secret privé configuré séparément. Activer une option ne lance pas un agent à elle seule.

Aucune fiche, dotation ou badge fictif n'est ajouté dans une installation YunoHost.

## Qualification et distribution

- Contrôles applicatifs et parcours locaux tracés dans TEST_REPORT.md.
- La candidate YunoHost est soumise au cycle de vie complet et à la mise à jour depuis 0.1.2~ynh1 avant promotion du catalogue preview.
- La publication ne réalise pas la mise à jour sur le serveur client et ne vaut pas recette d'une connexion Hermès, de la délivrance SMTP ou d'un téléphone réel.

## Sauvegarde et retour arrière

Conserver une sauvegarde YunoHost complète de la version installée avant la mise à jour, avec base de données, médias et configuration. Les nouvelles migrations sont additives, mais un retour arrière consiste à **restaurer cette sauvegarde complète avec la version précédente** ; changer seulement de révision Git ne restaure pas l'état métier et son schéma.

Les archives précédemment publiées ne sont ni écrasées ni remplacées. Les données des modules restent conservées lorsqu'ils sont simplement désactivés.

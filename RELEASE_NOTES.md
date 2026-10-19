# ARCenal Matos 0.2.1 — preview

## Liaison d’assistance avec ARCenal Agent

- Appariement sur le même serveur YunoHost avec **ARCenal Agent 0.22.2~ynh3**.
- Adresses et identifiants techniques préparés automatiquement par les paquets.
- Confirmation dans Matos, validation administrateur dans l’Agent, puis état
  **Liaison active** uniquement après vérification. Révocation dans chaque app.
- Bouton accessible **Demander à ARCenal Agent** dans Matériel, EPI et Dosimètres.
- Référence opaque à usage unique (60 secondes), identité SSO concordante et
  droits/rôle/module revérifiés dans Matos à réception.
- Assistance strictement en lecture seule, sans fiche ni document transmis.
  L’accueil valide le contexte ; il ne lance pas de conversation IA.
- Les fonctionnalités EPI, Dosimètres et MCP de 0.2.0 restent disponibles.

## Installation et première utilisation

1. Mettre à jour ARCenal Agent avec son paquet preview **0.22.2~ynh3**.
2. Mettre à jour Matos avec le paquet preview **0.2.1~ynh1**.
3. Dans Matos → Paramètres → Agent & MCP, confirmer la lecture seule et cliquer
   **Lier ARCenal Agent** ; valider dans l’Agent puis **Vérifier la liaison**.

L’identifiant YunoHost de l’Agent reste `arcenal`. Le dashboard natif Hermes,
ses configurations et conversations sont conservés. Aucun ancien broker ou
service d’administration ARC n’est réinstallé.

## Vérification et retour arrière

Contrôles et limites dans `TEST_REPORT.md`. Les essais locaux et CI ne valent pas
recette du serveur client. La publication ne réalise aucun déploiement.

Créer une sauvegarde YunoHost complète avant les mises à jour. En cas de retour
arrière, restaurer la sauvegarde avec le code, la base, les médias et la
configuration correspondants. Les migrations 0008/0009 sont additives.

Les archives 0.2.0 et antérieures restent immuables.

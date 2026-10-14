# Administration ARCenal Matos

La connexion humaine utilise YunoHost ; le compte choisi à l'installation reçoit le rôle administrateur. Attribuer les sites et profils depuis Organisation & profils. L'inventaire démarre vide.

Le serveur MCP est disponible sur `/mcp`, avec authentification technique Bearer. L'administrateur télécharge le YAML dans Agent & MCP. La valeur du paramètre YunoHost `mcp_token` doit être transmise au client par un canal privé et configurée dans `MATOS_MCP_TOKEN` côté Hermès ; elle n'est pas présente dans l'export YAML. Le YAML emploie un schéma ARCenal ; son import natif dans Hermès reste à vérifier.

Les rappels et envois validés passent par un timer systemd toutes les cinq minutes. Les e-mails utilisent le SMTP local YunoHost. L'état des demandes fournisseur et erreurs d'envoi est visible dans l'application. Les échecs sont réessayés jusqu'à cinq tentatives ; intervenir sur le transport avant de relancer une ligne échouée.

Les sauvegardes comprennent code/configuration, base et pièces jointes privées. Les fichiers de data_dir peuvent être exclus des sauvegardes de sécurité d'upgrade par YunoHost : prévoir une sauvegarde complète avant une opération affectant les documents.

Cette bêta doit être vérifiée sur une instance YunoHost d'essai : installation, SSO/LDAP, SMTP, suppression, mise à jour, sauvegarde et restauration. Le modèle n'est pas une preuve de cycle de vie réussi.

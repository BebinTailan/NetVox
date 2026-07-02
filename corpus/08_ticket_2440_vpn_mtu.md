---
titre: Ticket #2440 (résolu) — Déconnexions VPN répétées en télétravail
type: ticket résolu
---
Description : plusieurs télétravailleurs signalent des déconnexions VPN toutes les quelques minutes, surtout lors de transferts de fichiers volumineux.

Investigation : les déconnexions coïncidaient avec des paquets volumineux rejetés. Problème de MTU : la valeur par défaut (1500) provoquait de la fragmentation sur certaines box opérateur.

Résolution : abaissement de la MTU de l'interface VPN à 1400 dans le profil client, déployé via le gestionnaire de configuration. Plus aucune coupure constatée après déploiement.

Prévention : intégrer la MTU 1400 au profil VPN standard pour les nouveaux postes.

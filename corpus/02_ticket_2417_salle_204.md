---
titre: Ticket #2417 (résolu) — Salle 204 : perte totale d'Internet
type: ticket résolu
---
Description : les utilisateurs de la salle 204 signalent une perte totale d'accès Internet depuis le matin. Les postes obtiennent une adresse IP mais aucun trafic ne sort.

Investigation : le port du switch d'étage (baie B2, switch SW-ET2-01, port 14) desservant la salle 204 était passé en état err-disabled suite à une détection de boucle réseau (un utilisateur avait branché les deux extrémités d'un câble sur deux prises murales de la salle).

Résolution : débranchement du câble en boucle, puis réactivation du port avec shutdown / no shutdown sur l'interface. Vérification que le spanning-tree (STP) était bien actif sur le switch.

Prévention : sensibiliser les utilisateurs à ne pas brancher de câble entre deux prises murales. Vérifier l'activation de bpduguard sur les ports d'accès.

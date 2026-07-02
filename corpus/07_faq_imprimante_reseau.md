---
titre: FAQ — L'imprimante réseau est introuvable
type: faq
---
Question : l'imprimante réseau de l'étage n'apparaît plus ou les impressions restent bloquées en file d'attente.

Réponse : vérifier d'abord que l'imprimante est allumée et affiche une adresse IP sur son écran (menu réseau). Tester un ping vers cette adresse depuis le poste.

Si le ping échoue : redémarrer l'imprimante, vérifier son câble réseau, et contrôler que son adresse IP est bien celle réservée dans le DHCP (réservation par adresse MAC).

Si le ping répond mais l'impression échoue : redémarrer le spouleur d'impression sur le poste (services.msc → Spouleur d'impression), puis supprimer et réinstaller la file si nécessaire depuis le serveur d'impression SRV-PRINT-01.

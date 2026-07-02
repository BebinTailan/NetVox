---
titre: FAQ — Grésillements et coupures sur la téléphonie IP
type: faq
---
Question : les appels via les téléphones IP grésillent ou se coupent par moments.

Réponse : la voix sur IP est sensible à la perte de paquets et à la gigue. Vérifier que le téléphone est bien raccordé sur la prise dédiée et qu'il est placé dans le VLAN voix (VLAN 20).

Contrôler que la QoS est active sur le switch d'accès : la voix doit être marquée et prioritaire (DSCP EF). Un téléphone branché derrière un mini-switch non administré perd ce marquage.

Si un seul poste est concerné, remplacer le câble et tester sur une autre prise. Si tout un étage est concerné, vérifier la charge de la liaison montante du switch d'étage.

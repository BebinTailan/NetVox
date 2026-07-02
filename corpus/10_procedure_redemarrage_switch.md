---
titre: Procédure — Redémarrage contrôlé d'un switch d'étage
type: procédure
---
Contexte : à n'utiliser qu'en dernier recours, après validation du responsable réseau, lorsqu'un switch d'étage présente un comportement anormal généralisé (tous les postes de l'étage affectés).

Étape 1 — Prévenir les utilisateurs de l'étage de l'interruption (2 à 5 minutes).

Étape 2 — Sauvegarder la configuration courante : copy running-config startup-config, puis exporter une copie vers le serveur TFTP.

Étape 3 — Redémarrer le switch (reload) et chronométrer la remontée. Vérifier au retour : voyants, uplink vers le cœur de réseau, remontée des VLAN, et connectivité de deux postes témoins.

Étape 4 — Ouvrir un ticket de suivi et consigner l'heure, la cause suspectée et le comportement après redémarrage.

---
titre: Procédure — Adresse IP en 169.254.x.x (APIPA) : DHCP défaillant
type: procédure
---
Contexte : une adresse en 169.254.x.x signifie que le poste n'a reçu aucune réponse du serveur DHCP et s'est auto-attribué une adresse (APIPA). Le poste n'a alors aucun accès au réseau.

Étape 1 — Vérifier si le problème touche un seul poste ou plusieurs. Si plusieurs postes du même étage sont concernés, suspecter le relais DHCP du switch ou le serveur DHCP lui-même.

Étape 2 — Sur un poste isolé : tester une autre prise murale, tester un autre câble, forcer le renouvellement avec ipconfig /release et ipconfig /renew.

Étape 3 — Vérifier l'état du serveur DHCP (SRV-DHCP-01) : service démarré, étendue non saturée (taux d'occupation des baux visible dans la console DHCP).

Étape 4 — Si l'étendue est saturée, réduire la durée des baux ou élargir la plage après validation du responsable réseau.

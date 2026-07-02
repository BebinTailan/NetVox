---
titre: Procédure — Poste sans accès Internet (diagnostic de premier niveau)
type: procédure
---
Symptômes : un poste de travail n'a plus d'accès Internet alors que les autres postes du même segment fonctionnent.

Étape 1 — Vérifier le câblage physique : contrôler que le câble Ethernet est bien branché côté poste et côté prise murale. Vérifier le voyant de la carte réseau (doit être vert ou clignotant).

Étape 2 — Vérifier la configuration IP : ouvrir un invite de commandes et exécuter ipconfig /all. Contrôler que le poste a bien reçu une adresse IP du serveur DHCP (plage 10.x.x.x du site). Si l'adresse commence par 169.254, voir la procédure APIPA.

Étape 3 — Tester la connectivité : ping vers la passerelle par défaut, puis vers 8.8.8.8, puis vers un nom de domaine (ex. ping intranet.local). Si la passerelle répond mais pas le nom de domaine, suspecter un problème DNS.

Étape 4 — Renouveler le bail DHCP : ipconfig /release puis ipconfig /renew. Redémarrer le poste si nécessaire.

Étape 5 — Si le problème persiste, vérifier le port du switch d'étage correspondant à la prise murale (voir procédure baie de brassage) et escalader au niveau 2.

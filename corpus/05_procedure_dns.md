---
titre: Procédure — Résolution des problèmes DNS
type: procédure
---
Symptômes : la navigation échoue par nom de domaine mais les ping par adresse IP fonctionnent (ex. ping 8.8.8.8 répond, ping www.exemple.fr échoue).

Étape 1 — Identifier les serveurs DNS configurés : ipconfig /all (doivent pointer vers SRV-DNS-01 et SRV-DNS-02).

Étape 2 — Tester la résolution : nslookup intranet.local puis nslookup www.exemple.fr. Noter quel serveur répond et les éventuels délais.

Étape 3 — Vider le cache DNS local : ipconfig /flushdns.

Étape 4 — Si un seul serveur DNS est en cause, vérifier le service DNS sur ce serveur et basculer temporairement les postes sur le serveur secondaire.

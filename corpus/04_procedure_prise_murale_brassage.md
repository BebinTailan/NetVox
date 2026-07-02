---
titre: Procédure — Vérifier une prise murale et le brassage en baie
type: procédure
---
Objectif : confirmer qu'une prise réseau murale est correctement brassée et que le port du switch associé est opérationnel.

Étape 1 — Relever le numéro de la prise murale (étiquette, ex. B2-204-03) et identifier la baie de brassage de l'étage.

Étape 2 — Dans la baie, localiser le panneau de brassage correspondant et suivre le cordon jusqu'au port du switch. Mettre à jour le tableau de brassage si l'étiquetage est incohérent.

Étape 3 — Vérifier l'état du port sur le switch : show interface status. Un port en err-disabled ou administrativement down doit être analysé avant réactivation (cause : boucle, sécurité de port, etc.).

Étape 4 — Tester la prise avec un testeur de câble ou un poste de test. Si la liaison reste morte, suspecter le câblage horizontal et planifier une intervention câblage.

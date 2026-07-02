---
titre: Ticket #2389 (résolu) — Wi-Fi très lent au bâtiment B
type: ticket résolu
---
Description : débit Wi-Fi très dégradé au 1er étage du bâtiment B en fin de matinée, alors que le filaire fonctionne normalement.

Investigation : analyse du spectre depuis le contrôleur Wi-Fi. La borne AP-B1-03 émettait sur le canal 6 en 2,4 GHz, saturé par les bornes voisines et un équipement personnel (enceinte sans fil). Taux de réémission très élevé.

Résolution : passage de la borne sur le canal 11 et incitation des utilisateurs à privilégier le SSID 5 GHz. Débit redevenu normal.

Prévention : activer la sélection automatique de canal (RRM) sur le contrôleur et rappeler la charte sur les équipements personnels.

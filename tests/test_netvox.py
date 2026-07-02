#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests NetVox — exécutable sans clé API (l'API Mistral est simulée).
Lancement : python3 tests/test_netvox.py
"""
import json
import os
import sys
import threading
import urllib.request
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# Repartir d'un état propre (pas de cache, pas de docs ajoutés)
shutil.rmtree(os.path.join(BASE, "data"), ignore_errors=True)
os.makedirs(os.path.join(BASE, "data"), exist_ok=True)

import server  # noqa: E402

OK, KO = 0, 0
def check(nom, cond):
    global OK, KO
    print(("  ✓ " if cond else "  ✗ ") + nom)
    OK, KO = OK + int(bool(cond)), KO + int(not cond)

# ---------------------------------------------------------------------------
# Simulation de l'API Mistral
# ---------------------------------------------------------------------------
REPONSE_CHAT = json.dumps({
    "info_absente": False,
    "cause_probable": "Port du switch en err-disabled suite à une boucle réseau.",
    "etapes": ["Vérifier le port 14 du switch SW-ET2-01",
               "Débrancher le câble en boucle",
               "Réactiver le port (shutdown / no shutdown)"],
    "sources": ["D2.1"],
    "remarque": ""
})
server.appel_mistral_chat = lambda system, user: REPONSE_CHAT

# ---------------------------------------------------------------------------
# 1. Indexation en mode fallback TF-IDF (clé absente → parcours dégradé)
# ---------------------------------------------------------------------------
print("\n[1] Indexation (fallback TF-IDF, sans clé API)")
server.MISTRAL_KEY = ""
server.indexer()
check("mode = tfidf", server.MODE == "tfidf")
check("10 documents chargés", len(server.CORPUS) == 10)
check("fragments > 15", len(server.CHUNKS) > 15)
check("tous les fragments vectorisés", all("vec" in c for c in server.CHUNKS))

# ---------------------------------------------------------------------------
# 2. Recherche vectorielle : cas couverts et hors base
# ---------------------------------------------------------------------------
print("\n[2] Recherche par similarité cosinus")
hits, seuil = server.rechercher("le poste de la salle 204 n'a plus internet depuis ce matin")
check("salle 204 → ticket #2417 en tête", hits and "2417" in hits[0]["chunk"]["doc_titre"])
check("score au-dessus du seuil", hits and hits[0]["score"] >= seuil)

hits2, seuil2 = server.rechercher("adresse IP en 169.254 impossible d'accéder au réseau")
check("APIPA → doc DHCP/APIPA dans le top 2",
      any("APIPA" in h["chunk"]["doc_titre"] for h in hits2[:2]))

hits3, seuil3 = server.rechercher("la messagerie Exchange refuse d'envoyer les mails depuis hier")
check("Exchange → sous le seuil (info absente)",
      not hits3 or hits3[0]["score"] < seuil3)

# ---------------------------------------------------------------------------
# 3. Garde-fous du diagnostic
# ---------------------------------------------------------------------------
print("\n[3] Génération et garde-fous")
d = server.generer_diagnostic("le poste de la salle 204 n'a plus internet")
check("statut ok", d["statut"] == "ok")
check("cause probable présente", bool(d["cause_probable"]))
check("3 étapes", len(d["etapes"]) == 3)
check("source D2.1 validée (id existant)", d["sources_utilisees"] == ["D2.1"])
check("sources tracées avec scores", all("score" in s for s in d["sources"]))

d2 = server.generer_diagnostic("la messagerie Exchange refuse d'envoyer les mails")
check("hors base → statut absent SANS appel LLM", d2["statut"] == "absent")

# Garde-fou n°2 : le LLM signale lui-même l'insuffisance
server.appel_mistral_chat = lambda s, u: json.dumps(
    {"info_absente": True, "cause_probable": "", "etapes": [], "sources": [],
     "remarque": "Les extraits ne couvrent pas la messagerie."})
d3 = server.generer_diagnostic("le poste de la salle 204 a un souci de réseau et de mails")
check("LLM info_absente=true → statut absent", d3["statut"] == "absent")
server.appel_mistral_chat = lambda system, user: REPONSE_CHAT

# LLM qui invente un identifiant de source → filtré
server.appel_mistral_chat = lambda s, u: json.dumps(
    {"info_absente": False, "cause_probable": "x", "etapes": ["a", "b", "c"],
     "sources": ["D2.1", "D99.9"], "remarque": ""})
d4 = server.generer_diagnostic("salle 204 plus internet")
check("source inventée D99.9 filtrée", d4["sources_utilisees"] == ["D2.1"])
server.appel_mistral_chat = lambda system, user: REPONSE_CHAT

# ---------------------------------------------------------------------------
# 4. Serveur HTTP de bout en bout
# ---------------------------------------------------------------------------
print("\n[4] Endpoints HTTP")
from http.server import HTTPServer  # noqa: E402
httpd = HTTPServer(("127.0.0.1", 8791), server.NetVoxHandler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()

def get(chemin):
    with urllib.request.urlopen(f"http://127.0.0.1:8791{chemin}", timeout=10) as r:
        return r.status, json.loads(r.read().decode()) if "api" in chemin else r.read().decode()

def post(chemin, payload):
    req = urllib.request.Request(f"http://127.0.0.1:8791{chemin}",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

code, page = get("/")
check("GET / sert le frontend", code == 200 and "NetVox" in page)
code, statut = get("/api/status")
check("GET /api/status", code == 200 and statut["documents"] == 10)
code, docs = get("/api/documents")
check("GET /api/documents : corpus consultable", code == 200 and len(docs["documents"]) == 10)
check("contenu intégral exposé", all(d["contenu"] for d in docs["documents"]))

code, diag = post("/api/diagnostic", {"demande": "le poste de la salle 204 n'a plus internet"})
check("POST /api/diagnostic → ok", code == 200 and diag["statut"] == "ok")
code, diag2 = post("/api/diagnostic", {"demande": "la messagerie Exchange refuse d'envoyer les mails"})
check("POST /api/diagnostic hors base → absent", code == 200 and diag2["statut"] == "absent")
code, _ = post("/api/diagnostic", {"demande": ""})
check("demande vide → 400", code == 400)

# Ajout à chaud puis interrogation immédiate
code, rep = post("/api/documents", {
    "titre": "Procédure — Panne messagerie Exchange",
    "type": "procédure",
    "contenu": "Symptômes : la messagerie Exchange refuse d'envoyer les mails.\n\nÉtape 1 — Vérifier le service de transport Exchange sur SRV-MAIL-01.\n\nÉtape 2 — Contrôler la file d'attente SMTP et l'espace disque de la base."})
check("POST /api/documents : ajout à chaud", code == 200 and rep["documents"] == 11)
hits4, seuil4 = server.rechercher("la messagerie Exchange refuse d'envoyer les mails")
check("le nouveau doc est immédiatement trouvé",
      hits4 and "Exchange" in hits4[0]["chunk"]["doc_titre"] and hits4[0]["score"] >= seuil4)
code, _ = post("/api/documents", {"titre": "", "contenu": ""})
check("ajout invalide → 400", code == 400)

httpd.shutdown()

# ---------------------------------------------------------------------------
print(f"\nRésultat : {OK} réussis, {KO} échoués")
sys.exit(1 if KO else 0)

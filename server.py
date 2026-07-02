#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NetVox — Assistant de diagnostic réseau par la voix avec RAG documentaire.

Backend : bibliothèque standard Python uniquement (aucun pip install).
- Sert le frontend (static/index.html)
- Indexe le corpus (chunking + embeddings Mistral, avec cache local)
- Recherche vectorielle par similarité cosinus
- Génération du diagnostic via Mistral, contrainte aux extraits récupérés
- Fallback TF-IDF automatique si l'API d'embeddings est injoignable

Lancement :  python3 server.py   puis ouvrir http://localhost:8787
"""

import base64
import io
import json
import hashlib
import math
import os
import re
import sys
import unicodedata
import urllib.request
import urllib.error
import uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS_DIR = os.path.join(BASE_DIR, "corpus")
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
CACHE_FILE = os.path.join(DATA_DIR, "embeddings_cache.json")
DOCS_AJOUTES_FILE = os.path.join(DATA_DIR, "docs_ajoutes.json")  # ancien format, lu une fois à la migration
DOCUMENTS_FILE = os.path.join(DATA_DIR, "documents.json")

with open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8") as f:
    CONFIG = json.load(f)

MISTRAL_KEY = CONFIG.get("mistral_api_key", "").strip()
MODELE_CHAT = CONFIG.get("modele_chat", "mistral-small-latest")
MODELE_EMBED = CONFIG.get("modele_embeddings", "mistral-embed")
SEUIL = float(CONFIG.get("seuil_pertinence", 0.70))
SEUIL_TFIDF = float(CONFIG.get("seuil_pertinence_tfidf", 0.12))
PORT = int(CONFIG.get("port", 8787))
TOP_K = int(CONFIG.get("top_k", 4))

# ---------------------------------------------------------------------------
# Appels API Mistral (urllib, sans dépendance)
# ---------------------------------------------------------------------------
def _post_mistral(endpoint: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"https://api.mistral.ai/v1/{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MISTRAL_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as rep:
        return json.loads(rep.read().decode("utf-8"))


def appel_mistral_embed(textes: list) -> list:
    """Retourne un vecteur d'embedding par texte (mistral-embed, 1024 dim)."""
    data = _post_mistral("embeddings", {"model": MODELE_EMBED, "input": textes})
    tries = sorted(data["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in tries]


def appel_mistral_chat(system: str, user: str) -> str:
    data = _post_mistral("chat/completions", {
        "model": MODELE_CHAT,
        "temperature": 0.2,
        "max_tokens": 1000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    })
    return data["choices"][0]["message"]["content"]

# ---------------------------------------------------------------------------
# Corpus : chargement + chunking
# ---------------------------------------------------------------------------
def _parser_md(chemin: str) -> dict:
    """Lit un fichier markdown avec front-matter (titre / type)."""
    with open(chemin, encoding="utf-8") as f:
        brut = f.read()
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", brut, re.S)
    meta, corps = {}, brut
    if m:
        for ligne in m.group(1).splitlines():
            if ":" in ligne:
                k, v = ligne.split(":", 1)
                meta[k.strip()] = v.strip()
        corps = m.group(2).strip()
    return {
        "titre": meta.get("titre", os.path.basename(chemin)),
        "type": meta.get("type", "document"),
        "contenu": corps,
        "fichier": os.path.basename(chemin),
    }


def _nouvel_id() -> str:
    return uuid.uuid4().hex[:12]


def _sauver_documents(docs: list) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DOCUMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=1)


def _migrer_documents() -> list:
    """Construit le store unifié data/documents.json à partir du corpus initial
    (et de l'ancien data/docs_ajoutes.json s'il existe). Ne s'exécute qu'une fois :
    au premier lancement, ou si documents.json a été supprimé."""
    docs = []
    for nom in sorted(os.listdir(CORPUS_DIR)):
        if nom.endswith(".md"):
            d = _parser_md(os.path.join(CORPUS_DIR, nom))
            d["id"] = _nouvel_id()
            d["origine"] = "corpus"
            docs.append(d)
    if os.path.exists(DOCS_AJOUTES_FILE):
        with open(DOCS_AJOUTES_FILE, encoding="utf-8") as f:
            for d in json.load(f):
                docs.append({
                    "id": _nouvel_id(), "titre": d["titre"], "type": d["type"],
                    "contenu": d["contenu"], "origine": "ajoute", "fichier": None,
                })
    _sauver_documents(docs)
    return docs


def charger_documents() -> list:
    if not os.path.exists(DOCUMENTS_FILE):
        return _migrer_documents()
    with open(DOCUMENTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def chunker(doc: dict, doc_index: int, taille_max: int = 450) -> list:
    """Découpe un document en fragments (~450 caractères, par paragraphes)."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", doc["contenu"]) if p.strip()]
    morceaux, buf = [], ""
    for p in paras:
        if buf and len(buf) + len(p) > taille_max:
            morceaux.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        morceaux.append(buf)
    return [{
        "cid": f"D{doc_index + 1}.{i + 1}",
        "doc_index": doc_index,
        "doc_titre": doc["titre"],
        "doc_type": doc["type"],
        "texte": t,
    } for i, t in enumerate(morceaux)]

# ---------------------------------------------------------------------------
# Index vectoriel : embeddings Mistral (avec cache) OU fallback TF-IDF
# ---------------------------------------------------------------------------
CORPUS: list = []
CHUNKS: list = []
MODE = "embeddings"          # "embeddings" | "tfidf"
IDF: dict = {}

STOPWORDS = set(("le la les un une des du de d l au aux et ou mais donc or ni car a à dans en "
                 "sur sous vers chez par pour sans avec ce cet cette ces son sa ses leur leurs "
                 "mon ma mes ton ta tes notre nos votre vos qui que quoi dont où est sont était "
                 "été être avoir ai as avons avez ont il elle ils elles on nous vous je tu ne pas "
                 "plus moins très bien tout tous toute toutes autre autres même si alors ainsi "
                 "comme lors depuis entre puis aussi cela ça ceci fait faire faut peut peuvent "
                 "doit doivent après avant pendant lorsque quand chaque quelques deux trois ex etc").split())


def normaliser(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tokeniser(s: str) -> list:
    return [t for t in re.split(r"[^a-z0-9]+", normaliser(s))
            if len(t) > 2 and t not in STOPWORDS]


def _hash(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _charger_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _sauver_cache(cache: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def _embedder_chunks(chunks: list) -> None:
    """Attache un embedding à chaque chunk, via le cache puis l'API par lots."""
    cache = _charger_cache()
    manquants = [c for c in chunks if _hash(c["doc_titre"] + "\n" + c["texte"]) not in cache]
    for i in range(0, len(manquants), 32):                     # lots de 32
        lot = manquants[i:i + 32]
        vecteurs = appel_mistral_embed([c["doc_titre"] + "\n" + c["texte"] for c in lot])
        for c, v in zip(lot, vecteurs):
            cache[_hash(c["doc_titre"] + "\n" + c["texte"])] = v
    if manquants:
        _sauver_cache(cache)
    for c in chunks:
        c["vec"] = cache[_hash(c["doc_titre"] + "\n" + c["texte"])]
        c["norm"] = math.sqrt(sum(x * x for x in c["vec"])) or 1.0


def _indexer_tfidf(chunks: list) -> None:
    global IDF
    for c in chunks:
        c["tokens"] = tokeniser(c["doc_titre"] + " " + c["texte"])
    n = len(chunks)
    df: dict = {}
    for c in chunks:
        for t in set(c["tokens"]):
            df[t] = df.get(t, 0) + 1
    IDF = {t: math.log((n + 1) / (v + 1)) + 1 for t, v in df.items()}
    for c in chunks:
        tf: dict = {}
        for t in c["tokens"]:
            tf[t] = tf.get(t, 0) + 1
        vec = {t: (f / len(c["tokens"])) * IDF[t] for t, f in tf.items()}
        c["vec"] = vec
        c["norm"] = math.sqrt(sum(w * w for w in vec.values())) or 1.0


def indexer() -> None:
    """(Re)construit l'index complet. Bascule en TF-IDF si l'API échoue."""
    global CORPUS, CHUNKS, MODE
    CORPUS = charger_documents()
    CHUNKS = []
    for i, doc in enumerate(CORPUS):
        CHUNKS.extend(chunker(doc, i))
    if MISTRAL_KEY:
        try:
            _embedder_chunks(CHUNKS)
            MODE = "embeddings"
            return
        except Exception as e:                                  # noqa: BLE001
            print(f"[NetVox] Embeddings Mistral indisponibles ({e}) → fallback TF-IDF", file=sys.stderr)
    else:
        print("[NetVox] Aucune clé API dans config.json → mode TF-IDF", file=sys.stderr)
    MODE = "tfidf"
    _indexer_tfidf(CHUNKS)


def _cos_dense(q: list, c: dict) -> float:
    dot = sum(a * b for a, b in zip(q, c["vec"]))
    nq = math.sqrt(sum(a * a for a in q)) or 1.0
    return dot / (nq * c["norm"])


def _cos_sparse(qvec: dict, qnorm: float, c: dict) -> float:
    dot = sum(w * c["vec"].get(t, 0.0) for t, w in qvec.items())
    return dot / (qnorm * c["norm"])


def rechercher(demande: str, k: int = TOP_K) -> tuple:
    """Retourne (résultats triés, seuil applicable). Chaque résultat : {chunk, score}."""
    if MODE == "embeddings":
        try:
            qv = appel_mistral_embed([demande])[0]
            res = [{"chunk": c, "score": _cos_dense(qv, c)} for c in CHUNKS]
            res.sort(key=lambda r: r["score"], reverse=True)
            return res[:k], SEUIL
        except Exception as e:                                  # noqa: BLE001
            print(f"[NetVox] Embedding requête impossible ({e}) → TF-IDF ponctuel", file=sys.stderr)
            if not IDF:
                _indexer_tfidf(CHUNKS)
    toks = tokeniser(demande)
    tf: dict = {}
    for t in toks:
        tf[t] = tf.get(t, 0) + 1
    qvec = {t: (f / max(len(toks), 1)) * IDF.get(t, 0.0) for t, f in tf.items()}
    qvec = {t: w for t, w in qvec.items() if w > 0}
    qnorm = math.sqrt(sum(w * w for w in qvec.values())) or 1.0
    if not qvec:
        return [], SEUIL_TFIDF
    res = [{"chunk": c, "score": _cos_sparse(qvec, qnorm, c)} for c in CHUNKS if "tokens" in c]
    res = [r for r in res if r["score"] > 0]
    res.sort(key=lambda r: r["score"], reverse=True)
    return res[:k], SEUIL_TFIDF


# ---------------------------------------------------------------------------
# Génération du diagnostic (LLM contraint aux extraits)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Tu es un assistant de diagnostic pour techniciens réseau.
Règle absolue : tu réponds UNIQUEMENT à partir des extraits documentaires fournis, jamais à partir de tes connaissances générales. Si les extraits ne permettent pas de diagnostiquer le problème décrit, tu dois le dire.
Tu réponds UNIQUEMENT en JSON valide selon ce schéma exact :
{"info_absente": false, "cause_probable": "...", "etapes": ["...", "..."], "sources": ["D1.2", "D3.1"], "remarque": "..."}
- "sources" : identifiants des extraits réellement utilisés (uniquement parmi ceux fournis).
- "etapes" : 3 à 6 étapes concrètes, reprises des extraits.
- "remarque" : optionnelle (précaution, escalade). Chaîne vide sinon.
- Si les extraits ne couvrent pas le problème décrit : {"info_absente": true, "cause_probable": "", "etapes": [], "sources": [], "remarque": "explique brièvement ce qui manque"}"""


def generer_diagnostic(demande: str) -> dict:
    hits, seuil = rechercher(demande)
    sources_payload = [{
        "cid": h["chunk"]["cid"],
        "titre": h["chunk"]["doc_titre"],
        "type": h["chunk"]["doc_type"],
        "score": round(h["score"], 4),
        "texte": h["chunk"]["texte"],
    } for h in hits]

    # Garde-fou n°1 : score de similarité trop faible → information absente
    if not hits or hits[0]["score"] < seuil:
        return {"statut": "absent", "mode": MODE, "seuil": seuil,
                "sources": sources_payload,
                "remarque": "Aucun document de la base ne dépasse le seuil de pertinence."}

    extraits = "\n\n---\n\n".join(
        f"[{h['chunk']['cid']}] {h['chunk']['doc_titre']} ({h['chunk']['doc_type']})\n{h['chunk']['texte']}"
        for h in hits)
    user = f'Demande du technicien : "{demande}"\n\nExtraits de la base de connaissance :\n\n{extraits}'

    brut = appel_mistral_chat(SYSTEM_PROMPT, user)
    brut = re.sub(r"```json|```", "", brut).strip()
    diag = json.loads(brut)

    # Garde-fou n°2 : le LLM juge lui-même les extraits insuffisants
    if diag.get("info_absente"):
        return {"statut": "absent", "mode": MODE, "seuil": seuil,
                "sources": sources_payload,
                "remarque": diag.get("remarque", "")}

    cids_valides = {s["cid"] for s in sources_payload}
    return {"statut": "ok", "mode": MODE, "seuil": seuil,
            "cause_probable": diag.get("cause_probable", ""),
            "etapes": diag.get("etapes", []),
            "sources_utilisees": [c for c in diag.get("sources", []) if c in cids_valides],
            "remarque": diag.get("remarque", ""),
            "sources": sources_payload}

# ---------------------------------------------------------------------------
# Gestion des documents à chaud : ajout, édition, suppression, import PDF
# ---------------------------------------------------------------------------
def ajouter_document(titre: str, type_doc: str, contenu: str, origine: str = "ajoute") -> dict:
    docs = charger_documents()
    docs.append({"id": _nouvel_id(), "titre": titre, "type": type_doc, "contenu": contenu,
                 "origine": origine, "fichier": None})
    _sauver_documents(docs)
    indexer()   # réindexation immédiate (les embeddings existants sortent du cache)
    return {"ok": True, "documents": len(CORPUS), "fragments": len(CHUNKS)}


def modifier_document(doc_id: str, titre: str, type_doc: str, contenu: str) -> dict:
    docs = charger_documents()
    for d in docs:
        if d["id"] == doc_id:
            d["titre"], d["type"], d["contenu"] = titre, type_doc, contenu
            break
    else:
        raise ValueError("Document introuvable")
    _sauver_documents(docs)
    indexer()
    return {"ok": True, "documents": len(CORPUS), "fragments": len(CHUNKS)}


def supprimer_document(doc_id: str) -> dict:
    docs = charger_documents()
    restants = [d for d in docs if d["id"] != doc_id]
    if len(restants) == len(docs):
        raise ValueError("Document introuvable")
    _sauver_documents(restants)
    indexer()
    return {"ok": True, "documents": len(CORPUS), "fragments": len(CHUNKS)}


def pdf_vers_markdown(pdf_bytes: bytes) -> str:
    """Extrait le texte d'un PDF (via pypdf) et le reformate en paragraphes markdown."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError("pypdf n'est pas installé — lancez : pip install -r requirements.txt") from e
    lecteur = PdfReader(io.BytesIO(pdf_bytes))
    pages = [(page.extract_text() or "").strip() for page in lecteur.pages]
    brut = "\n\n".join(p for p in pages if p)
    paragraphes = [re.sub(r"[ \t]+", " ", p).strip() for p in re.split(r"\n\s*\n", brut)]
    return "\n\n".join(p for p in paragraphes if p)

# ---------------------------------------------------------------------------
# Serveur HTTP
# ---------------------------------------------------------------------------
class NetVoxHandler(BaseHTTPRequestHandler):

    def _json(self, code: int, payload: dict) -> None:
        corps = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def _fichier(self, chemin: str, mime: str) -> None:
        try:
            with open(chemin, "rb") as f:
                corps = f.read()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def do_GET(self):                                           # noqa: N802
        if self.path in ("/", "/index.html"):
            self._fichier(os.path.join(STATIC_DIR, "index.html"), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            self._json(200, {"mode": MODE, "modele_chat": MODELE_CHAT,
                             "modele_embeddings": MODELE_EMBED if MODE == "embeddings" else None,
                             "seuil": SEUIL if MODE == "embeddings" else SEUIL_TFIDF,
                             "documents": len(CORPUS), "fragments": len(CHUNKS)})
        elif self.path == "/api/documents":
            docs = []
            for i, d in enumerate(CORPUS):
                cids = [c["cid"] for c in CHUNKS if c["doc_index"] == i]
                docs.append({"id": d["id"], "titre": d["titre"], "type": d["type"],
                             "contenu": d["contenu"], "fichier": d.get("fichier"),
                             "origine": d.get("origine", "ajoute"), "fragments": cids})
            self._json(200, {"documents": docs})
        else:
            self.send_error(404)

    def do_POST(self):                                          # noqa: N802
        longueur = int(self.headers.get("Content-Length", 0))
        try:
            corps = json.loads(self.rfile.read(longueur).decode("utf-8")) if longueur else {}
        except json.JSONDecodeError:
            self._json(400, {"erreur": "JSON invalide"})
            return

        if self.path == "/api/diagnostic":
            demande = (corps.get("demande") or "").strip()
            if not demande:
                self._json(400, {"erreur": "Champ 'demande' requis"})
                return
            try:
                self._json(200, generer_diagnostic(demande))
            except Exception as e:                              # noqa: BLE001
                self._json(502, {"erreur": f"Échec de la génération : {e}"})

        elif self.path == "/api/documents":
            titre = (corps.get("titre") or "").strip()
            type_doc = (corps.get("type") or "document").strip()
            contenu = (corps.get("contenu") or "").strip()
            if not titre or not contenu:
                self._json(400, {"erreur": "Titre et contenu requis"})
                return
            try:
                self._json(200, ajouter_document(titre, type_doc, contenu))
            except Exception as e:                              # noqa: BLE001
                self._json(502, {"erreur": f"Échec de l'indexation : {e}"})

        elif self.path == "/api/documents/pdf":
            titre = (corps.get("titre") or "").strip()
            type_doc = (corps.get("type") or "document").strip()
            pdf_b64 = corps.get("pdf_base64") or ""
            if not titre or not pdf_b64:
                self._json(400, {"erreur": "Titre et fichier PDF requis"})
                return
            try:
                pdf_bytes = base64.b64decode(pdf_b64)
                contenu = pdf_vers_markdown(pdf_bytes)
                if not contenu:
                    self._json(400, {"erreur": "Aucun texte extrait du PDF (PDF scanné/image non supporté)"})
                    return
                self._json(200, ajouter_document(titre, type_doc, contenu, origine="pdf"))
            except Exception as e:                              # noqa: BLE001
                self._json(502, {"erreur": f"Échec de l'import PDF : {e}"})
        else:
            self.send_error(404)

    def do_PUT(self):                                           # noqa: N802
        longueur = int(self.headers.get("Content-Length", 0))
        try:
            corps = json.loads(self.rfile.read(longueur).decode("utf-8")) if longueur else {}
        except json.JSONDecodeError:
            self._json(400, {"erreur": "JSON invalide"})
            return

        if self.path.startswith("/api/documents/"):
            doc_id = self.path[len("/api/documents/"):]
            titre = (corps.get("titre") or "").strip()
            type_doc = (corps.get("type") or "document").strip()
            contenu = (corps.get("contenu") or "").strip()
            if not titre or not contenu:
                self._json(400, {"erreur": "Titre et contenu requis"})
                return
            try:
                self._json(200, modifier_document(doc_id, titre, type_doc, contenu))
            except ValueError as e:
                self._json(404, {"erreur": str(e)})
            except Exception as e:                              # noqa: BLE001
                self._json(502, {"erreur": f"Échec de la modification : {e}"})
        else:
            self.send_error(404)

    def do_DELETE(self):                                        # noqa: N802
        if self.path.startswith("/api/documents/"):
            doc_id = self.path[len("/api/documents/"):]
            try:
                self._json(200, supprimer_document(doc_id))
            except ValueError as e:
                self._json(404, {"erreur": str(e)})
            except Exception as e:                              # noqa: BLE001
                self._json(502, {"erreur": f"Échec de la suppression : {e}"})
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):                          # journal compact
        print(f"[NetVox] {self.address_string()} {fmt % args}")


def main() -> None:
    print("[NetVox] Indexation du corpus…")
    indexer()
    print(f"[NetVox] {len(CORPUS)} documents, {len(CHUNKS)} fragments — mode : {MODE}")
    print(f"[NetVox] Prêt → http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), NetVoxHandler).serve_forever()


if __name__ == "__main__":
    main()

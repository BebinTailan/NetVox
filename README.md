# NetVox — Assistant de diagnostic réseau par la voix avec RAG documentaire

Décrivez un incident réseau à l'oral. L'application transcrit la demande, recherche les
extraits les plus pertinents dans une base de connaissance interne (procédures, tickets
résolus, FAQ), puis génère un diagnostic structuré **exclusivement à partir de ces
extraits** — sources affichées, refus honnête si l'information est absente de la base.

## Lancement (aucune installation)

Prérequis : Python 3.8+ et un navigateur Chrome ou Edge (pour la reconnaissance vocale).

```bash
python3 server.py
```

Puis ouvrir **http://localhost:8787**

Au premier lancement, le serveur vectorise le corpus via l'API d'embeddings Mistral et
met les vecteurs en cache (`data/embeddings_cache.json`) : les lancements suivants sont
instantanés et gratuits.

> ⚠️ **Clé API** : elle est dans `config.json`, côté serveur uniquement (jamais exposée
> au navigateur). Ne jamais committer ce fichier sur un dépôt public, et régénérer la
> clé sur console.mistral.ai après le hackathon.

## Scénario de démonstration (exigé par le sujet)

1. **Cas couvert** — dire ou cliquer : *« Le poste de la salle 204 n'a plus internet
   depuis ce matin »* → le ticket résolu #2417 remonte en tête, le diagnostic cite ses
   étapes, les sources utilisées sont marquées ✓.
2. **Cas hors base** — *« La messagerie Exchange refuse d'envoyer les mails »* → le
   système affiche « information absente de la base » au lieu d'inventer.
3. **Bonus enchaîné** — ajouter à chaud une « Procédure — Panne messagerie Exchange »
   dans l'onglet Base documentaire, relancer la même demande : elle est maintenant
   diagnostiquée. Démonstration parfaite du RAG devant le jury.

## Architecture

```
Navigateur (static/index.html)                    Serveur local (server.py, stdlib)
┌─────────────────────────────┐                  ┌──────────────────────────────────┐
│ 1. Web Speech API (fr-FR)   │  POST            │ 3. Embedding de la requête       │
│    voix → texte             │  /api/diagnostic │    (mistral-embed, 1024 dim)     │
│ 2. Envoi de la demande      │ ───────────────► │ 4. Similarité cosinus vs chunks  │
│                             │                  │ 5. Seuil de pertinence (0,70)    │
│ 7. Affichage : cause,       │ ◄─────────────── │ 6. LLM contraint aux extraits    │
│    étapes, sources, scores  │  JSON            │    (mistral-small, JSON forcé)   │
│    + synthèse vocale        │                  │                                  │
└─────────────────────────────┘                  └──────────────────────────────────┘
                                                  Index : corpus/*.md → chunking →
                                                  embeddings (cache local JSON)
```

- **Frontend** : un seul fichier HTML/CSS/JS, capture vocale, pipeline visuel des trois
  étapes, historique persistant (localStorage), synthèse vocale du diagnostic.
- **Backend** : Python **bibliothèque standard uniquement** (http.server, urllib) —
  aucune dépendance à installer. Il sert le frontend, indexe le corpus, interroge
  Mistral, et protège la clé API.
- **Stockage** : fichiers JSON simples (`data/embeddings_cache.json`,
  `data/docs_ajoutes.json`) — conforme à la contrainte « base simple ».

### Endpoints

| Méthode | Route             | Rôle                                              |
|---------|-------------------|---------------------------------------------------|
| GET     | `/`               | Frontend                                          |
| GET     | `/api/status`     | Mode d'indexation, modèles, seuil, compteurs      |
| GET     | `/api/documents`  | Corpus intégral (consultable, exigé par le sujet) |
| POST    | `/api/diagnostic` | `{demande}` → diagnostic sourcé ou « absent »     |
| POST    | `/api/documents`  | Ajout d'un document à chaud + réindexation        |

## La chaîne RAG en détail (pour la présentation)

**Qu'est-ce que le RAG ?** Retrieval-Augmented Generation : au lieu de laisser le LLM
répondre depuis ses connaissances générales (risque d'hallucination, connaissances
figées), on **récupère** d'abord les passages pertinents d'une base documentaire, on les
**injecte** dans le prompt, et on contraint le modèle à ne répondre **que** depuis ces
passages. Le LLM devient un rédacteur de synthèse, pas une source de vérité.

**Notre implémentation, étape par étape :**

1. **Chunking** — chaque document (`corpus/*.md`) est découpé par paragraphes,
   regroupés en fragments d'environ 450 caractères. Le titre du document est préfixé à
   chaque fragment pour préserver le contexte. Chaque fragment reçoit un identifiant
   traçable (`D2.1` = document 2, fragment 1).
2. **Embeddings** — chaque fragment est transformé en vecteur de 1024 dimensions par
   `mistral-embed` (appels par lots de 32, cache local par hash SHA-256 du texte :
   on ne paie jamais deux fois le même fragment).
3. **Recherche** — la requête utilisateur est vectorisée de la même façon, puis
   comparée à tous les fragments par **similarité cosinus**. Les 4 meilleurs sont
   retenus.
4. **Double garde-fou anti-hallucination** (vérifiable en démo) :
   - *Seuil de pertinence* : si le meilleur score est sous 0,70, le LLM n'est **même
     pas appelé** — le système répond « information absente ».
   - *Consigne stricte + auto-évaluation* : le system prompt interdit les connaissances
     générales et impose un JSON avec un champ `info_absente` que le modèle doit
     activer si les extraits ne couvrent pas le problème. Les identifiants de sources
     cités par le modèle sont revalidés côté serveur (un id inventé est filtré).
5. **Traçabilité** — chaque réponse affiche les extraits récupérés, leur score de
   similarité, et marque ✓ ceux réellement cités par le diagnostic.

**Limites du RAG (à assumer devant le jury) :**

- *Dépendance à la recherche* : si le bon document n'est pas retrouvé (vocabulaire trop
  différent, chunking qui coupe mal), le diagnostic sera absent ou incomplet.
- *Chunking naïf* : un découpage par taille peut séparer un symptôme de sa résolution.
  Améliorations possibles : chevauchement (overlap), découpage sémantique.
- *Seuil délicat* : trop bas → extraits hors sujet injectés ; trop haut → faux
  « information absente ». Notre seuil (0,70) est ajustable dans `config.json` et les
  scores sont affichés dans l'interface pour le calibrer en direct.
- *Pas de raisonnement multi-documents complexe* : le top-k plat ne gère pas les
  questions nécessitant de croiser de nombreux documents.

**Alternatives et évolutions :**

- *Recherche hybride* : combiner vectoriel + lexical (BM25) avec fusion des rangs —
  notre fallback TF-IDF intégré en est la brique lexicale.
- *Reranking* : re-trier les candidats avec un modèle croisé (cross-encoder).
- *Fine-tuning* : réentraîner le modèle sur le domaine — coûteux, connaissances figées,
  pas de traçabilité ; c'est précisément ce que le RAG évite.
- *Contexte long* : injecter toute la base dans le prompt — coûteux et moins précis dès
  que la base grossit ; non traçable finement.
- *Bases vectorielles dédiées* (FAISS, Chroma, Qdrant) : indispensables à grande
  échelle ; à notre échelle (dizaines de fragments), un JSON et un cosinus en pur
  Python sont suffisants et 100 % transparents pour l'explication.

**Choix pour la capture vocale :** l'API **Web Speech** (SpeechRecognition) du
navigateur : native, sans dépendance, streaming en temps réel, excellente en français.
Limites assumées : support complet surtout sur Chrome/Edge (la reconnaissance passe par
le service de Google, donc nécessite Internet), d'où deux filets de sécurité : une zone
de texte toujours éditable (correction ou saisie manuelle) et des messages d'erreur
explicites (micro refusé, aucune parole détectée…). L'alternative robuste serait une
transcription serveur type Whisper (fonctionne hors ligne et sur tous navigateurs, mais
ajoute une dépendance lourde et de la latence). La synthèse vocale du diagnostic
utilise l'API speechSynthesis, disponible partout.

**Robustesse :** si l'API d'embeddings est injoignable au démarrage ou en cours de
route, le serveur bascule automatiquement en recherche TF-IDF locale (badge visible
dans l'en-tête) — la démo ne peut pas mourir sur un problème réseau.

## Structure du projet

```
netvox/
├── server.py                  # Backend (stdlib uniquement)
├── config.json                # Clé API, modèles, seuils, port — NE PAS COMMITTER
├── README.md
├── corpus/                    # Base de connaissance : 10 documents fictifs (.md)
│   ├── 01_procedure_poste_sans_internet.md
│   ├── 02_ticket_2417_salle_204.md
│   └── …
├── static/
│   └── index.html             # Frontend complet (voix, UI, sources, historique)
├── data/                      # Créé à l'exécution
│   ├── embeddings_cache.json  # Cache des vecteurs (hash → embedding)
│   └── docs_ajoutes.json      # Documents ajoutés à chaud
└── tests/
    └── test_netvox.py         # 26 tests (API Mistral simulée) : python3 tests/test_netvox.py
```

## Tests

```bash
python3 tests/test_netvox.py
```

26 vérifications : indexation, recherche (cas couverts, cas hors base), les deux
garde-fous anti-hallucination, filtrage des sources inventées, tous les endpoints HTTP,
ajout à chaud avec interrogation immédiate. L'API Mistral y est simulée : les tests
tournent sans clé et sans réseau.

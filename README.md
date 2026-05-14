# FakeNews-XAI

**Detectarea explicabilă a inconsistențelor temporale în știrile politice folosind Grafuri de Cunoștințe Temporale și un scor de coerență (TCS).**

Lucrare de licență — Universitatea Tehnică din Cluj-Napoca (UTCN), Facultatea de Automatică și Calculatoare, 2026  
Autor: Marius Pantea | Coordonator: Prof. Adrian Groza | Co-coordonator: Conf. Ioana Cheres

---

## Descriere

Sistemul analizează articole de știri politice și calculează un **Temporal Coherence Score (TCS)** — o valoare în intervalul [0, 1] care cuantifică coerența temporală a articolului. Un scor ridicat indică un articol consistent; un scor scăzut semnalează inconsistențe temporale care sugerează dezinformare.

Pe lângă scor, sistemul generează:
- lista inconsistențelor detectate (tip, severitate, descriere)
- timeline cronologic a faptelor extrase
- explicație în limbaj natural generată de un LLM local (XAI)

---

## Arhitectură

```
Articol de știri politice
        |
        v
[C1 — Temporal Extraction]
  Pipeline A: spaCy en_core_web_trf  (deterministic, Precision=0.75)
  Pipeline B: Ollama llama3:8b        (LLM few-shot,  Recall=0.50)
        |
        v  TemporalFacts (subject, predicate, object, time)
        |
        v
[C2 — TKG Construction]
  TemporalKnowledgeGraph (networkx MultiDiGraph) — per articol
  Neo4j Community Edition             — persistent, cross-article
        |
        v  TKG
        |
        v
[C3 — Verification]
  C3a: InternalVerifier   — cicluri, violări cauzale, erori de ordonare (V1–V7)
  C3b: ExternalVerifier   — Wikidata SPARQL (P580/P582/P585) + Reference KG local
  C3c: CrossArticleVerifier — conflicte cu articole anterioare (via Neo4j)
        |
        v  Inconsistencies (type, severity)
        |
        v
[C4 — TCS Score Computation]
  TCS = raw_tcs + coverage_factor × (raw_tcs − 0.5) × 0.3
  raw_tcs = (1 − penalty_ratio) × score_coherence
  SEVERITY: LOW=0.2  MEDIUM=0.5  HIGH=1.0  CRITICAL=1.5
        |
        v
[XAI — LLM Explainer]
  llama3:8b generează explicație în limbaj natural
  Fallback: template-uri statice per tip de inconsistență
        |
        v
OUTPUT: TCS Score + Label + Inconsistency List + Timeline + AI Explanation
```

---

## Interpretarea scorului TCS

| Interval | Label | Semnificație |
|---|---|---|
| 0.8 – 1.0 | Highly Consistent (Likely True) | Fapte temporale coerente |
| 0.5 – 0.8 | Moderately Consistent | Inconsistențe minore |
| 0.2 – 0.5 | Multiple Inconsistencies (Suspicious) | Contradicții multiple |
| 0.0 – 0.2 | Severe Violations (Likely Fake) | Inconsistențe critice |
| = 0.5 (special) | Insufficient Temporal Data | 0 fapte temporale extrase |

---

## Rezultate evaluare (benchmark 84 articole, fără Wikidata)

| Metric | Pipeline A (spaCy) | Pipeline B (LLM) |
|---|---|---|
| Precision | 0.625 | — |
| Recall | 0.139 | — |
| F1 | 0.227 | — |
| Accuracy | 0.595 | — |
---
## Setup

### Cerințe

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com) instalat și pornit
- [Neo4j Desktop](https://neo4j.com/download/) (opțional — pentru cross-article și cache Wikidata)

### Instalare

```bash
# Clonează repo-ul
git clone https://github.com/Marius1608/FakeNews-XAI.git
cd FakeNews-XAI

# Creează și activează venv
python -m venv venv
source venv/Scripts/activate        # Git Bash / Windows
# source venv/bin/activate          # Linux / macOS

# Instalează dependențele Python
pip install -r requirements.txt

# Descarcă modelul spaCy
python -m spacy download en_core_web_trf

# Descarcă modelul LLM (Ollama trebuie să fie pornit)
ollama pull llama3

# Configurează variabilele de mediu
cp .env.example .env
# Editează .env dacă vrei să schimbi porturile sau credențialele Neo4j
```

### Pornire

```bash
bash start.sh        # Git Bash / Linux / macOS
.\start.ps1          # Windows PowerShell
```

Scriptul pornește automat backend-ul FastAPI și frontend-ul React.

### Pornire manuală (3 terminale)

**Terminal 1 — Ollama**
```bash
ollama serve
```

**Terminal 2 — Backend FastAPI**
```bash
source venv/Scripts/activate
uvicorn backend.main:app --reload --port 8000
```

**Terminal 3 — Frontend React**
```bash
cd frontend
npm install
npm start
```

| Serviciu | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |

### Neo4j (opțional)

1. Instalează Neo4j Desktop
2. Creează o bază de date locală (ex: `fake-news`) și pornește-o
3. Setează în `.env`:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=parola_ta
```
Fără Neo4j, pipeline-ul rulează fără persistență (C3c omis).

---

## Configurare (.env)

| Variabilă | Default | Descriere |
|---|---|---|
| `SPACY_DEFAULT_MODEL` | `en_core_web_trf` | Modelul spaCy implicit |
| `LLM_DEFAULT_MODEL` | `llama3` | Modelul Ollama implicit |
| `OLLAMA_HOST` | `http://localhost:11434` | URL server Ollama |
| `WIKIDATA_ENDPOINT` | `https://query.wikidata.org/sparql` | Endpoint SPARQL Wikidata |
| `NEO4J_URI` | `bolt://localhost:7687` | URI Neo4j |
| `NEO4J_USER` | `neo4j` | User Neo4j |
| `NEO4J_PASSWORD` | — | Parolă Neo4j |
| `CORS_ORIGINS` | `http://localhost:3000` | Origini permise CORS |

---

## API Endpoints

| Metodă | Path | Descriere |
|---|---|---|
| POST | `/analyze` | Analizează un articol → TCS + inconsistențe + explicație |
| POST | `/compare` | Compară Pipeline A vs B pe același articol |
| POST | `/analyze-batch` | Analizează mai multe articole simultan |
| GET | `/articles` | Istoricul articolelor salvate în Neo4j |
| GET | `/health` | Status backend + componente active |

### Exemplu cerere `/analyze`

```json
{
  "text": "Obama served as president from 2009 to 2017...",
  "title": "Obama Presidency",
  "publication_date": "2024-01-01",
  "pipeline": "spacy",
  "use_wikidata": true,
  "persist": true
}
```

---

## Evaluare

```bash
# Benchmark complet (fără Wikidata, rapid)
python evaluation/run_evaluation.py --no-wikidata --benchmark-only

# Benchmark complet cu Wikidata (recomandat pentru teză)
python evaluation/run_evaluation.py

# Evaluare LIAR2
python evaluation/run_liar_eval.py --n 100 --split test

# Comparație Pipeline A vs B
python evaluation/run_evaluation.py --benchmark-only
```

Rezultatele se salvează în `evaluation/results/` și figurile în `evaluation/figures/`.

---

## Structura proiectului

```
FakeNews-XAI/
├── backend/
│   ├── config.py                    # Setări centralizate din .env
│   ├── main.py                      # FastAPI app, CORS, routere
│   ├── dependencies.py              # Injectare dependențe (Neo4j store)
│   ├── pipeline/
│   │   ├── orchestrator.py          # C1→C2→C3→C4 + XAI coordinator
│   │   ├── extraction/              # C1: SpacyExtractor, LLMExtractor, base
│   │   ├── graph/                   # C2: TKGBuilder, TemporalKnowledgeGraph,
│   │   │                            #     Neo4jTKGStore, models
│   │   ├── verification/            # C3: InternalVerifier, ExternalVerifier,
│   │   │                            #     CrossArticleVerifier, wikidata client
│   │   └── scoring/                 # C4: TCSCalculator, LLMExplainer, Explainer
│   └── routers/                     # FastAPI route handlers
├── frontend/
│   └── src/
│       ├── components/              # AnalyzeTab, CompareTab, BatchTab,
│       │                            #   ArticleHistory, TCSScoreDisplay,
│       │                            #   Timeline, TemporalGraph, TextHighlight
│       ├── api.ts                   # Client HTTP pentru backend
│       └── theme.ts                 # Tema MUI
├── evaluation/
│   ├── run_evaluation.py            # Suită completă evaluare
│   ├── run_benchmark.py             # Benchmark manual izolat
│   ├── run_liar_eval.py             # Evaluare LIAR2
│   ├── benchmark_articles.json      # 84 articole cu ground truth
│   ├── results/                     # Rezultate JSON
│   └── figures/                     # Boxplot-uri PNG
├── data/
│   └── reference_kg/
│       └── verified_events.json     # Reference KG local (16 entități)
├── docs/
│   ├── feature_extraction.md
│   ├── feature_tkg.md
│   ├── feature_verification.md
│   ├── feature_tcs.md
│   ├── feature_explainability.md
│   ├── feature_neo4j.md
│   └── feature_evaluation.md
├── .env.example
├── requirements.txt
├── start.sh
└── start.ps1
```

---

## Stack tehnologic

| Strat | Tehnologie |
|---|---|
| Backend | Python 3.11, FastAPI, uvicorn, Pydantic |
| NLP | spaCy `en_core_web_trf` (RoBERTa-based) |
| LLM | Ollama `llama3:8b` (inferență locală, GPU) |
| Graph | networkx MultiDiGraph + Neo4j Community Edition |
| Verificare externă | Wikidata SPARQL (endpoint public, fără API key) |
| Frontend | React 19, TypeScript, Material UI v6, recharts |
| Evaluare | pytest, matplotlib, seaborn |

---

## Datasets

| Dataset | Tip | Utilizare |
|---|---|---|
| Benchmark manual | 84 articole sintetice cu ground truth | Evaluare principală (F1, Precision, Recall) |
| LIAR2 | ~23K statements PolitiFact (2023) | Distribuție TCS per label |
| VER-1 (Conf. Cheres) | Articole românești | Evaluare multilingvă (future work) |
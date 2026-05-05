# FakeNews-XAI

## Overview

Explainable Agentic AI system for Fake News Detection through Temporal Consistency Analysis.
The system computes a **Temporal Coherence Score (TCS)** by extracting temporal facts from a
news article, constructing a Temporal Knowledge Graph (TKG), and detecting internal and external
inconsistencies across the article's timeline of claims.

**Bachelor Thesis — Technical University of Cluj-Napoca (UTCN), 2026**  
Author: Marius Pantea | Supervisors: Prof. Adrian Groza, Conf. Ioana Cheres

---

## Architecture

The pipeline consists of four sequential components:

```
Article Text
     |
     v
[C1: Temporal Extraction]    spaCy NER  OR  LLM (Ollama)
     |
     v
[C2: TKG Construction]       networkx MultiDiGraph — entities as nodes, temporal relations as edges
     |
     v
[C3: Verification]           Internal consistency checks  +  External Wikidata SPARQL queries
     |
     v
[C4: TCS Scoring]            Score in [0.0, 1.0] + structured natural-language explanation
```

**C1 — Temporal Information Extraction**  
Two interchangeable extractors produce normalized (subject, predicate, object, time) fact triples.
Pipeline A uses a deterministic spaCy NER model; Pipeline B uses an LLM running locally via Ollama.

**C2 — Temporal Knowledge Graph Construction**  
Facts are assembled into a `TemporalKnowledgeGraph` (networkx `MultiDiGraph`). Nodes represent
named entities; directed edges carry temporal metadata and per-fact confidence scores.

**C3 — Verification**  
`InternalVerifier` detects contradictions within the article's own timeline (overlapping date
ranges, reversed event order). `ExternalVerifier` cross-references claims against Wikidata via
SPARQL (temporal properties P580, P582, P585) and against a local Reference Knowledge Graph
stored in `data/reference_kg/`.

**C4 — TCS Scoring and Explainability**  
`TCSCalculator` combines the coherence factor and inconsistency penalties into a single score.
A structured explainer maps each inconsistency back to its source sentence for the UI.

### TCS Score Bands

| Score range | Label              | Interpretation              |
|-------------|--------------------|-----------------------------|
| 0.8 – 1.0   | Very Consistent    | Likely credible             |
| 0.5 – 0.8   | Moderately Consistent | Minor temporal issues    |
| 0.2 – 0.5   | Suspicious         | Multiple inconsistencies    |
| 0.0 – 0.2   | Severe Violations  | Likely fabricated           |

---

## Models

| Model ID          | Display Name            | Pipeline | Description                                              |
|-------------------|-------------------------|----------|----------------------------------------------------------|
| `en_core_web_trf` | spaCy Transformer       | spaCy    | RoBERTa-based NER — highest accuracy; default spaCy model |
| `en_core_web_lg`  | spaCy Large             | spaCy    | Word-vector NER — faster inference, slightly lower accuracy |
| `sciphi/triplex`  | Triplex (KG extraction) | LLM      | Fine-tuned for Knowledge Graph triplet extraction; default LLM model |
| `fakenews-ner`    | FakeNews-NER (custom)   | LLM      | Custom model fine-tuned for temporal political NER       |

All LLM models run locally through [Ollama](https://ollama.com) — no external API keys required.

---

## Features

- Single article analysis with selectable pipeline and model
- Side-by-side comparison of any two model/pipeline combinations on the same article
- Interactive TCS gauge with animated score display
- Per-sentence fact annotation with color-coded consistency status
- Inconsistency list with severity levels and evidence excerpts
- Temporal timeline chart (recharts)
- Temporal Knowledge Graph visualization (react-force-graph-2d)
- Fully on-premise — no cloud inference, no external API dependencies beyond public Wikidata SPARQL

---

## Quick Start

```bash
# Clone
git clone https://github.com/Marius1608/FakeNews-XAI.git
cd FakeNews-XAI

# Create and activate a Python virtual environment
python -m venv venv
source venv/bin/activate          # Linux / macOS / Git Bash
# venv\Scripts\activate           # Windows PowerShell

# Install Python dependencies
pip install -r requirements.txt

# Install spaCy models
python -m spacy download en_core_web_trf
python -m spacy download en_core_web_lg

# Configure environment
cp .env.example .env
# Edit .env if you need to change models or ports — defaults work out of the box

# Start all services
./start.sh          # Linux / macOS / Git Bash
.\start.ps1         # Windows PowerShell
```

The startup scripts check whether Ollama is running, pull any missing LLM models, then launch
both the FastAPI backend and the React frontend.

---

## Manual Start

Open three separate terminals:

**Terminal 1 — Ollama (LLM server)**
```bash
ollama serve
ollama pull sciphi/triplex
```

**Terminal 2 — FastAPI backend**
```bash
source venv/bin/activate          # or venv\Scripts\activate on Windows
uvicorn backend.main:app --reload --port 8000
```

**Terminal 3 — React frontend**
```bash
cd frontend
npm install
npm start
```

| Service        | URL                              |
|----------------|----------------------------------|
| Frontend       | http://localhost:3000            |
| API            | http://localhost:8000            |
| Swagger UI     | http://localhost:8000/docs       |

---

## API Endpoints

| Method | Path       | Description                                                |
|--------|------------|------------------------------------------------------------|
| POST   | `/analyze` | Analyze a single article — returns TCS score + explanation |
| POST   | `/compare` | Run any two model/pipeline combinations side by side       |
| GET    | `/models`  | List available models per pipeline                         |
| GET    | `/health`  | Server health check and active component configuration     |

### Analyze request

```json
POST /analyze
{
  "text": "The president signed the treaty on March 15, 2022 ...",
  "title": "Treaty Signing",
  "publication_date": "2022-03-15",
  "pipeline": "spacy",
  "model": "en_core_web_trf"
}
```

`pipeline` is `"spacy"` or `"llm"`. `model` is optional — omitting it uses the pipeline default.

### Compare request

```json
POST /compare
{
  "text": "...",
  "pipeline_a": "spacy",
  "model_a": "en_core_web_trf",
  "pipeline_b": "llm",
  "model_b": "sciphi/triplex"
}
```

The response includes both full results plus a `score_delta` and an `agreement` summary string.

---

## Configuration

Copy `.env.example` to `.env`. All variables have working defaults for local development.

| Variable                 | Default                             | Description                                      |
|--------------------------|-------------------------------------|--------------------------------------------------|
| `SPACY_MODELS`           | `en_core_web_trf,en_core_web_lg`    | Comma-separated spaCy models exposed by the API  |
| `SPACY_DEFAULT_MODEL`    | `en_core_web_trf`                   | spaCy model pre-selected in the UI               |
| `LLM_MODELS`             | `sciphi/triplex,fakenews-ner`       | Comma-separated Ollama models exposed by the API |
| `LLM_DEFAULT_MODEL`      | `sciphi/triplex`                    | LLM model pre-selected in the UI                 |
| `OLLAMA_HOST`            | `http://localhost:11434`            | Ollama server URL                                |
| `OLLAMA_TIMEOUT_SECONDS` | `120`                               | Seconds before an Ollama request times out       |
| `WIKIDATA_ENDPOINT`      | `https://query.wikidata.org/sparql` | SPARQL endpoint for external verification        |
| `CORS_ORIGINS`           | `http://localhost:3000`             | Allowed origins for the FastAPI CORS policy      |

---

## Project Structure

```
FakeNews-XAI/
├── backend/
│   ├── config.py                   # Centralized settings — all values come from .env
│   ├── main.py                     # FastAPI app entry point, CORS, router registration
│   ├── pipeline/
│   │   ├── orchestrator.py         # C1 → C2 → C3 → C4 coordinator
│   │   ├── extraction/             # C1: SpacyExtractor, LLMExtractor, abstract base
│   │   ├── graph/                  # C2: TKGBuilder, TemporalKnowledgeGraph, domain models
│   │   ├── verification/           # C3: InternalVerifier, ExternalVerifier (Wikidata)
│   │   └── scoring/                # C4: TCSCalculator, structured Explainer
│   └── routers/                    # FastAPI route handlers (analyze, compare, health)
├── frontend/
│   ├── src/
│   │   ├── components/             # React components: ArticleInput, TCSScoreDisplay,
│   │   │                           #   TextHighlight, InconsistencyList, Timeline, TemporalGraph
│   │   ├── utils/modelLabels.ts    # Human-readable model display names and descriptions
│   │   ├── api/client.ts           # Axios wrappers for all backend endpoints
│   │   └── types/api.ts            # TypeScript interfaces mirroring backend Pydantic schemas
│   └── package.json
├── data/
│   ├── datasets/                   # Evaluation datasets
│   └── reference_kg/              # Local Reference Knowledge Graph for C3 verification
├── .env.example
├── requirements.txt
├── start.ps1                       # Windows PowerShell startup script
└── start.sh                        # Linux / macOS / Git Bash startup script
```

---

## Tech Stack

| Layer    | Technology                                                              |
|----------|-------------------------------------------------------------------------|
| Backend  | Python 3.11, FastAPI, uvicorn, spaCy 3, networkx, python-dotenv         |
| LLM      | Ollama (local inference — no cloud dependency)                          |
| External | Wikidata SPARQL (public endpoint, no API key required)                  |
| Frontend | React 19, TypeScript, Material UI v9, recharts, react-force-graph-2d, axios |

---

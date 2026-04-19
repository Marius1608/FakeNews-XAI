# FakeNews-XAI — Explainable Agentic AI for Fake News Detection

**Bachelor's Thesis** — UTCN, Faculty of Automation and Computer Science, 2026  
**Author:** Marius Pantea  
**Supervisors:** Prof. Adrian Groza, Conf. Ioana Cheres

---

## Description

FakeNews-XAI is a system for detecting fake news through **temporal consistency analysis** of news articles. It builds a **Temporal Knowledge Graph (TKG)** from extracted temporal claims and computes a **Temporal Coherence Score (TCS)** — a value between 0 and 1 indicating how internally consistent and externally verifiable the article's temporal assertions are. The system supports two extraction pipelines: Pipeline A uses spaCy's transformer model for fast, deterministic extraction; Pipeline B uses an on-premise Ollama/Llama 3 LLM for richer semantic understanding. Results are explained via structured inconsistency annotations, fact-level highlights, and an interactive chronological timeline.

---

## Architecture

The pipeline is structured as 4 sequential components:

| Component | Name | Description |
|---|---|---|
| **C1** | Temporal Information Extraction | Extracts temporal facts (subject, predicate, object, time) from raw text using spaCy NLP or LLM prompting |
| **C2** | TKG Construction | Builds a directed Temporal Knowledge Graph using networkx; stores facts as typed nodes and edges with time intervals |
| **C3** | Temporal Consistency Verification | Internal graph verification (contradiction detection, ordering checks) + external Wikidata SPARQL queries (P580, P582, P585) |
| **C4** | TCS Scoring | Computes `TCS = 1 − (N_inconsist / C_temporal) × S_coherence`; labels article as Consistent / Suspicious / Likely Fake |

**Dual pipeline:** Pipeline A (spaCy `en_core_web_trf`) for speed; Pipeline B (Ollama / Llama 3) for depth. The `/compare` endpoint runs both on the same article for side-by-side evaluation.

### TCS Score Interpretation

| Range | Label |
|---|---|
| 0.8 – 1.0 | Consistent (likely real) |
| 0.5 – 0.7 | Moderately consistent |
| 0.2 – 0.4 | Multiple inconsistencies (suspicious) |
| 0.0 – 0.2 | Severe violations (likely fake) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.10+, FastAPI, Uvicorn |
| NLP (Pipeline A) | spaCy 3.7+, `en_core_web_trf` |
| LLM (Pipeline B) | Ollama (on-premise), Llama 3 |
| Knowledge Graph | networkx |
| External Verification | Wikidata SPARQL (P580, P582, P585) |
| Frontend | React 18, TypeScript, MUI v5 |
| Charts | Recharts, react-force-graph-2d |

---

## Quick Start

### Backend

```bash
# Create and activate virtual environment
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash

# Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_trf

# Configure environment
cp .env.example .env
# Edit .env with your OLLAMA_HOST, WIKIDATA settings

# Start API server
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm start          # Runs on http://localhost:3000
```

> The frontend proxies API calls to `http://localhost:8000`. Set `REACT_APP_API_URL` in `frontend/.env` to override.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Server status and component configuration |
| `POST` | `/analyze` | Analyze a single article with a chosen pipeline (`spacy` or `llm`) |
| `POST` | `/compare` | Run both pipelines on the same article and return a side-by-side comparison |

---

## Project Structure

```
FakeNews-XAI/
├── backend/
│   ├── main.py                  # FastAPI app entrypoint
│   ├── config.py                # Environment config (CORS, models, hosts)
│   ├── routers/
│   │   ├── analyze.py           # POST /analyze
│   │   ├── compare.py           # POST /compare
│   │   └── health.py            # GET /health
│   └── pipeline/
│       ├── orchestrator.py      # Pipeline A / B dispatch
│       ├── extraction/          # C1 — temporal fact extractors
│       ├── graph/               # C2 — TKG models and store
│       ├── verification/        # C3 — internal + external verifiers
│       └── scoring/             # C4 — TCS calculator + explainer
├── frontend/
│   ├── src/
│   │   ├── api/client.ts        # Axios instance + typed API functions
│   │   ├── types/api.ts         # TypeScript interfaces (1:1 with Pydantic)
│   │   ├── theme/theme.ts       # MUI dark theme
│   │   └── components/          # React UI components
│   └── package.json
├── data/
│   ├── cache/                   # Wikidata response cache
│   └── datasets/                # Evaluation datasets
├── requirements.txt
└── .env.example
```

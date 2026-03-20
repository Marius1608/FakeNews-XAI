# Explainable Agentic AI for Fake News Detection

**Lucrare de licenta** — UTCN, Facultatea de Automatica si Calculatoare

**Autor:** Marius Pantea  
**Coordonatori:** Adrian Groza, Ioana Cheres

---

## Descriere

Sistem de verificare a coerentei temporale a articolelor de stiri folosind Temporal Knowledge Graphs. Calculeaza un **Temporal Coherence Score (TCS)** care indica cat de consistente sunt afirmatiile temporale dintr-un articol.

### Arhitectura — 4 Componente Pipeline

1. **Temporal Information Extraction** — extragere fapte temporale (spaCy / LLM)
2. **Temporal Knowledge Graph Construction** — graf temporal cu networkx-temporal
3. **Temporal Consistency Verification** — verificare interna + Wikidata SPARQL
4. **TCS Score Computation** — scor final + explicatii

### Formula TCS

```
TCS = (N_inconsist / C_temporal) × S_coherence
S_coherence = 1 - (conf_temp / rel_temp)
```

- `N_inconsist` = numarul de inconsistente temporale detectate
- `C_temporal` = totalul afirmatiilor temporale din text
- `S_coherence` = coerenta grafului temporal (0-1)

### Interpretare scor

- **0.8 – 1.0**: Foarte consistent (probabil real)
- **0.5 – 0.7**: Moderat consistent
- **0.2 – 0.4**: Inconsistente multiple (suspect)
- **0.0 – 0.2**: Violari severe (probabil fake)

---

## Tech Stack

| Componenta | Tehnologie |
|---|---|
| NLP Processing | spaCy 3.7+ (en_core_web_trf) |
| Temporal Parsing | dateparser |
| Knowledge Graph | networkx-temporal |
| External Verification | Wikidata SPARQL (P580, P582, P585) |
| LLM Comparison | Ollama (on-premise) |
| Backend API | FastAPI |
| Frontend | React |

---

## Setup (Windows — Git Bash)

> **Nota:** Toate comenzile de mai jos se ruleaza in **Git Bash** (MINGW64)

### 1. Cloneaza repository-ul

```bash
git clone URL-project
cd FakeNews-XAI
```

### 2. Creeaza mediul virtual Python

```bash
python -m venv venv
```

### 3. Activeaza mediul virtual

```bash
source venv/Scripts/activate
```


### 4. Instaleaza dependentele

```bash
pip install -r requirements.txt
```

### 5. Descarca modelul spaCy (transformer — ~500MB)

```bash
python -m spacy download en_core_web_trf
```

### 6. Configureaza variabilele de environment

```bash
cp .env.example .env
```

Apoi editeaza `.env` si completeaza cheile necesare.

### 7. Verifica instalarea

```bash
python -c "import spacy; nlp = spacy.load('en_core_web_trf'); print('spaCy OK')"
python -c "import dateparser; print('dateparser OK')"
python -c "import fastapi; print('FastAPI OK')"
```

## Status

In dezvoltare — Sprint 1.
# Explainable Agentic AI for Fake News Detection

**Lucrare de licenta** — UTCN, Facultatea de Automatica si Calculatoare

**Autor:** Marius Pantea  
**Coordonatori:** Adrian Groza, Ioana Cheres

## Descriere

Sistem de verificare a coerentei temporale a articolelor de stiri folosind Temporal Knowledge Graphs. Calculeaza un **Temporal Coherence Score (TCS)** care indica cat de consistente sunt afirmatiile temporale dintr-un articol.

## Arhitectura — 4 Componente Pipeline

1. **Temporal Information Extraction** — extragere fapte temporale (spaCy / LLM)
2. **Temporal Knowledge Graph Construction** — graf temporal cu networkx-temporal
3. **Temporal Consistency Verification** — verificare interna + Wikidata SPARQL
4. **TCS Score Computation** — scor final + explicatii

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_trf
cp .env.example .env
```

## Status

In dezvoltare — Sprint 1.

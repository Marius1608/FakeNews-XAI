# Arhitectura Cod — Pipeline TCS

## Flux Pipeline

```
Article
  │
  ▼
┌─────────────────────────────────────────┐
│  C1: Temporal Information Extraction    │
│  spacy_extractor.py + temporal_parser.py│
│  NER → dependency parsing → date parse  │
└──────────────┬──────────────────────────┘
               │ list[TemporalFact]
               ▼
┌─────────────────────────────────────────┐
│  C2: TKG Construction                  │
│  builder.py → store.py                  │
│  filtrare → deduplicare → graf G=(E,R,T,F) │
└──────────────┬──────────────────────────┘
               │ TemporalKnowledgeGraph
               ▼
┌─────────────────────────────────────────┐
│  C3: Temporal Consistency Verification  │
│                                         │
│  C3a: internal.py                       │
│    cicluri · cauzalitate · ordering     │
│    → score_coherence                    │
│                                         │
│  C3b: external.py + wikidata.py         │
│    Reference KG → Wikidata SPARQL       │
│    → DATE_MISMATCH / ANACHRONISM        │
└──────────────┬──────────────────────────┘
               │ list[Inconsistency] + score_coherence
               ▼
┌─────────────────────────────────────────┐
│  C4: TCS Score Computation              │
│  tcs.py                                 │
│  TCS = 1 - (inconsist/claims) × coher. │
│  → TCSResult (score, label, timeline)   │
└─────────────────────────────────────────┘
```

Orchestratorul (`orchestrator.py`) apelează C1→C2→C3→C4 în secvență și returnează `TCSResult`.

---

## Fișiere per Componentă

### Structuri de date partajate — `models.py`

Definește toate tipurile folosite în pipeline: `Entity`, `TemporalExpression`, `TemporalFact`, `Article`, `Inconsistency`, `TCSResult`, plus enum-urile `EntityType`, `RelationType`, `InconsistencyType`, `Severity`. Fiecare componentă importă de aici.

`TemporalFact` e unitatea centrală — un triplet subiect→predicat→obiect cu ancoră temporală, extras din text. Circulă de la C1 la C2 și e stocat în graf. `TCSResult` e output-ul final cu scorul, inconsistențele, și timeline-ul pentru UI.

### Input — `base.py`, `dataset.py`

`base.py` definește `AbstractExtractor` — interfața comună pentru Pipeline A (spaCy) și Pipeline B (LLM, Sprint 3). Permite orchestratorului să funcționeze identic indiferent de extractorul folosit.

`dataset.py` încarcă articole din LIAR (TSV, 12.8K declarații PolitiFact), FakeNewsNet (JSON cu timestamps, PolitiFact + GossipCop), și VER-1 (CSV, dezinformare Europa de Est). Toate returnează obiecte `Article`.

### C1: Temporal Information Extraction — `temporal_parser.py`, `spacy_extractor.py`

**`temporal_parser.py`** — wrapper peste `dateparser`. Primește un string temporal ("January 2009", "early 2000s", "last Tuesday") și returnează `TemporalExpression` cu data normalizată, flag-uri `is_relative`/`is_approximate`, și un scor de confidence. Logică specială pentru decade patterns ("early 2000s"→2000, "mid 1990s"→1995, "late 1980s"→1989). Datele relative se rezolvă față de `publication_date`.

**`spacy_extractor.py`** — Pipeline A (deterministic). Pentru fiecare propoziție: (1) extrage entități cu NER (`en_core_web_trf`), (2) parsează entitățile DATE cu `temporal_parser`, (3) identifică subiect→predicat→obiect prin dependency parsing pe verbul ROOT, (4) clasifică verbul în `RelationType` (serve→HOLDS_POSITION, cause→CAUSED etc.), (5) asociază expresiile temporale (1 dată→time_point, 2 date→start/end). Dacă dependency parsing eșuează, fallback: asociere simplă cu confidence 0.5.

**Legătura C1→C2:** output-ul (`list[TemporalFact]`) e trimis la `TKGBuilder.build()`.

### C2: TKG Construction — `builder.py`, `store.py`

**`builder.py`** — trei pași: (1) **filtrare** — elimină faptele cu subiect gol, subiect DATE/OTHER, confidence sub 0.3, sau fără ancoră temporală parsată; (2) **deduplicare** — semnătură (subiect, predicat, obiect, timp), se păstrează faptul cu confidence mai mare; (3) **inserție** în graf.

**`store.py`** — clasa `TemporalKnowledgeGraph`, wrapper peste `nx.MultiDiGraph`. Implementează G = (E, R, T, F) conform Cai et al. (2024): noduri = entități, muchii = relații cu metadata temporală. Metode de interogare: `get_facts_for_entity()`, `get_edges_by_relation()`, `get_edges_in_interval()`, `snapshot(t)` (subgraf activ la momentul t).

**Legătura C2→C3:** TKG-ul populat e trimis atât la `InternalVerifier` cât și la `ExternalVerifier`.

### C3: Temporal Consistency Verification — `internal.py`, `wikidata.py`, `external.py`

**`internal.py`** — verifică consistența internă a grafului, fără surse externe. Trei verificări:

- **V1 — Cicluri temporale:** construiește subgraf cu doar muchiile PRECEDED/FOLLOWED și caută cicluri cu `nx.find_cycle()`. Ex: "A before B" + "B before A" → ciclu.
- **V2 — Violări cauzale:** pentru fapte CAUSED, verifică dacă efectul precede cauza în timp.
- **V3 — Ordering errors:** interval inversat (start > end) sau durată implausibilă (>50 ani).

Returnează `InternalVerificationResult` cu lista de `Inconsistency` și `score_coherence = 1 - (conf_temp / rel_temp)`.

**`wikidata.py`** — client SPARQL pur (nu face comparații). Două operații: `search_entity(name)` pentru a găsi Q-ID-ul, și `get_temporal_facts(entity_id)` pentru a interoga proprietățile temporale (P580=start, P582=end, P585=point in time). Rate limiting: max 1 request/secundă.

**`external.py`** — verificare externă contra Wikidata și Reference KG. Pentru faptele HOLDS_POSITION și MEMBER_OF: (1) caută mai întâi în `verified_events.json` (14 entități verificate manual, fără request HTTP); (2) dacă nu găsește, interogă Wikidata prin `WikidataClient`; (3) compară intervalele temporale cu toleranță de 365 zile. Dacă articolul zice "Obama was president in 2005" și sursa zice 2009-2017 → `DATE_MISMATCH`.

**`verified_events.json`** — Reference KG local cu 14 entități: Obama, Trump, Biden, Bush, Clinton×2, Merkel, Putin, Musk, Apple, Google, Microsoft, WW2, COVID-19, ACA.

**Legătura C3→C4:** inconsistențele (interne + externe) și `score_coherence` sunt trimise la `TCSCalculator`.

### C4: TCS Score Computation — `tcs.py`

Formula principală:

```
TCS = 1 - (inconsist_detected / claims_temporal) × score_coherence
```

- `inconsist_detected` = inconsistențe interne + externe combinate
- `claims_temporal` = faptele din TKG (după filtrare în builder)
- `score_coherence` = coerența internă (din internal.py)

Interpretare: TCS=1.0 → consistent, TCS=0.0 → suspect. Edge cases: `claims_temporal=0` → scor 0.0 (date insuficiente); `score_coherence=0` → scor 0.0 (graf total incoherent). Construiește și timeline-ul sortat cronologic pentru UI. Variantă ponderată disponibilă (`compute_weighted`) cu greutăți pe severitate.

### Orchestrator — `orchestrator.py`

`PipelineOrchestrator.run(article)` apelează secvențial: C1 → C2 → C3a → C3b → C4. Lazy-loading pentru modelul spaCy (se încarcă o singură dată, ~500MB). Metodă `run_batch()` pentru evaluare pe dataset-uri.

### Notebooks — `01_spacy_ner_exploration.py`, `02_pipeline_test.py`

`01` testează Sprint 1: NER pe un articol sintetic, parsare expresii temporale, extracție fapte. `02` testează pipeline-ul end-to-end pe 2 articole (A=consistent, B=cu erori), verifică că TCS_A > TCS_B, inspectează TKG-ul, și afișează timeline-ul.

---

## Dependențe între Fișiere

```
models.py ◄──── toate fișierele importă de aici
    │
    ├── base.py (AbstractExtractor)
    │     ▲
    │     └── spacy_extractor.py ──► temporal_parser.py
    │
    ├── dataset.py (loaders LIAR / FakeNewsNet / VER-1)
    │
    ├── store.py (TemporalKnowledgeGraph)
    │     ▲
    │     └── builder.py (TKGBuilder)
    │
    ├── internal.py (InternalVerifier) ──► store.py
    │
    ├── wikidata.py (WikidataClient)
    │     ▲
    │     └── external.py (ExternalVerifier) ──► store.py, wikidata.py
    │                                            verified_events.json
    │
    ├── tcs.py (TCSCalculator) ──► store.py, internal.py, external.py
    │
    └── orchestrator.py ──► toate componentele de mai sus
```

---

## Locația în Repo

```
backend/pipeline/
├── orchestrator.py              # Orchestrator
├── extraction/                  # C1
│   ├── base.py
│   ├── spacy_extractor.py
│   └── temporal_parser.py
├── graph/                       # C2 + structuri de date
│   ├── models.py
│   ├── builder.py
│   └── store.py
├── verification/                # C3
│   ├── internal.py
│   ├── external.py
│   └── wikidata.py
└── scoring/                     # C4
    └── tcs.py

data/reference_kg/
└── verified_events.json         # Reference KG (14 entități)

notebooks/
├── 01_spacy_ner_exploration.py  # Test Sprint 1
└── 02_pipeline_test.py          # Test E2E Sprint 2
```

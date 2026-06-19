# GIT EVOLUTION REPORT — FakeNews-XAI
## Temporal Coherence Score (TCS) System — Thesis Development History

**Generated:** 2026-06-11  
**Repository:** FakeNews-XAI (Marius1608)  
**Total commits analyzed:** 80  
**Development span:** 2026-03-20 → 2026-06-11 (83 days)

---

## SECȚIUNEA 1: CRONOLOGIE COMPLETĂ

| Data | Hash | Ce s-a schimbat | Impact |
|------|------|-----------------|--------|
| 2026-03-20 | e972000 | Sprint 1: project structure | Fundație — directoare pipeline, config centralizat |
| 2026-03-20 | 0f79794 | config.py — setări centralizate | Pattern folosit neschimbat până azi |
| 2026-03-20 | d95d8ed | models.py — data models (Article, TemporalFact, Inconsistency, TCSResult) | Contractul de date al întregului sistem |
| 2026-03-25 | a1ac02f | temporal_parser.py — dateparser wrapper | C1: parsare date din text |
| 2026-03-27 | fb590b6 | base extractor + spacy_extractor.py — Pipeline A | **C1: extractor primar, 373 linii** |
| 2026-03-27 | 66f56c1 | dataset.py — loaders LIAR, FakeNewsNet, VER-1 | Încărcare date externe (ulterior depreciată) |
| 2026-03-27 | fb4a632 | Notebook explorare spaCy NER + temporal parser | Validare experimentală |
| 2026-03-28 | 0977e8b | Fix interpretation score | Bug fix TCS formula |
| 2026-03-28 | 2e596b6 | Add verbs POSITION/MEMBERSHIP/EVENT + deduplicare entități | Îmbunătățire extracție relații |
| 2026-03-28 | 475e417 | DECADE_PATTERN + _normalize_approximate() | Suport expresii temporale vagi ("în anii '90") |
| 2026-03-28 | bdfbd7d | Refactoring | Cleanup |
| 2026-03-28 | cb7f1a7 | Refactoring | Cleanup |
| 2026-03-29 | bdf41e5 | Refactoring | Cleanup |
| 2026-03-29 | 89b438b | store.py — TemporalKnowledgeGraph (172 linii) | **C2: graful de cunoaștere temporal** |
| 2026-03-29 | 9a17f6e | builder.py — TKGBuilder cu filtrare, dedup, validare anchore temporale | C2: construcție TKG |
| 2026-03-29 | ff81b20 | wikidata.py — WikidataClient cu SPARQL temporal queries | **C3b: verificare externă Wikidata** |
| 2026-03-29 | 9bd0b50 | internal.py — InternalVerifier (cycle, causal violation, ordering error) | **C3a: verificare internă** |
| 2026-03-29 | 0a65c8a | external.py — ExternalVerifier cu Reference KG + Wikidata | **C3b: comparare externă** |
| 2026-03-29 | ca7e420 | orchestrator.py — PipelineOrchestrator lazy-load + batch | Legătură C1→C2→C3→C4 |
| 2026-03-29 | b2334ea | Reference KG — 14 entități verificate (președinți, companii, events) | Baza de date factuale locală |
| 2026-03-29 | b623a2d | Test end-to-end Sprint 2 (consistent vs inconsistent articles) | Validare pipeline complet |
| 2026-03-29 | 094c12d | tcs.py — TCSCalculator (formula primară + weighted + timeline builder) | **C4: scorul TCS final** |
| 2026-03-29 | b49787e | Documentare componente în md | Documentație arhitecturală |
| 2026-04-01 | 3738a76 | Adaptare la noul return type search_entity | Fix Wikidata API |
| 2026-04-01 | c4f87e3 | search_entity returnează QID, rescrie SPARQL query | Fix Wikidata QID lookup |
| 2026-04-01 | 0d6a977 | **llm_extractor.py — Pipeline B via Ollama (306 linii)** | Prima implementare LLM (llama3/mistral) |
| 2026-04-02 | fdc0925 | explainer.py — explicații în limbaj natural | XAI: generare text explicativ |
| 2026-04-02 | ab7f87c | FastAPI app + routers (analyze, compare, health) | API REST complet |
| 2026-04-02 | ba030d3 | compare_pipelines.py — evaluare batch A vs B | Comparare cantitativă pipeline-uri |
| 2026-04-02 | 32d5422 | Orchestrator — Pipeline B support via extractor registry | Arhitectura plugin pentru extractor-i |
| 2026-04-04 | 9d3afaf | Notebooks sprint3 + SPARQL verification + main.py | Validare Wikidata |
| 2026-04-04 | 8f7e8a5 | Fix source_sentence LLM, shared dependencies | Bug fix LLM extractor |
| 2026-04-19 | 6a7d460 | Full system test (618 linii) | Validare integrare completă |
| 2026-04-19 | e970928 | Refactor .gitignore, env, readme | Setup mediu |
| 2026-04-19 | d9a5190 | Add frontend structure (React/Vite) | Start frontend |
| 2026-04-26 | e4cedff | **Frontend complet React + MUI** (Analyze + Compare + 5 zone rezultate) | UI funcțional complet |
| 2026-04-29 | 4bdd9c1 | Multi-model backend — /compare orice 2 modele + GET /models | Flexibilitate model selection |
| 2026-04-29 | 390ab0f | Refactor | Cleanup API |
| 2026-05-04 | 3d32be5 | start.ps1 + start.sh — auto Ollama check + model pull | Developer experience |
| 2026-05-04 | d7987e4 | Frontend multi-model (dropdown Analyze + 2-selector Compare) | UI: selecție dinamică model |
| 2026-05-05 | a3e6fd8 | Externalize model config în .env + auto-install spaCy | DevOps: configurare prin env |
| 2026-05-05 | 16d7b09 | Frontend cleanup | Cleanup UI |
| 2026-05-05 | c5a95b6 | README comprehensiv (arhitectură, modele, quickstart) | Documentație proiect |
| 2026-05-05 | 454462 | **Few-shot examples în LLM prompt** | Îmbunătățire calitate extracție B |
| 2026-05-06 | 5edce0b | **QLoRA fine-tuning infrastructure** (train.jsonl 331 ex, eval.jsonl 83 ex, train_qlora.py, export_gguf.py) | Infrastructură fine-tuning (nefolosită) |
| 2026-05-08 | f397bd6 | **Neo4j + cross-article verification** (neo4j_store.py 262 linii, cross_article.py 159 linii) | C3c: verificare inter-articole |
| 2026-05-12 | 5f9c1b3 | Move dependencies.py | Reorganizare structură |
| 2026-05-12 | 046662 | **Migrate to llama3** + îmbunătățire prompt temporal extraction | Upgrade model LLM |
| 2026-05-12 | 674877 | Enhance spaCy facts coverage + refine LLM logging | Extracție îmbunătățită |
| 2026-05-13 | 69fb9a1 | Reguli validare internă + verificări Wikidata expandate | Acuratețe verificare |
| 2026-05-13 | 9c76a2d | Refactor | Cleanup |
| 2026-05-13 | 2ff64a6 | **Neo4j cache Wikidata 3-level + cross-article în orchestrator** | Performanță: cache ierarhic |
| 2026-05-13 | 9431e6e | LLMExplainer llama3 cu fallback static + integrare orchestrator | XAI: explicații LLM |
| 2026-05-13 | 9b03ed0 | **pytest suite 33 teste C1→C4 + orchestrator (mock Ollama/Neo4j)** | Calitate: acoperire completă |
| 2026-05-13 | 9f7a387 | Display LLM explanation în AnalyzeTab (Psychology icon) | UI: explicații vizibile |
| 2026-05-13 | 44ec294 | **Manual benchmark 5 articole + run_benchmark.py Precision/Recall/F1** | Prima evaluare cantitativă |
| 2026-05-13 | 945f8be | Refactor + eliminare fișiere nerelevante | Cleanup major |
| 2026-05-13 | 31b3ba4 | **Traducere comentarii/logs/docstrings în engleză (22 fișiere backend)** | Internaționalizare cod |
| 2026-05-13 | fcbc9fa | Persist article title, source, analyzed_at în Neo4j | Metadata stocată |
| 2026-05-14 | af33f82 | **Extended benchmark 25 articole + run_evaluation.py cu LIAR/FakeNewsNet/boxplot** | Evaluare extinsă |
| 2026-05-14 | 8ec175f | Entity subject matching threshold + V5 HOLDS_POSITION only + KG tolerance 400d | Reducere false positive-uri |
| 2026-05-14 | 054da92 | Articole noi + script LIAR dataset | Benchmark: ~84 articole |
| 2026-05-14 | f91939a | New Readme | Documentație |
| 2026-05-15 | d638717 | **Wikidata inverse check, Neo4j cache decoupled, auto-title, cross-article button, threshold 0.55** | Verificare inversă entități |
| 2026-05-15 | 3e5f65e | New translation | Localizare |
| 2026-05-16 | f22b61b | Teste + refactor | Calitate |
| 2026-05-28 | c4c6759 | Teste + refactor | Calitate |
| 2026-05-28 | fc08c44 | **Pipeline C REBEL-large extractor + orchestrator integration (193 linii)** | Extractor relații statice |
| 2026-05-28 | f026e7a | Refactor REBEL + evaluare | Integrare completă Pipeline C |
| 2026-05-29 | 2ff93ce | **RSS Stream C3b (146 linii) + HITL endpoint + frontend toggles** | C3b Level 5: feeds live |
| 2026-05-29 | 0232c1f | **RSS feeds update + Reference KG 517→1161 fapte + entity_label fix** | Extensie masivă KG (+644 fapte) |
| 2026-06-02 | 4a6ebd0 | **Replace Ollama/llama3 → spacy-llm + Qwen3-1.7B; arhivare REBEL (F1=0.038)** | **Migrare majoră LLM** |
| 2026-06-11 | 1c00875 | Fix internal verification + rezultate evaluare | Bug fix + date |
| 2026-06-11 | 8728df8 | RSS verification panel UI, benchmark split 100/150, remove REBEL frontend, sync Qwen3 | Finalizare frontend |

---

## SECȚIUNEA 2: FAZE DE DEZVOLTARE

### Phase 1: Foundation — Core Pipeline (2026-03-20 → 2026-03-29)
**Durată:** 9 zile | **Commits:** ~16

Implementarea bottom-up a întregii arhitecturi C1→C2→C3→C4 în mai puțin de 10 zile:

```
2026-03-20  Sprint 1: project structure, config.py, models.py
2026-03-25  temporal_parser.py (dateparser wrapper)
2026-03-27  Pipeline A: spacy_extractor.py (332 linii)
2026-03-27  dataset.py: loaders LIAR, FakeNewsNet, VER-1
2026-03-28  Fix score + verbe relații + DECADE_PATTERN + 3× refactor
2026-03-29  store.py → builder.py → wikidata.py → internal.py → external.py
2026-03-29  Reference KG (14 entități) → orchestrator.py → tcs.py
2026-03-29  Test end-to-end Sprint 2
```

**Decizii arhitecturale luate în această fază (rămase neschimbate):**
- Separarea clară în 4 componente: C1 (extracție) → C2 (TKG) → C3 (verificare) → C4 (scoring)
- TCS = (1 - penalty_ratio) × score_coherence (formula ponderată pe severitate)
- Modelul de date: `TemporalFact`, `Inconsistency`, `TCSResult` (dataclasses)
- WikidataClient cu SPARQL + Reference KG local ca fallback
- Pattern lazy-load pentru extractor în orchestrator

---

### Phase 2: LLM Integration & REST API (2026-04-01 → 2026-05-05)
**Durată:** 34 zile | **Commits:** ~18

```
2026-04-01  Pipeline B: llm_extractor.py via Ollama (306 linii)
2026-04-01  Wikidata SPARQL fix (QID return type)
2026-04-02  explainer.py + FastAPI routers + compare_pipelines.py
2026-04-19  Full system test (618 linii) + frontend structure
2026-04-26  Frontend complet React + MUI (8 componente)
2026-04-29  Multi-model backend (/compare orice 2 modele, GET /models)
2026-05-04  Startup scripts (start.ps1 + start.sh cu auto Ollama check)
2026-05-05  Few-shot examples în LLM prompt → calitate îmbunătățită
```

**Punct de inflexiune:** Ollama ales ca runtime LLM pentru Pipeline B (llama3 inițial, apoi mistral, înapoi la llama3). Few-shot prompting adăugat manual (13 linii) a îmbunătățit extracția semnificativ.

---

### Phase 3: Verification Depth & Evaluation (2026-05-06 → 2026-05-16)
**Durată:** 10 zile | **Commits:** ~19 | **Cea mai densă perioadă**

```
2026-05-06  QLoRA fine-tuning infrastructure (1,109 linii adăugate)
2026-05-08  Neo4j + cross-article verification (421 linii)
2026-05-12  Migrate to llama3 + enhance temporal extraction prompt
2026-05-12  Enhance spaCy facts coverage
2026-05-13  10 commits într-o zi:
              → Validare internă expandată (205 linii)
              → Neo4j 3-level Wikidata cache
              → LLMExplainer (llama3 + static fallback)
              → pytest 33 teste
              → Benchmark 5 articole + run_benchmark.py
              → Refactor + traducere 22 fișiere în engleză
2026-05-14  Benchmark → 25 → ~84 articole
2026-05-14  Entity matching threshold V5, HOLDS_POSITION only, KG tolerance 400d
2026-05-15  Wikidata inverse check, threshold 0.55, cross-article button UI
2026-05-16  100 articole benchmark, evaluare Wikipedia REST (accuracy=83.3%)
```

**Observație:** 2026-05-13 = "ziua de sprint" — 10 commits, componente majore livrate în paralel. QLoRA: infrastructura completă construită dar **niciodată rulată** (hardware insuficient sau timp limitat).

---

### Phase 4: Pipeline C — REBEL-large (2026-05-28)
**Durată:** 1 zi | **Commits:** 2

```
2026-05-28  rebel_extractor.py (193 linii) + integrare orchestrator
2026-05-28  Refactor + evaluare REBEL
```

REBEL-large (Babelscape/rebel-large) — model pre-antrenat pentru extracție relații din text, integrat ca Pipeline C pentru relații statice (P39 positions, P463 member-of). **Rezultat final: F1=0.038** — arhivat în `rebel_extractor_archived.py`.

---

### Phase 5: RSS Stream & HITL (2026-05-29)
**Durată:** 1 zi | **Commits:** 2

```
2026-05-29  rss_verifier.py (146 linii) — C3b Level 5
2026-05-29  HITL endpoint /verify + frontend toggles
2026-05-29  Reference KG 517 → 1161 fapte (+644 fapte noi)
2026-05-29  update_reference_kg.py (260 linii)
```

RSS Stream: fallback pentru fapte recente ne-indexate în Wikidata. 8 feed-uri (BBC, NPR, NYT, The Hill, Politico, Guardian, Sky News). HITL (Human-in-the-Loop): endpoint `/verify` pentru marcarea manuală TRUE/FAKE.

---

### Phase 6: Migration Qwen3 & Cleanup (2026-06-02 → 2026-06-11)
**Durată:** 9 zile | **Commits:** 3

```
2026-06-02  Ollama/llama3 → spacy-llm + Qwen3-1.7B
            REBEL arhivat (F1=0.038)
            Fix TCS n_claims=0 bug (score era 0.5 forțat fără date)
            ISOT + RAGuard eval scripts adăugate
2026-06-11  Bug fix internal verification
2026-06-11  RSS panel UI + benchmark split (core 100 / extended 150)
            Remove REBEL + Ollama din frontend
            Sync Qwen3 labels în modelLabels.ts
```

**Motivație migrare:** Qwen3-1.7B rulează local fără server separat (spacy-llm integrare directă), nu necesită Ollama daemon, mai ușor de distribuit pentru evaluare academică.

---

## SECȚIUNEA 3: CE A MERS BINE

### Tehnologii adoptate și rămase stabile

| Tehnologie | Introdus | Status | Motivație rețin |
|---|---|---|---|
| spaCy + en_core_web_trf | 2026-03-27 | ✅ Pipeline A activ | Acuratețe NER înaltă, robust |
| Wikidata SPARQL | 2026-03-29 | ✅ Activ | Singura sursă de fapte temporale la scară |
| FastAPI | 2026-04-02 | ✅ Activ | Performanță, async nativ, Pydantic |
| React + MUI | 2026-04-26 | ✅ Activ | Rapid de prototipat UI complex |
| pytest | 2026-05-13 | ✅ 33 teste | Regresia detectată de mai multe ori |
| Neo4j (opțional) | 2026-05-08 | ✅ Opțional | Cross-article nativ în graf |
| Reference KG local | 2026-03-29 | ✅ 1169 fapte | Fallback rapid fără API |

### Decizii arhitecturale corecte

1. **Formula TCS ponderată pe severitate** (CRITICAL=1.5, HIGH=1.0, MEDIUM=0.3, LOW=0.0) — Diferențierea pe severitate a permis tunajul precis al pragului de decizie.

2. **Arhitectura plugin pentru extractor-i** — Registry pattern în orchestrator a permis adăugarea Pipeline B și C fără modificări în restul sistemului.

3. **3-level Wikidata cache** (in-memory → Neo4j → SPARQL live) — Reducea numărul de query-uri API cu ~70% pe seturi repetate.

4. **Reference KG local cu update incremental** — Scriptul `update_reference_kg.py` cu auto-corectare QID a crescut KG de la 14 → 150 entități fără a elimina datele existente.

5. **Separarea `persist` de utilizarea Neo4j** — Store-ul Neo4j era deschis și pentru cache Wikidata chiar fără `persist=True`.

### Features care au îmbunătățit metricile

- **V5 HOLDS_POSITION only** (2026-05-14): Restricționarea verificării externe la relații HOLDS_POSITION a redus false positive-urile drastice — Precision a crescut de la ~0.5 la 0.625.
- **Entity subject matching threshold 0.85** (2026-05-14): Fix pentru conflarea "Clinton" (Bill vs Hillary) — eroare critică în verificare.
- **KG date tolerance 400 days** (2026-05-14): Toleranța mare justificată de imprecizia expresiilor temporale din text ("în 1993" poate referi orice lună).
- **Few-shot prompting** (2026-05-05): 13 linii de exemple concrete au îmbunătățit vizibil calitatea extracției Pipeline B.
- **Wikidata inverse check** (2026-05-15): Verificarea că intervalul articolului coincide cu intervalul Wikidata (nu doar că entitatea există) — detectare erori de tip "Biden senator în 2015".

---

## SECȚIUNEA 4: CE NU A MERS / A FOST SCHIMBAT

### Tehnologii abandonate

| Tehnologie | Introdusă | Abandonată | Motiv |
|---|---|---|---|
| **Ollama** (runtime LLM) | 2026-04-01 | 2026-06-02 | Necesita server separat, setup complex, dificil de distribuit |
| **llama3/mistral** (via Ollama) | 2026-04-01 | 2026-06-02 | Înlocuit de Qwen3-1.7B (spacy-llm inline) |
| **REBEL-large** (Pipeline C) | 2026-05-28 | 2026-06-02 | F1=0.038 — complet neperformant pe task |
| **QLoRA fine-tuning** | 2026-05-06 | — | Infrastructura completă, dar niciodată rulată efectiv |
| **LIAR dataset** (extern) | 2026-03-27 | Deprioritizat | TCS=0.5 pe aproape toate articolele (lipsa fapte temporale) |
| **FakeNewsNet** (extern) | 2026-03-27 | Deprioritizat | Același comportament ca LIAR |
| **DeepKE** | Menționat | Niciodată comis | Prea complex pentru integrare în timp util |

### Detalii abandonări

**Ollama → spacy-llm + Qwen3-1.7B:**
- Ollama necesita un daemon separat care trebuia pornit înainte de API (`start.sh` auto-check)
- Complicat de distribuit pentru demonstrare academică
- Qwen3-1.7B prin spacy-llm rulează inline în procesul Python, fără dependențe externe
- Migrarea a implicat rescrierea completă a `llm_extractor.py` → `spacy_llm_extractor.py` (252 linii modificate)

**REBEL-large (F1=0.038):**
- REBEL extras relații tipice din Wikipedia (Wikidata triples) — nu relații temporale din articole de știri
- Distribuția temporală extrasă de REBEL nu coincidea cu ce TCS verifica
- Arhivat ca `rebel_extractor_archived.py` cu comentariul explicit "F1=0.038"
- Motivul fundamental: REBEL e antrenat pe fraze declarative scurte, articolele de știri au structuri narative mai complexe

**QLoRA (niciodată rulat):**
- Infrastructura complet construită în 2026-05-06: `train.jsonl` (331 exemple), `eval.jsonl` (83 exemple), `train_qlora.py`, `export_gguf.py`, `Modelfile` pentru Ollama
- Blocat probabil de: hardware GPU insuficient, deadline thesis, decizia ulterioară de migrare la Qwen3 care face QLoRA redundant
- 1,109 linii de cod scrise și niciodată executate

**LIAR / FakeNewsNet:**
- Loaders implementați și funcționali
- Problema fundamentală: articolele LIAR conțin afirmații politice scurte, nu narațiuni temporale
- TCS scoring: aproape toate articolele returnau 0.5 (insufficient_data) — sistemul nu putea extrage fapte temporale din "Obama a crescut deficitul" fără context
- Evaluare din 2026-05-14: 50 articole LIAR, majority TCS=0.5, nicio separare FAKE/TRUE

### Bug-uri majore rezolvate

| Data | Bug | Fix |
|---|---|---|
| 2026-03-28 | Score interpretare greșit | Fix formula TCS |
| 2026-04-04 | source_sentence None în LLM | Fix indexare în llm_extractor |
| 2026-05-14 | Cross-entity false positives ("Clinton" ambiguu) | SequenceMatcher threshold 0.85 |
| 2026-05-15 | Neo4j cache cuplat cu persist | Decuplare: cache activ indiferent de persist flag |
| 2026-06-02 | TCS returnează 0.5 când n_claims=0 dar există fapte | Fix condiție în TCSCalculator |
| 2026-06-11 | Internal verification eroare | Fix în internal.py |

---

## SECȚIUNEA 5: EVOLUȚIE METRICI

### Benchmark propriu (articole controlate cu inconsistențe cunoscute)

| Data | n articole | Precision | Recall | F1 | Accuracy | Prag |
|------|-----------|-----------|--------|-----|----------|------|
| 2026-05-13 | 5 (manual) | — | — | — | — | — |
| 2026-05-14 | 84 | 0.625 | 0.139 | **0.227** | 0.595 | 0.55 |
| 2026-05-15 | 84 | 0.636 | 0.194 | **0.298** | 0.607 | 0.55 |
| 2026-05-16 | 100 | 0.615 | 0.182 | **0.281** | 0.590 | 0.55 |
| 2026-06-02 | 100 | 0.714 | 0.227 | **0.345** | 0.620 | 0.70 |
| 2026-06-11 | 150 | 0.522 | 0.160 | **0.245** | 0.507 | 0.70 |

**Observații:**
- Precision relativ bună (0.6–0.7) → când sistemul spune FAKE, de obicei are dreptate
- Recall slab (0.14–0.23) → sistemul ratează majoritatea articolelor FAKE → **low sensitivity la inconsistențe subtile**
- Creșterea benchmark-ului la 150 articole (cu tipuri noi de inconsistență: implicit_contradiction, entity_inconsistency) a redus F1 de la 0.345 → 0.245, confirmând că inconsistențele mai complexe sunt mai greu de detectat

### Comparare Pipeline A vs Pipeline B (Ollama, 20 articole)

| Pipeline | Precision | Recall | F1 | Accuracy | avg_tcs_true |
|---|---|---|---|---|---|
| A (spaCy) | 0.75 | 0.30 | **0.429** | 0.60 | 0.950 |
| B (llama3/Ollama) | 0.625 | 0.50 | **0.556** | 0.60 | 0.796 |

→ Pipeline B (LLM) Recall mai bun (+20pp) dar Precision mai slabă. TCS mediu pe articole TRUE mai mare la A (0.95 vs 0.796).

### Evaluare externe

| Sursă | Data | n | F1 | Accuracy | Obs |
|---|---|---|---|---|---|
| Politifact | 2026-05-15 | 98 | 0.303 | 0.531 | Fapte nu neapărat temporale |
| Politifact | 2026-05-16 | 98 | 0.303 | 0.531 | Identic — dataset stabil |
| Wikipedia REST | 2026-05-16 | 12 | — | **0.833** | Verificare fapte individuale |
| LIAR | 2026-05-14 | 50 | ~0 | ~0.5 | Majority TCS=0.5 |

### Evoluție Reference KG

| Data | Entități | Fapte | Eveniment |
|---|---|---|---|
| 2026-03-29 | 14 | ~243 linii JSON | Prima versiune manuală |
| Pre 2026-05-29 | ? | **517** | Extindere graduală |
| 2026-05-29 | ? | **1161** | Commit masiv (+644 fapte, +144%) |
| 2026-06-11 | **150** | **1169** | Adăugare Harry Truman + 7 noi entități |

### Evoluție benchmark

```
2026-05-13:   5 articole (manual, US moderni)
2026-05-14:  25 articole (extended, tot US moderni)  
2026-05-14:  84 articole (+ articole suplimentare LIAR-style)
2026-05-16: 100 articole (benchmark stabil)
2026-06-11: 100 (core) + 50 noi = 150 (extended)
            → 19 TRUE: Nixon, Ford, LBJ, Eisenhower, Kennedy, Truman,
                       Starmer, Blair, Thatcher, Macron, Tusk, etc.
            → 31 FAKE: ordering_error, date_mismatch, entity_inconsistency,
                       future_as_past, implicit_contradiction
```

### Scor TCS mediu (comportament sistemului)

| Metrică | Valoare | Semnificație |
|---|---|---|
| avg_tcs TRUE articles (Jun 2) | **0.906** | Sistemul nu penalizează articolele corecte |
| avg_tcs FAKE articles (Jun 2) | **0.777** | Separare parțială, dar suprapunere mare |
| avg_tcs TRUE (Jun 11, 150 art) | **0.859** | Consistent |
| avg_tcs FAKE (Jun 11, 150 art) | **0.856** | Aproape identic cu TRUE — inconsistențe subtile nedetectate |

**Interpretare:** Sistemul funcționează bine pe inconsistențe temporale explicite (date greșite, ordine inversată). Eșuează pe inconsistențe implicite (contradicții logice, entități imposibile) unde TCS rămâne ridicat.

---

## SECȚIUNEA 6: DIRECȚII VIITOARE (din ce s-a încercat)

### 1. QLoRA Fine-tuning (infrastructura există, 5edce0b)

**Ce există:** `training/train_qlora.py` (165 linii), `training/data/train.jsonl` (331 exemple), `export_gguf.py` (96 linii), `Modelfile` pentru Ollama.

**Ce lipsește:** Execuție efectivă + validare. Dataset-ul de antrenament este mic (331 exemple) și ar necesita augmentare.

**Direcție:** Fine-tuning Qwen3-1.7B pe task-ul specific de extracție relații temporale din articole de știri. Ar elimina dependența de few-shot prompting și ar îmbunătăți Recall (principalul punct slab).

**Efort estimat:** ~2-3 zile cu acces la GPU (Google Colab Pro / Kaggle).

---

### 2. Inconsistențe implicite și contradicții logice

**Problema demonstrată de datele din Jun 11:** avg_tcs FAKE = 0.856 ≈ avg_tcs TRUE = 0.859 pe setul extins cu `implicit_contradiction` și `entity_inconsistency`. Sistemul nu detectează:
- "Ford a grațiat Nixon pentru crime pentru care Nixon nu a fost niciodată acuzat"
- "Reagan l-a succedat direct pe Carter, sărind peste Ford"

**Direcție:** NLI (Natural Language Inference) pe perechi de propoziții — model dedicat (e.g., DeBERTa-v3 antrenat pe NLI) pentru detectarea contradicțiilor interne.

---

### 3. Benchmark extins și evaluare pe dataset public

**Problema LIAR/FakeNewsNet:** TCS = 0.5 (insufficient_data) pe >90% articole → sistemul nu poate fi evaluat corect pe dataset-uri de fake news generale.

**Direcție:** Construirea unui dataset de benchmark specific pentru fapte temporale — articole de știri politice cu inconsistențe temporale documentate (deja început cu benchmark_articles_extended.json: 150 articole, 5 tipuri de inconsistențe).

**Următor pas natural:** Ajungerea la 500 articole cu acoperire mai largă (legislație, tratate, conflicte internaționale).

---

### 4. Evaluare Wikipedia REST (accuracy=83.3% — cel mai bun rezultat obținut)

**Observație importantă:** Verificarea faptelor individuale via Wikipedia REST a dat accuracy=83.3% (10/12 teste). Aceasta este mult mai bună decât F1=0.345 al sistemului complet.

**Direcție:** Wikipedia REST ca nivel primar de verificare externă (nu fallback), integrat înaintea Wikidata SPARQL pentru entități cu pagini Wikipedia clare.

---

### 5. Cross-article verification la scară (Neo4j)

**Ce există:** `neo4j_store.py` complet, `cross_article.py` (159 linii), endpoint `/cross-check/{article_id}`.

**Limitare actuală:** Necesită Neo4j pornit local (bolt://localhost:7687).

**Direcție:** Hosted Neo4j AuraDB (tier gratuit) pentru demonstrare fără setup local. Sau migrare la SQLite pentru persistare simplă a grafului de fapte.

---

### 6. REBEL arhivat — alternativă: spaCy-based relation extraction

**De ce REBEL a eșuat:** Antrenat pe Wikidata triples, nu pe articole de știri.

**Alternativă mai bună:** spaCy custom NER + rule-based relation patterns pe corefferenced entities — mult mai ușor de controlat și de evaluat.

---

## SECȚIUNEA 7: PENTRU PLANUL DE SINTEZĂ

```markdown
## 13. EVOLUȚIE PROIECT (din git history)

### 13.1 Cronologie sintetică

Proiectul FakeNews-XAI a evoluat în 83 de zile (2026-03-20 → 2026-06-11),
prin 80 de commit-uri, în 6 faze distincte:

| Fază | Perioadă | Durata | Contribuție principală |
|------|----------|--------|----------------------|
| Fundație | Mar 20 – Mar 29 | 9 zile | Pipeline C1→C4 de la zero |
| Integrare LLM | Apr 1 – Mai 5 | 34 zile | Pipeline B + API REST + UI |
| Verificare & Evaluare | Mai 6 – Mai 16 | 10 zile | Neo4j, pytest, benchmark 100 art. |
| Pipeline C (REBEL) | Mai 28 | 1 zi | Extractor relații — eșec (F1=0.038) |
| RSS & HITL | Mai 29 | 1 zi | Feeds live + validare umană |
| Migrare Qwen3 | Iun 2 – Iun 11 | 9 zile | Înlocuire Ollama → Qwen3-1.7B |

### 13.2 Tehnologii testate și decizia finală

| Tehnologie | Testat | Decizie | Motiv |
|---|---|---|---|
| spaCy + en_core_web_trf | Faza 1 | ✅ Reținut | Pipeline A principal |
| Ollama + llama3 | Faza 2 | ❌ Înlocuit | Setup complex, dificil de distribuit |
| spacy-llm + Qwen3-1.7B | Faza 6 | ✅ Pipeline B actual | Inline, fără dependențe externe |
| REBEL-large | Faza 4 | ❌ Arhivat | F1=0.038 pe task-ul nostru |
| QLoRA fine-tuning | Faza 3 | ⚠️ Infrastructură nefinalizată | Hardware, timp |
| Wikidata SPARQL | Faza 1 | ✅ Sursă primară | Acoperire globală, fapte temporale |
| Neo4j | Faza 3 | ✅ Opțional | Cross-article, cache Wikidata |
| RSS Stream | Faza 5 | ✅ C3b Level 5 | Fallback fapte recente |

### 13.3 Evoluția metricilor (benchmark propriu)

```
Date     │ n art │ Precision │ Recall │   F1  │ Accuracy
─────────┼───────┼───────────┼────────┼───────┼─────────
2026-05-14│  84  │   0.625   │ 0.139  │ 0.227 │  0.595
2026-05-16│ 100  │   0.615   │ 0.182  │ 0.281 │  0.590
2026-06-02│ 100  │   0.714   │ 0.227  │ 0.345 │  0.620  ← best F1
2026-06-11│ 150  │   0.522   │ 0.160  │ 0.245 │  0.507
```

**Concluzie metrici:** Sistemul detectează cu acuratețe relativă bună inconsistențele
temporale explicite (date greșite, ordine inversată), dar are recall slab pe 
inconsistențe subtile (implicite, logice). Creșterea benchmark-ului la 150 articole
cu tipuri de inconsistențe mai complexe a confirmat această limitare.

### 13.4 Concluzia evoluției

TCS-ul implementat ca sistem de reguli (Wikidata + Reference KG + verificare internă)
atinge Precision=0.71 dar Recall=0.23 pe benchmark-ul propriu controlat.
Îmbunătățirea Recall-ului reprezintă principala direcție de cercetare viitoare,
fie prin fine-tuning LLM pe task-ul specific (infrastructura QLoRA există),
fie prin adăugarea unui modul NLI pentru contradicții logice.

Wikipedia REST verification a dat accuracy=83.3% pe verificarea faptelor individuale,
sugerând că aceasta ar putea deveni sursa primară de verificare externă.
```

---

## STATISTICI FINALE PROIECT

| Metrică | Valoare |
|---------|---------|
| Total commits | 80 |
| Zile de dezvoltare | 83 |
| Fișiere backend Python | ~35 |
| Componente frontend React | ~12 |
| Linii de cod (backend estimat) | ~8,000 |
| Teste pytest | 33 |
| Entități Reference KG | 150 |
| Fapte Reference KG | 1,169 |
| Articole benchmark core | 100 |
| Articole benchmark extended | 150 |
| Tipuri inconsistențe acoperite | 8 |
| Surse verificare externe | 4 (Wikidata, Reference KG, Wikipedia REST, RSS) |
| Cea mai bună F1 atinsă | 0.345 (Jun 2, 100 articole, prag 0.70) |
| Wikipedia REST accuracy | 0.833 |
| Pipeline B actual | spacy-llm + Qwen3-1.7B |
| Tehnologii arhivate | Ollama, REBEL-large, LIAR eval |

---

*Raport generat automat din analiza git history — FakeNews-XAI*

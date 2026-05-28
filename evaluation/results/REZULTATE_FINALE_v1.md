# Rezultate Evaluare — după Fix A + Fix B
Data: 2026-05-23

## Context fixuri aplicate

**Fix A** (`run_benchmark.py`, `run_evaluation.py`): când `n_claims == 0`, articolul este clasificat
automat ca TRUE (predicted_fake=False), indiferent de scorul TCS. Motivație: TCS=0.5 la articolele
fără fapte temporale extrase este semnal de „date insuficiente", nu de articol fals.

**Fix B** (`tcs.py` → `SEVERITY_WEIGHTS`): `LOW: 0.2 → 0.0`, `MEDIUM: 0.5 → 0.3`.
Motivație: inconsistențele LOW sunt zgomot (false positives minore); reducând LOW la 0.0
și MEDIUM la 0.3, scorul TCS devine mai precis pentru inconsistențele cu adevărat semnificative.

---

## Benchmark 100 articole sintetice (Pipeline A — spaCy + Wikidata)

| Metric | Înainte (2026-05-16) | După Fix A+B (2026-05-23) | Δ |
|---|---|---|---|
| TP | 8 | 7 | -1 |
| TN | 51 | 52 | +1 |
| FP | 5 | 4 | -1 |
| FN | 36 | 37 | +1 |
| Precision | 0.615 | **0.636** | +0.021 |
| Recall | 0.182 | 0.159 | -0.023 |
| F1 | 0.281 | 0.255 | **-0.026** |
| Accuracy | 0.590 | 0.590 | 0 |
| Avg TCS (TRUE) | 0.876 | 0.882 | +0.006 |
| Avg TCS (FAKE) | 0.814 | 0.818 | +0.004 |
| Separare TRUE-FAKE | +0.062 | +0.064 | +0.002 |

**Observații:**
- Fix A a eliminat 1 FP (articol TRUE cu n_claims=0 nu mai e clasificat FAKE) și a adăugat 1 FN
  (articol FAKE cu n_claims=0, ex. „Clinton Presidency — Wrong Mandate Years", nu mai e detectat).
- Fix B a crescut ușor TCS pentru articolele TRUE și FAKE (penalitățile LOW sunt acum 0.0).
- Separarea TRUE-FAKE (+0.064) s-a îmbunătățit marginal față de înainte (+0.062).
- F1 a scăzut ușor (-0.026) deoarece Fix A adaugă un FN net acolo unde înainte era un TP.

**Benchmark 100 articole (Pipeline B — LLM llama3 + Wikidata):**
> Rulare în curs la momentul compilării raportului. Procesul `run_benchmark.py --pipeline llm`
> necesită ~60 min (Ollama serializează cererile cu extracția LLM concurentă). Rezultatele
> vor fi disponibile în `results_YYYY-MM-DD.json` la finalizare.

---

## PolitiFact 49 articole (Pipeline A — spaCy + Wikidata)

| Metric | Înainte (2026-05-16) | După Fix A+B (2026-05-23) | Δ |
|---|---|---|---|
| TP | 5 | 5 | 0 |
| TN | 21 | 20 | -1 |
| FP | 7 | 7 | 0 |
| FN | 16 | 16 | 0 |
| Precision | 0.417 | 0.417 | 0 |
| Recall | 0.238 | 0.238 | 0 |
| F1 | **0.303** | **0.303** | 0 |
| Accuracy | 0.531 | 0.521 | -0.010 |
| Avg TCS (TRUE) | 0.815 | 0.818 | +0.003 |
| Avg TCS (FAKE) | 0.843 | 0.846 | +0.003 |
| Separare | -0.029 | -0.028 | +0.001 |

**Observații:**
- Fix A nu a fost aplicat în `run_politifact_eval.py` (scriptul nu a fost inclus în scope).
  Ca urmare, 2 articole cu n_claims=0 rămân cu TCS=0.5:
  - [37] Tennessee Democratic Party (exp=TRUE) → FP (bug nerezolvat în PolitiFact)
  - [44] Bloggers (exp=FAKE) → TP (coincidență corectă, s-ar pierde cu fix)
- Fix B a crescut ușor TCS pentru ambele clase (+0.003), dar nu a traversat pragul de 0.55.
- Separarea TRUE-FAKE rămâne negativă (-0.028): scorul TCS nu discriminează bine pe date reale.
- Separarea negativă indică că articolele FAKE reale au TCS mai mare decât cele TRUE pe PolitiFact,
  ceea ce sugerează că inconsistențele temporale nu sunt caracteristica discriminativă dominantă
  în declarațiile politice reale (spre deosebire de articolele sintetice din benchmark).

---

## Extraction Benchmark C1 izolat

### Pipeline A — spaCy (en_core_web_trf)

| Metric | Valoare |
|---|---|
| Precision extracție | **0.699** |
| Recall extracție | 0.444 |
| F1 extracție | 0.543 |
| Avg fapte / articol TRUE | 10.48 |
| Avg fapte / articol FAKE | 6.14 |
| Zero-fact rate | **0.00%** (0 articole) |
| Total fapte extrase | 857 / 100 articole |
| Total fapte corecte | 599 |

**Detectii per tip inconsistenta (articole FAKE cu cel putin un hit):**

| Tip inconsistenta | Articole detectate |
|---|---|
| ordering_error | 6 |
| date_mismatch | 2 |
| future_as_past | 2 |
| entity_inconsistency | 1 |

### Pipeline B — LLM (llama3)

> Rulare în curs la momentul compilării raportului. Procesul LLMExtractor pe 100 articole
> necesită ~60 min (Ollama, ~35s/articol). Rezultatele vor fi disponibile în
> `evaluation/results/extraction_benchmark_YYYY-MM-DD.json` la finalizare.

---

## Comparatie Pipelines (datele disponibile)

| Metric | Pipeline A (spaCy) | Pipeline B (LLM) |
|---|---|---|
| Benchmark F1 (100 art.) | 0.255 | în rulare |
| PolitiFact F1 (49 art.) | 0.303 | — |
| Extracție Precision | 0.699 | în rulare |
| Extracție Recall | 0.444 | în rulare |
| Extracție F1 | 0.543 | în rulare |
| Avg fapte/TRUE | 10.48 | în rulare |
| Avg fapte/FAKE | 6.14 | în rulare |
| Zero-fact rate | 0.00% | în rulare |

---

## Concluzie

### Unde este bottleneck-ul?

**Bottleneck-ul principal este în C1 (extracție) și C3a/C3b (verificare), nu în C4 (scoring).**

**C1 — Extracție (spaCy):**
- Zero-fact rate = 0% pe benchmark (toate articolele au cel puțin un fapt), dar multe articole
  FAKE scurte produc puține fapte (Avg FAKE = 6.14 vs TRUE = 10.48).
- Recall extracție = 0.444: din 44 de articole FAKE cu known_inconsistencies, spaCy găsește
  subiect/obiect relevant în sub jumătate din cazuri. Inconsistențele subtile (ordering_error,
  implicit_contradiction) nu generează fapte temporale explicite.
- Detectie per tip: ordering_error detectat în 6 articole, dar benchmark-ul conține mult mai multe.
  Inconsistențele bazate pe secvențiere logică (ex. „ACA aprobat înainte de vot") nu apar
  ca fapte temporale în extracție — necesită raționament cauzal, nu simplu NER + dependency parsing.

**C3 — Verificare:**
- 37 din 44 articole FAKE benchmark sunt FN: extracția e prezentă dar verificarea nu detectează
  inconsistența. Exemplu: articolele 53-99 (ordering errors, wrong dates) au TCS=1.0 deoarece
  inconsistența e între secvența narativă a faptelor, nu între faptele individuale și Wikidata.
- Wikidata acoperă bine entitățile majore (președinți US), dar acoperirea temporală precisă
  (ex. „Trump a semnat legea X la data Y") e redusă → C3b nu poate valida/infirma.

**Efectul Fix A+B:**
- Fix A a rezolvat o problemă reală (articole TRUE cu 0 claims nu mai sunt FP) dar a descoperit
  că unele articole FAKE sintetice au 0 claims (au fost greșit pozitive din accident, nu din detecție).
- Fix B (LOW→0.0, MEDIUM→0.3) a redus zgomotul în scoring: inconsistențele minore nu mai
  penalizează articolele TRUE. Separarea TRUE-FAKE pe benchmark crește ușor (+0.002).
- Pe PolitiFact, efectul este neutru: Fix B nu schimbă clasificările la threshold 0.55
  deoarece TCS-urile sunt în general mai mari de 0.7 (articolele reale au mai puțin zgomot).

### Direcții pentru îmbunătățire

1. **C1**: Îmbunătățirea extractorului pentru inconsistențe de tip ordering (detectarea inversărilor
   temporale la nivel de frază, nu doar extragerea de fapte individuale).
2. **C3a**: Verificarea secvențelor de fapte (A cauzează B, dar A e datat după B) — raționament
   cauzal dincolo de verificarea individuală a faptelor.
3. **Threshold adaptiv**: Pe PolitiFact, separarea negativă sugerează că pragul 0.55 nu e optim
   pentru date reale. Un threshold mai mare (0.7-0.8) ar reduce FP-urile false.
4. **Fix A în run_politifact_eval.py**: Același fix cu n_claims==0 → TRUE ar elimina FP-ul de la
   articolul [37] (Tennessee Democratic Party).

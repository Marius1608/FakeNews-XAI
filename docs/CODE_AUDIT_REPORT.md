# FakeNews-XAI — Code Audit Report

Generated: 2026-06-14
Scope: `backend/pipeline/**`, `backend/routers/**`, `backend/config.py`, `backend/main.py`,
`backend/pipeline/orchestrator.py`, `backend/dependencies.py`, `frontend/src/components/**`,
`frontend/src/types/**`, `frontend/src/utils/**`, `frontend/src/api/client.ts`, `frontend/src/App.tsx`.

Note: the actual layout differs from the audit brief — routers live in `backend/routers/`
(not `backend/api/`), the orchestrator is `backend/pipeline/orchestrator.py`, and shared
singletons live in `backend/dependencies.py`.

---

## CRITICAL ISSUES (must fix before thesis submission)

### C1 — Shared orchestrator singletons carry per-request state across requests and endpoints
`[backend/dependencies.py:16-23]` + `[backend/routers/analyze.py:136-145]` +
`[backend/routers/compare.py:119-132]` + `[backend/routers/batch.py:118-120]`

`get_orchestrator()` caches one `PipelineOrchestrator` per `pipeline:model` key and reuses it
for every request. Each request then *mutates* that shared instance:

```python
orchestrator._persistent_store = store
orchestrator.persist = req.persist
orchestrator._enable_cross_article = False
orchestrator.use_web_search = req.use_web_search
orchestrator.use_rss = req.use_rss
```

Because the values are stored on a long-lived shared object, state bleeds between **sequential**
requests (this is real today, independent of concurrency):

- A `/analyze` with `persist=True` leaves `orchestrator.persist=True` and a now-closed
  `_persistent_store` on the instance. A later `/analyze-batch` (`batch.py:118-120`) never
  resets these, so `orchestrator.run()` (`orchestrator.py:130-167`) generates a spurious
  `article_id` and tries `add_facts()` on a stale store — duplicating/conflicting with the
  batch router's own persistence path.
- Under a multi-worker / async-with-`await` deployment this also becomes a genuine race
  (two requests clobbering `_persistent_store`/`persist`). It is currently masked only because
  the `async def` handlers call the blocking sync `run()` and accidentally serialize.

Suggested fix: make the orchestrator stateless per request — pass `persistent_store`, `persist`,
`use_web_search`, `use_rss`, `enable_cross_article` as arguments to `run()` instead of setting
attributes; or construct a lightweight orchestrator per request and cache only the expensive
extractor/model objects.

### C2 — Cached external verifier holds a store that was already closed
`[backend/pipeline/orchestrator.py:88-97]` + `[backend/routers/analyze.py:142-154]`

`external_verifier` is lazily created **once** and caches `persistent_store=self._persistent_store`
at creation time. On later requests, `analyze.py` updates only `use_web_search` and `_rss_verifier`
on the cached verifier (`analyze.py:142-145`) — it never updates `_persistent_store`. Meanwhile the
router closes the store in `finally` (`analyze.py:152-154`). The next request's external
verification therefore calls `get_cached_wikidata` / `cache_wikidata_result` on a **closed** driver.

This is currently self-healed by `Neo4jTKGStore._ensure_connected()` (`neo4j_store.py:46-53`), which
silently reconnects — but that means the request-1 store object gets revived and is never closed
again (connection leak), and the verifier permanently uses a different store object than the one the
router opened/closed.

Suggested fix: same as C1 — do not cache the store on the verifier; pass it per call, or rebuild the
verifier when the store identity changes.

### C3 — `facts_verified` / `facts_total` are computed but never used in the TCS score
`[backend/pipeline/orchestrator.py:140-152]` + `[backend/pipeline/scoring/tcs.py:22-78]`

The orchestrator computes external coverage and passes it in:

```python
facts_verified = external.facts_checked
facts_total = len(all_facts)
result = self._calculator.compute(..., facts_verified=facts_verified, facts_total=facts_total, ...)
```

`TCSCalculator.compute()` accepts `facts_verified`/`facts_total` as parameters but never references
them — the score is `(1 - penalty_ratio) * score_coherence` only. External verification coverage has
no effect on the final TCS. For a thesis this is a substantive correctness/methodology gap: either
wire coverage into the formula or remove the parameters and document the omission so the written
methodology matches the code.

---

## MEDIUM ISSUES (should fix)

### M1 — `/analyze` cross-article banner is effectively dead
`[backend/routers/analyze.py:139]` + `[frontend/src/components/AnalyzeTab.tsx:234-262]`

`orchestrator._enable_cross_article = False` is forced in `/analyze`, so
`result.cross_article_inconsistencies` is always `[]`. The "Cross-article conflicts detected"
banner in `AnalyzeTab` (driven by `analyzeResult.cross_article_inconsistencies`) can therefore never
render from an analyze call. Cross-article checks only happen via the separate "Check against saved
articles" button. Either remove the banner or enable the inline check intentionally.

### M2 — `severity_label` differs between response code paths
`[backend/routers/analyze.py:85]` vs `[backend/pipeline/scoring/explainer.py:151]`

`_to_inconsistency_response` (used for cross-article + batch conflicts) sets
`severity_label=inc.severity.value.title()` → `"High"`, `"Medium"`. But
`explainer._inconsistency_detail` (used for the main inconsistency list) sets
`severity_label` from `_SEVERITY_LABELS` → `"significant"`, `"moderate"`. The frontend
`InconsistencyList` renders `item.severity_label` verbatim, so the same severity shows different
chip text depending on which list it appears in. Pick one mapping.

### M3 — Frontend re-segments article text, so highlights can land on the wrong sentence
`[frontend/src/components/TextHighlight.tsx:69]`

`TextHighlight` splits text with `text.split(/(?<=[.!?])\s+/)` and maps `annotation.sentence_idx`
to that array index. The backend `sentence_idx` comes from spaCy's `doc.sents`, whose segmentation
differs (abbreviations, quotes, decimals). When the two disagree, the colored highlight attaches to
the wrong sentence. For an XAI demo this is visible and misleading. Consider returning sentence
spans (char offsets) from the backend and highlighting by offset instead of re-splitting.

### M4 — `use_web_search` exists in the backend but is missing from the frontend request type
`[backend/routers/analyze.py:30]` vs `[frontend/src/types/api.ts:19-28]`

`AnalyzeRequest` (Pydantic) accepts `use_web_search`, but the TS `AnalyzeRequest` interface omits it,
so the Wikipedia REST fallback (C3b) can never be triggered from the UI. Add the field (and a toggle)
or remove the backend flag.

### M5 — `upload.py` has no error handling around PDF/DOCX parsing
`[backend/routers/upload.py:16-26]`

A corrupt/encrypted PDF or malformed DOCX raises inside `PdfReader(...)` / `Document(...)`, producing
an unhandled 500 instead of a clean 400. Wrap parsing in `try/except` and return a 400 with a useful
message.

### M6 — `/compare` leaks raw exception text to the client; `/analyze` does not
`[backend/routers/compare.py:125,135]` vs `[backend/routers/analyze.py:149-151]`

`/compare` returns `detail=f"Pipeline A error ...: {e}"`, exposing internal stack/message detail,
while `/analyze` returns a generic `"Internal pipeline error."`. Make them consistent (prefer the
generic message; keep the detail in logs).

### M7 — Stale model names in the API schema description
`[backend/routers/analyze.py:28]`

`description="Specific model: en_core_web_trf, llama3, mistral, etc."` still references the removed
Ollama models. This surfaces in the OpenAPI docs. Update to the current registry
(`en_core_web_trf`, `Qwen/Qwen3-1.7B`).

### M8 — Fragile Wikidata date slicing
`[backend/pipeline/verification/wikidata.py:201-215]`

`clean[:len(fmt.replace('%','X').replace('X',''))]` computes a meaningless slice length; the function
only works because of the `clean[:10]` fallback. Year-only qualifiers (`"2009"`) fall through to the
fallback `strptime("2009", "%Y-%m-%d")` and return `None`. Replace with explicit format attempts on
the full `clean` string.

---

## LOW PRIORITY (nice to fix)

- `[backend/main.py:51-58]` `@app.on_event("startup"/"shutdown")` is deprecated in modern FastAPI;
  migrate to the `lifespan` context manager.
- `[backend/pipeline/scoring/tcs.py:10-11]` unused imports (`TemporalKnowledgeGraph`,
  `InternalVerificationResult`, `ExternalVerificationResult`) and `[tcs.py:16]` `MIN_TEMPORAL_CLAIMS`
  is defined but never used.
- `[backend/pipeline/scoring/explainer.py:15-17]` same three unused imports; `explain()`
  (`explainer.py:71-81`) is not called by any router (only `explain_structured`).
- `[backend/pipeline/graph/neo4j_store.py:250]` `Optional[...]` used in an annotation without
  importing `Optional` — only safe because of `from __future__ import annotations`. Add the import.
- `[backend/pipeline/graph/neo4j_store.py:147]` `datetime.utcnow()` is deprecated; use
  `datetime.now(timezone.utc)`.
- `[backend/pipeline/graph/store.py:148]` `_edge_attrs` always sets `"fact_idx": -1` (dead
  placeholder).
- `[backend/pipeline/verification/external.py:121-125,387-402]` relation is filtered in
  `relevant_ref` and then re-filtered inside `_compare_with_reference` — redundant.
- `[backend/routers/health.py]` imports `logging` indirectly unused; endpoint fine. Minor.
- `[frontend/src/components/InconsistencyList.tsx:26-33]` `TYPE_LABELS` is missing several backend
  types (`factual_contradiction`, `implicit_contradiction`, `future_as_past`, `entity_inconsistency`)
  — they fall back to the raw enum string in the UI.
- `[frontend/src/App.tsx:127]` `availableModels` is only passed to `BatchTab`; `AnalyzeTab` and
  `CompareTab` each refetch `/models` independently (3 fetches of the same data on load).
- `[backend/pipeline/verification/internal.py:131]` `MAX_PLAUSIBLE_TENURE_YEARS`, and various magic
  buffers (180-day, 30-day, `DATE_TOLERANCE_DAYS=200`, `SIMILARITY_THRESHOLD`) are scattered as
  module constants — consider centralizing tuneables in `config.py`.

---

## DEAD CODE (safe to remove)

- `[backend/pipeline/extraction/rebel_extractor_archived.py]` — entire archived REBEL extractor;
  not imported anywhere (orchestrator only registers `spacy` and `llm`). Keep only if intentionally
  retained as a thesis artifact; otherwise delete.
- `[backend/pipeline/extraction/spacy_extractor.py:69-72]` `SEQUENCE_VERBS` set is never used —
  `_classify_relation` matches sequence verbs via inline literals (`{"precede","predate","antedate"}`,
  `{"follow","succeed"}`), not this set.
- `[backend/pipeline/verification/internal.py:270-276]` the `ended_facts` loop in V5 ends in `pass`
  (computes `point_end` and does nothing) — no-op dead block.
- `[backend/pipeline/graph/models.py:42]` + `[explainer.py:52]` `InconsistencyType.ANACHRONISM` and
  its template are never produced by any verifier.
- `[backend/pipeline/scoring/tcs.py:16]` `MIN_TEMPORAL_CLAIMS` (also listed under LOW).
- Unused imports listed under LOW (`tcs.py`, `explainer.py`).
- `[frontend/src/utils/modelLabels.ts:2-4,9]` `en_core_web_lg` / `en_core_web_sm` labels are unused
  given the current single-model registry (`SPACY_MODELS` defaults to `en_core_web_trf` only) — keep
  only if you plan to re-expose them.

---

## FRONTEND-BACKEND SYNC ISSUES

| Field / area | Backend returns / expects | Frontend has | Status |
|---|---|---|---|
| `AnalyzeRequest.use_web_search` | accepted (`analyze.py:30`) | absent in `api.ts:19-28` | Frontend cannot send it (M4) |
| `severity_label` | `"High"`/`"Medium"` (cross-article, `analyze.py:85`) vs `"significant"`/`"moderate"` (main list, `explainer.py:151`) | rendered verbatim (`InconsistencyList.tsx:92`) | Inconsistent labels (M2) |
| `cross_article_inconsistencies` | always `[]` from `/analyze` (`analyze.py:139`) | banner expects content (`AnalyzeTab.tsx:234`) | Dead UI path (M1) |
| inconsistency `type` values | 10 enum types (`models.py:36-46`) | `TYPE_LABELS` covers 6 (`InconsistencyList.tsx:26-33`) | Others show raw enum string |
| `sentence_idx` semantics | spaCy `doc.sents` index | re-split via regex (`TextHighlight.tsx:69`) | Possible mis-highlight (M3) |
| `AnalyzeResponse.timeline` | `list[dict]` (untyped, `analyze.py:67`) | typed `TimelineEvent[]` (`api.ts:53-64`) | Keys match; OK |
| `HealthResponse.components` | `pipeline_a.type="spacy"`, `pipeline_b.type="qwen"` | matching union types (`api.ts:204-220`) | OK |
| Upload response | `text/filename/file_type/char_count` | `UploadResponse` (`client.ts:73-78`) | OK |

Spot-check answers to the brief's targeted questions:

- Every endpoint has a frontend type/client function: yes (`/health`, `/models`, `/analyze`,
  `/compare`, `/articles`, `/articles/cross-check`, `DELETE /articles/{id}`,
  `/articles/{id}/verify`, `/analyze-batch`, `/upload` all covered in `client.ts`).
- Qwen3-1.7B is a true singleton: yes — module-level `_qwen_model`/`_qwen_tokenizer` with a
  `_load_failed` guard (`spacy_llm_extractor.py:27-30,106-125`); loaded once.
- No circular imports detected.
- No stray `localhost:8000` outside `client.ts`; base URL is `REACT_APP_API_URL ?? localhost:8000`.
- No `console.log` in components; no `print()` in audited backend modules (the `print()` hits are in
  out-of-scope `scripts/` and `evaluation/` CLI tools, which is appropriate).
- `useEffect` dependency arrays are all present and correct (the intentional ref pattern in
  `ArticleInput.tsx:73-83` is fine).

---

## SUMMARY

Total issues: **3 critical, 8 medium, ~11 low** (+ ~7 dead-code items).

The three critical findings share one root cause worth fixing first: **the orchestrator is a mutable
shared singleton** (C1/C2). Refactoring `run()` to take request-scoped parameters resolves the
stale-store reuse, the cross-endpoint state bleed, and the latent race in one change. C3 (TCS formula
ignores external-verification coverage) is independent and is the most important *methodology* fix for
the thesis — decide whether coverage should affect the score and align code with the written method.

Estimated fix time:
- Critical (C1+C2 refactor, C3 decision/wiring): ~4–6 hours
- Medium (M1–M8): ~3–4 hours
- Low + dead code cleanup: ~2 hours

**Total: ~9–12 hours.**
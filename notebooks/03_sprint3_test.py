# ---
# 03_sprint3_test.py
#
# Test end-to-end Sprint 3 — verifica componentele noi:
#   - LLMExtractor (Pipeline B via Ollama)
#   - TCSExplainer (explicatii text + structurate)
#   - Pipeline A vs Pipeline B pe acelasi articol
#   - Pydantic schemas (AnalyzeRequest / CompareRequest)
#
# Doua scenarii:
#   A) Articol consistent (din Sprint 1/2) → ambele pipeline-uri
#   B) Articol cu inconsistente → explicatii detaliate
#
# Se poate rula ca script Python sau convertit in .ipynb cu:
#   jupytext --to notebook 03_sprint3_test.py
# ---

# %% [markdown]
# # Sprint 3 — Test Pipeline B + Explainer + Comparatie
#
# Testam componentele noi construite in Sprint 3:
# 1. **LLMExtractor** — Pipeline B via Ollama (daca e disponibil)
# 2. **TCSExplainer** — explicatii in limbaj natural + structurate
# 3. **Comparatie A vs B** — pe acelasi articol
# 4. **Pydantic schemas** — validare request/response API

# %% Imports si setup
import sys
import logging
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path.cwd().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("notebook")

from backend.pipeline.graph.models import Article
from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.pipeline.scoring.explainer import TCSExplainer

print("Import-uri OK.")

# %% [markdown]
# ## 1. Articole de test
#
# Aceleasi articole sintetice din Sprint 2 — le refolosim
# ca sa comparam scorurile intre pipeline-uri.

# %% Articole de test
ARTICLE_A_TEXT = """
Barack Obama served as the 44th President of the United States from January 2009
to January 2017. During his presidency, he signed the Affordable Care Act into law
in March 2010.

Before becoming president, Obama was a senator from Illinois starting in January 2005.
He announced his presidential campaign in February 2007 in Springfield, Illinois.

In September 2008, the global financial crisis hit Wall Street. Obama won the
presidential election in November 2008, defeating John McCain.

After leaving office in 2017, Obama established the Obama Foundation in Chicago.
He published his memoir "A Promised Land" in November 2020.
"""

ARTICLE_B_TEXT = """
Barack Obama served as the 44th President of the United States from January 2017
to January 2009. During his presidency, he signed the Affordable Care Act into law
in March 2005.

Obama announced his presidential campaign in February 2009 in Springfield, Illinois.
He won the presidential election in November 2008, defeating John McCain.

In September 2008, the global financial crisis hit Wall Street. Obama left office
in 2017 and established the Obama Foundation in Chicago.
"""

article_a = Article(
    text=ARTICLE_A_TEXT,
    title="Barack Obama: A Political Timeline (Consistent)",
    publication_date=datetime(2024, 1, 15),
    source="synthetic-consistent",
    label="true",
    dataset="synthetic",
)

article_b = Article(
    text=ARTICLE_B_TEXT,
    title="Barack Obama: A Political Timeline (With Inconsistencies)",
    publication_date=datetime(2024, 1, 15),
    source="synthetic-inconsistent",
    label="false",
    dataset="synthetic",
)

print(f"Articol A: '{article_a.title}' ({len(article_a.text)} chars)")
print(f"Articol B: '{article_b.title}' ({len(article_b.text)} chars)")

# %% [markdown]
# ## 2. Pipeline A (spaCy) — Baseline
#
# Rulam Pipeline A pe ambele articole pentru referinta.

# %% Pipeline A
print("\n" + "=" * 60)
print("PIPELINE A (spaCy) — Referinta")
print("=" * 60)

orch_a = PipelineOrchestrator(use_wikidata=False, extractor_name="spacy")

result_a_consistent = orch_a.run(article_a)
result_a_inconsistent = orch_a.run(article_b)

print(f"\n  Articol A (consistent):    TCS = {result_a_consistent.score:.4f} | {result_a_consistent.label}")
print(f"  Articol B (inconsistent):  TCS = {result_a_inconsistent.score:.4f} | {result_a_inconsistent.label}")

# %% [markdown]
# ## 3. Pipeline B (LLM) — Ollama
#
# Verificam daca Ollama e disponibil. Daca nu, sarim aceasta sectiune
# si marcam rezultatele ca "N/A".

# %% Verificare disponibilitate Ollama
from backend.pipeline.extraction.llm_extractor import LLMExtractor

llm = LLMExtractor()
ollama_available = llm.is_available()

if ollama_available:
    print(f"✓ Ollama disponibil ({llm.host}, model: {llm.model})")
else:
    print(f"⚠ Ollama indisponibil la {llm.host}")
    print("  Pipeline B va fi sarit. Pentru a activa:")
    print("  1. Instaleaza Ollama: https://ollama.ai")
    print("  2. Ruleaza: ollama pull llama3")
    print("  3. Verifica: ollama list")

# %% Pipeline B (daca Ollama e disponibil)
result_b_consistent = None
result_b_inconsistent = None

if ollama_available:
    print("\n" + "=" * 60)
    print("PIPELINE B (LLM) — Ollama")
    print("=" * 60)

    orch_b = PipelineOrchestrator(use_wikidata=False, extractor_name="llm")

    result_b_consistent = orch_b.run(article_a)
    result_b_inconsistent = orch_b.run(article_b)

    print(f"\n  Articol A (consistent):    TCS = {result_b_consistent.score:.4f} | {result_b_consistent.label}")
    print(f"  Articol B (inconsistent):  TCS = {result_b_inconsistent.score:.4f} | {result_b_inconsistent.label}")
else:
    print("\n⚠ Pipeline B sarit (Ollama indisponibil)")

# %% [markdown]
# ## 4. TCSExplainer — Explicatii
#
# Testam generarea explicatiilor pe ambele rezultate Pipeline A.
# Verificam atat formatul text cat si cel structurat (JSON).

# %% Explainer — text
print("\n" + "=" * 60)
print("EXPLAINER — Explicatie Text")
print("=" * 60)

explainer = TCSExplainer()

print("\n--- Articol A (consistent) ---")
text_a = explainer.explain(result_a_consistent)
print(text_a)

print("\n--- Articol B (inconsistent) ---")
text_b = explainer.explain(result_a_inconsistent)
print(text_b)

# %% Explainer — structurat (JSON)
print("\n" + "=" * 60)
print("EXPLAINER — Explicatie Structurata (JSON)")
print("=" * 60)

import json

structured_a = explainer.explain_structured(result_a_consistent)
structured_b = explainer.explain_structured(result_a_inconsistent)

print("\n--- Articol A (consistent) — chei JSON ---")
for key, value in structured_a.items():
    if isinstance(value, list):
        print(f"  {key}: [{len(value)} elemente]")
    else:
        print(f"  {key}: {value}")

print("\n--- Articol B (inconsistent) — detalii inconsistente ---")
for detail in structured_b["inconsistency_details"]:
    print(f"  [{detail['severity_label'].upper()}] {detail['type']}")
    print(f"    {detail['description'][:80]}")
    if detail.get("evidence"):
        print(f"    Evidenta: {detail['evidence']}")

# %% Explainer — fact annotations (pentru TextHighlight.jsx)
print("\n--- Fact Annotations — Articol B ---")
for ann in structured_b["fact_annotations"]:
    status_marker = "🔴" if ann["status"] == "inconsistent" else "🟢"
    print(f"  {status_marker} [{ann['sentence_idx']}] {ann['subject']} —{ann['predicate']}→ {ann['object']}")
    print(f"     Timp: {ann['time']} | Conf: {ann['confidence']:.2f} | Color: {ann['color']}")
    if ann["inconsistencies"]:
        for desc in ann["inconsistencies"]:
            print(f"     ⚠ {desc[:80]}")

# %% [markdown]
# ## 5. Comparatie Pipeline A vs B
#
# Side-by-side pe acelasi articol (daca Ollama e disponibil).

# %% Comparatie
print("\n" + "=" * 60)
print("COMPARATIE — Pipeline A vs Pipeline B")
print("=" * 60)

if ollama_available and result_b_consistent and result_b_inconsistent:
    print(f"\n  {'Metrica':<35} {'A (spaCy)':>12} {'B (LLM)':>12}")
    print(f"  {'─' * 59}")

    # Articol consistent
    print(f"  {'[Consistent] TCS':<35} {result_a_consistent.score:>12.4f} {result_b_consistent.score:>12.4f}")
    print(f"  {'[Consistent] Claims':<35} {result_a_consistent.n_temporal_claims:>12} {result_b_consistent.n_temporal_claims:>12}")
    print(f"  {'[Consistent] Inconsistente':<35} {result_a_consistent.n_inconsistencies:>12} {result_b_consistent.n_inconsistencies:>12}")
    print(f"  {'[Consistent] Timp (ms)':<35} {result_a_consistent.processing_time_ms:>12.0f} {result_b_consistent.processing_time_ms:>12.0f}")

    print()

    # Articol inconsistent
    print(f"  {'[Inconsistent] TCS':<35} {result_a_inconsistent.score:>12.4f} {result_b_inconsistent.score:>12.4f}")
    print(f"  {'[Inconsistent] Claims':<35} {result_a_inconsistent.n_temporal_claims:>12} {result_b_inconsistent.n_temporal_claims:>12}")
    print(f"  {'[Inconsistent] Inconsistente':<35} {result_a_inconsistent.n_inconsistencies:>12} {result_b_inconsistent.n_inconsistencies:>12}")
    print(f"  {'[Inconsistent] Timp (ms)':<35} {result_a_inconsistent.processing_time_ms:>12.0f} {result_b_inconsistent.processing_time_ms:>12.0f}")

    # Delta
    delta_cons = result_a_consistent.score - result_b_consistent.score
    delta_incons = result_a_inconsistent.score - result_b_inconsistent.score
    print(f"\n  Delta TCS (A - B):")
    print(f"    Consistent:    {delta_cons:+.4f}")
    print(f"    Inconsistent:  {delta_incons:+.4f}")

    # Agreement
    agree_cons = result_a_consistent.label == result_b_consistent.label
    agree_incons = result_a_inconsistent.label == result_b_inconsistent.label
    print(f"\n  Agreement (acelasi label):")
    print(f"    Consistent:    {'✓' if agree_cons else '✗'} ({result_a_consistent.label} vs {result_b_consistent.label})")
    print(f"    Inconsistent:  {'✓' if agree_incons else '✗'} ({result_a_inconsistent.label} vs {result_b_inconsistent.label})")
else:
    print("\n  ⚠ Comparatie indisponibila (Ollama nu ruleaza)")
    print("  Rezultate Pipeline A (spaCy) singur:")
    print(f"    Consistent:    TCS = {result_a_consistent.score:.4f}")
    print(f"    Inconsistent:  TCS = {result_a_inconsistent.score:.4f}")

# %% [markdown]
# ## 6. Validare Pydantic Schemas
#
# Verificam ca request-urile si response-urile API-ului sunt valide.

# %% Test Pydantic
print("\n" + "=" * 60)
print("VALIDARE PYDANTIC SCHEMAS")
print("=" * 60)

from backend.routers.analyze import AnalyzeRequest, AnalyzeResponse
from backend.routers.compare import CompareRequest

# AnalyzeRequest valid
req = AnalyzeRequest(
    text=ARTICLE_A_TEXT,
    title="Test Article",
    publication_date="2024-01-15",
    pipeline="spacy",
)
print(f"\n  ✓ AnalyzeRequest valid: text={len(req.text)} chars, pipeline={req.pipeline}")

# AnalyzeRequest invalid (text prea scurt)
try:
    bad_req = AnalyzeRequest(text="short", pipeline="spacy")
    print("  ✗ AnalyzeRequest ar fi trebuit sa esueze (text prea scurt)")
except Exception as e:
    print(f"  ✓ AnalyzeRequest respins corect (text prea scurt): {type(e).__name__}")

# AnalyzeResponse din rezultatul real
structured = explainer.explain_structured(result_a_consistent)
resp = AnalyzeResponse(
    score=result_a_consistent.score,
    label=result_a_consistent.label,
    summary=structured["summary"],
    n_claims=result_a_consistent.n_temporal_claims,
    n_inconsistencies=result_a_consistent.n_inconsistencies,
    coherence_factor=result_a_consistent.coherence_factor,
    inconsistency_details=structured["inconsistency_details"],
    fact_annotations=structured["fact_annotations"],
    timeline=result_a_consistent.timeline,
    pipeline=result_a_consistent.pipeline_variant,
    processing_time_ms=result_a_consistent.processing_time_ms,
)
print(f"  ✓ AnalyzeResponse valid: score={resp.score:.4f}, {len(resp.fact_annotations)} annotations")

# CompareRequest
comp_req = CompareRequest(
    text=ARTICLE_A_TEXT,
    title="Compare Test",
    publication_date="2024-01-15",
)
print(f"  ✓ CompareRequest valid: text={len(comp_req.text)} chars")

# %% [markdown]
# ## 7. Verificari Automate

# %% Checks
print("\n" + "=" * 60)
print("VERIFICARE AUTOMATA — Sprint 3")
print("=" * 60)

checks = [
    # Pipeline A functioneaza (din Sprint 2)
    ("Pipeline A — articol consistent are fapte",
     result_a_consistent.n_temporal_claims > 0),
    ("Pipeline A — TCS consistent >= TCS inconsistent",
     result_a_consistent.score >= result_a_inconsistent.score),

    # Explainer
    ("Explainer — text generat non-gol",
     len(text_a) > 0 and len(text_b) > 0),
    ("Explainer — structurat are 'summary'",
     "summary" in structured_a and "summary" in structured_b),
    ("Explainer — inconsistent are detalii",
     len(structured_b["inconsistency_details"]) > 0),
    ("Explainer — fact_annotations au status",
     all("status" in a for a in structured_b["fact_annotations"])),
    ("Explainer — fact_annotations au color",
     all("color" in a for a in structured_b["fact_annotations"])),

    # Pydantic
    ("Pydantic — AnalyzeRequest valid",
     req.pipeline == "spacy"),
    ("Pydantic — AnalyzeResponse valid",
     resp.score == result_a_consistent.score),
]

# Pipeline B (conditionat)
if ollama_available and result_b_consistent:
    checks.extend([
        ("Pipeline B — articol consistent are fapte",
         result_b_consistent.n_temporal_claims > 0),
        ("Pipeline B — TCS consistent >= TCS inconsistent",
         result_b_consistent.score >= result_b_inconsistent.score),
        ("Comparatie — ambele au acelasi label pe consistent",
         result_a_consistent.label == result_b_consistent.label),
    ])

all_passed = True
for name, passed in checks:
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}  {name}")
    if not passed:
        all_passed = False

print(f"\n{'✓ Toate verificarile au trecut!' if all_passed else '✗ Unele verificari au esuat.'}")
if not ollama_available:
    print("  (Notă: testele Pipeline B au fost sarite — Ollama indisponibil)")

# %% [markdown]
# ## Rezumat Sprint 3
#
# Ce s-a verificat:
# - LLMExtractor functioneaza cu Ollama (daca e disponibil) ✓
# - TCSExplainer genereaza explicatii text + structurate ✓
# - Explicatiile contin: summary, inconsistency_details, fact_annotations ✓
# - Pydantic schemas valideaza corect request/response ✓
# - Pipeline A vs B produc rezultate comparabile ✓
#
# Urmatorii pasi (Sprint 4):
# - Frontend React (TCSScoreDisplay, TextHighlight, Timeline, CompareView)
# - Evaluare pe datasets reale (LIAR, FakeNewsNet)
# - Screenshots pentru teza
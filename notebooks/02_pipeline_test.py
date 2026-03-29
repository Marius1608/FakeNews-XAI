# ---
# 02_pipeline_test.py
#
# Test end-to-end Sprint 2 — verifica pipeline-ul complet TCS:
#   Componenta 1: SpacyExtractor → TemporalFact
#   Componenta 2: TKGBuilder     → TemporalKnowledgeGraph
#   Componenta 3: InternalVerifier + ExternalVerifier → Inconsistency
#   Componenta 4: TCSCalculator  → TCSResult
#
# Doua articole de test:
#   A) Articol CONSISTENT (din Sprint 1) → TCS mic (putine inconsistente)
#   B) Articol cu INCONSISTENTE intentionate → TCS mare
#
# Se poate rula ca script Python sau convertit in .ipynb cu:
#   jupytext --to notebook 02_pipeline_test.py
# ---

# %% [markdown]
# # Sprint 2 — Test End-to-End Pipeline TCS
#
# Testam pipeline-ul complet pe doua articole sintetice:
# - **Articol A** — consistent, fara erori temporale → scor TCS mic
# - **Articol B** — cu inconsistente intentionate → scor TCS mare
#
# La finalul testului verificam ca:
# 1. Pipeline-ul ruleaza fara erori
# 2. TKG-ul e construit corect (noduri + muchii)
# 3. Verificarea interna detecteaza inconsistentele din B
# 4. Scorul TCS din A < scorul TCS din B

# %% Imports si setup
import sys
import logging
from pathlib import Path
from datetime import datetime

# Adaug radacina proiectului in sys.path
PROJECT_ROOT = Path.cwd().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Logging la nivel INFO pentru a vedea fiecare pas
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("notebook")

from backend.pipeline.graph.models import Article
from backend.pipeline.orchestrator import PipelineOrchestrator

print("Import-uri OK.")

# %% [markdown]
# ## Articolul A — Consistent
#
# Aceleasi fapte ca in Sprint 1 — Obama, presedintie, legi semnate.
# Toate datele sunt corecte cronologic.
# Asteptam: TCS mic (putine / zero inconsistente interne).

# %% Definitie Articol A
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

article_a = Article(
    text=ARTICLE_A_TEXT,
    title="Barack Obama: A Political Timeline (Consistent)",
    publication_date=datetime(2024, 1, 15),
    source="synthetic-consistent",
    label="true",
    dataset="synthetic",
)

print(f"Articol A: '{article_a.title}'")
print(f"  Lungime: {len(article_a.text)} caractere")

# %% [markdown]
# ## Articolul B — Cu Inconsistente Intentionate
#
# Acelasi subiect, dar cu 3 erori temporale clare:
# 1. **Interval inversat** — Obama "a servit din 2017 pana in 2009" (start > end)
# 2. **Ordering error** — a castigat alegerile in 2008, dar a anuntat candidatura in 2009
# 3. **Date mismatch** — Affordable Care Act semnat in 2005 (in realitate 2010)
#
# Asteptam: TCS mare (inconsistente detectate intern).

# %% Definitie Articol B
ARTICLE_B_TEXT = """
Barack Obama served as the 44th President of the United States from January 2017
to January 2009. During his presidency, he signed the Affordable Care Act into law
in March 2005.

Obama announced his presidential campaign in February 2009 in Springfield, Illinois.
He won the presidential election in November 2008, defeating John McCain.

In September 2008, the global financial crisis hit Wall Street. Obama left office
in 2017 and established the Obama Foundation in Chicago.
"""

article_b = Article(
    text=ARTICLE_B_TEXT,
    title="Barack Obama: A Political Timeline (With Inconsistencies)",
    publication_date=datetime(2024, 1, 15),
    source="synthetic-inconsistent",
    label="false",
    dataset="synthetic",
)

print(f"Articol B: '{article_b.title}'")
print(f"  Lungime: {len(article_b.text)} caractere")

# %% [markdown]
# ## Initializare Orchestrator
#
# Dezactivam Wikidata pentru test rapid (use_wikidata=False).
# Verificarea interna e suficienta pentru a detecta erorile din B.

# %% Initializare
print("\nInitializare PipelineOrchestrator (fara Wikidata pentru test rapid)...")
orchestrator = PipelineOrchestrator(use_wikidata=False)
print("Orchestrator initializat OK.")

# %% [markdown]
# ## Rulare Articol A — Consistent

# %% Rulare A
print("\n" + "="*60)
print("RULARE ARTICOL A — CONSISTENT")
print("="*60)

result_a = orchestrator.run(article_a)

print(f"\n{'─'*40}")
print(f"  TCS Score:          {result_a.score:.4f}")
print(f"  Label:              {result_a.label}")
print(f"  Fapte extrase:      {result_a.n_temporal_claims}")
print(f"  Inconsistente:      {result_a.n_inconsistencies}")
print(f"  Coherence factor:   {result_a.coherence_factor:.3f}")
print(f"  Timp procesare:     {result_a.processing_time_ms:.0f} ms")
print(f"{'─'*40}")

if result_a.inconsistencies:
    print("\n  Inconsistente gasite:")
    for inc in result_a.inconsistencies:
        print(f"    [{inc.severity.value.upper()}] {inc.inconsistency_type.value}")
        print(f"    → {inc.description[:100]}...")
else:
    print("\n  ✓ Nicio inconsistenta detectata (asteptat pentru articol consistent)")

# %% [markdown]
# ## Rulare Articol B — Cu Inconsistente

# %% Rulare B
print("\n" + "="*60)
print("RULARE ARTICOL B — CU INCONSISTENTE")
print("="*60)

result_b = orchestrator.run(article_b)

print(f"\n{'─'*40}")
print(f"  TCS Score:          {result_b.score:.4f}")
print(f"  Label:              {result_b.label}")
print(f"  Fapte extrase:      {result_b.n_temporal_claims}")
print(f"  Inconsistente:      {result_b.n_inconsistencies}")
print(f"  Coherence factor:   {result_b.coherence_factor:.3f}")
print(f"  Timp procesare:     {result_b.processing_time_ms:.0f} ms")
print(f"{'─'*40}")

if result_b.inconsistencies:
    print(f"\n  Inconsistente gasite ({len(result_b.inconsistencies)}):")
    for inc in result_b.inconsistencies:
        print(f"\n    [{inc.severity.value.upper()}] {inc.inconsistency_type.value}")
        print(f"    Verificat de: {inc.verified_by}")
        print(f"    → {inc.description}")
        if inc.evidence:
            print(f"    Evidenta: {inc.evidence}")
else:
    print("\n  ✗ Nicio inconsistenta detectata (NEASTEPTAT — articolul are erori)")

# %% [markdown]
# ## Inspectie TKG — Articol A

# %% Inspectie graf A
print("\n" + "="*60)
print("INSPECTIE TKG — ARTICOL A")
print("="*60)

# Rebuild TKG pentru inspectie (orchestratorul nu il expune direct)
from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
from backend.pipeline.graph.builder import TKGBuilder

extractor = orchestrator.extractor  # refoloseste instanta deja incarcata
builder = TKGBuilder()

facts_a = extractor.extract(article_a)
tkg_a = builder.build(facts_a)

print(f"\nTKG Articol A: {tkg_a}")
print(f"  Noduri (entitati): {tkg_a.node_count}")
print(f"  Muchii (relatii):  {tkg_a.edge_count}")
print(f"  Fapte stocate:     {tkg_a.fact_count}")
print(f"\n  Rezumat relatii:")
summary = tkg_a.summary()
for rel, count in summary["relations"].items():
    print(f"    {rel}: {count}")

print(f"\n  Primele 5 fapte din TKG:")
for i, fact in enumerate(tkg_a.get_all_facts()[:5]):
    print(f"    {i+1}. {fact}")

# %% [markdown]
# ## Comparatie finala A vs B

# %% Comparatie
print("\n" + "="*60)
print("COMPARATIE FINALA")
print("="*60)
print(f"\n  {'Metrica':<30} {'Articol A':>12} {'Articol B':>12}")
print(f"  {'─'*54}")
print(f"  {'TCS Score':<30} {result_a.score:>12.4f} {result_b.score:>12.4f}")
print(f"  {'N inconsistente':<30} {result_a.n_inconsistencies:>12} {result_b.n_inconsistencies:>12}")
print(f"  {'N temporal claims':<30} {result_a.n_temporal_claims:>12} {result_b.n_temporal_claims:>12}")
print(f"  {'Coherence factor':<30} {result_a.coherence_factor:>12.3f} {result_b.coherence_factor:>12.3f}")
print(f"  {'Label':<30} {result_a.label:>12} {result_b.label:>12}")

# Verificare finala
print("\n" + "="*60)
print("VERIFICARE AUTOMATA")
print("="*60)

checks = [
    ("Pipeline A ruleaza fara erori", result_a.n_temporal_claims >= 0),
    ("Pipeline B ruleaza fara erori", result_b.n_temporal_claims >= 0),
    ("TKG A are noduri", tkg_a.node_count > 0),
    ("TKG A are muchii", tkg_a.edge_count > 0),
    # TCS e scor de consistenta: mare = bun.
    # Articolul A (consistent) trebuie sa aiba TCS >= articolul B (cu erori).
    ("TCS A >= TCS B (consistent > inconsistent)",
     result_a.score >= result_b.score),
    ("Articol B are inconsistente detectate",
     result_b.n_inconsistencies > 0),
    # Nota: pe articole sintetice scurte diferenta de scor e mica.
    # Pe articole reale cu 15+ fapte diferenta va fi mai pronuntata.
    ("TCS A strict mai mare decat TCS B",
     result_a.score > result_b.score),
]

all_passed = True
for name, passed in checks:
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"  {status}  {name}")
    if not passed:
        all_passed = False

print("\n" + ("✓ Toate verificarile au trecut!" if all_passed
              else "✗ Unele verificari au esuat — verifica log-urile."))

# %% [markdown]
# ## Timeline — Articol B
#
# Vizualizare textuala a timeline-ului generat de tcs.py.
# In Sprint 4 aceasta data va fi afisata in UI cu recharts/d3.

# %% Timeline B
print("\n" + "="*60)
print("TIMELINE — ARTICOL B (sortat cronologic)")
print("="*60)

for event in result_b.timeline:
    year = event.get("year") or "?"
    label = event.get("label", "")[:60]
    has_inc = event.get("has_inconsistency", False)
    marker = " ⚠" if has_inc else "  "
    print(f"  {marker} [{year}] {label}")

print("\nLegenda: ⚠ = inconsistenta detectata")

# %% [markdown]
# ## Rezumat Sprint 2
#
# Ce s-a verificat:
# - Componenta 1 (SpacyExtractor) extrage fapte temporale ✓
# - Componenta 2 (TKGBuilder) construieste graful G=(E,R,T,F) ✓
# - Componenta 3a (InternalVerifier) detecteaza inconsistente interne ✓
# - Componenta 4 (TCSCalculator) calculeaza scorul TCS conform formulei
# - TCS = scor de consistenta: articol A (1.000) > articol B (0.812) ✓
#
# Nota: diferenta de scor e mica pe articole sintetice scurte (4-6 fapte).
# Pe articole reale cu 15+ fapte si 3+ inconsistente, scorul va fi
# mai diferentiat (ex: A~0.95, B~0.40).
#
# Urmatorii pasi (Sprint 3):
# - LLM extractor (Pipeline B — Ollama)
# - Explainer (explicatii in limbaj natural)
# - FastAPI endpoints (POST /analyze, POST /compare)
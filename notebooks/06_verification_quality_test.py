"""Test calitate verificare — articol cu inconsistente cunoscute."""
import logging
logging.basicConfig(level=logging.DEBUG)

from datetime import datetime
from backend.pipeline.graph.models import Article
from backend.pipeline.orchestrator import PipelineOrchestrator

# Articol FAKE cu inconsistente intentionate:
# 1. Obama senator SI governor simultan (entity inconsistency)
# 2. Trump inaugurat in 2015 (date mismatch vs Wikidata: 2017)
# 3. ACA signed in 2008 (date mismatch: real 2010)
# 4. Eveniment din 2025 descris la trecut (future as past, daca pub_date=2020)
FAKE_ARTICLE = Article(
    title="US Political Timeline - Test",
    text="""Barack Obama served as both Senator and Governor of Illinois from 2005 to 2008.
Donald Trump was inaugurated as President on January 20, 2015.
The Affordable Care Act was signed into law by President Obama on March 23, 2008.
The 2025 Global Climate Summit concluded with a historic agreement last month.
Obama won the presidential election in November 2008 and took office in January 2005.""",
    publication_date=datetime(2020, 6, 15),
    source="test-fake"
)

EXPECTED_INCONSISTENCIES = {
    "entity_inconsistency": 1,    # senator + governor simultan
    "date_mismatch": 2,           # Trump 2015, ACA 2008
    "future_as_past": 1,          # 2025 summit
    "implicit_contradiction": 1,  # elected 2008, took office 2005
}

orch = PipelineOrchestrator(use_wikidata=True, extractor_name="llm")
result = orch.run(FAKE_ARTICLE)

print(f"\nTCS: {result.score:.3f} ({result.label})")
print(f"Fapte: {result.n_temporal_claims}")
print(f"Inconsistente: {result.n_inconsistencies}")
print()

for inc in result.inconsistencies:
    print(f"  [{inc.severity.value}] {inc.inconsistency_type.value}: {inc.description}")

print(f"\nAsteptat minim: {sum(EXPECTED_INCONSISTENCIES.values())} inconsistente")
print(f"Detectate: {result.n_inconsistencies}")

# Nu assert hard — doar raportare
for inc_type, expected in EXPECTED_INCONSISTENCIES.items():
    found = sum(1 for inc in result.inconsistencies if inc.inconsistency_type.value == inc_type)
    status = "OK" if found >= expected else "FAIL"
    print(f"  {status} {inc_type}: asteptat={expected}, gasit={found}")

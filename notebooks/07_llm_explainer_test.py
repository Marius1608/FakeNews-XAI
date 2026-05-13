"""Test LLM Explainer — verifica generarea explicatiilor XAI."""
import logging
logging.basicConfig(level=logging.INFO)

from datetime import datetime
from backend.pipeline.graph.models import Article
from backend.pipeline.orchestrator import PipelineOrchestrator

FAKE = Article(
    title="Suspicious Political Timeline",
    text="""Barack Obama served as both Senator and Governor of Illinois from 2005 to 2008.
Donald Trump was inaugurated as President on January 20, 2015.
The Affordable Care Act was signed into law by President Obama on March 23, 2008.""",
    publication_date=datetime(2020, 6, 15),
    source="test"
)

REAL = Article(
    title="Accurate Obama Summary",
    text="""Barack Obama was inaugurated as the 44th President on January 20, 2009.
He signed the Affordable Care Act on March 23, 2010.
Obama won re-election on November 6, 2012.""",
    publication_date=datetime(2020, 1, 1),
    source="test"
)

for label, article in [("FAKE", FAKE), ("REAL", REAL)]:
    print(f"\n{'='*60}")
    print(f"{label}: {article.title}")
    print(f"{'='*60}")

    orch = PipelineOrchestrator(use_wikidata=False, extractor_name="llm")
    result = orch.run(article)

    print(f"TCS: {result.score:.3f} ({result.label})")
    print(f"Inconsistente: {result.n_inconsistencies}")
    print(f"\nExplicatie XAI:")
    print(f"  {result.explanation_text}")
    print()

    if len(result.explanation_text) > 50:
        print("  [OK] Explicatie LLM generata cu succes")
    else:
        print("  [FAIL] Explicatie e doar un label, LLM explainer nu a functionat")

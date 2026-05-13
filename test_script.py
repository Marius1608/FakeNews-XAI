import logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

from datetime import datetime
from backend.pipeline.graph.models import Article
from backend.pipeline.orchestrator import PipelineOrchestrator

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

REAL_ARTICLE = Article(
    title="Obama Presidency - Real",
    text="""Barack Obama was inaugurated as the 44th President on January 20, 2009.
He signed the Affordable Care Act on March 23, 2010.
Obama won re-election on November 6, 2012.
His presidency ended on January 20, 2017.""",
    publication_date=datetime(2020, 1, 1),
    source="test-real"
)

for label, article in [("FAKE", FAKE_ARTICLE), ("REAL", REAL_ARTICLE)]:
    print(f"\n{'='*60}")
    print(f"TEST: {label} — {article.title}")
    print(f"{'='*60}")
    
    orch = PipelineOrchestrator(use_wikidata=False, extractor_name="spacy")
    result = orch.run(article)
    
    print(f"\nFapte extrase: {result.n_temporal_claims}")
    print(f"Inconsistente: {result.n_inconsistencies}")
    print(f"TCS: {result.score:.3f} ({result.label})")
    
    if result.inconsistencies:
        for inc in result.inconsistencies:
            print(f"  [{inc.severity.value}] {inc.inconsistency_type.value}: {inc.description}")
    
    print(f"\nExplicatie: {result.explanation_text}")

"""Test calitate extractie — compara spaCy vs LLM pe articol de referinta."""
import logging
logging.basicConfig(level=logging.DEBUG)

from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
from backend.pipeline.extraction.llm_extractor import LLMExtractor
from backend.pipeline.graph.models import Article

ARTICLE = Article(
    title="Obama's Presidential Legacy",
    text="""Barack Obama was inaugurated as the 44th President of the United States on January 20, 2009. 
He succeeded George W. Bush, who had served two terms from 2001 to 2009. 
Obama signed the Affordable Care Act into law on March 23, 2010, after months of congressional debate.
He won re-election on November 6, 2012, defeating Republican nominee Mitt Romney.
The Iran nuclear deal was reached on July 14, 2015, between Iran and the P5+1 nations.
Obama's presidency ended on January 20, 2017, when Donald Trump was inaugurated.
During his tenure, the US economy recovered from the 2008 financial crisis.
He ordered the operation that killed Osama bin Laden on May 2, 2011.""",
    publication_date=None,
    source="test"
)

# Fapte asteptate (minim):
# 1. Obama inaugurated 2009-01-20
# 2. Bush served 2001-2009
# 3. ACA signed 2010-03-23
# 4. Obama re-elected 2012-11-06
# 5. Iran deal 2015-07-14
# 6. Trump inaugurated 2017-01-20
# 7. 2008 financial crisis
# 8. Bin Laden killed 2011-05-02
EXPECTED_MIN_FACTS = 6

print("=" * 60)
print("PIPELINE A (spaCy)")
print("=" * 60)
spacy_ext = SpacyExtractor()
spacy_facts = spacy_ext.extract(ARTICLE)
for f in spacy_facts:
    print(f"  {f}")
print(f"\nTotal spaCy: {len(spacy_facts)} fapte (minim asteptat: {EXPECTED_MIN_FACTS})")
assert len(spacy_facts) >= EXPECTED_MIN_FACTS, f"spaCy a extras doar {len(spacy_facts)} fapte!"

print("\n" + "=" * 60)
print("PIPELINE B (LLM / llama3)")
print("=" * 60)
llm_ext = LLMExtractor()
if llm_ext.is_available():
    llm_facts = llm_ext.extract(ARTICLE)
    for f in llm_facts:
        print(f"  {f}")
    print(f"\nTotal LLM: {len(llm_facts)} fapte (minim asteptat: {EXPECTED_MIN_FACTS})")
    assert len(llm_facts) >= EXPECTED_MIN_FACTS, f"LLM a extras doar {len(llm_facts)} fapte!"
else:
    print("  Ollama indisponibil — skip test LLM")

print("\nDONE ✓")

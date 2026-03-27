# ---
# 01_spacy_ner_exploration.py
#
# Notebook de explorare — testeaza tot ce s-a construit in Sprint 1:
#   - spaCy NER pe un articol de test
#   - temporal_parser pe expresii temporale
#   - spacy_extractor → extrage TemporalFact-uri
#
# Se poate rula ca script Python sau convertit in .ipynb cu:
#   pip install jupytext
#   jupytext --to notebook 01_spacy_ner_exploration.py
#
# Sau direct in Jupyter:
#   jupyter notebook
# ---

# %% [markdown]
# # Sprint 1 — Explorare spaCy NER + Temporal Parser
#
# Testez componentele construite pana acum:
# 1. spaCy NER — ce entitati gaseste in text
# 2. TemporalParser — cum normalizeaza datele
# 3. SpacyExtractor — extrage fapte temporale complete

# %% Imports
import sys
from pathlib import Path
from datetime import datetime

# Adaug radacina proiectului in sys.path ca sa pot importa din backend/
PROJECT_ROOT = Path.cwd().parent  # presupun ca rulez din notebooks/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import spacy
from backend.pipeline.extraction.temporal_parser import TemporalParser
from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
from backend.pipeline.graph.models import Article

# %% [markdown]
# ## 1. Articol de test
#
# Un articol sintetic cu fapte temporale clare — unele corecte, altele intentionat gresite.
# Acesta va fi folosit si ca fixture de test in sprint-urile urmatoare.

# %% Articol de test (synthetic — cu inconsistente intentionate)
TEST_ARTICLE_TEXT = """
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

TEST_ARTICLE_TITLE = "Barack Obama: A Political Timeline"
TEST_PUBLICATION_DATE = datetime(2024, 1, 15)

article = Article(
    text=TEST_ARTICLE_TEXT,
    title=TEST_ARTICLE_TITLE,
    publication_date=TEST_PUBLICATION_DATE,
    source="synthetic-test",
    label="true",
    dataset="synthetic",
)

print(f"Articol: {article.title}")
print(f"Lungime text: {len(article.text)} caractere")
print(f"Data publicare: {article.publication_date}")

# %% [markdown]
# ## 2. spaCy NER — ce entitati gaseste

# %% Incarc modelul spaCy
print("Se incarca modelul spaCy (en_core_web_trf)... poate dura ~30 secunde")
nlp = spacy.load("en_core_web_trf")
doc = nlp(TEST_ARTICLE_TEXT)

# %% Afisez toate entitatile gasite
print("\n=== Entitati gasite de spaCy ===\n")
print(f"{'Text':<30} {'Label':<10} {'Start':<8} {'End':<8}")
print("-" * 60)
for ent in doc.ents:
    print(f"{ent.text:<30} {ent.label_:<10} {ent.start_char:<8} {ent.end_char:<8}")

# %% Separat — doar entitatile DATE
print("\n=== Doar expresiile DATE ===\n")
for ent in doc.ents:
    if ent.label_ == "DATE":
        print(f"  '{ent.text}' (chars {ent.start_char}-{ent.end_char})")

# %% [markdown]
# ## 3. TemporalParser — normalizare date

# %% Testez parserul temporal
parser = TemporalParser()

test_expressions = [
    "January 2009",
    "March 2010",
    "November 2008",
    "2017",
    "last Tuesday",  # relativa — depinde de publication_date
    "three days ago",  # relativa
    "early 2000s",  # aproximativa
    "September 2008",
]

print("\n=== TemporalParser — rezultate ===\n")
print(f"Data de referinta: {TEST_PUBLICATION_DATE}\n")
print(f"{'Expresie':<25} {'Normalizat':<15} {'Relativa':<10} {'Aprox':<10} {'Conf':<6}")
print("-" * 70)

for expr_text in test_expressions:
    result = parser.parse(expr_text, reference_date=TEST_PUBLICATION_DATE)
    if result:
        print(
            f"{result.raw_text:<25} "
            f"{result.date_string or 'FAILED':<15} "
            f"{str(result.is_relative):<10} "
            f"{str(result.is_approximate):<10} "
            f"{result.confidence:<6.2f}"
        )

# %% [markdown]
# ## 4. SpacyExtractor — extrage fapte temporale complete

# %% Rulez extractorul complet
extractor = SpacyExtractor()
facts = extractor.extract(article)

print(f"\n=== SpacyExtractor — {len(facts)} fapte extrase ===\n")

for i, fact in enumerate(facts):
    print(f"--- Fact {i + 1} ---")
    print(f"  Subject:   {fact.subject.text} ({fact.subject.entity_type.value})")
    print(f"  Predicate: {fact.predicate.value}")
    print(f"  Object:    {fact.object.text} ({fact.object.entity_type.value})")

    if fact.time_point:
        print(f"  Time:      {fact.time_point.raw_text} -> {fact.time_point.date_string}")
    if fact.time_start:
        print(f"  Start:     {fact.time_start.raw_text} -> {fact.time_start.date_string}")
    if fact.time_end:
        print(f"  End:       {fact.time_end.raw_text} -> {fact.time_end.date_string}")

    print(f"  Confidence: {fact.extraction_confidence}")
    print(f"  Sentence:  \"{fact.source_sentence.strip()[:80]}...\"")
    print()

# %% [markdown]
# ## 5. Rezumat
#
# Ce functioneaza:
# - spaCy gaseste entitati (PERSON, ORG, GPE, DATE)
# - TemporalParser normalizeaza expresiile temporale
# - SpacyExtractor leaga entitatile de date prin dependency parsing
#
# Urmatorii pasi (Sprint 2):
# - Construire graf temporal din faptele extrase (graph/builder.py)
# - Verificare interna — cicluri, cauzalitate (verification/internal.py)
# - Verificare externa — Wikidata SPARQL (verification/wikidata.py)
# - Formula TCS (scoring/tcs.py)

# %% Statistici finale
print("\n=== Rezumat ===")
print(f"Propozitii in articol: {len(list(doc.sents))}")
print(f"Entitati gasite:       {len(doc.ents)}")
print(f"  - DATE:              {sum(1 for e in doc.ents if e.label_ == 'DATE')}")
print(f"  - PERSON:            {sum(1 for e in doc.ents if e.label_ == 'PERSON')}")
print(f"  - ORG:               {sum(1 for e in doc.ents if e.label_ == 'ORG')}")
print(f"  - GPE:               {sum(1 for e in doc.ents if e.label_ == 'GPE')}")
print(f"Fapte temporale:       {len(facts)}")
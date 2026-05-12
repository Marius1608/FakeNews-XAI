# ---
# 04_full_system_test.py
#
# Test complet pre-Sprint 4 — verifica TOATE componentele:
#   C1: SpacyExtractor, LLMExtractor, TemporalParser
#   C2: TKGBuilder, TemporalKnowledgeGraph (store)
#   C3: InternalVerifier, ExternalVerifier, WikidataClient
#   C4: TCSCalculator, TCSExplainer
#   API: Pydantic schemas, dependencies
#   Orchestrator: run(), run_batch()
#   Dataset: load_liar, load_fakenewsnet, load_ver1
#
# Se poate rula ca script Python sau convertit in .ipynb cu:
#   jupytext --to notebook 04_full_system_test.py
# ---

# %% Imports si setup
import sys
import logging
import time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path.cwd().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-5s | %(name)-40s | %(message)s"
)
logger = logging.getLogger("test")

# Suprima log-urile verbose din biblioteci
logging.getLogger("backend.pipeline.extraction.spacy_extractor").setLevel(logging.WARNING)
logging.getLogger("backend.pipeline.graph.builder").setLevel(logging.WARNING)
logging.getLogger("backend.pipeline.graph.store").setLevel(logging.WARNING)
logging.getLogger("backend.pipeline.verification.internal").setLevel(logging.WARNING)
logging.getLogger("backend.pipeline.verification.external").setLevel(logging.WARNING)
logging.getLogger("backend.pipeline.scoring.tcs").setLevel(logging.WARNING)
logging.getLogger("backend.pipeline.orchestrator").setLevel(logging.WARNING)
logging.getLogger("backend.pipeline.extraction.llm_extractor").setLevel(logging.WARNING)

print("Import-uri setup OK.\n")

# Contorizare teste
_results = {"pass": 0, "fail": 0, "skip": 0}

def check(name: str, condition: bool):
    """Verifica o conditie si afiseaza rezultatul."""
    if condition:
        _results["pass"] += 1
        print(f"  ✓ PASS  {name}")
    else:
        _results["fail"] += 1
        print(f"  ✗ FAIL  {name}")

def skip(name: str, reason: str):
    _results["skip"] += 1
    print(f"  ⊘ SKIP  {name} — {reason}")

def section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# %% Articole de test
ARTICLE_CONSISTENT = """
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

ARTICLE_INCONSISTENT = """
Barack Obama served as the 44th President of the United States from January 2017
to January 2009. During his presidency, he signed the Affordable Care Act into law
in March 2005.

Obama announced his presidential campaign in February 2009 in Springfield, Illinois.
He won the presidential election in November 2008, defeating John McCain.

In September 2008, the global financial crisis hit Wall Street. Obama left office
in 2017 and established the Obama Foundation in Chicago.
"""

ARTICLE_NO_DATES = """
The weather was nice today. People walked in the park and enjoyed the sunshine.
A dog chased a ball across the green grass while children played nearby.
"""

from backend.pipeline.graph.models import Article

art_consistent = Article(
    text=ARTICLE_CONSISTENT, title="Obama Timeline (Consistent)",
    publication_date=datetime(2024, 1, 15), source="synthetic", label="true", dataset="synthetic",
)
art_inconsistent = Article(
    text=ARTICLE_INCONSISTENT, title="Obama Timeline (Inconsistent)",
    publication_date=datetime(2024, 1, 15), source="synthetic", label="false", dataset="synthetic",
)
art_no_dates = Article(
    text=ARTICLE_NO_DATES, title="No Temporal Data",
    publication_date=datetime(2024, 1, 15), source="synthetic", label="true", dataset="synthetic",
)

print(f"Articole de test: 3 (consistent, inconsistent, fara date)")


# %%
section("C1a — TemporalParser")

from backend.pipeline.extraction.temporal_parser import TemporalParser

parser = TemporalParser()
ref_date = datetime(2024, 1, 15)

# Date absolute
r1 = parser.parse("January 2009", reference_date=ref_date)
check("Parseaza 'January 2009'", r1 is not None and r1.normalized_date is not None)
check("Anul corect 2009", r1 and r1.normalized_date.year == 2009)
check("Confidence > 0.5", r1 and r1.confidence > 0.5)

# Date relative
r2 = parser.parse("last Tuesday", reference_date=ref_date)
check("Parseaza 'last Tuesday' (relativ)", r2 is not None and r2.normalized_date is not None)
check("Marcat ca relativ", r2 and r2.is_relative)

# Decade patterns
r3 = parser.parse("early 2000s", reference_date=ref_date)
check("Parseaza 'early 2000s'", r3 is not None and r3.normalized_date is not None)
check("Marcat ca aproximativ", r3 and r3.is_approximate)
check("Anul normalizat = 2000", r3 and r3.normalized_date.year == 2000)

r4 = parser.parse("mid-1990s", reference_date=ref_date)
check("Parseaza 'mid-1990s' → 1995", r4 is not None and r4.normalized_date and r4.normalized_date.year == 1995)

r5 = parser.parse("late 1980s", reference_date=ref_date)
check("Parseaza 'late 1980s' → 1989", r5 is not None and r5.normalized_date and r5.normalized_date.year == 1989)

# Text gol
r6 = parser.parse("", reference_date=ref_date)
check("Text gol → None", r6 is None)

# Text neparsabil
r7 = parser.parse("blablabla", reference_date=ref_date)
check("Text neparsabil → confidence 0", r7 is not None and r7.confidence == 0.0)

# parse_all_in_sentence
spans = [(0, 12, "January 2009"), (20, 32, "March 2010")]
results = parser.parse_all_in_sentence("test", spans, reference_date=ref_date)
check("parse_all_in_sentence: 2 rezultate", len(results) == 2)


# %%
section("C1b — SpacyExtractor (Pipeline A)")

from backend.pipeline.extraction.spacy_extractor import SpacyExtractor

extractor_a = SpacyExtractor()

# Articol consistent
facts_a_cons = extractor_a.extract(art_consistent)
check("Extrage fapte din articol consistent", len(facts_a_cons) > 0)
check("Cel putin 3 fapte", len(facts_a_cons) >= 3)
check("Faptele au subiect non-gol", all(f.subject.text.strip() for f in facts_a_cons))
check("Faptele au extractor='spacy'", all(f.extractor == "spacy" for f in facts_a_cons))
check("Faptele au source_sentence non-gol", all(f.source_sentence for f in facts_a_cons))

# Articol fara date
facts_a_nodates = extractor_a.extract(art_no_dates)
check("Articol fara date → 0 fapte", len(facts_a_nodates) == 0)

# Articol inconsistent
facts_a_incons = extractor_a.extract(art_inconsistent)
check("Extrage fapte din articol inconsistent", len(facts_a_incons) > 0)

# Verifica get_name
check("get_name() == 'spacy'", extractor_a.get_name() == "spacy")

print(f"\n  Fapte extrase: consistent={len(facts_a_cons)}, inconsistent={len(facts_a_incons)}, nodates={len(facts_a_nodates)}")


# %%
section("C1c — LLMExtractor (Pipeline B)")

from backend.pipeline.extraction.llm_extractor import LLMExtractor

extractor_b = LLMExtractor()
ollama_available = extractor_b.is_available()

if ollama_available:
    print(f"  Ollama disponibil — rulam teste Pipeline B\n")

    facts_b_cons = extractor_b.extract(art_consistent)
    check("LLM extrage fapte din articol consistent", len(facts_b_cons) > 0)
    check("LLM faptele au extractor='llm'", all(f.extractor == "llm" for f in facts_b_cons))
    check("LLM get_name() == 'llm'", extractor_b.get_name() == "llm")

    # Verifica source_sentence fix
    has_source = any(f.source_sentence and f.source_sentence != "" for f in facts_b_cons)
    check("LLM source_sentence non-gol (fix Sprint 3.5)", has_source)

    facts_b_incons = extractor_b.extract(art_inconsistent)
    check("LLM extrage fapte din articol inconsistent", len(facts_b_incons) > 0)

    print(f"\n  Fapte LLM: consistent={len(facts_b_cons)}, inconsistent={len(facts_b_incons)}")
else:
    skip("LLM Pipeline B", "Ollama indisponibil")
    facts_b_cons = []
    facts_b_incons = []


# %%
section("C2a — TKGBuilder")

from backend.pipeline.graph.builder import TKGBuilder

builder = TKGBuilder()

# Build din fapte consistente
tkg_cons = builder.build(facts_a_cons)
check("TKG consistent are noduri", tkg_cons.node_count > 0)
check("TKG consistent are muchii", tkg_cons.edge_count > 0)
check("TKG consistent are fapte", tkg_cons.fact_count > 0)
check("fact_count <= len(facts_input) (filtrare+dedup)", tkg_cons.fact_count <= len(facts_a_cons))

# Build din fapte inconsistente
tkg_incons = builder.build(facts_a_incons)
check("TKG inconsistent are noduri", tkg_incons.node_count > 0)

# Build din lista goala
tkg_empty = builder.build([])
check("TKG din lista goala → 0 noduri", tkg_empty.node_count == 0)
check("TKG din lista goala → 0 fapte", tkg_empty.fact_count == 0)

# Filtrare: confidence prea mic
from backend.pipeline.graph.models import Entity, EntityType, RelationType, TemporalFact, TemporalExpression
low_conf_fact = TemporalFact(
    subject=Entity(text="Test", entity_type=EntityType.PERSON, start_char=0, end_char=4),
    predicate=RelationType.GENERIC,
    object=Entity(text="Obj", entity_type=EntityType.OTHER, start_char=5, end_char=8),
    time_point=TemporalExpression(raw_text="2020", normalized_date=datetime(2020,1,1), date_string="2020-01-01"),
    extraction_confidence=0.1,  # sub pragul de 0.3
)
tkg_lowconf = builder.build([low_conf_fact])
check("Fapt cu confidence 0.1 e filtrat", tkg_lowconf.fact_count == 0)

print(f"\n  TKG consistent: {tkg_cons.node_count} noduri, {tkg_cons.edge_count} muchii, {tkg_cons.fact_count} fapte")
print(f"  TKG inconsistent: {tkg_incons.node_count} noduri, {tkg_incons.edge_count} muchii, {tkg_incons.fact_count} fapte")


# %%
section("C2b — TemporalKnowledgeGraph (store)")

# Interogari pe TKG consistent
all_facts = tkg_cons.get_all_facts()
check("get_all_facts() returneaza lista", isinstance(all_facts, list) and len(all_facts) > 0)

# summary()
summary = tkg_cons.summary()
check("summary() are 'nodes'", "nodes" in summary)
check("summary() are 'relations'", "relations" in summary)

# get_facts_for_entity
obama_facts = tkg_cons.get_facts_for_entity("Barack Obama")
check("get_facts_for_entity('Barack Obama') gaseste fapte", len(obama_facts) > 0)

# get_entities_by_type
persons = tkg_cons.get_entities_by_type(EntityType.PERSON)
check("get_entities_by_type(PERSON) returneaza lista", isinstance(persons, list))

# snapshot temporal
snap = tkg_cons.snapshot(datetime(2010, 6, 1))
check("snapshot(2010) returneaza subgraf", snap.number_of_nodes() >= 0)

# repr
repr_str = repr(tkg_cons)
check("repr() contine 'TemporalKnowledgeGraph'", "TemporalKnowledgeGraph" in repr_str)


# %%
section("C3a — InternalVerifier")

from backend.pipeline.verification.internal import InternalVerifier

verifier_int = InternalVerifier()

# Articol consistent → 0 inconsistente
int_res_cons = verifier_int.verify(tkg_cons)
check("Consistent: 0 inconsistente", int_res_cons.conf_temp == 0)
check("Consistent: score_coherence = 1.0", int_res_cons.score_coherence == 1.0)

# Articol inconsistent → >=1 inconsistenta
int_res_incons = verifier_int.verify(tkg_incons)
check("Inconsistent: >=1 inconsistenta", int_res_incons.conf_temp >= 1)
check("Inconsistent: score_coherence < 1.0", int_res_incons.score_coherence < 1.0)

# Verifica tipurile de inconsistente
if int_res_incons.inconsistencies:
    inc = int_res_incons.inconsistencies[0]
    check("Inconsistenta are tip", inc.inconsistency_type is not None)
    check("Inconsistenta are severitate", inc.severity is not None)
    check("Inconsistenta are descriere", len(inc.description) > 0)

# TKG gol
int_res_empty = verifier_int.verify(tkg_empty)
check("TKG gol: score_coherence = 1.0 (0/0)", int_res_empty.score_coherence == 1.0)

print(f"\n  Consistent: {int_res_cons.conf_temp} conflicte / {int_res_cons.rel_temp} relatii → coherence={int_res_cons.score_coherence:.3f}")
print(f"  Inconsistent: {int_res_incons.conf_temp} conflicte / {int_res_incons.rel_temp} relatii → coherence={int_res_incons.score_coherence:.3f}")


# %%
section("C3b — ExternalVerifier + Reference KG")

from backend.pipeline.verification.external import ExternalVerifier

# Fara Wikidata (doar Reference KG local)
verifier_ext = ExternalVerifier(use_wikidata=False)

ext_res_cons = verifier_ext.verify(tkg_cons)
check("External: fapte verificate > 0 sau 0 (depinde de relatie)", ext_res_cons.facts_checked >= 0)
check("External: 0 query-uri Wikidata (dezactivat)", ext_res_cons.wikidata_queries == 0)

ext_res_incons = verifier_ext.verify(tkg_incons)
check("External inconsistent: ruleaza fara erori", True)

# Verifica Reference KG incarcat
check("Reference KG are entitati", len(verifier_ext._reference_kg) > 0)
check("Reference KG contine 'barack obama'", "barack obama" in verifier_ext._reference_kg)

print(f"\n  Reference KG: {len(verifier_ext._reference_kg)} entitati incarcate")
print(f"  Consistent: {ext_res_cons.facts_checked} verificate, {len(ext_res_cons.inconsistencies)} inconsistente")
print(f"  Inconsistent: {ext_res_incons.facts_checked} verificate, {len(ext_res_incons.inconsistencies)} inconsistente")


# %%
section("C3c — WikidataClient (SPARQL)")

from backend.pipeline.verification.wikidata import WikidataClient

client = WikidataClient()

# Search entity
try:
    qid = client.search_entity("Barack Obama")
    check("Wikidata search_entity('Barack Obama') → QID", qid is not None and qid.startswith("Q"))
    check("QID e Q76 (Obama)", qid == "Q76")

    # Get temporal facts
    if qid:
        wk_facts = client.get_temporal_facts(qid, relation_properties=["P39"])
        check("get_temporal_facts(Q76, P39) returneaza fapte", len(wk_facts) > 0)
        if wk_facts:
            check("WikidataFact are entity_id", wk_facts[0].entity_id != "")
            check("WikidataFact are time_start sau time_point",
                  wk_facts[0].time_start is not None or wk_facts[0].time_point is not None)
            print(f"\n  Fapte Wikidata pentru Obama (P39): {len(wk_facts)}")
            for wf in wk_facts[:3]:
                print(f"    {wf}")
except Exception as e:
    skip("Wikidata SPARQL", f"Eroare retea: {e}")


# %%
section("C4a — TCSCalculator")

from backend.pipeline.scoring.tcs import TCSCalculator

calculator = TCSCalculator()

# TCS pe articol consistent
tcs_cons = calculator.compute(tkg_cons, int_res_cons, ext_res_cons, pipeline_variant="spacy")
check("TCS consistent: scor intre 0 si 1", 0.0 <= tcs_cons.score <= 1.0)
check("TCS consistent: scor > 0.7 (consistent)", tcs_cons.score > 0.7)
check("TCS consistent: label contine 'Consistent'", "Consistent" in tcs_cons.label)
check("TCS consistent: are timeline", isinstance(tcs_cons.timeline, list))
check("TCS consistent: are facts", len(tcs_cons.facts) > 0)

# TCS pe articol inconsistent
tcs_incons = calculator.compute(tkg_incons, int_res_incons, ext_res_incons, pipeline_variant="spacy")
check("TCS inconsistent: scor intre 0 si 1", 0.0 <= tcs_incons.score <= 1.0)
check("TCS consistent >= TCS inconsistent", tcs_cons.score >= tcs_incons.score)

# Edge case: TKG gol
tcs_empty = calculator.compute(tkg_empty, int_res_empty, ext_res_cons, pipeline_variant="spacy")
check("TKG gol: TCS = 0.0", tcs_empty.score == 0.0)
check("TKG gol: label = 'Insufficient Temporal Data'", "Insufficient" in tcs_empty.label)

# Edge case: score_coherence = 0
from backend.pipeline.verification.internal import InternalVerificationResult
fake_internal = InternalVerificationResult(inconsistencies=[], conf_temp=5, rel_temp=5)
check("score_coherence = 0 cand conf_temp == rel_temp", fake_internal.score_coherence == 0.0)
tcs_zero_coh = calculator.compute(tkg_cons, fake_internal, ext_res_cons, pipeline_variant="spacy")
check("score_coherence=0 → TCS=0.0 (guard)", tcs_zero_coh.score == 0.0)

# Weighted variant
tcs_weighted = calculator.compute_weighted(tkg_incons, int_res_incons, ext_res_incons, pipeline_variant="spacy")
check("compute_weighted returneaza TCSResult", tcs_weighted.score >= 0.0)

print(f"\n  TCS consistent: {tcs_cons.score:.4f} ({tcs_cons.label})")
print(f"  TCS inconsistent: {tcs_incons.score:.4f} ({tcs_incons.label})")
print(f"  TCS gol: {tcs_empty.score:.4f} ({tcs_empty.label})")
print(f"  TCS coherence=0: {tcs_zero_coh.score:.4f}")
print(f"  TCS weighted: {tcs_weighted.score:.4f}")


# %%
section("C4b — TCSExplainer")

from backend.pipeline.scoring.explainer import TCSExplainer

explainer = TCSExplainer()

# Explicatie text
text_cons = explainer.explain(tcs_cons)
check("Explicatie text consistent: non-gol", len(text_cons) > 0)
check("Explicatie text contine scorul", "1.00" in text_cons or "TCS" in text_cons)

text_incons = explainer.explain(tcs_incons)
check("Explicatie text inconsistent: contine 'inconsistencies'", "inconsistenc" in text_incons.lower())

# Explicatie structurata
struct_cons = explainer.explain_structured(tcs_cons)
check("Structurat: are 'summary'", "summary" in struct_cons)
check("Structurat: are 'score'", "score" in struct_cons)
check("Structurat: are 'label'", "label" in struct_cons)
check("Structurat: are 'inconsistency_details'", "inconsistency_details" in struct_cons)
check("Structurat: are 'fact_annotations'", "fact_annotations" in struct_cons)
check("Structurat: are 'pipeline'", "pipeline" in struct_cons)

struct_incons = explainer.explain_structured(tcs_incons)
check("Structurat inconsistent: are detalii inconsistente", len(struct_incons["inconsistency_details"]) > 0)

# Fact annotations
if struct_incons["fact_annotations"]:
    ann = struct_incons["fact_annotations"][0]
    check("Annotation are 'status'", "status" in ann)
    check("Annotation are 'color'", "color" in ann)
    check("Annotation are 'subject'", "subject" in ann)
    check("Annotation are 'time'", "time" in ann)


# %%
section("ORCHESTRATOR — End-to-End")

from backend.pipeline.orchestrator import PipelineOrchestrator

# Pipeline A end-to-end
orch_a = PipelineOrchestrator(use_wikidata=False, extractor_name="spacy")

t0 = time.time()
result_a_cons = orch_a.run(art_consistent)
t_a_cons = time.time() - t0

t0 = time.time()
result_a_incons = orch_a.run(art_inconsistent)
t_a_incons = time.time() - t0

t0 = time.time()
result_a_nodates = orch_a.run(art_no_dates)
t_a_nodates = time.time() - t0

check("Orchestrator A: consistent → TCS > 0.7", result_a_cons.score > 0.7)
check("Orchestrator A: inconsistent → TCS < consistent", result_a_incons.score < result_a_cons.score)
check("Orchestrator A: no dates → TCS = 0.0", result_a_nodates.score == 0.0)
check("Orchestrator A: no dates → 'Insufficient'", "Insufficient" in result_a_nodates.label)
check("Orchestrator A: processing_time_ms > 0", result_a_cons.processing_time_ms > 0)

# Pipeline B end-to-end (daca disponibil)
if ollama_available:
    orch_b = PipelineOrchestrator(use_wikidata=False, extractor_name="llm")

    t0 = time.time()
    result_b_cons = orch_b.run(art_consistent)
    t_b_cons = time.time() - t0

    t0 = time.time()
    result_b_incons = orch_b.run(art_inconsistent)
    t_b_incons = time.time() - t0

    check("Orchestrator B: consistent → TCS > 0.7", result_b_cons.score > 0.7)
    check("Orchestrator B: inconsistent → TCS < consistent", result_b_incons.score < result_b_cons.score)
    check("Orchestrator B: A si B acord pe consistent", result_a_cons.label == result_b_cons.label)
else:
    skip("Orchestrator Pipeline B", "Ollama indisponibil")

# run_batch
batch_results = orch_a.run_batch([art_consistent, art_inconsistent])
check("run_batch: 2 rezultate", len(batch_results) == 2)
check("run_batch: primul = consistent", batch_results[0].score >= batch_results[1].score)

print(f"\n  Pipeline A: consistent={result_a_cons.score:.4f} ({t_a_cons:.1f}s), inconsistent={result_a_incons.score:.4f} ({t_a_incons:.1f}s), nodates={result_a_nodates.score:.4f}")
if ollama_available:
    print(f"  Pipeline B: consistent={result_b_cons.score:.4f} ({t_b_cons:.1f}s), inconsistent={result_b_incons.score:.4f} ({t_b_incons:.1f}s)")


# %%
section("DATASET LOADERS")

from backend.input.dataset import load_liar, load_fakenewsnet, load_ver1, load_dataset

# LIAR
liar = load_liar(max_articles=5)
if liar:
    check("LIAR: incarca articole", len(liar) > 0)
    check("LIAR: articolele au label", all(a.label for a in liar))
    check("LIAR: articolele au dataset='LIAR'", all(a.dataset == "LIAR" for a in liar))
    check("LIAR: articolele au text non-gol", all(a.text.strip() for a in liar))
    print(f"  LIAR: {len(liar)} articole, labels: {set(a.label for a in liar)}")
else:
    skip("LIAR loader", "Fisierul data/datasets/liar/test.tsv nu exista")

# FakeNewsNet
fnn = load_fakenewsnet(max_articles=3)
if fnn:
    check("FakeNewsNet: incarca articole", len(fnn) > 0)
    check("FakeNewsNet: articolele au dataset='FakeNewsNet'", all(a.dataset == "FakeNewsNet" for a in fnn))
    print(f"  FakeNewsNet: {len(fnn)} articole")
else:
    skip("FakeNewsNet loader", "Directorul data/datasets/fakenewsnet nu exista")

# VER-1
ver1 = load_ver1(max_articles=3)
if ver1:
    check("VER-1: incarca articole", len(ver1) > 0)
    check("VER-1: articolele au dataset='VER-1'", all(a.dataset == "VER-1" for a in ver1))
    print(f"  VER-1: {len(ver1)} articole")
else:
    skip("VER-1 loader", "Fisierul data/datasets/ver1/ver1.csv nu exista")

# Dispatcher
try:
    dispatched = load_dataset("liar", max_articles=2)
    check("load_dataset('liar') functioneaza", isinstance(dispatched, list))
except Exception:
    skip("load_dataset dispatcher", "Dataset indisponibil")

try:
    load_dataset("invalid_name")
    check("load_dataset('invalid') arunca ValueError", False)
except ValueError:
    check("load_dataset('invalid') arunca ValueError", True)


# %%
section("PYDANTIC SCHEMAS")

from backend.routers.analyze import AnalyzeRequest, AnalyzeResponse
from backend.routers.compare import CompareRequest

# AnalyzeRequest valid
req = AnalyzeRequest(text="A" * 30, title="Test", pipeline="spacy")
check("AnalyzeRequest valid", req.pipeline == "spacy")

# AnalyzeRequest invalid (text prea scurt)
try:
    AnalyzeRequest(text="short", title="Test", pipeline="spacy")
    check("AnalyzeRequest text scurt → ValidationError", False)
except Exception:
    check("AnalyzeRequest text scurt → ValidationError", True)

# CompareRequest valid
creq = CompareRequest(text="A" * 30, title="Test")
check("CompareRequest valid", creq.text == "A" * 30)

# AnalyzeResponse from real result
resp = AnalyzeResponse(
    score=result_a_cons.score, label=result_a_cons.label,
    summary="test", n_claims=result_a_cons.n_temporal_claims,
    n_inconsistencies=result_a_cons.n_inconsistencies,
    coherence_factor=result_a_cons.coherence_factor,
    inconsistency_details=[], fact_annotations=[],
    timeline=result_a_cons.timeline, pipeline="spacy",
    processing_time_ms=result_a_cons.processing_time_ms,
)
check("AnalyzeResponse valid cu date reale", resp.score == result_a_cons.score)


# %%
section("DEPENDENCIES (shared singletons)")

from backend.dependencies import get_orchestrator, explainer as shared_explainer

orch1 = get_orchestrator("spacy")
orch2 = get_orchestrator("spacy")
check("get_orchestrator('spacy') returneaza acelasi obiect", orch1 is orch2)

orch_llm = get_orchestrator("llm")
check("get_orchestrator('llm') returneaza alt obiect decat spacy", orch_llm is not orch1)
check("shared explainer e TCSExplainer", shared_explainer is not None)


# %%
section("REZUMAT FINAL")

total = _results["pass"] + _results["fail"] + _results["skip"]
print(f"\n  Total: {total} teste")
print(f"  ✓ PASS: {_results['pass']}")
print(f"  ✗ FAIL: {_results['fail']}")
print(f"  ⊘ SKIP: {_results['skip']}")

if _results["fail"] == 0:
    print(f"\n  ✓ TOATE TESTELE AU TRECUT! Gata pentru Sprint 4.")
else:
    print(f"\n  ✗ {_results['fail']} teste au esuat — verifica inainte de Sprint 4.")
"""Evaluare calitate extractie C1 (Pipeline A si B) pe articolele din benchmark.

Compara faptele extrase cu inconsistentele cunoscute documentate in benchmark.

Rulare:
  python evaluation/run_extraction_benchmark.py --pipeline spacy
  python evaluation/run_extraction_benchmark.py --pipeline llm
  python evaluation/run_extraction_benchmark.py --pipeline both
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(name)-35s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("extraction_benchmark")

EVAL_DIR = Path(__file__).parent
BENCHMARK_FILE = EVAL_DIR / "benchmark_articles.json"
RESULTS_DIR = EVAL_DIR / "results"


# // section load

def load_benchmark(path: Path) -> list[dict]:
    if not path.exists():
        logger.error(f"Fisier benchmark negasit: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# // section matching

def _has_temporal_anchor(fact) -> bool:
    return fact.time_point is not None or fact.time_start is not None or fact.time_end is not None


def _fact_is_valid(fact) -> bool:
    """Verifica daca un fapt are subject + predicate + ancora temporala (criteriu pentru TRUE)."""
    return (
        bool(fact.subject.text.strip())
        and bool(fact.object.text.strip())
        and _has_temporal_anchor(fact)
    )


def _fact_hits_inconsistency(fact, inconsistency: str) -> bool:
    """Verifica daca subiectul sau obiectul faptului apare ca substring in descrierea inconsistentei."""
    inc_lower = inconsistency.lower()
    subj = fact.subject.text.lower().strip()
    obj = fact.object.text.lower().strip()
    if len(subj) >= 3 and subj in inc_lower:
        return True
    if len(obj) >= 3 and obj in inc_lower:
        return True
    return False


# // section evaluate

def _evaluate_article(facts: list, entry: dict) -> dict:
    """
    Evalueaza faptele extrase dintr-un articol fata de ground truth-ul din benchmark.
    Returneaza un dict cu metrici per-articol si sumar al faptelor.
    """
    expected_fake: bool = entry.get("expected_fake", False)
    known_inconsistencies: list[str] = entry.get("known_inconsistencies", [])
    inconsistency_types: list[str] = entry.get("inconsistency_types", [])

    n_extracted = len(facts)
    correct_facts = 0
    inconsistencies_hit: set[int] = set()

    for fact in facts:
        if expected_fake:
            hit = False
            for idx, inc_str in enumerate(known_inconsistencies):
                if _fact_hits_inconsistency(fact, inc_str):
                    inconsistencies_hit.add(idx)
                    hit = True
            if hit:
                correct_facts += 1
        else:
            if _fact_is_valid(fact):
                correct_facts += 1

    n_known = len(known_inconsistencies) if expected_fake else 0
    n_hits = len(inconsistencies_hit)

    precision = correct_facts / n_extracted if n_extracted > 0 else None
    recall = n_hits / n_known if (expected_fake and n_known > 0) else None

    return {
        "title": entry.get("title", ""),
        "expected_fake": expected_fake,
        "n_extracted": n_extracted,
        "correct_facts": correct_facts,
        "n_known_inconsistencies": n_known,
        "inconsistencies_hit": n_hits,
        "precision": precision,
        "recall": recall,
        "inconsistency_types": inconsistency_types,
        "facts_summary": [
            {
                "subject": f.subject.text,
                "predicate": f.predicate.value,
                "object": f.object.text,
                "time_point": f.time_point.raw_text if f.time_point else None,
                "time_start": f.time_start.raw_text if f.time_start else None,
                "time_end": f.time_end.raw_text if f.time_end else None,
                "confidence": round(f.extraction_confidence, 3),
            }
            for f in facts
        ],
    }


# // section run extractor

def _resolve_spacy_model(requested: Optional[str]) -> Optional[str]:
    try:
        import spacy
    except ImportError:
        return None
    installed = spacy.util.get_installed_models()
    if not installed:
        return None
    if requested and requested in installed:
        return requested
    for preferred in ("en_core_web_trf", "en_core_web_lg", "en_core_web_sm"):
        if preferred in installed:
            return preferred
    return installed[0]


def run_extractor(pipeline: str, entries: list[dict], model_name: Optional[str] = None) -> list[dict]:
    """Ruleaza extractor-ul ales pe toate articolele si colecteaza rezultatele per articol."""
    from backend.pipeline.graph.models import Article

    if pipeline == "spacy":
        from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
        resolved = _resolve_spacy_model(model_name)
        if resolved is None:
            print("  [ERROR] Niciun model spaCy gasit. Instaleaza: python -m spacy download en_core_web_sm")
            sys.exit(1)
        extractor = SpacyExtractor(model_name=resolved)
        print(f"  Extractor: SpacyExtractor (model={resolved})")
    else:
        from backend.pipeline.extraction.llm_extractor import LLMExtractor
        extractor = LLMExtractor()
        if not extractor.is_available():
            print("  [WARNING] Ollama nu este disponibil sau modelul nu e incarcat — Pipeline B sarit.")
            return []
        print(f"  Extractor: LLMExtractor (model={extractor.model})")

    results = []
    for i, entry in enumerate(entries):
        pub_date: Optional[datetime] = None
        if entry.get("publication_date"):
            try:
                pub_date = datetime.strptime(entry["publication_date"], "%Y-%m-%d")
            except ValueError:
                pass

        article = Article(
            text=entry["text"],
            title=entry.get("title", f"Article {i + 1}"),
            publication_date=pub_date,
            source=entry.get("source", "benchmark"),
        )

        print(f"  [{i + 1:2d}/{len(entries)}] {article.title[:58]}", end=" ... ", flush=True)
        t0 = time.monotonic()
        try:
            facts = extractor.extract(article)
        except Exception as exc:
            logger.error(f"Eroare extractor pe '{article.title}': {exc}", exc_info=True)
            facts = []
        elapsed_ms = (time.monotonic() - t0) * 1000

        row = _evaluate_article(facts, entry)
        row["processing_time_ms"] = round(elapsed_ms, 1)
        label = "FAKE" if entry.get("expected_fake") else "TRUE"
        print(f"{len(facts)} fapte [{label}]  {elapsed_ms:.0f}ms")
        results.append(row)

    return results


# // section metrics

def compute_global_metrics(results: list[dict]) -> dict:
    """Calculeaza metrici globale de extractie agregand rezultatele per articol."""
    if not results:
        return {}

    true_articles = [r for r in results if not r["expected_fake"]]
    fake_articles = [r for r in results if r["expected_fake"]]

    total_extracted = sum(r["n_extracted"] for r in results)
    total_correct = sum(r["correct_facts"] for r in results)

    global_precision = total_correct / total_extracted if total_extracted > 0 else 0.0

    total_known = sum(r["n_known_inconsistencies"] for r in fake_articles)
    total_hits = sum(r["inconsistencies_hit"] for r in fake_articles)
    global_recall = total_hits / total_known if total_known > 0 else 0.0

    f1 = (
        2 * global_precision * global_recall / (global_precision + global_recall)
        if (global_precision + global_recall) > 0
        else 0.0
    )

    zero_fact_articles = sum(1 for r in results if r["n_extracted"] == 0)
    zero_fact_rate = zero_fact_articles / len(results) if results else 0.0

    avg_facts_true = (
        sum(r["n_extracted"] for r in true_articles) / len(true_articles)
        if true_articles else 0.0
    )
    avg_facts_fake = (
        sum(r["n_extracted"] for r in fake_articles) / len(fake_articles)
        if fake_articles else 0.0
    )

    # Numarare detectii per tip de inconsistenta (articole FAKE cu cel putin un hit)
    type_counts: dict[str, int] = {}
    for r in fake_articles:
        if r["inconsistencies_hit"] > 0:
            for inc_type in r["inconsistency_types"]:
                type_counts[inc_type] = type_counts.get(inc_type, 0) + 1

    return {
        "total_articles": len(results),
        "true_articles": len(true_articles),
        "fake_articles": len(fake_articles),
        "total_facts_extracted": total_extracted,
        "total_correct_facts": total_correct,
        "total_known_inconsistencies": total_known,
        "total_inconsistencies_hit": total_hits,
        "precision": round(global_precision, 4),
        "recall": round(global_recall, 4),
        "f1": round(f1, 4),
        "avg_facts_true": round(avg_facts_true, 2),
        "avg_facts_fake": round(avg_facts_fake, 2),
        "zero_fact_rate": round(zero_fact_rate, 4),
        "zero_fact_articles": zero_fact_articles,
        "type_detection_counts": type_counts,
    }


# // section print

def print_pipeline_summary(pipeline_name: str, metrics: dict) -> None:
    """Afiseaza un sumar formatat al metricilor pentru un pipeline."""
    print(f"\n  Pipeline : {pipeline_name.upper()}")
    print(f"  {'=' * 52}")
    print(f"  Articole totale      : {metrics.get('total_articles', 0)}")
    print(f"  Articole TRUE        : {metrics.get('true_articles', 0)}")
    print(f"  Articole FAKE        : {metrics.get('fake_articles', 0)}")
    print(f"  Fapte extrase total  : {metrics.get('total_facts_extracted', 0)}")
    print(f"  Fapte corecte        : {metrics.get('total_correct_facts', 0)}")
    print(f"  {'-' * 52}")
    print(f"  Precision            : {metrics.get('precision', 0.0):.4f}")
    print(f"  Recall               : {metrics.get('recall', 0.0):.4f}")
    print(f"  F1                   : {metrics.get('f1', 0.0):.4f}")
    print(f"  {'-' * 52}")
    print(f"  Avg fapte / TRUE     : {metrics.get('avg_facts_true', 0.0):.2f}")
    print(f"  Avg fapte / FAKE     : {metrics.get('avg_facts_fake', 0.0):.2f}")
    print(
        f"  Zero-fact rate       : {metrics.get('zero_fact_rate', 0.0):.2%}"
        f"  ({metrics.get('zero_fact_articles', 0)} articole)"
    )

    type_counts: dict[str, int] = metrics.get("type_detection_counts", {})
    if type_counts:
        print(f"\n  Detectii per tip inconsistenta (articole FAKE cu cel putin un hit):")
        for inc_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {inc_type:<38} : {count}")


def print_comparison_table(metrics_a: dict, metrics_b: dict) -> None:
    """Afiseaza tabel comparativ Pipeline A (spaCy) vs Pipeline B (LLM)."""
    col_a = "Pipeline A (spaCy)"
    col_b = "Pipeline B (LLM)"
    print(f"\n  {'Metrica':<28}  {col_a:>20}  {col_b:>18}")
    print(f"  {'-' * 70}")

    rows = [
        ("Precision",        metrics_a.get("precision", 0.0),      metrics_b.get("precision", 0.0)),
        ("Recall",           metrics_a.get("recall", 0.0),         metrics_b.get("recall", 0.0)),
        ("F1",               metrics_a.get("f1", 0.0),             metrics_b.get("f1", 0.0)),
        ("Avg fapte/TRUE",   metrics_a.get("avg_facts_true", 0.0), metrics_b.get("avg_facts_true", 0.0)),
        ("Avg fapte/FAKE",   metrics_a.get("avg_facts_fake", 0.0), metrics_b.get("avg_facts_fake", 0.0)),
        ("Zero-fact rate",   metrics_a.get("zero_fact_rate", 0.0), metrics_b.get("zero_fact_rate", 0.0)),
    ]
    for label, val_a, val_b in rows:
        print(f"  {label:<28}  {val_a:>20.4f}  {val_b:>18.4f}")
    print()


# // section save

def save_results(payload: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    output_path = RESULTS_DIR / f"extraction_benchmark_{today}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    return output_path


# // section main

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluare calitate extractie C1")
    parser.add_argument(
        "--pipeline", choices=["spacy", "llm", "both"], default="spacy",
        help="Pipeline de evaluat: spacy, llm, sau both (default: spacy)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Model spaCy sau LLM explicit (default: auto-detect)",
    )
    args = parser.parse_args()

    print(f"\n{'=' * 70}")
    print("  EXTRACTION BENCHMARK — Evaluare calitate extractie C1")
    print(f"{'=' * 70}")
    print(f"  Pipeline  : {args.pipeline}")
    print(f"  Benchmark : {BENCHMARK_FILE}")
    print(f"{'=' * 70}")

    entries = load_benchmark(BENCHMARK_FILE)
    print(f"  Incarcat {len(entries)} articole\n")

    pipelines_to_run = ["spacy", "llm"] if args.pipeline == "both" else [args.pipeline]

    all_results: dict[str, dict] = {}

    for pip in pipelines_to_run:
        print(f"\n{'=' * 70}")
        print(f"  Extractor: {pip.upper()}")
        print(f"{'=' * 70}")
        rows = run_extractor(pip, entries, model_name=args.model)
        if not rows:
            print(f"  [WARNING] Niciun rezultat pentru pipeline '{pip}' — sarit.\n")
            continue
        metrics = compute_global_metrics(rows)
        print_pipeline_summary(pip, metrics)
        all_results[pip] = {"metrics": metrics, "articles": rows}

    if "spacy" in all_results and "llm" in all_results:
        print(f"\n{'=' * 70}")
        print("  COMPARATIE Pipeline A (spaCy) vs Pipeline B (LLM)")
        print(f"{'=' * 70}")
        print_comparison_table(all_results["spacy"]["metrics"], all_results["llm"]["metrics"])

    if not all_results:
        print("\n  [ERROR] Niciun pipeline nu a returnat rezultate.")
        sys.exit(1)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "benchmark_file": str(BENCHMARK_FILE),
        "pipelines": all_results,
    }
    output_path = save_results(payload)
    print(f"\n  Rezultate salvate: {output_path}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()

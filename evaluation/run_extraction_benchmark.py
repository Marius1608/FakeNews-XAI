"""Extraction quality benchmark for Pipelines A and B.

Compares extracted facts against known inconsistencies documented in the benchmark.

Usage:
  python evaluation/run_extraction_benchmark.py --pipeline spacy
  python evaluation/run_extraction_benchmark.py --pipeline llm
  python evaluation/run_extraction_benchmark.py --pipeline all
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

PIPELINE_CHOICES = ["spacy", "llm", "all"]

PIPELINE_LABELS = {
    "spacy": "spaCy (A)",
    "llm":   "Qwen3-1.7B (B)",
}


# // section load

def load_benchmark(path: Path) -> list[dict]:
    if not path.exists():
        logger.error(f"Benchmark file not found: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# // section matching

def _has_temporal_anchor(fact) -> bool:
    return fact.time_point is not None or fact.time_start is not None or fact.time_end is not None


def _fact_is_valid(fact) -> bool:
    """Checks that a fact has subject + object + temporal anchor (criterion for TRUE articles)."""
    return (
        bool(fact.subject.text.strip())
        and bool(fact.object.text.strip())
        and _has_temporal_anchor(fact)
    )


def _fact_hits_inconsistency(fact, inconsistency: str) -> bool:
    """True if the fact's subject or object appears as a substring in the inconsistency description."""
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
    Evaluates extracted facts against benchmark ground truth.
    Returns a per-article metrics dict and a facts summary.
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
                "extractor": getattr(f, "extractor", "unknown"),
            }
            for f in facts
        ],
    }


# // section extractors

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


def _build_article(entry: dict, idx: int):
    from backend.pipeline.graph.models import Article
    pub_date: Optional[datetime] = None
    if entry.get("publication_date"):
        try:
            pub_date = datetime.strptime(entry["publication_date"], "%Y-%m-%d")
        except ValueError:
            pass
    return Article(
        text=entry["text"],
        title=entry.get("title", f"Article {idx + 1}"),
        publication_date=pub_date,
        source=entry.get("source", "benchmark"),
    )


def run_extractor(pipeline: str, entries: list[dict], model_name: Optional[str] = None) -> list[dict]:
    """Runs the chosen pipeline on all articles and returns per-article evaluation rows."""
    if pipeline == "spacy":
        return _run_spacy(entries, model_name)
    elif pipeline == "llm":
        return _run_llm(entries, model_name)
    else:
        raise ValueError(f"Unknown pipeline: {pipeline}")


def _run_spacy(entries: list[dict], model_name: Optional[str]) -> list[dict]:
    from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
    resolved = _resolve_spacy_model(model_name)
    if resolved is None:
        print("  [ERROR] No spaCy model found. Install: python -m spacy download en_core_web_sm")
        sys.exit(1)
    extractor = SpacyExtractor(model_name=resolved)
    print(f"  Extractor: SpacyExtractor (model={resolved})")
    return _run_loop(extractor, entries)


def _run_llm(entries: list[dict], model_name: Optional[str]) -> list[dict]:
    from backend.pipeline.extraction.spacy_llm_extractor import SpacyLLMExtractor
    extractor = SpacyLLMExtractor()
    if not extractor.is_available():
        print("  [WARNING] Qwen model not available — Pipeline B skipped.")
        return []
    print("  Extractor: SpacyLLMExtractor (Qwen3-1.7B)")
    return _run_loop(extractor, entries)


def _run_loop(extractor, entries: list[dict]) -> list[dict]:
    """Generic extraction loop for a single extractor."""
    results = []
    for i, entry in enumerate(entries):
        article = _build_article(entry, i)
        print(f"  [{i + 1:2d}/{len(entries)}] {article.title[:58]}", end=" ... ", flush=True)
        t0 = time.monotonic()
        try:
            facts = extractor.extract(article)
        except Exception as exc:
            logger.error(f"Extractor error on '{article.title}': {exc}", exc_info=True)
            facts = []
        elapsed_ms = (time.monotonic() - t0) * 1000

        row = _evaluate_article(facts, entry)
        row["processing_time_ms"] = round(elapsed_ms, 1)
        label = "FAKE" if entry.get("expected_fake") else "TRUE"
        print(f"{len(facts)} facts [{label}]  {elapsed_ms:.0f}ms")
        results.append(row)
    return results


# // section metrics

def compute_global_metrics(results: list[dict]) -> dict:
    """Computes global extraction metrics by aggregating per-article results."""
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
    """Prints a formatted summary of metrics for one pipeline."""
    label = PIPELINE_LABELS.get(pipeline_name, pipeline_name.upper())
    print(f"\n  Pipeline : {label}")
    print(f"  {'=' * 52}")
    print(f"  Total articles       : {metrics.get('total_articles', 0)}")
    print(f"  TRUE articles        : {metrics.get('true_articles', 0)}")
    print(f"  FAKE articles        : {metrics.get('fake_articles', 0)}")
    print(f"  Facts extracted      : {metrics.get('total_facts_extracted', 0)}")
    print(f"  Correct facts        : {metrics.get('total_correct_facts', 0)}")
    print(f"  {'-' * 52}")
    print(f"  Precision            : {metrics.get('precision', 0.0):.4f}")
    print(f"  Recall               : {metrics.get('recall', 0.0):.4f}")
    print(f"  F1                   : {metrics.get('f1', 0.0):.4f}")
    print(f"  {'-' * 52}")
    print(f"  Avg facts / TRUE     : {metrics.get('avg_facts_true', 0.0):.2f}")
    print(f"  Avg facts / FAKE     : {metrics.get('avg_facts_fake', 0.0):.2f}")
    print(
        f"  Zero-fact rate       : {metrics.get('zero_fact_rate', 0.0):.2%}"
        f"  ({metrics.get('zero_fact_articles', 0)} articles)"
    )

    type_counts: dict[str, int] = metrics.get("type_detection_counts", {})
    if type_counts:
        print(f"\n  Detections per inconsistency type (FAKE articles with at least one hit):")
        for inc_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {inc_type:<38} : {count}")


def print_comparison_table(all_results: dict[str, dict]) -> None:
    """Prints a comparison table across all evaluated pipelines."""
    pipelines = list(all_results.keys())
    labels = [PIPELINE_LABELS.get(p, p) for p in pipelines]

    col_w = 20
    header_pad = 18
    print(f"\n  {'Pipeline':<{header_pad}}", end="")
    for lbl in labels:
        print(f"  {lbl:>{col_w}}", end="")
    print()
    print(f"  {'-' * (header_pad + (col_w + 2) * len(pipelines))}")

    rows = [
        ("Precision",      "precision"),
        ("Recall",         "recall"),
        ("F1",             "f1"),
        ("Avg facts/TRUE", "avg_facts_true"),
        ("Avg facts/FAKE", "avg_facts_fake"),
        ("Zero-fact %",    "zero_fact_rate"),
    ]
    for row_label, key in rows:
        print(f"  {row_label:<{header_pad}}", end="")
        for p in pipelines:
            val = all_results[p]["metrics"].get(key, 0.0)
            if key == "zero_fact_rate":
                print(f"  {val:>{col_w}.2%}", end="")
            else:
                print(f"  {val:>{col_w}.4f}", end="")
        print()
    print()


# // section save

def save_results(payload: dict, pipeline: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    safe_pipeline = pipeline.replace("+", "_plus_")
    output_path = RESULTS_DIR / f"extraction_benchmark_{today}_{safe_pipeline}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    return output_path


# // section main

def main() -> None:
    parser = argparse.ArgumentParser(description="Extraction quality benchmark — Pipelines A / B")
    parser.add_argument(
        "--pipeline",
        choices=PIPELINE_CHOICES,
        default="spacy",
        help="Pipeline to evaluate (default: spacy)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Explicit spaCy model (default: auto-detect)",
    )
    args = parser.parse_args()

    print(f"\n{'=' * 70}")
    print("  EXTRACTION BENCHMARK — Pipelines A / B")
    print(f"{'=' * 70}")
    print(f"  Pipeline  : {args.pipeline}")
    print(f"  Benchmark : {BENCHMARK_FILE}")
    print(f"{'=' * 70}")

    entries = load_benchmark(BENCHMARK_FILE)
    print(f"  Loaded {len(entries)} articles\n")

    pipelines_to_run = (
        ["spacy", "llm"]
        if args.pipeline == "all"
        else [args.pipeline]
    )

    all_results: dict[str, dict] = {}

    for pip in pipelines_to_run:
        print(f"\n{'=' * 70}")
        print(f"  Extractor: {PIPELINE_LABELS.get(pip, pip.upper())}")
        print(f"{'=' * 70}")
        rows = run_extractor(pip, entries, model_name=args.model)
        if not rows:
            print(f"  [WARNING] No results for pipeline '{pip}' — skipped.\n")
            continue
        metrics = compute_global_metrics(rows)
        print_pipeline_summary(pip, metrics)
        all_results[pip] = {"metrics": metrics, "articles": rows}

    if len(all_results) > 1:
        print(f"\n{'=' * 70}")
        print("  COMPARISON TABLE")
        print(f"{'=' * 70}")
        print_comparison_table(all_results)

    if not all_results:
        print("\n  [ERROR] No pipeline returned results.")
        sys.exit(1)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "benchmark_file": str(BENCHMARK_FILE),
        "pipelines": all_results,
    }
    output_path = save_results(payload, args.pipeline)
    print(f"\n  Results saved: {output_path}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()

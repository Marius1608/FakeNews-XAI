"""Evaluare manuala pipeline TCS pe un set de articole cu ground truth.

Rulare: python evaluation/run_benchmark.py
Optiuni:
  --wikidata      Activeaza verificare Wikidata (necesita retea)
  --threshold N   Threshold TCS sub care articolul e prezis FAKE (default: 0.6)
  --pipeline P    Pipeline de folosit: spacy sau llm (default: spacy)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# Adauga project root in sys.path (necesar cand scriptul e rulat direct)
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(name)-35s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("benchmark")

EVAL_DIR = Path(__file__).parent
BENCHMARK_FILE = EVAL_DIR / "benchmark_articles.json"
RESULTS_DIR = EVAL_DIR / "results"
FAKE_THRESHOLD = 0.55


# // section load

def load_benchmark(path: Path) -> list[dict]:
    """Incarca articolele de benchmark din JSON."""
    if not path.exists():
        logger.error(f"Fisier benchmark negasit: {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    logger.info(f"Incarcat {len(data)} articole din {path}")
    return data


# // section run

def _resolve_spacy_model(requested: Optional[str]) -> Optional[str]:
    """Returneaza modelul spaCy de folosit: cel cerut (daca e instalat) sau primul disponibil."""
    import spacy
    installed = spacy.util.get_installed_models()
    if not installed:
        return None
    if requested and requested in installed:
        return requested
    # Fallback: preferinta lg > sm > primul disponibil
    for preferred in ("en_core_web_trf", "en_core_web_lg", "en_core_web_sm"):
        if preferred in installed:
            return preferred
    return installed[0]


def run_benchmark(
    articles: list[dict],
    pipeline: str = "spacy",
    use_wikidata: bool = False,
    threshold: float = FAKE_THRESHOLD,
    model_name: Optional[str] = None,
) -> list[dict]:
    """Ruleaza pipeline-ul TCS pe fiecare articol si colecteaza rezultatele."""
    from backend.pipeline.graph.models import Article
    from backend.pipeline.orchestrator import PipelineOrchestrator

    resolved_model = _resolve_spacy_model(model_name) if pipeline == "spacy" else model_name
    if pipeline == "spacy" and resolved_model is None:
        logger.error("Niciun model spaCy instalat. Instaleaza cu: python -m spacy download en_core_web_sm")
        sys.exit(1)
    if resolved_model:
        logger.info(f"Model spaCy: {resolved_model}")

    orch = PipelineOrchestrator(
        use_wikidata=use_wikidata,
        extractor_name=pipeline,
        model_name=resolved_model,
        persistent_store=None,
    )

    rows = []
    for i, entry in enumerate(articles):
        pub_date: Optional[datetime] = None
        if entry.get("publication_date"):
            try:
                pub_date = datetime.strptime(entry["publication_date"], "%Y-%m-%d")
            except ValueError:
                pass

        article = Article(
            text=entry["text"],
            title=entry.get("title", f"Article {i+1}"),
            publication_date=pub_date,
            source=entry.get("source", "benchmark"),
        )

        logger.info(f"[{i+1}/{len(articles)}] '{article.title[:60]}'")
        t0 = time.monotonic()

        try:
            result = orch.run(article)
        except Exception as e:
            logger.error(f"Eroare pipeline pe '{article.title}': {e}", exc_info=True)
            rows.append(_error_row(entry, i + 1))
            continue

        elapsed_ms = (time.monotonic() - t0) * 1000
        expected_fake: bool = entry.get("expected_fake", False)
        predicted_fake: bool = result.n_temporal_claims > 0 and result.score < threshold

        outcome = _classify_outcome(expected_fake, predicted_fake)

        rows.append({
            "idx": i + 1,
            "title": article.title,
            "tcs": round(result.score, 4),
            "tcs_label": result.label,
            "n_claims": result.n_temporal_claims,
            "n_inconsistencies": result.n_inconsistencies,
            "coherence_factor": round(result.coherence_factor, 4),
            "expected_fake": expected_fake,
            "predicted_fake": predicted_fake,
            "outcome": outcome,
            "known_inconsistencies": entry.get("known_inconsistencies", []),
            "detected_inconsistencies": [
                {
                    "type": inc.inconsistency_type.value,
                    "severity": inc.severity.value,
                    "description": inc.description,
                }
                for inc in result.inconsistencies
            ],
            "processing_time_ms": round(elapsed_ms, 1),
            "source": entry.get("source", ""),
        })

    return rows


def _classify_outcome(expected_fake: bool, predicted_fake: bool) -> str:
    if expected_fake and predicted_fake:
        return "TP"
    if not expected_fake and not predicted_fake:
        return "TN"
    if not expected_fake and predicted_fake:
        return "FP"
    return "FN"


def _error_row(entry: dict, idx: int) -> dict:
    return {
        "idx": idx,
        "title": entry.get("title", f"Article {idx}"),
        "tcs": 0.0,
        "tcs_label": "error",
        "n_claims": 0,
        "n_inconsistencies": 0,
        "coherence_factor": 0.0,
        "expected_fake": entry.get("expected_fake", False),
        "predicted_fake": False,
        "outcome": "ERROR",
        "known_inconsistencies": entry.get("known_inconsistencies", []),
        "detected_inconsistencies": [],
        "processing_time_ms": 0.0,
        "source": entry.get("source", ""),
    }


# // section metrics

def compute_metrics(rows: list[dict]) -> dict:
    """Calculeaza Precision, Recall, F1 pe baza clasificarilor TP/FP/FN/TN."""
    tp = sum(1 for r in rows if r["outcome"] == "TP")
    tn = sum(1 for r in rows if r["outcome"] == "TN")
    fp = sum(1 for r in rows if r["outcome"] == "FP")
    fn = sum(1 for r in rows if r["outcome"] == "FN")

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(rows) if rows else 0.0

    avg_tcs_true = _avg_tcs(rows, expected_fake=False)
    avg_tcs_fake = _avg_tcs(rows, expected_fake=True)

    return {
        "total": len(rows),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "avg_tcs_true_articles": round(avg_tcs_true, 4) if avg_tcs_true is not None else None,
        "avg_tcs_fake_articles": round(avg_tcs_fake, 4) if avg_tcs_fake is not None else None,
    }


def _avg_tcs(rows: list[dict], expected_fake: bool) -> Optional[float]:
    subset = [r["tcs"] for r in rows if r["expected_fake"] == expected_fake and r["outcome"] != "ERROR"]
    return sum(subset) / len(subset) if subset else None


# // section print_table

def print_table(rows: list[dict], threshold: float) -> None:
    """Afiseaza tabelul de rezultate in consola."""
    title_w = 42
    sep = "-" * (title_w + 62)

    print(f"\n{'='*(title_w + 62)}")
    print(f"  TCS BENCHMARK  |  threshold = {threshold:.2f}  |  fake = TCS < {threshold:.2f}")
    print(f"{'='*(title_w + 62)}")
    print(
        f"  {'#':>2}  {'Title':<{title_w}}  {'TCS':>6}  "
        f"{'Exp':>4}  {'Pred':>5}  {'Out':>4}  {'Inc':>4}  {'ms':>6}"
    )
    print(sep)

    for r in rows:
        exp_str = "FAKE" if r["expected_fake"] else "TRUE"
        pred_str = "FAKE" if r["predicted_fake"] else "TRUE"
        outcome = r["outcome"]
        marker = " " if outcome in ("TP", "TN") else "*"
        title_short = r["title"][:title_w]

        print(
            f"{marker} {r['idx']:>2}  {title_short:<{title_w}}  {r['tcs']:>6.3f}  "
            f"{exp_str:>4}  {pred_str:>5}  {outcome:>4}  "
            f"{r['n_inconsistencies']:>4}  {r['processing_time_ms']:>6.0f}"
        )

    print(sep)
    print("  * = misclassified\n")


def print_metrics(metrics: dict, threshold: float) -> None:
    """Afiseaza metricile de evaluare."""
    print(f"  Metrics (threshold TCS < {threshold:.2f} = FAKE predicted):")
    print(f"  {'-'*40}")
    print(f"  TP={metrics['tp']}  TN={metrics['tn']}  FP={metrics['fp']}  FN={metrics['fn']}")
    print(f"  Precision : {metrics['precision']:.4f}")
    print(f"  Recall    : {metrics['recall']:.4f}")
    print(f"  F1        : {metrics['f1']:.4f}")
    print(f"  Accuracy  : {metrics['accuracy']:.4f}")
    if metrics["avg_tcs_true_articles"] is not None:
        print(f"  Avg TCS (TRUE articles) : {metrics['avg_tcs_true_articles']:.4f}")
    if metrics["avg_tcs_fake_articles"] is not None:
        print(f"  Avg TCS (FAKE articles) : {metrics['avg_tcs_fake_articles']:.4f}")
    print()


def print_inconsistency_details(rows: list[dict]) -> None:
    """Afiseaza detalii inconsistente detectate vs asteptate pentru fiecare articol."""
    print("  Inconsistency details:")
    print(f"  {'â”€'*60}")
    for r in rows:
        print(f"  [{r['idx']}] {r['title'][:55]}")
        if r["known_inconsistencies"]:
            for k in r["known_inconsistencies"]:
                print(f"      expected : {k}")
        if r["detected_inconsistencies"]:
            for d in r["detected_inconsistencies"]:
                print(f"      detected : [{d['severity']}] {d['type']}: {d['description'][:70]}")
        if not r["known_inconsistencies"] and not r["detected_inconsistencies"]:
            print("      (no inconsistencies expected or found)")
        print()


# // section save

def save_results(rows: list[dict], metrics: dict, pipeline: str, threshold: float) -> Path:
    """Salveaza rezultatele in evaluation/results/results_YYYY-MM-DD.json."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    output_path = RESULTS_DIR / f"results_{today}.json"

    payload = {
        "generated_at": datetime.now().isoformat(),
        "pipeline": pipeline,
        "fake_threshold": threshold,
        "metrics": metrics,
        "articles": rows,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    return output_path


# // section main

def main() -> None:
    parser = argparse.ArgumentParser(description="TCS Pipeline Benchmark")
    parser.add_argument("--wikidata", action="store_true", help="Activeaza verificare Wikidata")
    parser.add_argument("--threshold", type=float, default=FAKE_THRESHOLD, help="Threshold TCS fake (default: 0.6)")
    parser.add_argument("--pipeline", choices=["spacy", "llm"], default="spacy", help="Pipeline extractor")
    parser.add_argument("--model", type=str, default=None, help="Model spaCy/LLM explicit (default: auto-detect)")
    args = parser.parse_args()

    print(f"\nBenchmark: pipeline={args.pipeline}, wikidata={args.wikidata}, threshold={args.threshold}")
    print(f"Fisier:    {BENCHMARK_FILE}\n")

    articles = load_benchmark(BENCHMARK_FILE)
    rows = run_benchmark(
        articles,
        pipeline=args.pipeline,
        use_wikidata=args.wikidata,
        threshold=args.threshold,
        model_name=args.model,
    )
    metrics = compute_metrics(rows)

    print_table(rows, args.threshold)
    print_metrics(metrics, args.threshold)
    print_inconsistency_details(rows)

    output_path = save_results(rows, metrics, args.pipeline, args.threshold)
    print(f"  Rezultate salvate: {output_path}")


if __name__ == "__main__":
    main()


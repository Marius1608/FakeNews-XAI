"""ISOT dataset evaluation — filters political articles and runs TCS pipeline.

ISOT dataset: True.csv + Fake.csv
Political filter: articles mentioning president/senator/congress/election/government/trump/obama/clinton/biden

Usage:
  python evaluation/run_isot_eval.py --path data/datasets/isot/
  python evaluation/run_isot_eval.py --path data/datasets/isot/ --pipeline llm
  python evaluation/run_isot_eval.py --path data/datasets/isot/ --max 50
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
logger = logging.getLogger("isot_eval")

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
FAKE_THRESHOLD = 0.70

POLITICAL_KEYWORDS = [
    "president", "senate", "congress", "election",
    "government", "white house", "trump", "obama", "clinton", "biden",
    "republican", "democrat", "political", "washington",
]


# // section load

def load_isot(
    true_path: Path,
    fake_path: Path,
    max_per_class: int = 50,
    political_filter: bool = True,
) -> list[dict]:
    """Reads True.csv and Fake.csv, optionally filters to political articles."""
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pandas is required: pip install pandas")
        sys.exit(1)

    articles: list[dict] = []

    for csv_path, is_fake in [(true_path, False), (fake_path, True)]:
        if not csv_path.exists():
            logger.error(f"ISOT file not found: {csv_path}")
            sys.exit(1)

        df = pd.read_csv(csv_path)

        # Normalize column names
        df.columns = [c.strip().lower() for c in df.columns]

        if "text" not in df.columns:
            logger.error(f"No 'text' column in {csv_path}. Columns: {list(df.columns)}")
            sys.exit(1)

        if political_filter:
            mask = df["text"].str.lower().apply(
                lambda t: any(kw in t for kw in POLITICAL_KEYWORDS)
                if isinstance(t, str) else False
            )
            if "subject" in df.columns:
                mask = mask | df["subject"].str.lower().apply(
                    lambda s: any(kw in s for kw in POLITICAL_KEYWORDS)
                    if isinstance(s, str) else False
                )
            df = df[mask]

        df = df.dropna(subset=["text"])
        df = df[df["text"].str.strip().str.len() > 100]

        count = 0
        for _, row in df.iterrows():
            if count >= max_per_class:
                break
            articles.append({
                "text": str(row["text"]).strip(),
                "title": str(row.get("title", f"Article {count + 1}")).strip(),
                "expected_fake": is_fake,
                "source": "isot",
            })
            count += 1

    label = "TRUE" if not any(a["expected_fake"] for a in articles) else "mixed"
    true_count = sum(1 for a in articles if not a["expected_fake"])
    fake_count = sum(1 for a in articles if a["expected_fake"])
    logger.info(f"ISOT loaded: {true_count} TRUE + {fake_count} FAKE articles")
    return articles


# // section run

def _resolve_spacy_model(requested: Optional[str]) -> Optional[str]:
    import spacy
    installed = spacy.util.get_installed_models()
    if not installed:
        return None
    if requested and requested in installed:
        return requested
    for preferred in ("en_core_web_trf", "en_core_web_lg", "en_core_web_sm"):
        if preferred in installed:
            return preferred
    return installed[0]


def run_isot(
    articles: list[dict],
    pipeline: str = "spacy",
    use_wikidata: bool = False,
    threshold: float = FAKE_THRESHOLD,
    model_name: Optional[str] = None,
    use_rss: bool = False,
) -> list[dict]:
    """Runs the TCS pipeline on ISOT articles and returns evaluation rows."""
    from backend.pipeline.graph.models import Article
    from backend.pipeline.orchestrator import PipelineOrchestrator

    resolved_model = _resolve_spacy_model(model_name) if pipeline == "spacy" else model_name
    if pipeline == "spacy" and resolved_model is None:
        print("[ERROR] No spaCy model found. Install: python -m spacy download en_core_web_sm")
        sys.exit(1)

    orch = PipelineOrchestrator(
        use_wikidata=use_wikidata,
        extractor_name=pipeline,
        model_name=resolved_model,
        persistent_store=None,
        use_rss=use_rss,
    )

    rows = []
    for i, entry in enumerate(articles):
        article = Article(
            text=entry["text"],
            title=entry["title"],
            publication_date=None,
            source="isot",
        )

        print(f"  [{i + 1:3d}/{len(articles)}] {article.title[:55]}", end=" ... ", flush=True)
        t0 = time.monotonic()

        try:
            result = orch.run(article)
        except Exception as e:
            logger.error(f"Pipeline error on '{article.title}': {e}", exc_info=True)
            rows.append(_error_row(entry, i + 1))
            print("ERROR")
            continue

        elapsed_ms = (time.monotonic() - t0) * 1000
        expected_fake: bool = entry["expected_fake"]
        predicted_fake: bool = result.n_temporal_claims > 0 and result.score < threshold
        outcome = _classify_outcome(expected_fake, predicted_fake)

        print(f"TCS={result.score:.3f} {outcome}  {elapsed_ms:.0f}ms")

        rows.append({
            "idx": i + 1,
            "title": article.title,
            "tcs": round(result.score, 4),
            "label": result.label,
            "n_claims": result.n_temporal_claims,
            "n_inconsistencies": result.n_inconsistencies,
            "coherence_factor": round(result.coherence_factor, 4),
            "expected_fake": expected_fake,
            "predicted_fake": predicted_fake,
            "outcome": outcome,
            "processing_time_ms": round(elapsed_ms, 1),
            "source": "isot",
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
        "label": "error",
        "n_claims": 0,
        "n_inconsistencies": 0,
        "coherence_factor": 0.0,
        "expected_fake": entry.get("expected_fake", False),
        "predicted_fake": False,
        "outcome": "ERROR",
        "processing_time_ms": 0.0,
        "source": "isot",
    }


# // section metrics

def compute_metrics(rows: list[dict]) -> dict:
    tp = sum(1 for r in rows if r["outcome"] == "TP")
    tn = sum(1 for r in rows if r["outcome"] == "TN")
    fp = sum(1 for r in rows if r["outcome"] == "FP")
    fn = sum(1 for r in rows if r["outcome"] == "FN")

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(rows) if rows else 0.0

    successful = [r for r in rows if r["outcome"] != "ERROR"]
    avg_tcs_true = _avg_tcs(successful, expected_fake=False)
    avg_tcs_fake = _avg_tcs(successful, expected_fake=True)

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
    subset = [r["tcs"] for r in rows if r["expected_fake"] == expected_fake]
    return sum(subset) / len(subset) if subset else None


# // section print

def print_results(rows: list[dict], metrics: dict, threshold: float) -> None:
    title_w = 45
    sep = "-" * (title_w + 52)

    print(f"\n{'=' * (title_w + 52)}")
    print(f"  ISOT EVALUATION  |  threshold = {threshold:.2f}")
    print(f"{'=' * (title_w + 52)}")
    print(f"  {'#':>3}  {'Title':<{title_w}}  {'TCS':>6}  {'Exp':>4}  {'Pred':>5}  {'Out':>4}")
    print(sep)

    for r in rows:
        exp_str = "FAKE" if r["expected_fake"] else "TRUE"
        pred_str = "FAKE" if r["predicted_fake"] else "TRUE"
        marker = " " if r["outcome"] in ("TP", "TN") else "*"
        print(
            f"{marker} {r['idx']:>3}  {r['title'][:title_w]:<{title_w}}  "
            f"{r['tcs']:>6.3f}  {exp_str:>4}  {pred_str:>5}  {r['outcome']:>4}"
        )

    print(sep)
    print("  * = misclassified\n")

    print(f"  Metrics (threshold TCS < {threshold:.2f} = FAKE):")
    print(f"  {'-' * 40}")
    print(f"  TP={metrics['tp']}  TN={metrics['tn']}  FP={metrics['fp']}  FN={metrics['fn']}")
    print(f"  Precision : {metrics['precision']:.4f}")
    print(f"  Recall    : {metrics['recall']:.4f}")
    print(f"  F1        : {metrics['f1']:.4f}")
    print(f"  Accuracy  : {metrics['accuracy']:.4f}")
    if metrics["avg_tcs_true_articles"] is not None:
        print(f"  Avg TCS (TRUE) : {metrics['avg_tcs_true_articles']:.4f}")
    if metrics["avg_tcs_fake_articles"] is not None:
        print(f"  Avg TCS (FAKE) : {metrics['avg_tcs_fake_articles']:.4f}")
    print()


# // section save

def save_results(rows: list[dict], metrics: dict, pipeline: str, threshold: float) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    output_path = RESULTS_DIR / f"isot_{today}_{pipeline}.json"
    payload = {
        "generated_at": datetime.now().isoformat(),
        "dataset": "isot",
        "pipeline": pipeline,
        "fake_threshold": threshold,
        "metrics": metrics,
        "articles": rows,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    return output_path


# // section main

_DEFAULT_ISOT_DIRS = [
    _PROJECT_ROOT / "data" / "datasets" / "isot",
    _PROJECT_ROOT / "data" / "isot",
]


def _find_isot_dir(explicit: Optional[Path]) -> tuple[Path, Path]:
    """Return (True.csv, Fake.csv) paths, searching known locations if --path omitted."""
    candidates = ([explicit] if explicit else []) + _DEFAULT_ISOT_DIRS
    for d in candidates:
        true_csv = d / "True.csv"
        fake_csv = d / "Fake.csv"
        if true_csv.exists() and fake_csv.exists():
            return true_csv, fake_csv

    searched = "\n  ".join(str(d) for d in candidates)
    print(
        "[ERROR] ISOT dataset not found. Expected True.csv and Fake.csv in one of:\n"
        f"  {searched}\n\n"
        "Download ISOT from https://www.kaggle.com/datasets/clmentbisaillon/fake-and-real-news-dataset\n"
        "and place True.csv + Fake.csv in data/datasets/isot/ or pass --path <dir>"
    )
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="ISOT dataset evaluation — TCS pipeline")
    parser.add_argument(
        "--path", default=None,
        help="Directory containing True.csv and Fake.csv. "
             "If omitted, searches data/datasets/isot/ automatically.",
    )
    parser.add_argument("--pipeline", choices=["spacy", "llm"], default="spacy", help="Pipeline (default: spacy)")
    parser.add_argument("--wikidata", action="store_true", help="Enable Wikidata verification")
    parser.add_argument("--threshold", type=float, default=FAKE_THRESHOLD, help=f"TCS fake threshold (default: {FAKE_THRESHOLD})")
    parser.add_argument("--max", type=int, default=50, dest="max_per_class", help="Max articles per class (default: 50)")
    parser.add_argument("--model", type=str, default=None, help="Explicit model name")
    parser.add_argument("--rss", action="store_true", help="Enable RSS Stream in C3b")
    args = parser.parse_args()

    true_csv, fake_csv = _find_isot_dir(Path(args.path) if args.path else None)
    isot_dir = true_csv.parent

    print(f"\n{'=' * 70}")
    print("  ISOT EVALUATION")
    print(f"{'=' * 70}")
    print(f"  Path      : {isot_dir}")
    print(f"  Pipeline  : {args.pipeline}")
    print(f"  Threshold : {args.threshold}")
    print(f"  Max/class : {args.max_per_class}")
    print(f"{'=' * 70}\n")

    articles = load_isot(true_csv, fake_csv, max_per_class=args.max_per_class)
    true_count = sum(1 for a in articles if not a["expected_fake"])
    fake_count = sum(1 for a in articles if a["expected_fake"])
    print(f"  Loaded {len(articles)} articles ({true_count} TRUE, {fake_count} FAKE)\n")

    rows = run_isot(
        articles,
        pipeline=args.pipeline,
        use_wikidata=args.wikidata,
        threshold=args.threshold,
        model_name=args.model,
        use_rss=args.rss,
    )
    metrics = compute_metrics(rows)

    print_results(rows, metrics, args.threshold)

    output_path = save_results(rows, metrics, args.pipeline, args.threshold)
    print(f"  Results saved: {output_path}")


if __name__ == "__main__":
    main()

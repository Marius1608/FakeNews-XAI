"""RAGuard dataset evaluation.

RAGuard: UCSC-IRKM/RAGuard on HuggingFace
Format: parquet files with columns including question, answer, label (0=real, 1=fake or similar)
Political filter: same POLITICAL_KEYWORDS as ISOT

Usage:
  python evaluation/run_raguard_eval.py --path data/datasets/raguard/
  python evaluation/run_raguard_eval.py --path data/datasets/raguard/ --max 50
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
logger = logging.getLogger("raguard_eval")

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
FAKE_THRESHOLD = 0.70

POLITICAL_KEYWORDS = [
    "president", "senate", "congress", "election",
    "government", "white house", "trump", "obama", "clinton", "biden",
    "republican", "democrat", "political", "washington",
]

_LABEL_CANDIDATES = ["label", "fake", "is_fake", "ground_truth"]


# // section load

def load_raguard(
    path: Path,
    max_per_class: int = 50,
    political_filter: bool = True,
) -> list[dict]:
    """Reads parquet files from path, auto-detects label column, returns article dicts."""
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pandas is required: pip install pandas")
        sys.exit(1)

    parquet_files = list(path.glob("*.parquet"))
    if not parquet_files:
        # Also try nested train/test splits
        parquet_files = list(path.glob("**/*.parquet"))
    if not parquet_files:
        logger.error(f"No parquet files found in {path}")
        sys.exit(1)

    frames = [pd.read_parquet(f) for f in sorted(parquet_files)]
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.strip().lower() for c in df.columns]

    # Auto-detect label column
    label_col = next((c for c in _LABEL_CANDIDATES if c in df.columns), None)
    if label_col is None:
        logger.error(f"No label column found. Available columns: {list(df.columns)}")
        sys.exit(1)
    logger.info(f"RAGuard: using label column '{label_col}'")

    # Determine text column
    if "text" in df.columns:
        text_col = "text"
    elif "answer" in df.columns and "question" in df.columns:
        df["text"] = df["question"].fillna("").astype(str) + " " + df["answer"].fillna("").astype(str)
        text_col = "text"
    elif "answer" in df.columns:
        text_col = "answer"
    elif "question" in df.columns:
        text_col = "question"
    else:
        logger.error(f"No usable text column found. Columns: {list(df.columns)}")
        sys.exit(1)

    df = df.dropna(subset=[text_col])
    df = df[df[text_col].astype(str).str.strip().str.len() > 50]

    # Normalize label: 1/True/"fake"/"1" → is_fake=True
    def _to_fake(val) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return int(val) == 1
        return str(val).strip().lower() in ("1", "true", "fake", "yes")

    df["_is_fake"] = df[label_col].apply(_to_fake)

    if political_filter:
        mask = df[text_col].astype(str).str.lower().apply(
            lambda t: any(kw in t for kw in POLITICAL_KEYWORDS)
        )
        df = df[mask]

    title_col = next((c for c in ("title", "headline", "question") if c in df.columns), None)

    articles: list[dict] = []
    class_counts: dict[bool, int] = {True: 0, False: 0}

    for _, row in df.iterrows():
        is_fake = bool(row["_is_fake"])
        if class_counts[is_fake] >= max_per_class:
            continue

        text = str(row[text_col]).strip()
        if title_col:
            title = str(row[title_col]).strip()[:120]
        else:
            title = text[:80].replace("\n", " ")

        articles.append({
            "text": text,
            "title": title,
            "expected_fake": is_fake,
            "source": "raguard",
        })
        class_counts[is_fake] += 1

        if class_counts[True] >= max_per_class and class_counts[False] >= max_per_class:
            break

    true_count = class_counts[False]
    fake_count = class_counts[True]
    logger.info(f"RAGuard loaded: {true_count} TRUE + {fake_count} FAKE articles")
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


def run_raguard(
    articles: list[dict],
    pipeline: str = "spacy",
    use_wikidata: bool = False,
    threshold: float = FAKE_THRESHOLD,
    model_name: Optional[str] = None,
    use_rss: bool = False,
) -> list[dict]:
    """Runs the TCS pipeline on RAGuard articles and returns evaluation rows."""
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
            source="raguard",
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
            "source": "raguard",
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
        "source": "raguard",
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
    print(f"  RAGuard EVALUATION  |  threshold = {threshold:.2f}")
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
    output_path = RESULTS_DIR / f"raguard_{today}_{pipeline}.json"
    payload = {
        "generated_at": datetime.now().isoformat(),
        "dataset": "raguard",
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
    parser = argparse.ArgumentParser(description="RAGuard dataset evaluation — TCS pipeline")
    parser.add_argument("--path", required=True, help="Path to RAGuard directory containing parquet files")
    parser.add_argument("--pipeline", choices=["spacy", "llm"], default="spacy", help="Pipeline (default: spacy)")
    parser.add_argument("--wikidata", action="store_true", help="Enable Wikidata verification")
    parser.add_argument("--threshold", type=float, default=FAKE_THRESHOLD, help=f"TCS fake threshold (default: {FAKE_THRESHOLD})")
    parser.add_argument("--max", type=int, default=50, dest="max_per_class", help="Max articles per class (default: 50)")
    parser.add_argument("--model", type=str, default=None, help="Explicit model name")
    parser.add_argument("--rss", action="store_true", help="Enable RSS Stream in C3b")
    args = parser.parse_args()

    raguard_dir = Path(args.path)

    print(f"\n{'=' * 70}")
    print("  RAGuard EVALUATION")
    print(f"{'=' * 70}")
    print(f"  Path      : {raguard_dir}")
    print(f"  Pipeline  : {args.pipeline}")
    print(f"  Threshold : {args.threshold}")
    print(f"  Max/class : {args.max_per_class}")
    print(f"{'=' * 70}\n")

    articles = load_raguard(raguard_dir, max_per_class=args.max_per_class)
    true_count = sum(1 for a in articles if not a["expected_fake"])
    fake_count = sum(1 for a in articles if a["expected_fake"])
    print(f"  Loaded {len(articles)} articles ({true_count} TRUE, {fake_count} FAKE)\n")

    rows = run_raguard(
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

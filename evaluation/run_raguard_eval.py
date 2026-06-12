"""RAGuard dataset evaluation.

RAGuard: UCSC-IRKM/RAGuard on HuggingFace
CSV format:
  claims.csv   — Claim ID, Claim, Verdict (bool), Document IDs, Document Labels, Original Verdict
  documents.csv — Document ID, Title, Full Text, Claim ID, Document Label, Link

Verdict=True means the claim is FAKE/hallucinated in RAGuard.

Usage:
  python evaluation/run_raguard_eval.py                          # auto-detects from HF cache or downloads
  python evaluation/run_raguard_eval.py --path data/raguard/    # explicit directory
  python evaluation/run_raguard_eval.py --max 50
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

_HF_CLAIMS_URL = "https://huggingface.co/datasets/UCSC-IRKM/RAGuard/resolve/main/claims.csv"
_HF_DOCS_URL   = "https://huggingface.co/datasets/UCSC-IRKM/RAGuard/resolve/main/documents.csv"
_DEFAULT_DOWNLOAD_DIR = _PROJECT_ROOT / "data" / "datasets" / "raguard"


# // section load

def _find_in_hf_cache(filename: str) -> Optional[Path]:
    """Search the HuggingFace hub cache for a specific filename."""
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    if not cache_dir.exists():
        return None
    matches = list(cache_dir.rglob(filename))
    return matches[0] if matches else None


def _download_csv(url: str, dest: Path) -> None:
    """Download a file from url to dest, showing progress."""
    import requests
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading {url} -> {dest}")
    print(f"  Downloading {dest.name} from HuggingFace ...", end=" ", flush=True)
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        print("done")
    except Exception as e:
        print(f"FAILED: {e}")
        raise


def _resolve_csv_paths(path: Optional[Path]) -> tuple[Path, Path]:
    """
    Return (claims_path, docs_path) by:
      1. Using explicit --path directory if provided and files exist there.
      2. Searching the HuggingFace cache.
      3. Downloading to _DEFAULT_DOWNLOAD_DIR.
    """
    # 1. Explicit path
    if path is not None:
        claims = path / "claims.csv"
        docs   = path / "documents.csv"
        if claims.exists() and docs.exists():
            return claims, docs
        print(f"  [WARN] claims.csv or documents.csv not found in {path}, trying HF cache ...")

    # 2. HF cache search
    cached_claims = _find_in_hf_cache("claims.csv")
    cached_docs   = _find_in_hf_cache("documents.csv")
    if cached_claims and cached_docs:
        logger.info(f"RAGuard found in HF cache: {cached_claims.parent}")
        return cached_claims, cached_docs

    # 3. Download
    dl_dir = path if path is not None else _DEFAULT_DOWNLOAD_DIR
    claims_dest = dl_dir / "claims.csv"
    docs_dest   = dl_dir / "documents.csv"

    if not claims_dest.exists():
        _download_csv(_HF_CLAIMS_URL, claims_dest)
    if not docs_dest.exists():
        _download_csv(_HF_DOCS_URL, docs_dest)

    return claims_dest, docs_dest


def load_raguard(
    path: Optional[Path] = None,
    max_per_class: int = 50,
    political_filter: bool = True,
) -> list[dict]:
    """
    Load RAGuard from CSV files.

    Resolution order:
      1. CSV files in `path` (if provided)
      2. HuggingFace hub cache (~/.cache/huggingface/hub/**/claims.csv)
      3. Download from HuggingFace to `path` or data/datasets/raguard/

    claims.csv  columns: Claim ID, Claim, Verdict (bool), ...
    documents.csv columns: Document ID, Title, Full Text, Claim ID, ...

    Verdict=True in RAGuard means the claim is FAKE/hallucinated.
    """
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pandas is required: pip install pandas")
        sys.exit(1)

    claims_path, docs_path = _resolve_csv_paths(path)
    logger.info(f"RAGuard claims   : {claims_path}")
    logger.info(f"RAGuard documents: {docs_path}")

    claims_df = pd.read_csv(claims_path)
    docs_df   = pd.read_csv(docs_path)

    # Normalize column names (strip whitespace)
    claims_df.columns = [c.strip() for c in claims_df.columns]
    docs_df.columns   = [c.strip() for c in docs_df.columns]

    # Validate required columns
    for col in ("Claim ID", "Claim", "Verdict"):
        if col not in claims_df.columns:
            logger.error(f"claims.csv missing column '{col}'. Found: {list(claims_df.columns)}")
            sys.exit(1)
    for col in ("Claim ID", "Full Text"):
        if col not in docs_df.columns:
            logger.error(f"documents.csv missing column '{col}'. Found: {list(docs_df.columns)}")
            sys.exit(1)

    # Merge: one row per document, enriched with claim metadata
    merged = claims_df.merge(docs_df, on="Claim ID", how="left")

    # Political filter on Full Text + Claim
    if political_filter:
        def _has_kw(row) -> bool:
            text = " ".join([
                str(row.get("Full Text", "") or ""),
                str(row.get("Claim", "") or ""),
                str(row.get("Title", "") or ""),
            ]).lower()
            return any(kw in text for kw in POLITICAL_KEYWORDS)
        merged = merged[merged.apply(_has_kw, axis=1)]

    articles: list[dict] = []
    class_counts: dict[bool, int] = {True: 0, False: 0}

    for _, row in merged.iterrows():
        # Verdict=True → fake; Verdict=False → real/confirmed
        verdict_raw = row["Verdict"]
        if isinstance(verdict_raw, bool):
            is_fake = verdict_raw
        elif isinstance(verdict_raw, str):
            is_fake = verdict_raw.strip().lower() in ("true", "1", "yes", "fake")
        else:
            is_fake = bool(verdict_raw)

        if class_counts[is_fake] >= max_per_class:
            continue

        full_text = row.get("Full Text", "")
        claim     = str(row.get("Claim", "")).strip()
        title_raw = row.get("Title", "")

        text  = str(full_text).strip() if pd.notna(full_text) and str(full_text).strip() else claim
        title = str(title_raw).strip()[:120] if pd.notna(title_raw) and str(title_raw).strip() else claim[:80]

        if len(text) < 30:
            continue

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
    parser.add_argument(
        "--path", default=None,
        help="Directory containing claims.csv and documents.csv. "
             "If omitted, auto-detects from HuggingFace cache or downloads to data/datasets/raguard/",
    )
    parser.add_argument("--pipeline", choices=["spacy", "llm"], default="spacy", help="Pipeline (default: spacy)")
    parser.add_argument("--wikidata", action="store_true", help="Enable Wikidata verification")
    parser.add_argument("--threshold", type=float, default=FAKE_THRESHOLD, help=f"TCS fake threshold (default: {FAKE_THRESHOLD})")
    parser.add_argument("--max", type=int, default=50, dest="max_per_class", help="Max articles per class (default: 50)")
    parser.add_argument("--model", type=str, default=None, help="Explicit model name")
    parser.add_argument("--rss", action="store_true", help="Enable RSS Stream in C3b")
    args = parser.parse_args()

    raguard_dir = Path(args.path) if args.path else None

    print(f"\n{'=' * 70}")
    print("  RAGuard EVALUATION")
    print(f"{'=' * 70}")
    print(f"  Path      : {raguard_dir or '(auto — HF cache / download)'}")
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

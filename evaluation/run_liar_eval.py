"""Evaluare TCS pe LIAR2 — TCS mediu per label si metrici binare fake/true.

Rulare rapida:
  python evaluation/run_liar_eval.py --n 20 --split test
Rulare completa:
  python evaluation/run_liar_eval.py --n 100
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
logger = logging.getLogger("liar_eval")

EVAL_DIR    = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
FIGURES_DIR = EVAL_DIR / "figures"

LABEL_ORDER  = ["true", "mostly-true", "half-true", "barely-true", "false", "pants-fire"]
FAKE_LABELS  = {"false", "pants-fire", "barely-true"}
TRUE_LABELS  = {"true", "mostly-true", "half-true"}
DEFAULT_THRESHOLD = 0.6


# section: pipeline helpers

def _resolve_spacy_model(model_name: Optional[str]) -> Optional[str]:
    import spacy
    installed = spacy.util.get_installed_models()
    if not installed:
        return None
    if model_name and model_name in installed:
        return model_name
    for preferred in ("en_core_web_trf", "en_core_web_lg", "en_core_web_sm"):
        if preferred in installed:
            return preferred
    return installed[0]


def _build_orchestrator(pipeline: str, use_wikidata: bool, model_name: Optional[str]):
    from backend.pipeline.orchestrator import PipelineOrchestrator
    resolved = _resolve_spacy_model(model_name) if pipeline == "spacy" else model_name
    if pipeline == "spacy" and not resolved:
        print("  [ERROR] No spaCy model installed. Run: python -m spacy download en_core_web_sm")
        sys.exit(1)
    return PipelineOrchestrator(
        use_wikidata=use_wikidata,
        extractor_name=pipeline,
        model_name=resolved,
        persistent_store=None,
    )


# section: run

def run_liar_eval(
    n: int,
    split: str,
    pipeline: str,
    use_wikidata: bool,
    threshold: float,
    model_name: Optional[str],
) -> dict:
    from backend.input.dataset import load_liar

    print(f"\n{'='*65}")
    print(f"  LIAR2 Evaluation — split={split}, n={n}, threshold={threshold}")
    print(f"{'='*65}")

    articles = load_liar(split=split, max_articles=n)
    if not articles:
        print("  [ERROR] No LIAR articles found. Check data/datasets/liar/")
        sys.exit(1)
    print(f"  Loaded {len(articles)} articles\n")

    orch = _build_orchestrator(pipeline, use_wikidata, model_name)

    per_label: dict[str, list[float]] = {lbl: [] for lbl in LABEL_ORDER}
    per_label["other"] = []
    rows: list[dict] = []

    for i, article in enumerate(articles):
        print(f"  [{i+1:3d}/{len(articles)}] {article.title[:55]:<55}", end=" ", flush=True)
        t0 = time.monotonic()
        try:
            result = orch.run(article)
            tcs = result.score
            n_inc = result.n_inconsistencies
        except Exception as exc:
            logger.error(f"Pipeline error on article {i+1}: {exc}")
            tcs, n_inc = 0.0, 0
        elapsed_ms = (time.monotonic() - t0) * 1000

        lbl = article.label or "other"
        bucket = lbl if lbl in per_label else "other"
        per_label[bucket].append(tcs)

        predicted_fake = tcs < threshold
        expected_fake  = lbl in FAKE_LABELS
        expected_true  = lbl in TRUE_LABELS

        print(f"TCS={tcs:.3f}  label={lbl}")
        rows.append({
            "idx": i + 1,
            "title": article.title[:80],
            "label": lbl,
            "tcs": round(tcs, 4),
            "n_inconsistencies": n_inc,
            "predicted_fake": predicted_fake,
            "expected_fake": expected_fake,
            "expected_true": expected_true,
            "processing_time_ms": round(elapsed_ms, 1),
        })

    return {"rows": rows, "per_label": per_label}


# section: metrics

def compute_per_label_stats(per_label: dict[str, list[float]], threshold: float) -> dict:
    stats: dict[str, dict] = {}
    for lbl in LABEL_ORDER + ["other"]:
        scores = per_label.get(lbl, [])
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        predicted_fake_pct = sum(1 for s in scores if s < threshold) / len(scores) * 100
        stats[lbl] = {
            "n": len(scores),
            "avg_tcs": round(avg, 4),
            "min_tcs": round(min(scores), 4),
            "max_tcs": round(max(scores), 4),
            "predicted_fake_pct": round(predicted_fake_pct, 1),
            "scores": [round(s, 4) for s in scores],
        }
    return stats


def compute_binary_metrics(rows: list[dict], threshold: float) -> dict:
    tp = sum(1 for r in rows if r["expected_fake"] and r["predicted_fake"])
    tn = sum(1 for r in rows if r["expected_true"] and not r["predicted_fake"])
    fp = sum(1 for r in rows if r["expected_true"] and r["predicted_fake"])
    fn = sum(1 for r in rows if r["expected_fake"] and not r["predicted_fake"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy  = (tp + tn) / len(rows) if rows else 0.0

    classified = sum(1 for r in rows if r["expected_fake"] or r["expected_true"])

    return {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall":    round(recall, 4),
        "f1":        round(f1, 4),
        "accuracy":  round(accuracy, 4),
        "classified_articles": classified,
        "unclassified_articles": len(rows) - classified,
    }


# section: print

def print_per_label_table(stats: dict, threshold: float) -> None:
    print(f"\n  {'Label':<14} {'N':>4}  {'Avg TCS':>8}  {'Min':>6}  {'Max':>6}  {'Pred FAKE%':>10}")
    print("  " + "-" * 56)
    for lbl in LABEL_ORDER + ["other"]:
        if lbl not in stats:
            continue
        s = stats[lbl]
        marker = "F" if lbl in FAKE_LABELS else ("T" if lbl in TRUE_LABELS else " ")
        print(
            f"  [{marker}] {lbl:<12} {s['n']:>4}  {s['avg_tcs']:>8.4f}"
            f"  {s['min_tcs']:>6.4f}  {s['max_tcs']:>6.4f}  {s['predicted_fake_pct']:>9.1f}%"
        )
    print(f"  [T]=true-side  [F]=fake-side  threshold={threshold}\n")


def print_binary_metrics(metrics: dict, threshold: float) -> None:
    print(f"  Binary metrics (fake={sorted(FAKE_LABELS)}, threshold TCS<{threshold}):")
    print(f"  {'-'*44}")
    print(f"  TP={metrics['tp']}  TN={metrics['tn']}  FP={metrics['fp']}  FN={metrics['fn']}")
    print(f"  Precision : {metrics['precision']:.4f}")
    print(f"  Recall    : {metrics['recall']:.4f}")
    print(f"  F1        : {metrics['f1']:.4f}")
    print(f"  Accuracy  : {metrics['accuracy']:.4f}")
    print(f"  Classified: {metrics['classified_articles']} / {metrics['classified_articles'] + metrics['unclassified_articles']}")
    print()


# section: boxplot

def save_boxplot(stats: dict, threshold: float) -> Optional[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [WARNING] matplotlib not installed — skipping boxplot.")
        return None

    color_map = {
        "true": "#4caf50", "mostly-true": "#8bc34a", "half-true": "#ffc107",
        "barely-true": "#ff9800", "false": "#f44336", "pants-fire": "#b71c1c",
        "other": "#9e9e9e",
    }

    labels = [lbl for lbl in LABEL_ORDER + ["other"] if lbl in stats]
    data   = [stats[lbl]["scores"] for lbl in labels]
    colors = [color_map.get(lbl, "#9e9e9e") for lbl in labels]

    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 1.3), 5))
    bp = ax.boxplot(data, patch_artist=True, notch=False)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    ax.axhline(y=threshold, color="red", linestyle="--", linewidth=1.2,
               label=f"Threshold ({threshold})")
    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels, fontsize=9, rotation=15)
    ax.set_ylabel("TCS Score")
    ax.set_title("TCS Distribution per LIAR2 Label")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    today    = date.today().strftime("%Y-%m-%d")
    out_path = FIGURES_DIR / f"liar_boxplot_{today}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_path


# section: save

def save_results(
    per_label_stats: dict,
    binary_metrics: dict,
    rows: list[dict],
    pipeline: str,
    split: str,
    threshold: float,
    boxplot_path: Optional[Path],
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today    = date.today().strftime("%Y-%m-%d")
    out_path = RESULTS_DIR / f"liar_eval_{today}.json"

    payload = {
        "generated_at": datetime.now().isoformat(),
        "pipeline": pipeline,
        "split": split,
        "threshold": threshold,
        "total": len(rows),
        "per_label": {
            lbl: {k: v for k, v in s.items() if k != "scores"}
            for lbl, s in per_label_stats.items()
        },
        "per_label_scores": {lbl: s["scores"] for lbl, s in per_label_stats.items()},
        "binary_metrics": binary_metrics,
        "boxplot": str(boxplot_path) if boxplot_path else None,
        "articles": rows,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return out_path


# section: main

def main() -> None:
    parser = argparse.ArgumentParser(description="TCS evaluation on LIAR2 dataset")
    parser.add_argument("--n",         type=int,   default=100,              help="Number of articles to evaluate (default: 100)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="TCS threshold for fake prediction (default: 0.6)")
    parser.add_argument("--pipeline",  choices=["spacy", "llm"], default="spacy", help="Extractor pipeline (default: spacy)")
    parser.add_argument("--wikidata",  action="store_true",                  help="Enable Wikidata verification")
    parser.add_argument("--split",     choices=["train", "test", "valid"], default="test", help="LIAR split to use (default: test)")
    parser.add_argument("--model",     type=str,   default=None,             help="Explicit spaCy/LLM model name")
    args = parser.parse_args()

    eval_data = run_liar_eval(
        n=args.n,
        split=args.split,
        pipeline=args.pipeline,
        use_wikidata=args.wikidata,
        threshold=args.threshold,
        model_name=args.model,
    )

    rows      = eval_data["rows"]
    per_label = eval_data["per_label"]

    per_label_stats = compute_per_label_stats(per_label, args.threshold)
    binary_metrics  = compute_binary_metrics(rows, args.threshold)

    print(f"\n{'='*65}")
    print_per_label_table(per_label_stats, args.threshold)
    print_binary_metrics(binary_metrics, args.threshold)

    boxplot_path = save_boxplot(per_label_stats, args.threshold)
    if boxplot_path:
        print(f"  Boxplot saved: {boxplot_path}")

    out_path = save_results(
        per_label_stats, binary_metrics, rows,
        pipeline=args.pipeline,
        split=args.split,
        threshold=args.threshold,
        boxplot_path=boxplot_path,
    )

    print(f"\n{'='*65}")
    print(f"  Results saved: {out_path}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()

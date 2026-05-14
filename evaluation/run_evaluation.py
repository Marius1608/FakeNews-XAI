"""Full TCS evaluation: manual benchmark + LIAR subset + FakeNewsNet + pipeline comparison.

Usage:
  python evaluation/run_evaluation.py                  # all datasets
  python evaluation/run_evaluation.py --benchmark-only # only manual benchmark
  python evaluation/run_evaluation.py --no-wikidata    # skip Wikidata lookups
  python evaluation/run_evaluation.py --threshold 0.5  # custom fake threshold
  python evaluation/run_evaluation.py --pipeline llm   # use LLM extractor
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
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
logger = logging.getLogger("run_evaluation")

EVAL_DIR = Path(__file__).parent
BENCHMARK_FILE = EVAL_DIR / "benchmark_articles.json"
RESULTS_DIR = EVAL_DIR / "results"
FIGURES_DIR = EVAL_DIR / "figures"
FAKE_THRESHOLD = 0.6

LIAR_LABEL_ORDER = ["true", "mostly-true", "half-true", "barely-true", "false", "pants-fire"]


# section: pipeline helpers

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


def _build_orchestrator(pipeline: str, use_wikidata: bool, model_name: Optional[str]):
    from backend.pipeline.orchestrator import PipelineOrchestrator
    resolved_model = _resolve_spacy_model(model_name) if pipeline == "spacy" else model_name
    if pipeline == "spacy" and resolved_model is None:
        logger.error("No spaCy model installed. Run: python -m spacy download en_core_web_sm")
        sys.exit(1)
    return PipelineOrchestrator(
        use_wikidata=use_wikidata,
        extractor_name=pipeline,
        model_name=resolved_model,
        persistent_store=None,
    )


def _run_article(orch, article) -> dict:
    t0 = time.monotonic()
    try:
        result = orch.run(article)
        elapsed_ms = (time.monotonic() - t0) * 1000
        return {
            "ok": True,
            "tcs": round(result.score, 4),
            "tcs_label": result.label,
            "n_claims": result.n_temporal_claims,
            "n_inconsistencies": result.n_inconsistencies,
            "coherence_factor": round(result.coherence_factor, 4),
            "inconsistencies": [
                {
                    "type": inc.inconsistency_type.value,
                    "severity": inc.severity.value,
                    "description": inc.description,
                }
                for inc in result.inconsistencies
            ],
            "processing_time_ms": round(elapsed_ms, 1),
        }
    except Exception as exc:
        logger.error(f"Pipeline error: {exc}", exc_info=True)
        return {
            "ok": False,
            "tcs": 0.0,
            "tcs_label": "error",
            "n_claims": 0,
            "n_inconsistencies": 0,
            "coherence_factor": 0.0,
            "inconsistencies": [],
            "processing_time_ms": 0.0,
        }


def _classify_outcome(expected_fake: bool, predicted_fake: bool) -> str:
    if expected_fake and predicted_fake:
        return "TP"
    if not expected_fake and not predicted_fake:
        return "TN"
    if not expected_fake and predicted_fake:
        return "FP"
    return "FN"


def _compute_metrics(rows: list[dict]) -> dict:
    tp = sum(1 for r in rows if r["outcome"] == "TP")
    tn = sum(1 for r in rows if r["outcome"] == "TN")
    fp = sum(1 for r in rows if r["outcome"] == "FP")
    fn = sum(1 for r in rows if r["outcome"] == "FN")

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy  = (tp + tn) / len(rows) if rows else 0.0

    true_scores = [r["tcs"] for r in rows if not r["expected_fake"] and r["outcome"] != "ERROR"]
    fake_scores = [r["tcs"] for r in rows if r["expected_fake"] and r["outcome"] != "ERROR"]

    return {
        "total": len(rows),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "avg_tcs_true": round(sum(true_scores) / len(true_scores), 4) if true_scores else None,
        "avg_tcs_fake": round(sum(fake_scores) / len(fake_scores), 4) if fake_scores else None,
    }


# section: benchmark manual

def run_benchmark(
    orch,
    threshold: float,
    pipeline_name: str,
) -> dict:
    print("\n" + "=" * 70)
    print("  STEP 1 — Manual Benchmark")
    print("=" * 70)

    if not BENCHMARK_FILE.exists():
        print(f"  [ERROR] Benchmark file not found: {BENCHMARK_FILE}")
        return {}

    with open(BENCHMARK_FILE, encoding="utf-8") as f:
        entries = json.load(f)
    print(f"  Loaded {len(entries)} articles from {BENCHMARK_FILE.name}")

    from backend.pipeline.graph.models import Article

    rows = []
    for i, entry in enumerate(entries):
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

        print(f"  [{i+1:2d}/{len(entries)}] {article.title[:60]}", end=" ... ", flush=True)
        res = _run_article(orch, article)
        print(f"TCS={res['tcs']:.3f}")

        expected_fake: bool = entry.get("expected_fake", False)
        predicted_fake: bool = res["tcs"] < threshold
        outcome = _classify_outcome(expected_fake, predicted_fake) if res["ok"] else "ERROR"

        rows.append({
            "idx": i + 1,
            "title": article.title,
            "source": entry.get("source", ""),
            "expected_fake": expected_fake,
            "inconsistency_types": entry.get("inconsistency_types", []),
            "notes": entry.get("notes", ""),
            "predicted_fake": predicted_fake,
            "outcome": outcome,
            "tcs": res["tcs"],
            "tcs_label": res["tcs_label"],
            "n_claims": res["n_claims"],
            "n_inconsistencies": res["n_inconsistencies"],
            "coherence_factor": res["coherence_factor"],
            "known_inconsistencies": entry.get("known_inconsistencies", []),
            "detected_inconsistencies": res["inconsistencies"],
            "processing_time_ms": res["processing_time_ms"],
        })

    metrics = _compute_metrics(rows)
    _print_benchmark_table(rows, threshold)
    _print_metrics(metrics, threshold, label="Manual Benchmark")

    return {"rows": rows, "metrics": metrics}


def _print_benchmark_table(rows: list[dict], threshold: float) -> None:
    w = 44
    sep = "-" * (w + 56)
    print(f"\n  {'#':>2}  {'Title':<{w}}  {'TCS':>6}  {'Exp':>4}  {'Pred':>5}  {'Out':>4}  {'Inc':>4}")
    print(f"  {sep}")
    for r in rows:
        marker = " " if r["outcome"] in ("TP", "TN") else "*"
        exp_s  = "FAKE" if r["expected_fake"] else "TRUE"
        pred_s = "FAKE" if r["predicted_fake"] else "TRUE"
        print(
            f"{marker} {r['idx']:>2}  {r['title'][:w]:<{w}}  {r['tcs']:>6.3f}"
            f"  {exp_s:>4}  {pred_s:>5}  {r['outcome']:>4}  {r['n_inconsistencies']:>4}"
        )
    print(f"  {sep}")
    print("  * = misclassified\n")


def _print_metrics(metrics: dict, threshold: float, label: str = "") -> None:
    tag = f"  [{label}]" if label else " "
    print(f"{tag} threshold TCS < {threshold:.2f} = FAKE")
    print(f"  TP={metrics['tp']}  TN={metrics['tn']}  FP={metrics['fp']}  FN={metrics['fn']}")
    print(f"  Precision : {metrics['precision']:.4f}")
    print(f"  Recall    : {metrics['recall']:.4f}")
    print(f"  F1        : {metrics['f1']:.4f}")
    print(f"  Accuracy  : {metrics['accuracy']:.4f}")
    if metrics.get("avg_tcs_true") is not None:
        print(f"  Avg TCS (TRUE) : {metrics['avg_tcs_true']:.4f}")
    if metrics.get("avg_tcs_fake") is not None:
        print(f"  Avg TCS (FAKE) : {metrics['avg_tcs_fake']:.4f}")
    print()


# section: LIAR evaluation

def run_liar(orch, threshold: float, max_articles: int = 50) -> dict:
    print("\n" + "=" * 70)
    print("  STEP 2 — LIAR Subset Evaluation")
    print("=" * 70)

    try:
        from backend.input.dataset import load_liar
        articles = load_liar(max_articles=max_articles)
    except Exception as exc:
        print(f"  [WARNING] Could not load LIAR dataset: {exc}")
        return {}

    if not articles:
        print("  [WARNING] LIAR dataset not found at data/datasets/liar/test.tsv — skipping.")
        return {}

    print(f"  Loaded {len(articles)} LIAR articles")

    per_label: dict[str, list[float]] = {lbl: [] for lbl in LIAR_LABEL_ORDER}
    per_label["other"] = []

    for i, article in enumerate(articles):
        print(f"  [{i+1:2d}/{len(articles)}] {article.title[:55]}", end=" ... ", flush=True)
        res = _run_article(orch, article)
        print(f"TCS={res['tcs']:.3f}  label={article.label}")
        bucket = article.label if article.label in per_label else "other"
        per_label[bucket].append(res["tcs"])

    summary: dict[str, dict] = {}
    print("\n  TCS per LIAR category:")
    print(f"  {'Label':<14} {'N':>4}  {'Avg TCS':>8}  {'Min':>6}  {'Max':>6}")
    print("  " + "-" * 46)
    for lbl in LIAR_LABEL_ORDER + ["other"]:
        scores = per_label[lbl]
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        summary[lbl] = {
            "n": len(scores),
            "avg_tcs": round(avg, 4),
            "min_tcs": round(min(scores), 4),
            "max_tcs": round(max(scores), 4),
            "scores": scores,
        }
        print(f"  {lbl:<14} {len(scores):>4}  {avg:>8.4f}  {min(scores):>6.4f}  {max(scores):>6.4f}")
    print()

    return {"per_label": summary, "total": len(articles)}


# section: FakeNewsNet evaluation

def run_fakenewsnet(orch, threshold: float, max_articles: int = 25) -> dict:
    print("\n" + "=" * 70)
    print("  STEP 3 — FakeNewsNet Evaluation (politifact)")
    print("=" * 70)

    try:
        from backend.input.dataset import load_fakenewsnet
    except Exception as exc:
        print(f"  [WARNING] Could not import FakeNewsNet loader: {exc}")
        return {}

    results: dict[str, dict] = {}

    for label in ("fake", "real"):
        articles = load_fakenewsnet(source="politifact", label=label, max_articles=max_articles)
        if not articles:
            print(f"  [WARNING] FakeNewsNet politifact/{label} not found — skipping.")
            results[label] = {}
            continue

        print(f"\n  politifact/{label}: {len(articles)} articles")
        scores = []
        for i, article in enumerate(articles):
            print(f"  [{i+1:2d}/{len(articles)}] {article.title[:55]}", end=" ... ", flush=True)
            res = _run_article(orch, article)
            print(f"TCS={res['tcs']:.3f}")
            scores.append(res["tcs"])

        avg = sum(scores) / len(scores) if scores else 0.0
        results[label] = {
            "n": len(scores),
            "avg_tcs": round(avg, 4),
            "min_tcs": round(min(scores), 4) if scores else None,
            "max_tcs": round(max(scores), 4) if scores else None,
            "scores": scores,
        }
        print(f"  Avg TCS [{label}]: {avg:.4f}")

    if results.get("fake") and results.get("real"):
        gap = (results["real"].get("avg_tcs", 0) or 0) - (results["fake"].get("avg_tcs", 0) or 0)
        print(f"\n  TCS gap (real − fake): {gap:+.4f}")
        results["gap_real_minus_fake"] = round(gap, 4)

    return results


# section: pipeline comparison

def run_pipeline_comparison(threshold: float, use_wikidata: bool, max_articles: int = 20) -> dict:
    print("\n" + "=" * 70)
    print("  STEP 5 — Pipeline A (spaCy) vs Pipeline B (LLM) Comparison")
    print("=" * 70)

    if not BENCHMARK_FILE.exists():
        print(f"  [ERROR] Benchmark file not found: {BENCHMARK_FILE}")
        return {}

    with open(BENCHMARK_FILE, encoding="utf-8") as f:
        entries = json.load(f)
    entries = entries[:max_articles]
    print(f"  Using first {len(entries)} benchmark articles")

    from backend.pipeline.graph.models import Article

    try:
        orch_a = _build_orchestrator("spacy", use_wikidata, None)
    except SystemExit:
        print("  [WARNING] spaCy not available — skipping pipeline comparison.")
        return {}

    try:
        orch_b = _build_orchestrator("llm", use_wikidata, None)
        has_llm = True
    except Exception as exc:
        print(f"  [WARNING] LLM pipeline unavailable ({exc}) — showing spaCy only.")
        has_llm = False

    rows = []
    for i, entry in enumerate(entries):
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

        print(f"  [{i+1:2d}/{len(entries)}] {article.title[:50]}", end=" ... ", flush=True)
        res_a = _run_article(orch_a, article)
        res_b = _run_article(orch_b, article) if has_llm else {"tcs": None, "tcs_label": "N/A", "processing_time_ms": 0.0}

        delta = (res_a["tcs"] - res_b["tcs"]) if (has_llm and res_b["tcs"] is not None) else None
        pred_a = res_a["tcs"] < threshold
        pred_b = (res_b["tcs"] < threshold) if (has_llm and res_b["tcs"] is not None) else None
        agree  = (pred_a == pred_b) if pred_b is not None else None

        print(f"A={res_a['tcs']:.3f}  B={res_b['tcs'] if res_b['tcs'] is not None else 'N/A'}")

        expected_fake: bool = entry.get("expected_fake", False)
        rows.append({
            "idx": i + 1,
            "title": article.title,
            "expected_fake": expected_fake,
            "tcs_a": res_a["tcs"],
            "label_a": res_a["tcs_label"],
            "time_a_ms": res_a["processing_time_ms"],
            "predicted_a": pred_a,
            "outcome_a": _classify_outcome(expected_fake, pred_a),
            "tcs_b": res_b["tcs"],
            "label_b": res_b["tcs_label"],
            "time_b_ms": res_b["processing_time_ms"],
            "predicted_b": pred_b,
            "outcome_b": _classify_outcome(expected_fake, pred_b) if pred_b is not None else "N/A",
            "delta": delta,
            "agree": agree,
        })

    _print_comparison_table(rows, has_llm)
    metrics_a = _compute_metrics([
        {**r, "tcs": r["tcs_a"], "predicted_fake": r["predicted_a"], "outcome": r["outcome_a"]}
        for r in rows
    ])
    metrics_b = _compute_metrics([
        {**r, "tcs": r["tcs_b"] or 0.0, "predicted_fake": r["predicted_b"] or False, "outcome": r["outcome_b"]}
        for r in rows if r["predicted_b"] is not None
    ]) if has_llm else {}

    print("  Pipeline A (spaCy):")
    _print_metrics(metrics_a, threshold)
    if has_llm and metrics_b:
        print("  Pipeline B (LLM):")
        _print_metrics(metrics_b, threshold)

    agreement_rate = sum(1 for r in rows if r["agree"]) / len(rows) if rows else 0.0
    print(f"  Agreement rate A vs B: {agreement_rate:.2%}")

    return {
        "rows": rows,
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "agreement_rate": round(agreement_rate, 4),
        "has_llm": has_llm,
    }


def _print_comparison_table(rows: list[dict], has_llm: bool) -> None:
    w = 40
    print(f"\n  {'#':>2}  {'Title':<{w}}  {'TCS-A':>6}  {'TCS-B':>6}  {'Delta':>7}  {'Agree':>6}  {'Exp':>4}")
    print("  " + "-" * (w + 52))
    for r in rows:
        tcs_b_str = f"{r['tcs_b']:.3f}" if r["tcs_b"] is not None else "  N/A "
        delta_str = f"{r['delta']:+.3f}" if r["delta"] is not None else "   N/A"
        agree_str = ("Y" if r["agree"] else "N") if r["agree"] is not None else "-"
        exp_str   = "FAKE" if r["expected_fake"] else "TRUE"
        print(
            f"  {r['idx']:>2}  {r['title'][:w]:<{w}}  {r['tcs_a']:>6.3f}"
            f"  {tcs_b_str:>6}  {delta_str:>7}  {agree_str:>6}  {exp_str:>4}"
        )
    print("  " + "-" * (w + 52) + "\n")


# section: boxplot

def generate_boxplot(
    benchmark_rows: list[dict],
    liar_data: dict,
    fnn_data: dict,
    threshold: float,
) -> Optional[Path]:
    print("\n" + "=" * 70)
    print("  STEP 4 — Generating TCS Boxplot")
    print("=" * 70)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [WARNING] matplotlib not installed — skipping boxplot.")
        return None

    groups: list[tuple[str, list[float]]] = []

    if benchmark_rows:
        true_scores = [r["tcs"] for r in benchmark_rows if not r["expected_fake"] and r["outcome"] != "ERROR"]
        fake_scores = [r["tcs"] for r in benchmark_rows if r["expected_fake"] and r["outcome"] != "ERROR"]
        if true_scores:
            groups.append(("Benchmark\nTRUE", true_scores))
        if fake_scores:
            groups.append(("Benchmark\nFAKE", fake_scores))

    for lbl in LIAR_LABEL_ORDER:
        if lbl in liar_data and liar_data[lbl].get("scores"):
            groups.append((f"LIAR\n{lbl}", liar_data[lbl]["scores"]))

    if fnn_data.get("real", {}).get("scores"):
        groups.append(("FakeNewsNet\nreal", fnn_data["real"]["scores"]))
    if fnn_data.get("fake", {}).get("scores"):
        groups.append(("FakeNewsNet\nfake", fnn_data["fake"]["scores"]))

    if not groups:
        print("  [WARNING] No data available for boxplot.")
        return None

    labels  = [g[0] for g in groups]
    data    = [g[1] for g in groups]
    colors  = []
    for lbl in labels:
        if "TRUE" in lbl or "real" in lbl or "true" in lbl or "mostly-true" in lbl:
            colors.append("#4caf50")
        elif "FAKE" in lbl or "fake" in lbl or "pants-fire" in lbl or "false" in lbl:
            colors.append("#f44336")
        elif "half-true" in lbl:
            colors.append("#ff9800")
        elif "barely-true" in lbl:
            colors.append("#ff5722")
        else:
            colors.append("#9e9e9e")

    fig, ax = plt.subplots(figsize=(max(10, len(groups) * 1.4), 6))
    bp = ax.boxplot(data, patch_artist=True, notch=False, vert=True)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)

    ax.axhline(y=threshold, color="red", linestyle="--", linewidth=1.2, label=f"Threshold ({threshold})")
    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("TCS Score")
    ax.set_title("TCS Distribution per Dataset / Label")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="upper right")
    ax.grid(axis="y", linestyle=":", alpha=0.5)

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    out_path = FIGURES_DIR / f"tcs_boxplot_{today}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"  Boxplot saved: {out_path}")
    return out_path


# section: save results

def save_full_results(
    benchmark: dict,
    liar: dict,
    fnn: dict,
    comparison: dict,
    boxplot_path: Optional[Path],
    pipeline: str,
    threshold: float,
    use_wikidata: bool,
) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y-%m-%d")
    out_path = RESULTS_DIR / f"full_eval_{today}.json"

    payload = {
        "generated_at": datetime.now().isoformat(),
        "pipeline": pipeline,
        "threshold": threshold,
        "use_wikidata": use_wikidata,
        "benchmark": {
            "metrics": benchmark.get("metrics", {}),
            "articles": benchmark.get("rows", []),
        },
        "liar": liar,
        "fakenewsnet": fnn,
        "pipeline_comparison": {
            k: v for k, v in comparison.items() if k != "rows"
        },
        "pipeline_comparison_rows": comparison.get("rows", []),
        "boxplot": str(boxplot_path) if boxplot_path else None,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

    return out_path


# section: main

def main() -> None:
    parser = argparse.ArgumentParser(description="Full TCS Evaluation Suite")
    parser.add_argument("--benchmark-only", action="store_true",
                        help="Run only the manual benchmark (skip LIAR and FakeNewsNet)")
    parser.add_argument("--no-wikidata", action="store_true",
                        help="Skip Wikidata verification (faster offline runs)")
    parser.add_argument("--threshold", type=float, default=FAKE_THRESHOLD,
                        help=f"TCS threshold below which an article is predicted FAKE (default: {FAKE_THRESHOLD})")
    parser.add_argument("--pipeline", choices=["spacy", "llm"], default="spacy",
                        help="Extractor pipeline to use (default: spacy)")
    parser.add_argument("--model", type=str, default=None,
                        help="Explicit spaCy model name or LLM model name")
    args = parser.parse_args()

    use_wikidata = not args.no_wikidata

    print(f"\n{'='*70}")
    print("  TCS FULL EVALUATION")
    print(f"{'='*70}")
    print(f"  Pipeline  : {args.pipeline}")
    print(f"  Threshold : {args.threshold}")
    print(f"  Wikidata  : {use_wikidata}")
    print(f"  Mode      : {'benchmark-only' if args.benchmark_only else 'full'}")
    print(f"{'='*70}")

    orch = _build_orchestrator(args.pipeline, use_wikidata, args.model)

    benchmark_result = run_benchmark(orch, args.threshold, args.pipeline)

    liar_result: dict = {}
    fnn_result: dict = {}
    comparison_result: dict = {}
    boxplot_path: Optional[Path] = None

    if not args.benchmark_only:
        liar_result = run_liar(orch, args.threshold, max_articles=50)
        fnn_result  = run_fakenewsnet(orch, args.threshold, max_articles=25)
        boxplot_path = generate_boxplot(
            benchmark_result.get("rows", []),
            liar_result.get("per_label", {}),
            fnn_result,
            args.threshold,
        )
        comparison_result = run_pipeline_comparison(
            threshold=args.threshold,
            use_wikidata=use_wikidata,
            max_articles=20,
        )
    else:
        boxplot_path = generate_boxplot(
            benchmark_result.get("rows", []),
            {},
            {},
            args.threshold,
        )

    out_path = save_full_results(
        benchmark=benchmark_result,
        liar=liar_result,
        fnn=fnn_result,
        comparison=comparison_result,
        boxplot_path=boxplot_path,
        pipeline=args.pipeline,
        threshold=args.threshold,
        use_wikidata=use_wikidata,
    )

    print("\n" + "=" * 70)
    print("  EVALUATION COMPLETE")
    print(f"  Results : {out_path}")
    if boxplot_path:
        print(f"  Boxplot : {boxplot_path}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()

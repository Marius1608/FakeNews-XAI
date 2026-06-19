"""Threshold sweep peste scorurile TCS deja calculate intr-un benchmark run.

Reclasifica articolele la praguri 0.50 -> 0.90 (pas 0.05) folosind scorurile TCS
existente, fara a re-rula pipeline-ul. Daca nu exista niciun fisier de rezultate,
ruleaza benchmark-ul o singura data pentru a genera scorurile.

Rulare: python evaluation/run_threshold_sweep.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional

# Adauga project root in sys.path (necesar cand scriptul e rulat direct)
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
BENCHMARK_FILE = EVAL_DIR / "benchmark_articles.json"

THRESHOLDS = [round(0.50 + 0.05 * i, 2) for i in range(9)]  # 0.50 .. 0.90
RECALL_TARGET = 0.35

_RESULTS_RE = re.compile(r"^results_(\d{4}-\d{2}-\d{2})\.json$")


# // section load

def find_latest_results() -> Optional[Path]:
    """Returneaza cel mai recent fisier results_YYYY-MM-DD.json dupa data din nume."""
    candidates: list[tuple[str, Path]] = []
    for p in RESULTS_DIR.glob("results_*.json"):
        m = _RESULTS_RE.match(p.name)
        if m:
            candidates.append((m.group(1), p))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[-1][1]


def load_article_rows() -> tuple[list[dict], str]:
    """Incarca articolele cu scoruri TCS deja calculate.

    Cauta intai cel mai recent results_*.json; daca nu exista, ruleaza benchmark-ul.
    Returneaza (rows, source_label).
    """
    latest = find_latest_results()
    if latest is not None:
        with open(latest, encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("articles", [])
        print(f"Scoruri TCS incarcate din: {latest.name} ({len(rows)} articole)")
        return rows, latest.name

    print("Niciun fisier de rezultate gasit — rulez benchmark-ul o singura data...")
    from evaluation.run_benchmark import load_benchmark, run_benchmark

    articles = load_benchmark(BENCHMARK_FILE)
    rows = run_benchmark(articles)
    return rows, "freshly-run benchmark"


# // section metrics

def classify(rows: list[dict], threshold: float) -> dict:
    """Reclasifica fiecare articol la pragul dat si calculeaza metricile.

    Regula identica cu run_benchmark: predicted_fake = (n_claims > 0 AND tcs < threshold).
    """
    tp = tn = fp = fn = 0
    for r in rows:
        expected_fake = bool(r.get("expected_fake", False))
        n_claims = r.get("n_claims", 0)
        tcs = r.get("tcs", 0.0)
        predicted_fake = n_claims > 0 and tcs < threshold

        if expected_fake and predicted_fake:
            tp += 1
        elif not expected_fake and not predicted_fake:
            tn += 1
        elif not expected_fake and predicted_fake:
            fp += 1
        else:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total > 0 else 0.0

    return {
        "threshold": threshold,
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
    }


# // section print

def print_table(sweep: list[dict]) -> None:
    """Afiseaza tabelul de metrici sortat dupa threshold."""
    print(f"\n{'='*78}")
    print("  THRESHOLD SWEEP  (fake = n_claims > 0 AND TCS < threshold)")
    print(f"{'='*78}")
    print(f"  {'Thr':>5}  {'P':>6}  {'R':>6}  {'F1':>6}  {'Acc':>6}  "
          f"{'TP':>3}  {'TN':>3}  {'FP':>3}  {'FN':>3}")
    print(f"  {'-'*70}")
    for m in sorted(sweep, key=lambda x: x["threshold"]):
        print(f"  {m['threshold']:>5.2f}  {m['precision']:>6.3f}  {m['recall']:>6.3f}  "
              f"{m['f1']:>6.3f}  {m['accuracy']:>6.3f}  "
              f"{m['tp']:>3}  {m['tn']:>3}  {m['fp']:>3}  {m['fn']:>3}")
    print(f"  {'-'*70}")


def find_optima(sweep: list[dict]) -> dict:
    """Identifica pragul optim pentru F1, Precision si primul cu Recall >= target."""
    f1_best = max(sweep, key=lambda m: (m["f1"], m["threshold"]))
    prec_best = max(sweep, key=lambda m: (m["precision"], m["threshold"]))
    recall_ok = [m for m in sorted(sweep, key=lambda x: x["threshold"]) if m["recall"] >= RECALL_TARGET]
    first_recall = recall_ok[0] if recall_ok else None
    return {
        "f1_optimal": f1_best,
        "precision_optimal": prec_best,
        "first_recall_ge_target": first_recall,
    }


def print_optima(optima: dict) -> None:
    print("\n  Praguri optime:")
    f1 = optima["f1_optimal"]
    print(f"    F1-optimal        : threshold={f1['threshold']:.2f}  "
          f"F1={f1['f1']:.4f}  P={f1['precision']:.4f}  R={f1['recall']:.4f}  Acc={f1['accuracy']:.4f}")
    pr = optima["precision_optimal"]
    print(f"    Precision-optimal : threshold={pr['threshold']:.2f}  "
          f"P={pr['precision']:.4f}  R={pr['recall']:.4f}  F1={pr['f1']:.4f}")
    fr = optima["first_recall_ge_target"]
    if fr:
        print(f"    First Recall>={RECALL_TARGET:.2f}   : threshold={fr['threshold']:.2f}  "
              f"R={fr['recall']:.4f}  P={fr['precision']:.4f}  F1={fr['f1']:.4f}")
    else:
        print(f"    First Recall>={RECALL_TARGET:.2f}   : niciun prag nu atinge acest recall")
    print()


# // section save

def save_results(sweep: list[dict], optima: dict, source: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / "threshold_sweep.json"
    payload = {
        "generated_at": datetime.now().isoformat(),
        "source_scores": source,
        "recall_target": RECALL_TARGET,
        "sweep": sorted(sweep, key=lambda x: x["threshold"]),
        "optima": optima,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    return output_path


# // section main

def main() -> None:
    rows, source = load_article_rows()
    if not rows:
        print("Niciun articol disponibil pentru sweep.")
        sys.exit(1)

    sweep = [classify(rows, t) for t in THRESHOLDS]
    optima = find_optima(sweep)

    print_table(sweep)
    print_optima(optima)

    output_path = save_results(sweep, optima, source)
    print(f"  Rezultate salvate: {output_path}")


if __name__ == "__main__":
    main()

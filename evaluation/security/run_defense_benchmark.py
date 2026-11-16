"""Cost of the defences on normal data (report chapter 6): does the guard hurt detection?

Runs the 100-article benchmark through the chosen pipeline with the defences off or on and
reports P / R / F1 / accuracy at theta = 0.75 (the thesis' operating point, reference
P=0.909 R=0.227 F1=0.364 for Pipeline A) plus, when the guard is active, how often the two
extractors disagree on LEGITIMATE articles (the guard's false-alarm rate).

  python evaluation/security/run_defense_benchmark.py --pipeline llm --defenses off
  python evaluation/security/run_defense_benchmark.py --pipeline llm --defenses on [--limit 20]

Add --with-explainer to also generate the LLM narrative and count how many narratives the
explanation check rejects (slow).
"""

from __future__ import annotations

import argparse
from datetime import datetime

from common import (
    RESULTS_DIR, THETA, append_jsonl, apply_defenses, load_benchmark, logger, make_orchestrator,
    mean, pct, seed_everything, setup_logging, summarize_result, to_article,
)


def prf(rows: list[dict]) -> dict:
    tp = sum(1 for r in rows if r["expected_fake"] and r["predicted_fake"])
    fp = sum(1 for r in rows if not r["expected_fake"] and r["predicted_fake"])
    fn = sum(1 for r in rows if r["expected_fake"] and not r["predicted_fake"])
    tn = sum(1 for r in rows if not r["expected_fake"] and not r["predicted_fake"])
    p = tp / (tp + fp) if tp + fp else 0.0
    r_ = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r_ / (p + r_) if p + r_ else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(p, 3),
            "recall": round(r_, 3), "f1": round(f1, 3),
            "accuracy": round((tp + tn) / len(rows), 3) if rows else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", default="llm", choices=["llm", "spacy"])
    ap.add_argument("--defenses", choices=["off", "on", "strict", "complete", "api", "full", "guard", "hardening", "tiers"], default="off")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--with-explainer", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    setup_logging(args.verbose)
    defenses = apply_defenses(args.defenses)
    data = load_benchmark()[: args.limit] if args.limit else load_benchmark()
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = RESULTS_DIR / f"benchmark_{args.pipeline}_def-{args.defenses}_{ts}.jsonl"
    orch = make_orchestrator(args.pipeline, with_explainer=args.with_explainer)
    logger.info(f"{len(data)} articles | pipeline={args.pipeline} | defences={defenses} -> {out}")

    rows = []
    for i, e in enumerate(data):
        seed_everything(args.seed)
        try:
            result = orch.run(to_article(e))
        except Exception as ex:  # keep going, count the error
            logger.error(f"[{i}] pipeline error: {ex}")
            continue
        s = summarize_result(result)
        s.update({"phase": "article", "bench_idx": e["bench_idx"], "expected_fake": e["expected_fake"],
                  "explanation_present": bool(result.explanation_text)})
        rows.append(s)
        append_jsonl(out, s)
        logger.info(f"[{i + 1}/{len(data)}] TCS={s['tcs']} facts={s['n_facts']} "
                    f"pred_fake={s['predicted_fake']} expected_fake={e['expected_fake']}")

    metrics = prf(rows)
    true_rows = [r for r in rows if not r["expected_fake"]]
    guard_rows = [r for r in rows if r.get("guard")]
    summary = {
        "phase": "summary", "pipeline": args.pipeline, "defenses": defenses, "theta": THETA,
        "n": len(rows), "metrics": metrics,
        "mean_tcs_true": mean([r["tcs"] for r in true_rows]),
        "mean_tcs_fake": mean([r["tcs"] for r in rows if r["expected_fake"]]),
    }
    if guard_rows:
        legit_guard = [r for r in guard_rows if not r["expected_fake"]]
        summary["guard"] = {
            "articles_with_disagreement_signal": sum(1 for r in guard_rows if r["guard"]["attack_suspected"]),
            "false_alarm_rate_on_true_articles": pct(
                sum(1 for r in legit_guard if r["guard"]["attack_suspected"]), len(legit_guard)),
            "mean_quarantined": mean([r["guard"]["n_quarantined"] for r in guard_rows]),
            "mean_recovered": mean([r["guard"]["n_recovered"] for r in guard_rows]),
        }
    if args.with_explainer:
        summary["explanations_present"] = f"{sum(r['explanation_present'] for r in rows)}/{len(rows)}"
    append_jsonl(out, summary)

    print(f"\n=== Benchmark | pipeline={args.pipeline} | defences={args.defenses} | n={len(rows)} ===")
    print(f"  P={metrics['precision']}  R={metrics['recall']}  F1={metrics['f1']}  "
          f"Acc={metrics['accuracy']}  (TP={metrics['tp']} FP={metrics['fp']} FN={metrics['fn']} TN={metrics['tn']})")
    print(f"  mean TCS: true={summary['mean_tcs_true']}  fake={summary['mean_tcs_fake']}")
    if "guard" in summary:
        print(f"  guard: {summary['guard']}")
    if args.with_explainer:
        print(f"  explanations kept: {summary['explanations_present']}")
    print(f"\nRaw rows: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

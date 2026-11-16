"""Experiment 4.1 — robustness of Pipeline B to indirect prompt injection (OWASP LLM01).

For each FAKE benchmark article and each payload case (from payloads.json), builds
an attacked variant and runs it through the real pipeline. Measures the attack
success rate = fraction of articles whose verdict flips FAKE -> TRUE under the payload,
compared to the clean baseline. Also reports fact-count change and TCS change.

The payloads are inert test strings authored by the operator in payloads.json; this
script only places them and records the detector's output. Run only against your own
instance.

Usage:
  python evaluation/security/run_injection.py --pipeline llm [--limit N] [--seed 42] [-v]
  python evaluation/security/run_injection.py --payloads evaluation/security/payloads.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from common import (
    RESULTS_DIR, append_jsonl, apply_defenses, load_benchmark, logger, make_orchestrator,
    mean, pct, seed_everything, setup_logging, summarize_result, to_article,
)

HERE = Path(__file__).resolve().parent


def load_payloads(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(
            f"Payload file not found: {path}\n"
            f"Copy payloads.example.json to payloads.json and add your own cases."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def incriminating_sentence(entry: dict) -> str:
    """Best-effort: the sentence carrying the injected error. Falls back to first dated sentence."""
    import re
    sents = re.split(r"(?<=[.!?])\s+", entry["text"].strip())
    year = re.compile(r"\b(19|20)\d{2}\b")
    for s in sents:
        if year.search(s):
            return s
    return sents[0] if sents else entry["text"]


def build_attacked(entry: dict, case: dict) -> dict:
    """Return a shallow copy of entry with the payload placed per case['channel']."""
    text = entry["text"].strip()
    title = entry.get("title", "")
    claim = incriminating_sentence(entry)
    tmpl = case["template"]
    ch = case["channel"]

    if ch == "title":
        title = tmpl.replace("{claim}", claim)
    elif ch == "inline":
        text = text.replace(claim, tmpl.replace("{claim}", claim), 1)
    elif ch == "prefix":
        text = tmpl.replace("{claim}", claim) + " " + text
    elif ch == "suffix":
        text = text + " " + tmpl.replace("{claim}", claim)
    else:
        raise ValueError(f"unknown channel: {ch}")

    out = dict(entry)
    out["text"] = text
    out["title"] = title
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", default="llm", choices=["llm", "spacy"],
                    help="Pipeline B (llm) is the injection target; spacy is a control")
    ap.add_argument("--payloads", type=Path, default=HERE / "payloads.json")
    ap.add_argument("--limit", type=int, default=None, help="cap on number of FAKE articles")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--defenses", choices=["off", "on", "strict", "complete", "api", "full", "guard", "hardening", "tiers"], default="off",
                    help="off = original system (baseline); on = guard + trust tiers (recommended), full = + prompt hardening")
    ap.add_argument("--cases", default=None, help="comma-separated payload ids to run (default: all)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    setup_logging(args.verbose)
    defenses = apply_defenses(args.defenses)
    logger.info(f"Defences: {defenses}")
    cases = load_payloads(args.payloads)
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    fakes = [e for e in load_benchmark() if e.get("expected_fake")]
    if args.limit:
        fakes = fakes[: args.limit]

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_path = RESULTS_DIR / f"injection_{args.pipeline}_def-{args.defenses}_{ts}.jsonl"
    logger.info(f"{len(fakes)} FAKE articles x {len(cases)} payload cases -> {out_path}")

    orch = make_orchestrator(args.pipeline)

    # 1) clean baseline per article
    baseline: dict[int, dict] = {}
    for e in fakes:
        seed_everything(args.seed)
        r = summarize_result(orch.run(to_article(e)))
        baseline[e["bench_idx"]] = r
        append_jsonl(out_path, {"phase": "baseline", "bench_idx": e["bench_idx"],
                                "title": e.get("title", ""), **r})
        logger.info(f"baseline [{e['bench_idx']}] TCS={r['tcs']} facts={r['n_facts']} "
                    f"pred_fake={r['predicted_fake']}")

    base_detected = [i for i, r in baseline.items() if r["predicted_fake"]]
    logger.info(f"Baseline: {len(base_detected)}/{len(fakes)} FAKE correctly detected")

    # 2) per payload case
    per_case: dict[str, int] = {}
    per_case_silent: dict[str, int] = {}   # flipped AND not flagged by the guard (attack_suspected)
    for case in cases:
        flips = 0
        silent = 0
        considered = 0
        for e in fakes:
            idx = e["bench_idx"]
            if not baseline[idx]["predicted_fake"]:
                continue  # only articles the detector caught can be made to flip
            considered += 1
            seed_everything(args.seed)
            r = summarize_result(orch.run(to_article(build_attacked(e, case))))
            flipped = not r["predicted_fake"]
            flips += int(flipped)
            suspected = bool((r.get("guard") or {}).get("attack_suspected"))
            silent += int(flipped and not suspected)
            append_jsonl(out_path, {
                "phase": "attack", "case_id": case["id"], "family": case.get("family", ""),
                "channel": case["channel"], "bench_idx": idx, "title": e.get("title", ""),
                "base_tcs": baseline[idx]["tcs"], "base_facts": baseline[idx]["n_facts"],
                "attacked_flipped_to_true": flipped, **r,
            })
        per_case[case["id"]] = flips
        per_case_silent[case["id"]] = silent
        logger.info(f"[{case['id']:>22}] success {flips}/{considered} = {pct(flips, considered)}")

    # 3) summary
    summary = {
        "phase": "summary", "pipeline": args.pipeline, "seed": args.seed, "defenses": defenses,
        "n_fake": len(fakes), "n_detected_baseline": len(base_detected),
        "per_case_flips": per_case, "per_case_silent_flips": per_case_silent,
        "payload_file": str(args.payloads),
    }
    append_jsonl(out_path, summary)
    print("\n=== 4.1 Prompt-injection summary ===")
    print(f"Pipeline: {args.pipeline} | defences: {args.defenses} | "
          f"baseline detected: {len(base_detected)}/{len(fakes)}")
    for cid, f in per_case.items():
        print(f"  {cid:>22}: {f}/{len(base_detected)} flipped FAKE->TRUE ({pct(f, len(base_detected))})"
              f"  | silent (not flagged by guard): {per_case_silent[cid]}")
    print(f"\nRaw rows: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

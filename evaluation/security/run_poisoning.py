"""Experiment 4.2 / 6 — knowledge-graph poisoning through persisted articles (OWASP LLM04).

Threat model: the attacker can call /analyze with persist=true (no authentication, V-01) and
store articles containing false facts about a target entity. A later LEGITIMATE article about
that entity then collects cross-article conflicts (C3c) and its TCS drops below theta, so
true reporting is flagged FAKE.

Per scenario the script measures:
  baseline         verdict of the legitimate article on a clean graph
  after_poison     verdict after the poison articles are persisted   -> attack_succeeded
  after_hitl_fake  verdict after the poison is marked FAKE by a human -> hitl_recovered
                   (V-05: without the defence the human verdict is never read)

and, if the scenario file has a `utility` block, a UTILITY check: a trusted article is
persisted and confirmed by a human, then a genuinely contradicting article is analysed.
The defence must keep detecting that conflict (`conflict_detected`), otherwise it would
only trade poisoning resistance for lost detection.

Run it twice and compare:  --defenses off   (original system)   /   --defenses on

Everything written to Neo4j is deleted at the end (even on error). Run only against your own
instance and keep it private while poison data is in the graph.

Usage:
  python evaluation/security/run_poisoning.py --target "Obama" --defenses off -v
  python evaluation/security/run_poisoning.py --scenarios evaluation/security/poison.json --defenses on
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from common import (
    RESULTS_DIR, append_jsonl, apply_defenses, load_benchmark, logger, make_orchestrator,
    seed_everything, setup_logging, summarize_result, to_article,
)

from backend.config import NEO4J_ENABLED
from backend.pipeline.graph.factory import create_persistent_store

HERE = Path(__file__).resolve().parent


# scenarios ---------------------------------------------------------------------------

def auto_scenario(target: str) -> dict:
    """Year-shifted copies of a benchmark TRUE article about `target` (the same controlled
    mutation the thesis uses to build its own FAKE set)."""
    t = target.lower()
    legit = [e for e in load_benchmark()
             if not e.get("expected_fake") and t in (e["text"] + " " + e.get("title", "")).lower()]
    if not legit:
        raise SystemExit(f"No benchmark TRUE article mentions '{target}'")
    base = legit[0]
    shifted = re.sub(r"\b(19|20)\d{2}\b", lambda m: str(int(m.group(0)) + 6), base["text"])
    return {
        "name": f"auto-{target}", "target": target,
        "legit": {"title": base.get("title", ""), "text": base["text"],
                  "publication_date": base.get("publication_date")},
        "poison": [{"title": f"{target} timeline (variant {k + 1})", "text": shifted,
                    "publication_date": base.get("publication_date")} for k in range(3)],
    }


def load_scenarios(path: Path | None, target: str | None) -> tuple[list[dict], dict | None]:
    if path:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        scenarios = data["scenarios"]
        for sc in scenarios:  # legacy form: legit_bench_idx
            if "legit" not in sc and "legit_bench_idx" in sc:
                e = next(x for x in load_benchmark() if x["bench_idx"] == sc["legit_bench_idx"])
                sc["legit"] = {"title": e.get("title", ""), "text": e["text"],
                               "publication_date": e.get("publication_date")}
        return scenarios, data.get("utility")
    if not target:
        raise SystemExit("Provide --target or --scenarios")
    return [auto_scenario(target)], None


def _article(d: dict):
    return to_article({"title": d.get("title", ""), "text": d["text"],
                       "publication_date": d.get("publication_date"), "source": "security-eval"})


def _cleanup(store, ids: list[str], label: str) -> None:
    removed = 0
    for aid in ids:
        try:
            removed += int(store.delete_article(aid))
        except Exception as e:  # keep cleaning the rest
            logger.error(f"cleanup failed for {aid}: {e}")
    logger.info(f"[{label}] cleanup: removed {removed}/{len(ids)} article(s)")


# poisoning scenario ----------------------------------------------------------------------

def run_scenario(sc: dict, out_path: Path, seed: int, defenses: dict) -> dict:
    store = create_persistent_store()
    if store is None:
        raise SystemExit("Neo4j store unavailable — set NEO4J_ENABLED=true and check .env")
    reader = make_orchestrator("spacy", store=store)   # cross-article on, no persist
    writer = make_orchestrator("spacy", store=store)   # persists the poison
    legit = _article(sc["legit"])
    ids: list[str] = []
    try:
        seed_everything(seed)
        base = summarize_result(reader.run(legit))
        logger.info(f"[{sc['name']}] baseline: TCS={base['tcs']} pred_fake={base['predicted_fake']}")

        stored_tiers = []
        for p in sc["poison"]:
            seed_everything(seed)
            r = writer.run(_article(p), persist=True, enable_cross_article=False)
            if getattr(r, "article_id", None):
                ids.append(r.article_id)
                stored_tiers.append({"tcs": round(r.score, 3), "flagged_fake": r.score < 0.75})
        logger.info(f"[{sc['name']}] persisted {len(ids)} poison article(s): {stored_tiers}")

        seed_everything(seed)
        after = summarize_result(reader.run(legit))
        logger.info(f"[{sc['name']}] after poison: TCS={after['tcs']} cross={after['n_cross_article']} "
                    f"pred_fake={after['predicted_fake']}")

        for aid in ids:
            store.save_human_verdict(article_id=aid, verdict="fake", confidence=1.0,
                                     notes="poison", annotator="eval")
        seed_everything(seed)
        after_hitl = summarize_result(reader.run(legit))
        logger.info(f"[{sc['name']}] after HITL-fake: TCS={after_hitl['tcs']} "
                    f"cross={after_hitl['n_cross_article']} pred_fake={after_hitl['predicted_fake']}")

        row = {
            "phase": "scenario", "name": sc["name"], "defenses": defenses, "n_poison": len(ids),
            "poison_flagged_fake_at_write": stored_tiers,
            "baseline": base, "after_poison": after, "after_hitl_fake": after_hitl,
            "attack_succeeded": (not base["predicted_fake"]) and after["predicted_fake"],
            "hitl_recovered": after["predicted_fake"] and (not after_hitl["predicted_fake"]),
        }
        append_jsonl(out_path, row)
        return row
    finally:
        _cleanup(store, ids, sc["name"])
        store.close()


# utility check ----------------------------------------------------------------------------

def run_utility(u: dict, out_path: Path, seed: int, defenses: dict) -> dict:
    """A trusted, human-confirmed article must still expose a genuinely contradicting one."""
    store = create_persistent_store()
    if store is None:
        raise SystemExit("Neo4j store unavailable")
    reader = make_orchestrator("spacy", store=store)
    writer = make_orchestrator("spacy", store=store)
    ids: list[str] = []
    try:
        seed_everything(seed)
        r = writer.run(_article(u["trusted"]), persist=True, enable_cross_article=False)
        if r.article_id:
            ids.append(r.article_id)
            store.save_human_verdict(article_id=r.article_id, verdict="true", confidence=1.0,
                                     notes="trusted reference", annotator="eval")
        seed_everything(seed)
        res = summarize_result(reader.run(_article(u["conflicting"])))
        row = {"phase": "utility", "defenses": defenses, "result": res,
               # a genuine conflict must keep MEDIUM+ severity (a single one gives TCS ~0.8, above theta)
               "conflict_detected": any(s in ("medium", "high", "critical")
                                        for s in res["cross_severities"])}
        append_jsonl(out_path, row)
        logger.info(f"[utility] cross={res['cross_severities']} TCS={res['tcs']} "
                    f"conflict_detected={row['conflict_detected']}")
        return row
    finally:
        _cleanup(store, ids, "utility")
        store.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=None, help="entity present in a benchmark TRUE article")
    ap.add_argument("--scenarios", type=Path, default=None, help="scenario file (see poison.example.json)")
    ap.add_argument("--defenses", choices=["off", "on", "strict", "complete", "api", "full", "guard", "hardening", "tiers"], default="off",
                    help="off = original system (baseline); on = guard + trust tiers (recommended), full = + prompt hardening")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    setup_logging(args.verbose)
    defenses = apply_defenses(args.defenses)
    logger.info(f"Defences: {defenses}")
    if not NEO4J_ENABLED:
        raise SystemExit("NEO4J_ENABLED is false — enable Neo4j in .env first")

    scenarios, utility = load_scenarios(args.scenarios, args.target)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_path = RESULTS_DIR / f"poisoning_def-{args.defenses}_{ts}.jsonl"

    rows = [run_scenario(sc, out_path, args.seed, defenses) for sc in scenarios]
    util = run_utility(utility, out_path, args.seed, defenses) if utility else None

    verdict = lambda x: "FAKE" if x["predicted_fake"] else "TRUE"
    print(f"\n=== Knowledge-graph poisoning | defences: {args.defenses} ===")
    for r in rows:
        print(f"  {r['name']:>22} | legit: {verdict(r['baseline'])} (TCS {r['baseline']['tcs']}) -> "
              f"after poison {verdict(r['after_poison'])} (TCS {r['after_poison']['tcs']}, "
              f"{r['after_poison']['n_cross_article']} cross) -> after HITL-fake "
              f"{verdict(r['after_hitl_fake'])}")
        print(f"  {'':>22} | attack_succeeded={r['attack_succeeded']}  hitl_recovered={r['hitl_recovered']}")
    if util:
        print(f"  utility: genuine conflict detected = {util['conflict_detected']} "
              f"(cross severities {util['result']['cross_severities']}, TCS {util['result']['tcs']})")
    print(f"\nRaw rows: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

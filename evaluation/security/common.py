"""Shared helpers for the security experiments (RC report, chapters 4 and 6).

All experiments run the real pipeline (PipelineOrchestrator) locally.
The LLM explainer is disabled by default: it does not influence the verdict
(TCS is computed from structured evidence) and it is the slowest step.
"""

from __future__ import annotations

import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import defense_config  # noqa: E402
from backend.pipeline.graph.models import Article  # noqa: E402
from backend.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402

BENCHMARK_FILE = PROJECT_ROOT / "evaluation" / "benchmark_articles.json"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
THETA = 0.75  # operating threshold from the thesis

logger = logging.getLogger("security")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(name)-28s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.setLevel(logging.INFO)


def load_benchmark() -> list[dict]:
    with open(BENCHMARK_FILE, encoding="utf-8") as f:
        data = json.load(f)
    for i, entry in enumerate(data):
        entry["bench_idx"] = i
    return data


def to_article(entry: dict) -> Article:
    pub = None
    if entry.get("publication_date"):
        try:
            pub = datetime.strptime(entry["publication_date"], "%Y-%m-%d")
        except ValueError:
            pass
    return Article(
        text=entry["text"],
        title=entry.get("title", ""),
        publication_date=pub,
        source=entry.get("source", "security-eval"),
    )


class _NoExplainer:
    def is_available(self) -> bool:
        return False


def make_orchestrator(pipeline: str, store=None, use_wikidata: bool = True,
                      with_explainer: bool = False) -> PipelineOrchestrator:
    """pipeline: 'spacy' (Pipeline A) or 'llm' (Pipeline B)."""
    orch = PipelineOrchestrator(
        use_wikidata=use_wikidata,
        extractor_name=pipeline,
        persistent_store=store,
        enable_cross_article=store is not None,
        persist=False,
        use_rss=False,
    )
    if not with_explainer:
        orch._llm_explainer = _NoExplainer()  # see PipelineOrchestrator.llm_explainer
    return orch


DEFENSE_MODES = ["off", "on", "strict", "complete", "api", "full", "guard", "hardening", "tiers"]


def apply_defenses(mode: str) -> dict:
    """Explicit flags (ignores .env).
    off  = original system;  on = guard + trust tiers;  strict = on + title isolation;
    full = on + prompt hardening;  guard / hardening / tiers = one component only (ablation)."""
    flags = defense_config.all_off()
    if mode == "on":
        flags["cross_pipeline"] = True
        flags["trust_tiers"] = True
    elif mode == "strict":   # on + title isolation
        flags["cross_pipeline"] = True
        flags["trust_tiers"] = True
        flags["title_isolation"] = True
    elif mode == "api":      # API hardening only (V-01/07/08/10/11)
        flags["api_hardening"] = True
    elif mode == "complete": # every measured-useful defence: on + title isolation + API hardening
        flags.update(cross_pipeline=True, trust_tiers=True, title_isolation=True, api_hardening=True)
    elif mode == "full":     # on + prompt hardening (title isolation not included: measured earlier)
        flags["cross_pipeline"] = True
        flags["prompt_hardening"] = True
        flags["trust_tiers"] = True
    elif mode == "guard":
        flags["cross_pipeline"] = True
    elif mode == "hardening":
        flags["prompt_hardening"] = True
    elif mode == "tiers":
        flags["trust_tiers"] = True
    elif mode != "off":
        raise ValueError(f"unknown defence mode: {mode}")
    defense_config.set_flags(**flags)
    return defense_config.snapshot()


def seed_everything(seed: int) -> None:
    """Pipeline B samples (temperature 0.1); seed each run for reproducibility."""
    random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        pass


def predict_fake(result) -> bool:
    """Classification rule from the thesis: FAKE iff >=1 temporal fact and TCS < theta."""
    return result.n_temporal_claims > 0 and result.score < THETA


def summarize_result(result) -> dict:
    incs = result.inconsistencies or []
    return {
        "tcs": round(result.score, 4),
        "n_facts": result.n_temporal_claims,
        "n_inconsistencies": len(incs),
        "n_high": sum(1 for i in incs if i.severity.value.upper() == "HIGH"),
        "n_cross_article": len(getattr(result, "cross_article_inconsistencies", None) or []),
        "cross_severities": sorted(i.severity.value for i in
                                   (getattr(result, "cross_article_inconsistencies", None) or [])),
        "predicted_fake": predict_fake(result),
        "article_id": getattr(result, "article_id", None),
        "guard": getattr(result, "guard", None),
    }


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def mean(xs: list[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 4) if xs else None

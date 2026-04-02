"""Evaluare — comparatie batch Pipeline A vs Pipeline B pe un set de articole."""

from __future__ import annotations

import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import DATASETS_DIR
from backend.input.dataset import load_liar, load_fakenewsnet
from backend.pipeline.graph.models import Article, TCSResult
from backend.pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


# Comparatie batch
def compare_batch(
    articles: list[Article],
    use_wikidata: bool = True,
) -> list[dict]:
    """
    Ruleaza Pipeline A (spaCy) si Pipeline B (LLM) pe fiecare articol.
    Returneaza lista de dictionare cu rezultatele comparate.
    """
    orch_a = PipelineOrchestrator(use_wikidata=use_wikidata, extractor_name="spacy")
    orch_b = PipelineOrchestrator(use_wikidata=use_wikidata, extractor_name="llm")

    rows = []
    for i, article in enumerate(articles):
        logger.info(f"[{i + 1}/{len(articles)}] '{article.title[:50]}'")

        result_a = _safe_run(orch_a, article)
        result_b = _safe_run(orch_b, article)

        delta = result_a.score - result_b.score
        rows.append({
            "idx": i + 1,
            "title": article.title[:80],
            "label": article.label or "unknown",
            "dataset": article.dataset or "",
            # Pipeline A
            "tcs_a": round(result_a.score, 4),
            "claims_a": result_a.n_temporal_claims,
            "inc_a": result_a.n_inconsistencies,
            "label_a": result_a.label,
            "time_a_ms": round(result_a.processing_time_ms, 1),
            # Pipeline B
            "tcs_b": round(result_b.score, 4),
            "claims_b": result_b.n_temporal_claims,
            "inc_b": result_b.n_inconsistencies,
            "label_b": result_b.label,
            "time_b_ms": round(result_b.processing_time_ms, 1),
            # Comparatie
            "delta": round(delta, 4),
            "agree": result_a.label == result_b.label,
        })

    return rows


def _safe_run(orch: PipelineOrchestrator, article: Article) -> TCSResult:
    """Ruleaza pipeline cu protectie la exceptii."""
    try:
        return orch.run(article)
    except Exception as e:
        logger.error(f"Eroare {orch.extractor_name}: {e}")
        return TCSResult(
            score=0.0, n_inconsistencies=0, n_temporal_claims=0,
            coherence_factor=1.0, pipeline_variant=orch.extractor_name,
        )



# Statistici sumar
def summarize(rows: list[dict]) -> dict:
    """Statistici agregate din rezultatele comparatiei."""
    n = len(rows)
    if n == 0:
        return {}

    avg_a = sum(r["tcs_a"] for r in rows) / n
    avg_b = sum(r["tcs_b"] for r in rows) / n
    agreement_rate = sum(1 for r in rows if r["agree"]) / n

    avg_time_a = sum(r["time_a_ms"] for r in rows) / n
    avg_time_b = sum(r["time_b_ms"] for r in rows) / n

    # Corelare cu ground truth
    true_articles = [r for r in rows if r["label"] in ("true", "mostly-true", "half-true")]
    fake_articles = [r for r in rows if r["label"] in ("false", "pants-fire", "barely-true")]

    return {
        "total_articles": n,
        "avg_tcs_spacy": round(avg_a, 4),
        "avg_tcs_llm": round(avg_b, 4),
        "agreement_rate": round(agreement_rate, 4),
        "avg_time_spacy_ms": round(avg_time_a, 1),
        "avg_time_llm_ms": round(avg_time_b, 1),
        "true_articles": len(true_articles),
        "fake_articles": len(fake_articles),
        "avg_tcs_true_spacy": round(sum(r["tcs_a"] for r in true_articles) / len(true_articles), 4) if true_articles else None,
        "avg_tcs_fake_spacy": round(sum(r["tcs_a"] for r in fake_articles) / len(fake_articles), 4) if fake_articles else None,
        "avg_tcs_true_llm": round(sum(r["tcs_b"] for r in true_articles) / len(true_articles), 4) if true_articles else None,
        "avg_tcs_fake_llm": round(sum(r["tcs_b"] for r in fake_articles) / len(fake_articles), 4) if fake_articles else None,
    }


# Export CSV
def export_csv(rows: list[dict], output_path: Path) -> None:
    """Exporta rezultatele comparatiei intr-un CSV."""
    if not rows:
        logger.warning("Nimic de exportat.")
        return

    fieldnames = list(rows[0].keys())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Rezultate exportate: {output_path} ({len(rows)} randuri)")


# CLI entry point
def main() -> None:
    """Ruleaza comparatie pe articole LIAR (default 20 articole)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    logger.info(f"Comparatie Pipeline A vs B pe {n} articole LIAR...")

    articles = load_liar(max_articles=n)
    if not articles:
        logger.error("Nu s-au gasit articole LIAR. Verifica data/datasets/liar/test.tsv")
        return

    rows = compare_batch(articles, use_wikidata=True)

    # Afiseaza tabel sumar
    print(f"\n{'='*100}")
    print(f"{'#':>3} {'Title':<40} {'Label':<12} {'TCS-A':>6} {'TCS-B':>6} {'Δ':>7} {'Agree':>6}")
    print(f"{'-'*100}")
    for r in rows:
        print(
            f"{r['idx']:>3} {r['title'][:40]:<40} {r['label']:<12} "
            f"{r['tcs_a']:>6.3f} {r['tcs_b']:>6.3f} {r['delta']:>+7.3f} "
            f"{'✓' if r['agree'] else '✗':>6}"
        )
    print(f"{'='*100}")

    stats = summarize(rows)
    print(f"\nStatistici:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Export CSV
    output_path = Path("evaluation/results/compare_a_vs_b.csv")
    export_csv(rows, output_path)


if __name__ == "__main__":
    main()
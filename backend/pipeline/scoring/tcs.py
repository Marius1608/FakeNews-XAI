"""C4 — TCS Score Computation: TCS = 1 - (inconsist_detected / claims_temporal) × score_coherence."""

from __future__ import annotations

import logging
import time
from typing import Optional

from backend.pipeline.graph.models import Inconsistency, Severity, TemporalFact, TCSResult
from backend.pipeline.graph.store import TemporalKnowledgeGraph
from backend.pipeline.verification.internal import InternalVerificationResult
from backend.pipeline.verification.external import ExternalVerificationResult

logger = logging.getLogger(__name__)

MIN_TEMPORAL_CLAIMS = 1

SEVERITY_WEIGHTS = {
    Severity.LOW: 1.0, Severity.MEDIUM: 2.0, Severity.HIGH: 3.0, Severity.CRITICAL: 4.0,
}


class TCSCalculator:
    """Calculeaza scorul TCS din rezultatele C2 (TKG) + C3 (verificari)."""

    def compute(
        self, tkg: TemporalKnowledgeGraph,
        internal: InternalVerificationResult, external: ExternalVerificationResult,
        pipeline_variant: str = "spacy", start_time_ms: Optional[float] = None,
    ) -> TCSResult:
        """Calcul TCS standard (numarare simpla inconsistente)."""
        all_inconsistencies = internal.inconsistencies + external.inconsistencies
        claims_temporal = tkg.fact_count
        n_inconsistencies = len(all_inconsistencies)
        score_coherence = internal.score_coherence

        tcs_raw = _compute_tcs_raw(n_inconsistencies, claims_temporal, score_coherence)
        tcs_score = max(0.0, min(1.0, tcs_raw))

        timeline = _build_timeline(tkg.get_all_facts(), all_inconsistencies)

        processing_time = 0.0
        if start_time_ms is not None:
            processing_time = (time.monotonic() * 1000) - start_time_ms

        result = TCSResult(
            score=tcs_score, n_inconsistencies=n_inconsistencies,
            n_temporal_claims=claims_temporal, coherence_factor=score_coherence,
            inconsistencies=all_inconsistencies, facts=tkg.get_all_facts(),
            timeline=timeline, pipeline_variant=pipeline_variant,
            processing_time_ms=processing_time,
        )
        logger.info(f"TCS: {tcs_score:.3f} | {n_inconsistencies}/{claims_temporal} inconsistente | coherence={score_coherence:.3f} | '{result.label}'")
        return result

    def compute_weighted(
        self, tkg: TemporalKnowledgeGraph,
        internal: InternalVerificationResult, external: ExternalVerificationResult,
        pipeline_variant: str = "spacy", start_time_ms: Optional[float] = None,
    ) -> TCSResult:
        """Varianta ponderata: LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4."""
        all_inconsistencies = internal.inconsistencies + external.inconsistencies
        claims_temporal = tkg.fact_count
        score_coherence = internal.score_coherence

        weighted_sum = sum(SEVERITY_WEIGHTS.get(inc.severity, 1.0) for inc in all_inconsistencies)
        max_weight = SEVERITY_WEIGHTS[Severity.CRITICAL]

        if claims_temporal == 0:
            tcs_score = 0.0
        else:
            weighted_ratio = weighted_sum / (claims_temporal * max_weight)
            tcs_score = max(0.0, min(1.0, 1.0 - (weighted_ratio * score_coherence)))

        timeline = _build_timeline(tkg.get_all_facts(), all_inconsistencies)
        processing_time = 0.0
        if start_time_ms is not None:
            processing_time = (time.monotonic() * 1000) - start_time_ms

        return TCSResult(
            score=tcs_score, n_inconsistencies=len(all_inconsistencies),
            n_temporal_claims=claims_temporal, coherence_factor=score_coherence,
            inconsistencies=all_inconsistencies, facts=tkg.get_all_facts(),
            timeline=timeline, pipeline_variant=pipeline_variant,
            processing_time_ms=processing_time,
        )


def _compute_tcs_raw(n_inconsistencies: int, claims_temporal: int, score_coherence: float) -> float:
    """
    TCS = 1 - (inconsist_detected / claims_temporal) × score_coherence
    Edge cases: claims_temporal=0 → 0.0; score_coherence=0 → 0.0.
    """
    if claims_temporal < MIN_TEMPORAL_CLAIMS:
        logger.warning(f"TCS: claims_temporal={claims_temporal} sub minim. Scor = 0.0.")
        return 0.0
    if score_coherence <= 0.0:
        logger.warning("TCS: score_coherence=0. Scor = 0.0.")
        return 0.0

    return 1.0 - (n_inconsistencies / claims_temporal) * score_coherence


def _build_timeline(facts: list[TemporalFact], inconsistencies: list[Inconsistency]) -> list[dict]:
    """Timeline sortat cronologic pentru UI (Sprint 4)."""
    inc_by_sentence: dict[int, Inconsistency] = {}
    for inc in inconsistencies:
        for idx in inc.sentence_indices:
            inc_by_sentence[idx] = inc

    events = []
    for fact in facts:
        year = _extract_year(fact)
        inc = inc_by_sentence.get(fact.source_sentence_idx)
        events.append({
            "year": year,
            "label": f"{fact.subject.text} — {fact.predicate.value} → {fact.object.text}",
            "has_inconsistency": inc is not None,
            "inconsistency_type": inc.inconsistency_type.value if inc else None,
            "inconsistency_description": inc.description if inc else None,
            "inconsistency_severity": inc.severity.value if inc else None,
            "verified_by": inc.verified_by if inc else None,
            "sentence_idx": fact.source_sentence_idx,
            "confidence": fact.extraction_confidence,
            "extractor": fact.extractor,
        })

    events.sort(key=lambda e: (e["year"] is None, e["year"] or 0))
    return events


def _extract_year(fact: TemporalFact) -> int | None:
    for field in ("time_point", "time_start", "time_end"):
        expr = getattr(fact, field)
        if expr and expr.normalized_date:
            return expr.normalized_date.year
    return None
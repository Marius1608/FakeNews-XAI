"""C4 — TCS Score Computation: TCS = 1 - (inconsist_detected / claims_temporal) × score_coherence."""

from __future__ import annotations

import logging
import time
from typing import Optional

from backend.pipeline.graph.models import Inconsistency, Severity, TemporalFact, TCSResult

logger = logging.getLogger(__name__)


class TCSCalculator:
    """Computes the TCS score from C2 (TKG) and C3 (verification) results."""

    def compute(
        self, n_claims: int, inconsistencies: list[Inconsistency],
        score_coherence: float, facts_verified: int = 0, facts_total: int = 0,
        facts: list[TemporalFact] = None, pipeline_variant: str = "spacy",
        start_time_ms: Optional[float] = None
    ) -> TCSResult:
        """
        TCS = (1 - penalty_ratio) × score_coherence × (0.85 + 0.15 × coverage_factor)

        Three components:
        - penalty_ratio: weighted_penalty / max_possible_penalty, normalized to [0, 1];
          weighted_penalty is the sum of severity weights for detected inconsistencies.
        - score_coherence: internal coherence score from C3a (structural consistency).
        - coverage_factor: facts_verified / facts_total, proportion of temporal claims
          externally confirmed (Wikidata / Reference KG); 0.5 when no facts are available.
        Returns 0.5 explicitly when there are no temporal facts (insufficient data).
        """
        facts = facts or []

        if n_claims == 0:
            return TCSResult(
                score=0.5, n_inconsistencies=0, n_temporal_claims=0,
                coherence_factor=1.0, inconsistencies=[], facts=[],
                explanation_text="insufficient_data"
            )

        # Severity weights
        SEVERITY_WEIGHTS = {
            Severity.LOW: 0.0,
            Severity.MEDIUM: 0.3,
            Severity.HIGH: 1.0,
            Severity.CRITICAL: 1.5,
        }

        # Weighted penalty
        weighted_penalty = sum(SEVERITY_WEIGHTS.get(inc.severity, 0.5) for inc in inconsistencies)
        # Worst-case: every claim has a critical inconsistency
        max_possible_penalty = n_claims * max(SEVERITY_WEIGHTS.values())

        # coverage_factor: rewards articles where external sources (Wikidata/RefKG)
        # verified a higher proportion of temporal claims. Range [0.85, 1.00].
        coverage_factor = facts_verified / facts_total if facts_total > 0 else 0.5

        # TCS formula: normalized penalty × internal coherence × coverage bonus
        penalty_ratio = min(1.0, weighted_penalty / max_possible_penalty) if max_possible_penalty > 0 else 0.0
        tcs_base = (1.0 - penalty_ratio) * score_coherence
        tcs = max(0.0, min(1.0, tcs_base * (0.85 + 0.15 * coverage_factor)))

        logger.info(f"TCS: penalty={weighted_penalty:.2f}/{max_possible_penalty:.2f}, "
                    f"coherence={score_coherence:.3f}, coverage={coverage_factor:.3f} "
                    f"({facts_verified}/{facts_total}) -> TCS={tcs:.3f}")

        timeline = _build_timeline(facts, inconsistencies)

        processing_time = 0.0
        if start_time_ms is not None:
            processing_time = (time.monotonic() * 1000) - start_time_ms

        return TCSResult(
            score=tcs, n_inconsistencies=len(inconsistencies),
            n_temporal_claims=n_claims, coherence_factor=score_coherence,
            inconsistencies=inconsistencies, facts=facts,
            timeline=timeline, pipeline_variant=pipeline_variant,
            processing_time_ms=processing_time,
            explanation_text=""
        )


def _build_timeline(facts: list[TemporalFact], inconsistencies: list[Inconsistency]) -> list[dict]:
    """Build a chronologically sorted timeline for the UI."""
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
            "label": f"{fact.subject.text} — {fact.predicate.value} -> {fact.object.text}",
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

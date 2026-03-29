"""C2 — TKG Construction: filtrare + deduplicare + insertie in graf."""

from __future__ import annotations

import logging
from typing import Optional

from backend.pipeline.graph.models import EntityType, RelationType, TemporalFact
from backend.pipeline.graph.store import TemporalKnowledgeGraph

logger = logging.getLogger(__name__)

IGNORED_SUBJECT_TYPES = {EntityType.DATE, EntityType.OTHER}
MIN_CONFIDENCE_THRESHOLD = 0.3


class TKGBuilder:
    """
    Construieste TemporalKnowledgeGraph din lista de TemporalFact.
    Pasi: filtrare → deduplicare → insertie in graf.
    """

    def __init__(self, min_confidence: float = MIN_CONFIDENCE_THRESHOLD, require_temporal_anchor: bool = True):
        self.min_confidence = min_confidence
        self.require_temporal_anchor = require_temporal_anchor

    def build(self, facts: list[TemporalFact]) -> TemporalKnowledgeGraph:
        tkg = TemporalKnowledgeGraph()
        if not facts:
            logger.warning("TKGBuilder.build() apelat cu lista goala de fapte.")
            return tkg

        valid_facts = self._filter(facts)
        n_filtered = len(facts) - len(valid_facts)
        if n_filtered > 0:
            logger.info(f"TKGBuilder: {n_filtered} fapte filtrate ({len(valid_facts)} raman din {len(facts)})")

        unique_facts = self._deduplicate(valid_facts)
        n_dupes = len(valid_facts) - len(unique_facts)
        if n_dupes > 0:
            logger.info(f"TKGBuilder: {n_dupes} fapte duplicate eliminate.")

        tkg.add_facts(unique_facts)
        logger.info(f"TKGBuilder: graf construit — {tkg.summary()}")
        return tkg

    def _filter(self, facts: list[TemporalFact]) -> list[TemporalFact]:
        """Elimina fapte invalide: subiect gol, tip ignorabil, confidence prea mic, fara ancora."""
        result = []
        for fact in facts:
            reason = self._rejection_reason(fact)
            if reason:
                logger.debug(f"TKGBuilder: fapt respins ({reason}): {fact!r}")
            else:
                result.append(fact)
        return result

    def _rejection_reason(self, fact: TemporalFact) -> Optional[str]:
        if not fact.subject.text.strip():
            return "subiect gol"
        if not fact.object.text.strip():
            return "obiect gol"
        if fact.subject.entity_type in IGNORED_SUBJECT_TYPES:
            return f"subiect de tip ignorabil ({fact.subject.entity_type.value})"
        if fact.extraction_confidence < self.min_confidence:
            return f"confidence prea mic ({fact.extraction_confidence:.2f})"
        if self.require_temporal_anchor and not _has_temporal_anchor(fact):
            return "fara ancora temporala parsata"
        return None

    def _deduplicate(self, facts: list[TemporalFact]) -> list[TemporalFact]:
        """Elimina duplicate dupa semnatura (subj, pred, obj, timp). Pastreaza confidence mai mare."""
        seen: dict[tuple, TemporalFact] = {}
        for fact in facts:
            sig = _fact_signature(fact)
            if sig not in seen or fact.extraction_confidence > seen[sig].extraction_confidence:
                seen[sig] = fact
        seen_ids = set(id(f) for f in seen.values())
        return [f for f in facts if id(f) in seen_ids]


def _has_temporal_anchor(fact: TemporalFact) -> bool:
    """Cel putin un camp temporal (point/start/end) cu normalized_date valid."""
    return any(
        getattr(fact, field) and getattr(fact, field).normalized_date
        for field in ("time_point", "time_start", "time_end")
    )


def _fact_signature(fact: TemporalFact) -> tuple:
    return (
        fact.subject.text.lower().strip(), fact.predicate.value, fact.object.text.lower().strip(),
        fact.time_start.date_string if fact.time_start else None,
        fact.time_end.date_string if fact.time_end else None,
        fact.time_point.date_string if fact.time_point else None,
    )
"""C2 — TKG Construction: filter, deduplicate, and insert temporal facts into the graph."""

from __future__ import annotations

import logging
from typing import Optional

from backend import runtime_settings
from backend.pipeline.graph.models import EntityType, RelationType, TemporalFact
from backend.pipeline.graph.store import TemporalKnowledgeGraph

logger = logging.getLogger(__name__)

IGNORED_SUBJECT_TYPES = {EntityType.DATE, EntityType.OTHER}


class TKGBuilder:
    """
    Builds a TemporalKnowledgeGraph from a list of TemporalFacts.
    Steps: filter -> deduplicate -> insert into graph.
    """

    def __init__(self, min_confidence: Optional[float] = None, require_temporal_anchor: bool = True):
        # None -> read min_fact_confidence from runtime_settings at each use, so
        # UI changes take effect on the next request. An explicit value overrides.
        self.min_confidence = min_confidence
        self.require_temporal_anchor = require_temporal_anchor

    def build(self, facts: list[TemporalFact]) -> TemporalKnowledgeGraph:
        tkg = TemporalKnowledgeGraph()
        if not facts:
            logger.warning("TKGBuilder.build() called with empty facts list.")
            return tkg

        valid_facts = self._filter(facts)
        n_filtered = len(facts) - len(valid_facts)
        if n_filtered > 0:
            logger.info(f"TKGBuilder: {n_filtered} facts filtered ({len(valid_facts)} remaining from {len(facts)})")

        unique_facts = self._deduplicate(valid_facts)
        n_dupes = len(valid_facts) - len(unique_facts)
        if n_dupes > 0:
            logger.info(f"TKGBuilder: {n_dupes} duplicate facts removed.")

        tkg.add_facts(unique_facts)
        logger.info(f"TKGBuilder: graph built — {tkg.summary()}")
        return tkg

    def _filter(self, facts: list[TemporalFact]) -> list[TemporalFact]:
        """Remove invalid facts: empty subject, ignored type, low confidence, no anchor."""
        result = []
        for fact in facts:
            reason = self._rejection_reason(fact)
            if reason:
                logger.debug(f"TKGBuilder: fact rejected ({reason}): {fact!r}")
            else:
                result.append(fact)
        return result

    def _rejection_reason(self, fact: TemporalFact) -> Optional[str]:
        if not fact.subject.text.strip():
            return "empty subject"
        if not fact.object.text.strip():
            return "empty object"
        if fact.subject.entity_type in IGNORED_SUBJECT_TYPES:
            return f"ignored subject type ({fact.subject.entity_type.value})"
        min_confidence = (
            self.min_confidence if self.min_confidence is not None
            else runtime_settings.get_value("min_fact_confidence")
        )
        if fact.extraction_confidence < min_confidence:
            return f"confidence too low ({fact.extraction_confidence:.2f})"
        if self.require_temporal_anchor and not _has_temporal_anchor(fact):
            return "no parsed temporal anchor"
        return None

    def _deduplicate(self, facts: list[TemporalFact]) -> list[TemporalFact]:
        """Remove duplicates by signature (subj, pred, obj, time). Keep higher confidence."""
        seen: dict[tuple, TemporalFact] = {}
        for fact in facts:
            sig = _fact_signature(fact)
            if sig not in seen or fact.extraction_confidence > seen[sig].extraction_confidence:
                seen[sig] = fact
        seen_ids = set(id(f) for f in seen.values())
        return [f for f in facts if id(f) in seen_ids]


def _has_temporal_anchor(fact: TemporalFact) -> bool:
    """True if at least one temporal field (point/start/end) has a valid normalized_date."""
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

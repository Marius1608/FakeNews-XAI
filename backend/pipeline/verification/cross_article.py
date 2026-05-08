"""C3c — Cross-article inconsistency detection using the persistent TKG store."""

from __future__ import annotations

import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional

from backend.pipeline.graph.base_store import AbstractTKGStore
from backend.pipeline.graph.models import (
    Inconsistency, InconsistencyType, Severity, TemporalFact,
)

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.80


class CrossArticleVerifier:
    """Detects inconsistencies between facts in the current article and
    previously analyzed articles stored in Neo4j."""

    def __init__(self, persistent_store: AbstractTKGStore) -> None:
        self.store = persistent_store

    def verify(
        self,
        current_facts: list[TemporalFact],
        current_article_id: str,
    ) -> list[Inconsistency]:
        """Compare current article facts against all stored facts for the same entities.

        Call this BEFORE persisting the current article so stored results belong
        exclusively to prior articles.
        """
        inconsistencies: list[Inconsistency] = []

        for fact in current_facts:
            entity_name = fact.subject.text.lower().strip()
            stored_facts = self.store.get_facts_for_entity(entity_name)

            # safety guard: skip any fact already tagged to this article
            other_facts = [
                f for f in stored_facts
                if getattr(f, "article_id", None) != current_article_id
            ]

            for stored in other_facts:
                # check 1: same relation + similar object + conflicting dates
                if (
                    fact.predicate == stored.predicate
                    and _objects_similar(fact.object.text, stored.object.text)
                ):
                    conflict = _check_date_conflict(fact, stored)
                    if conflict:
                        inconsistencies.append(conflict)

                # check 2: same entity holds different positions at overlapping times
                if (
                    fact.predicate.value == "holds_position"
                    and stored.predicate.value == "holds_position"
                    and _overlapping_time(fact, stored)
                    and not _objects_similar(fact.object.text, stored.object.text)
                ):
                    inconsistencies.append(
                        Inconsistency(
                            inconsistency_type=InconsistencyType.DATE_MISMATCH,
                            severity=Severity.HIGH,
                            description=(
                                f"Cross-article conflict: '{fact.subject.text}' holds "
                                f"different positions at overlapping times: "
                                f"'{fact.object.text}' vs '{stored.object.text}'"
                            ),
                            facts_involved=[fact, stored],
                            sentence_indices=[fact.source_sentence_idx],
                            verified_by="cross_article",
                            evidence=f"Article {current_article_id} vs stored facts",
                        )
                    )

        logger.info(
            f"Cross-article verification: {len(inconsistencies)} conflicts found "
            f"for article {current_article_id}"
        )
        return inconsistencies


def _objects_similar(a: str, b: str) -> bool:
    """True when strings are equal (case-insensitive) or fuzzy-match above threshold."""
    a_norm, b_norm = a.lower().strip(), b.lower().strip()
    if a_norm == b_norm:
        return True
    return SequenceMatcher(None, a_norm, b_norm).ratio() >= SIMILARITY_THRESHOLD


def _check_date_conflict(
    fact_a: TemporalFact, fact_b: TemporalFact
) -> Optional[Inconsistency]:
    """Return an Inconsistency when the same claim appears with dates more than 1 year apart."""
    time_a = _best_date(fact_a)
    time_b = _best_date(fact_b)
    if time_a is None or time_b is None:
        return None

    if abs((time_a - time_b).days) <= 365:
        return None

    return Inconsistency(
        inconsistency_type=InconsistencyType.DATE_MISMATCH,
        severity=Severity.MEDIUM,
        description=(
            f"Cross-article date conflict: '{fact_a.subject.text} "
            f"{fact_a.predicate.value} {fact_a.object.text}' — "
            f"{time_a.year} (current article) vs {time_b.year} (stored)"
        ),
        facts_involved=[fact_a, fact_b],
        sentence_indices=[fact_a.source_sentence_idx],
        verified_by="cross_article",
        evidence=f"{time_a.date()} (current) vs {time_b.date()} (stored)",
    )


def _overlapping_time(fact_a: TemporalFact, fact_b: TemporalFact) -> bool:
    """True if the temporal ranges of the two facts overlap."""
    start_a = _range_start(fact_a)
    start_b = _range_start(fact_b)
    if start_a is None or start_b is None:
        return False

    end_a = _range_end(fact_a) or datetime.max
    end_b = _range_end(fact_b) or datetime.max

    return start_a <= end_b and start_b <= end_a


def _best_date(fact: TemporalFact) -> Optional[datetime]:
    """Most representative single datetime: time_point > time_start > time_end."""
    for attr in ("time_point", "time_start", "time_end"):
        expr = getattr(fact, attr)
        if expr and expr.normalized_date:
            return expr.normalized_date
    return None


def _range_start(fact: TemporalFact) -> Optional[datetime]:
    for attr in ("time_start", "time_point"):
        expr = getattr(fact, attr)
        if expr and expr.normalized_date:
            return expr.normalized_date
    return None


def _range_end(fact: TemporalFact) -> Optional[datetime]:
    for attr in ("time_end", "time_point"):
        expr = getattr(fact, attr)
        if expr and expr.normalized_date:
            return expr.normalized_date
    return None

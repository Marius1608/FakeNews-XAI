"""C3a — Internal Verification: temporal cycles, causal violations, ordering errors."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from difflib import SequenceMatcher
import re

import networkx as nx

from backend import runtime_settings
from backend.pipeline.graph.models import (
    InconsistencyType, RelationType, Severity, TemporalFact, Inconsistency,
)
from backend.pipeline.graph.store import TemporalKnowledgeGraph

logger = logging.getLogger(__name__)

ORDERING_RELATIONS = {RelationType.PRECEDED, RelationType.FOLLOWED}
CAUSAL_RELATIONS = {RelationType.CAUSED}

INCOMPATIBLE_POSITIONS = [
    {"senator", "governor", "representative", "mayor", "congressman"},
    {"president", "prime minister", "chancellor", "secretary of state"},
    {"vice president", "senator", "governor"},
    {"speaker", "senator", "governor"},
    # A head of state/government cannot simultaneously hold a state/legislative
    # office. Catches fakes like "Clinton was Governor and President at once".
    {"president", "governor"},
    {"president", "senator"},
    {"president", "representative"},
    {"president", "mayor"},
    {"prime minister", "mayor"},
]

# Object strings that are not real positions — V5 must not treat a party
# adjective ("Democratic"/"Republican") as a held office.
NON_POSITION_OBJECTS = {
    "democratic", "republican", "democrat", "democratic party", "republican party",
    "labour", "conservative", "tory", "independent", "liberal",
}

FUTURE_INDICATORS = {"will ", "going to ", "expected to ", "planned for ", "is set to ",
                     "shall ", "is expected", "are expected", "will be ", "would "}

INAUGURATION_KEYWORDS = {"inaugurat", "inaugurated", "sworn in", "took office", "assumed office"}
ELECTION_KEYWORDS = {"elected", "election", "won", "re-elected", "voted"}

def _split_compound_positions(position_text: str) -> list[str]:
    """Split compound position strings: 'Senator and Governor' -> ['Senator', 'Governor']."""
    parts = re.split(r'\s+and\s+|\s*&\s*|\s*,\s*', position_text, flags=re.IGNORECASE)
    return [p.strip().lower() for p in parts if p.strip()]

def _is_inauguration_or_election(fact: TemporalFact) -> bool:
    text = (fact.object.text + " " + (fact.source_sentence or "")).lower()
    return any(kw in text for kw in INAUGURATION_KEYWORDS | ELECTION_KEYWORDS)


@dataclass
class InternalVerificationResult:
    """
    Internal verification result.
    score_coherence = 1 - (conf_temp / rel_temp) — input to the TCS formula.
    """
    inconsistencies: list[Inconsistency] = field(default_factory=list)
    # Temporal conflicts detected
    conf_temp: int = 0
    # Total temporal relations
    rel_temp: int = 0

    @property
    def score_coherence(self) -> float:
        if self.rel_temp == 0:
            return 1.0
        return max(0.0, min(1.0, 1.0 - (self.conf_temp / self.rel_temp)))


class InternalVerifier:
    """Runs internal checks on the TKG and returns a score_coherence value."""

    def verify(self, tkg: TemporalKnowledgeGraph, publication_date: Optional[datetime] = None) -> InternalVerificationResult:
        all_facts = tkg.get_all_facts()
        rel_temp = len(all_facts)
        inconsistencies: list[Inconsistency] = []

        inconsistencies.extend(self._check_temporal_cycles(tkg))
        inconsistencies.extend(self._check_causal_violations(all_facts))
        inconsistencies.extend(self._check_ordering_errors(all_facts))

        # Additional checks
        inconsistencies.extend(self._check_factual_contradictions(all_facts))
        inconsistencies.extend(self._check_implicit_contradictions(all_facts))
        if publication_date:
            inconsistencies.extend(self._check_future_as_past(all_facts, publication_date))
        inconsistencies.extend(self._check_entity_consistency(all_facts))
        inconsistencies.extend(self._check_action_before_office(tkg))

        # Coherence ignores LOW-severity items: they carry zero penalty weight in
        # the TCS formula and are mostly low-confidence noise (parse artifacts,
        # "no temporal data" fallbacks). Counting them would let a pile of LOW
        # warnings tank a genuinely consistent article (e.g. a misparsed date).
        conf_temp = sum(1 for i in inconsistencies if i.severity != Severity.LOW)
        result = InternalVerificationResult(
            inconsistencies=inconsistencies, conf_temp=conf_temp, rel_temp=rel_temp,
        )
        logger.info(f"Internal verification: {result.conf_temp} conflicts / {rel_temp} relations -> score_coherence={result.score_coherence:.3f}")
        return result

    # V1: Temporal cycles
    def _check_temporal_cycles(self, tkg: TemporalKnowledgeGraph) -> list[Inconsistency]:
        """V1: Cycles in PRECEDED/FOLLOWED relations (e.g. A before B before A)."""
        order_graph = nx.DiGraph()
        for edge in tkg.get_edges_by_relation(RelationType.PRECEDED) + tkg.get_edges_by_relation(RelationType.FOLLOWED):
            order_graph.add_edge(edge["source"], edge["target"])

        if order_graph.number_of_edges() == 0:
            return []

        try:
            cycle = nx.find_cycle(order_graph, orientation="original")
            nodes_in_cycle = [u for u, v, _ in cycle]
            cycle_str = " -> ".join(nodes_in_cycle) + f" -> {nodes_in_cycle[0]}"
            return [Inconsistency(
                inconsistency_type=InconsistencyType.TEMPORAL_CYCLE,
                severity=Severity.HIGH,
                description=f"Temporal cycle: {cycle_str}.",
                verified_by="internal", evidence=f"Cycle: {cycle_str}",
            )]
        except nx.NetworkXNoCycle:
            return []

    # V2: Causal violations
    def _check_causal_violations(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V2: Effect precedes cause in CAUSED facts."""
        inconsistencies = []
        causal_facts = [f for f in facts if f.predicate in CAUSAL_RELATIONS]

        for fact in causal_facts:
            cause_time = _extract_point_time(fact)
            if cause_time is None:
                continue

            effect_facts = [
                f2 for f2 in facts
                if f2.subject.text.lower() == fact.object.text.lower() and _extract_point_time(f2) is not None
            ]
            for ef in effect_facts:
                effect_time = _extract_point_time(ef)
                if effect_time and effect_time < cause_time:
                    inconsistencies.append(Inconsistency(
                        inconsistency_type=InconsistencyType.CAUSAL_VIOLATION,
                        severity=Severity.HIGH,
                        description=f"Causal violation: '{fact.subject.text}' -> '{fact.object.text}', effect ({effect_time.year}) precedes cause ({cause_time.year}).",
                        facts_involved=[fact, ef],
                        sentence_indices=[fact.source_sentence_idx, ef.source_sentence_idx],
                        verified_by="internal",
                        evidence=f"Cause: {cause_time.strftime('%Y-%m-%d')}, Effect: {effect_time.strftime('%Y-%m-%d')}",
                    ))
        return inconsistencies

    # V3: Ordering errors
    def _check_ordering_errors(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V3: Inverted interval (start > end) and implausible duration (>50 years)."""
        inconsistencies = []
        inverted_tolerance_days = runtime_settings.get_value("inverted_interval_tolerance_days")
        max_plausible_tenure_years = runtime_settings.get_value("max_plausible_tenure_years")
        # Beyond this, an interval is almost certainly a date-parsing artifact (e.g. a
        # misparsed token resolved to 1960) rather than a real claim — do not flag it.
        absurd_duration_years = runtime_settings.get_value("absurd_duration_years")
        for fact in facts:
            if not (fact.time_start and fact.time_end):
                continue
            t_start = fact.time_start.normalized_date
            t_end = fact.time_end.normalized_date
            if t_start is None or t_end is None:
                continue

            if t_start > t_end:
                gap_days = (t_start - t_end).days
                if gap_days < inverted_tolerance_days:
                    continue
                inconsistencies.append(Inconsistency(
                    inconsistency_type=InconsistencyType.ORDERING_ERROR,
                    severity=Severity.MEDIUM,
                    description=f"Inverted interval: '{fact.subject.text}' [{fact.time_start.date_string} -> {fact.time_end.date_string}].",
                    facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                    verified_by="internal", evidence=f"start={fact.time_start.date_string}, end={fact.time_end.date_string}",
                ))
            else:
                duration_years = (t_end - t_start).days / 365.25
                if duration_years > absurd_duration_years:
                    # Date-parsing artifact (e.g. "Cuba" misparsed to 1960) — skip
                    # silently so it does not pollute the coherence denominator.
                    continue
                if duration_years > max_plausible_tenure_years:
                    inconsistencies.append(Inconsistency(
                        inconsistency_type=InconsistencyType.DURATION_IMPLAUSIBLE,
                        severity=Severity.LOW,
                        description=f"Implausible duration: '{fact.subject.text}' — {duration_years:.0f} years.",
                        facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                        verified_by="internal", evidence=f"Duration: {duration_years:.0f} years",
                    ))
        return inconsistencies

    # V4: Factual contradictions
    def _check_factual_contradictions(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V4: Factual contradictions (same object held by different subjects with temporal overlap)."""
        inconsistencies = []
        text_sim_threshold = runtime_settings.get_value("text_similarity_threshold_v4")
        for i, f1 in enumerate(facts):
            for j, f2 in enumerate(facts):
                if i >= j:
                    continue
                if f1.predicate != f2.predicate:
                    continue
                if f1.predicate != RelationType.HOLDS_POSITION:
                    continue

                obj1 = f1.object.text.lower()
                obj2 = f2.object.text.lower()

                # Same object (e.g. 'president') held by different subjects
                if SequenceMatcher(None, obj1, obj2).ratio() >= text_sim_threshold:
                    subj1 = f1.subject.text.lower()
                    subj2 = f2.subject.text.lower()

                    if SequenceMatcher(None, subj1, subj2).ratio() < text_sim_threshold:
                        # Different subjects + same object: check temporal overlap
                        start1, end1 = _extract_bounds(f1)
                        start2, end2 = _extract_bounds(f2)

                        if _check_overlap(start1, end1, start2, end2):
                            if len(obj1.strip()) < 5:
                                continue
                            orig_obj1 = f1.object.text.strip()
                            if orig_obj1 and orig_obj1[0].islower():
                                continue
                            inconsistencies.append(Inconsistency(
                                inconsistency_type=InconsistencyType.FACTUAL_CONTRADICTION,
                                severity=Severity.HIGH,
                                description=f"Contradiction: '{f1.subject.text}' and '{f2.subject.text}' both as '{f1.object.text}' in the same interval.",
                                facts_involved=[f1, f2],
                                sentence_indices=[f1.source_sentence_idx, f2.source_sentence_idx],
                                verified_by="internal",
                                evidence="Facts overlap in time."
                            ))
        return inconsistencies

    # V5: Implicit contradictions
    def _check_implicit_contradictions(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V5: Implicit contradictions (e.g. holding a position before the election)."""
        inconsistencies = []

        # Only HOLDS_POSITION facts are meaningful anchors for V5.
        # GENERIC facts often capture peripheral noun phrases (e.g. "John Kerry" extracted
        # from "defeating John Kerry") and do not reliably indicate role occupancy.
        holds_facts = [f for f in facts if f.predicate == RelationType.HOLDS_POSITION]
        event_facts = facts
        election_buffer_days = runtime_settings.get_value("election_to_office_buffer_days")

        for h_fact in holds_facts:
            subj_h = h_fact.subject.text.lower()

            # Skip non-position objects (party adjectives, fragments) — these are
            # extraction noise, not held offices, and produce false contradictions.
            obj_h = h_fact.object.text.lower().strip()
            if obj_h in NON_POSITION_OBJECTS or len(obj_h) < 4:
                continue

            # V5 only fires for entities that appear in at least 2 distinct facts.
            entity_fact_count = sum(
                1 for f in facts
                if SequenceMatcher(None, subj_h, f.subject.text.lower()).ratio() >= 0.85
            )
            if entity_fact_count < 2:
                continue

            start_h = _extract_point_time(h_fact) or (h_fact.time_start.normalized_date if h_fact.time_start else None)

            if not start_h:
                continue

            # Check against inauguration/election events
            for e_fact in event_facts:
                subj_e = e_fact.subject.text.lower()

                if SequenceMatcher(None, subj_h, subj_e).ratio() >= 0.85:
                    if _is_inauguration_or_election(e_fact):
                        point_e = _extract_point_time(e_fact)
                        # election -> inauguration transition is normal (up to ~6 months by default)
                        if point_e and (point_e - start_h).days > election_buffer_days:
                            inconsistencies.append(Inconsistency(
                                inconsistency_type=InconsistencyType.IMPLICIT_CONTRADICTION,
                                severity=Severity.MEDIUM,
                                description=f"Implicit contradiction: '{h_fact.subject.text}' started '{h_fact.object.text}' ({start_h.year}) BEFORE '{e_fact.object.text}' ({point_e.year}).",
                                facts_involved=[h_fact, e_fact],
                                sentence_indices=[h_fact.source_sentence_idx, e_fact.source_sentence_idx],
                                verified_by="internal",
                                evidence="Sequential incompatibility."
                            ))

        return inconsistencies

    # V6: Future as past
    def _check_future_as_past(self, facts: list[TemporalFact], publication_date: datetime) -> list[Inconsistency]:
        """V6: Future dates presented as already-happened events."""
        inconsistencies = []
        for fact in facts:
            fact_date = _extract_point_time(fact)
            if fact_date is None or fact_date <= publication_date:
                continue

            source = (fact.source_sentence or "").lower()

            # If the sentence contains future tense indicators, it is expected
            if any(ind in source for ind in FUTURE_INDICATORS):
                continue

            # Article refers to a future event as if it already happened
            inconsistencies.append(Inconsistency(
                inconsistency_type=InconsistencyType.FUTURE_AS_PAST,
                severity=Severity.HIGH,
                description=f"Event from {fact_date.year} presented as past, but article is from {publication_date.year}: '{fact.subject.text}'.",
                facts_involved=[fact],
                sentence_indices=[fact.source_sentence_idx],
                verified_by="internal",
                evidence=f"Fact date: {fact_date.strftime('%Y-%m-%d')}, Publication: {publication_date.strftime('%Y-%m-%d')}",
            ))
        return inconsistencies

    # V7: Entity consistency
    def _check_entity_consistency(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V7: Same person holds two incompatible positions simultaneously."""
        inconsistencies = []
        holds_facts = [f for f in facts if f.predicate == RelationType.HOLDS_POSITION]

        # Check individual facts with compound incompatible positions
        for f in holds_facts:
            roles = _split_compound_positions(f.object.text)
            if len(roles) > 1:
                for inc_set in INCOMPATIBLE_POSITIONS:
                    matched_terms = set()
                    for r in roles:
                        for t in inc_set:
                            if t in r:
                                matched_terms.add(t)
                    if len(matched_terms) > 1:
                        inconsistencies.append(Inconsistency(
                            inconsistency_type=InconsistencyType.ENTITY_INCONSISTENCY,
                            severity=Severity.MEDIUM,
                            description=f"Incompatible simultaneous roles for '{f.subject.text}': {', '.join(matched_terms)}.",
                            facts_involved=[f],
                            sentence_indices=[f.source_sentence_idx],
                            verified_by="internal",
                            evidence="Incompatible compound positions in the same fact."
                        ))
                        break

        # Group by subject (fuzzy match)
        grouped_facts = []
        for f in holds_facts:
            added = False
            for group in grouped_facts:
                if SequenceMatcher(None, group[0].subject.text.lower(), f.subject.text.lower()).ratio() >= 0.75:
                    group.append(f)
                    added = True
                    break
            if not added:
                grouped_facts.append([f])

        for group in grouped_facts:
            for i, f1 in enumerate(group):
                for j, f2 in enumerate(group):
                    if i >= j:
                        continue

                    obj1 = f1.object.text.lower()
                    obj2 = f2.object.text.lower()

                    if SequenceMatcher(None, obj1, obj2).ratio() < 0.70:
                        # Different roles
                        start1, end1 = _extract_bounds(f1)
                        start2, end2 = _extract_bounds(f2)
                        roles1 = _split_compound_positions(obj1)
                        roles2 = _split_compound_positions(obj2)

                        if _check_overlap(start1, end1, start2, end2):
                            for inc_set in INCOMPATIBLE_POSITIONS:
                                has_1 = any(any(t in r for t in inc_set) for r in roles1)
                                has_2 = any(any(t in r for t in inc_set) for r in roles2)

                                if has_1 and has_2:
                                    inconsistencies.append(Inconsistency(
                                        inconsistency_type=InconsistencyType.ENTITY_INCONSISTENCY,
                                        severity=Severity.MEDIUM,
                                        description=f"Incompatible simultaneous roles for '{f1.subject.text}': '{f1.object.text}' and '{f2.object.text}'.",
                                        facts_involved=[f1, f2],
                                        sentence_indices=[f1.source_sentence_idx, f2.source_sentence_idx],
                                        verified_by="internal",
                                        evidence="Overlapping incompatible positions."
                                    ))
                                    break

                        # Fallback: no temporal data on either fact — flag with LOW severity
                        elif start1 is None and start2 is None:
                            for inc_set in INCOMPATIBLE_POSITIONS:
                                has_1 = any(any(t in r for t in inc_set) for r in roles1)
                                has_2 = any(any(t in r for t in inc_set) for r in roles2)
                                if has_1 and has_2:
                                    inconsistencies.append(Inconsistency(
                                        inconsistency_type=InconsistencyType.ENTITY_INCONSISTENCY,
                                        severity=Severity.LOW,
                                        description=f"Potentially incompatible roles for '{f1.subject.text}': '{f1.object.text}' and '{f2.object.text}' (no temporal data to confirm overlap).",
                                        facts_involved=[f1, f2],
                                        sentence_indices=[f1.source_sentence_idx, f2.source_sentence_idx],
                                        verified_by="internal",
                                        evidence="Incompatible roles present; no dates available to confirm or deny overlap."
                                    ))
                                    break

        return inconsistencies

    # V8: Action before office
    def _check_action_before_office(self, tkg) -> list[Inconsistency]:
        """V8: Entity performed action before holding the relevant office."""
        inconsistencies = []
        facts = tkg.get_all_facts()

        # Build map: entity -> list of (office_name, office_start_date)
        office_starts: dict[str, list[tuple]] = {}
        for fact in facts:
            if fact.predicate != RelationType.HOLDS_POSITION:
                continue
            if not fact.time_start or not fact.time_start.normalized_date:
                continue
            entity = fact.subject.text.lower().strip()
            office_starts.setdefault(entity, []).append(
                (fact.object.text, fact.time_start.normalized_date)
            )

        # Check OCCURRED_ON/GENERIC/STARTED facts for same entities
        action_buffer_days = runtime_settings.get_value("action_before_office_buffer_days")
        for fact in facts:
            if fact.predicate not in {RelationType.OCCURRED_ON, RelationType.GENERIC, RelationType.STARTED}:
                continue
            entity = fact.subject.text.lower().strip()
            if entity not in office_starts:
                continue

            fact_time = None
            if fact.time_point and fact.time_point.normalized_date:
                fact_time = fact.time_point.normalized_date
            elif fact.time_start and fact.time_start.normalized_date:
                fact_time = fact.time_start.normalized_date
            if not fact_time:
                continue

            for office_name, office_start in office_starts[entity]:
                gap_days = (fact_time - office_start).days
                # Action more than N days before taking office is suspicious
                if gap_days < -action_buffer_days:
                    inconsistencies.append(Inconsistency(
                        inconsistency_type=InconsistencyType.CAUSAL_VIOLATION,
                        severity=Severity.HIGH,
                        description=f"'{fact.subject.text}' performed action in {fact_time.year} but only took office ({office_name}) in {office_start.year}.",
                        facts_involved=[fact],
                        sentence_indices=[fact.source_sentence_idx],
                        verified_by="internal_v8",
                        evidence=f"Office start: {office_start.date()}, action date: {fact_time.date()}",
                    ))
                    break

        return inconsistencies


# Utility functions
def _extract_point_time(fact: TemporalFact) -> Optional[datetime]:
    """Most representative datetime: time_point > time_start > time_end."""
    for field in ("time_point", "time_start", "time_end"):
        expr = getattr(fact, field)
        if expr and expr.normalized_date:
            return expr.normalized_date
    return None

def _extract_bounds(fact: TemporalFact) -> tuple[Optional[datetime], Optional[datetime]]:
    """Extract (start, end) from a fact, treating point times as degenerate intervals."""
    if fact.time_start and fact.time_end:
        return fact.time_start.normalized_date, fact.time_end.normalized_date
    if fact.time_point:
        pt = fact.time_point.normalized_date
        return pt, pt
    return None, None

def _check_overlap(s1: Optional[datetime], e1: Optional[datetime], s2: Optional[datetime], e2: Optional[datetime]) -> bool:
    """True if the intervals [s1, e1] and [s2, e2] overlap."""
    if not (s1 and e1 and s2 and e2):
        # If only start times are available, match on same year
        if s1 and s2 and s1.year == s2.year:
            return True
        return False

    return max(s1, s2) <= min(e1, e2)

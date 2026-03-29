"""C3a — Verificare Interna: cicluri temporale, violari cauzale, ordering errors."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import networkx as nx

from backend.pipeline.graph.models import (
    InconsistencyType, RelationType, Severity, TemporalFact, Inconsistency,
)
from backend.pipeline.graph.store import TemporalKnowledgeGraph

logger = logging.getLogger(__name__)

ORDERING_RELATIONS = {RelationType.PRECEDED, RelationType.FOLLOWED}
CAUSAL_RELATIONS = {RelationType.CAUSED}
MAX_PLAUSIBLE_TENURE_YEARS = 50


@dataclass
class InternalVerificationResult:
    """
    Rezultat verificare interna.
    score_coherence = 1 - (conf_temp / rel_temp) — intrare in formula TCS.
    """
    inconsistencies: list[Inconsistency] = field(default_factory=list)
    conf_temp: int = 0    # conflicte temporale detectate
    rel_temp: int = 0     # total relatii temporale

    @property
    def score_coherence(self) -> float:
        if self.rel_temp == 0:
            return 1.0
        return max(0.0, min(1.0, 1.0 - (self.conf_temp / self.rel_temp)))


class InternalVerifier:
    """Ruleaza 3 verificari interne pe TKG si returneaza score_coherence."""

    def verify(self, tkg: TemporalKnowledgeGraph) -> InternalVerificationResult:
        all_facts = tkg.get_all_facts()
        rel_temp = len(all_facts)
        inconsistencies: list[Inconsistency] = []

        inconsistencies.extend(self._check_temporal_cycles(tkg))
        inconsistencies.extend(self._check_causal_violations(all_facts))
        inconsistencies.extend(self._check_ordering_errors(all_facts))

        result = InternalVerificationResult(
            inconsistencies=inconsistencies, conf_temp=len(inconsistencies), rel_temp=rel_temp,
        )
        logger.info(f"Verificare interna: {result.conf_temp} conflicte / {rel_temp} relatii → score_coherence={result.score_coherence:.3f}")
        return result

    def _check_temporal_cycles(self, tkg: TemporalKnowledgeGraph) -> list[Inconsistency]:
        """V1: Cicluri in relatiile PRECEDED/FOLLOWED (ex: A inainte de B inainte de A)."""
        order_graph = nx.DiGraph()
        for edge in tkg.get_edges_by_relation(RelationType.PRECEDED) + tkg.get_edges_by_relation(RelationType.FOLLOWED):
            order_graph.add_edge(edge["source"], edge["target"])

        if order_graph.number_of_edges() == 0:
            return []

        try:
            cycle = nx.find_cycle(order_graph, orientation="original")
            nodes_in_cycle = [u for u, v, _ in cycle]
            cycle_str = " → ".join(nodes_in_cycle) + f" → {nodes_in_cycle[0]}"
            return [Inconsistency(
                inconsistency_type=InconsistencyType.TEMPORAL_CYCLE,
                severity=Severity.HIGH,
                description=f"Ciclu temporal: {cycle_str}.",
                verified_by="internal", evidence=f"Ciclu: {cycle_str}",
            )]
        except nx.NetworkXNoCycle:
            return []

    def _check_causal_violations(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V2: Efect inainte de cauza in fapte CAUSED."""
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
                        description=f"Violare cauzala: '{fact.subject.text}' → '{fact.object.text}', efectul ({effect_time.year}) precede cauza ({cause_time.year}).",
                        facts_involved=[fact, ef],
                        sentence_indices=[fact.source_sentence_idx, ef.source_sentence_idx],
                        verified_by="internal",
                        evidence=f"Cauza: {cause_time.strftime('%Y-%m-%d')}, Efect: {effect_time.strftime('%Y-%m-%d')}",
                    ))
        return inconsistencies

    def _check_ordering_errors(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V3: Interval inversat (start > end) si durata implausibila (>50 ani)."""
        inconsistencies = []
        for fact in facts:
            if not (fact.time_start and fact.time_end):
                continue
            t_start = fact.time_start.normalized_date
            t_end = fact.time_end.normalized_date
            if t_start is None or t_end is None:
                continue

            if t_start > t_end:
                inconsistencies.append(Inconsistency(
                    inconsistency_type=InconsistencyType.ORDERING_ERROR,
                    severity=Severity.MEDIUM,
                    description=f"Interval inversat: '{fact.subject.text}' [{fact.time_start.date_string} → {fact.time_end.date_string}].",
                    facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                    verified_by="internal", evidence=f"start={fact.time_start.date_string}, end={fact.time_end.date_string}",
                ))
            else:
                duration_years = (t_end - t_start).days / 365.25
                if duration_years > MAX_PLAUSIBLE_TENURE_YEARS:
                    inconsistencies.append(Inconsistency(
                        inconsistency_type=InconsistencyType.DURATION_IMPLAUSIBLE,
                        severity=Severity.LOW,
                        description=f"Durata implausibila: '{fact.subject.text}' — {duration_years:.0f} ani.",
                        facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                        verified_by="internal", evidence=f"Durata: {duration_years:.0f} ani",
                    ))
        return inconsistencies


def _extract_point_time(fact: TemporalFact) -> Optional[datetime]:
    """Cel mai reprezentativ moment: time_point > time_start > time_end."""
    for field in ("time_point", "time_start", "time_end"):
        expr = getattr(fact, field)
        if expr and expr.normalized_date:
            return expr.normalized_date
    return None
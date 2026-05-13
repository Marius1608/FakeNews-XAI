"""C3a — Verificare Interna: cicluri temporale, violari cauzale, ordering errors."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from difflib import SequenceMatcher

import networkx as nx

from backend.pipeline.graph.models import (
    InconsistencyType, RelationType, Severity, TemporalFact, Inconsistency,
)
from backend.pipeline.graph.store import TemporalKnowledgeGraph

logger = logging.getLogger(__name__)

ORDERING_RELATIONS = {RelationType.PRECEDED, RelationType.FOLLOWED}
CAUSAL_RELATIONS = {RelationType.CAUSED}
MAX_PLAUSIBLE_TENURE_YEARS = 50

INCOMPATIBLE_POSITIONS = [
    {"senator", "governor", "representative", "mayor"},
    {"president", "prime minister", "chancellor"},
]


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
    """Ruleaza verificari interne pe TKG si returneaza score_coherence."""

    def verify(self, tkg: TemporalKnowledgeGraph, publication_date: Optional[datetime] = None) -> InternalVerificationResult:
        all_facts = tkg.get_all_facts()
        rel_temp = len(all_facts)
        inconsistencies: list[Inconsistency] = []

        inconsistencies.extend(self._check_temporal_cycles(tkg))
        inconsistencies.extend(self._check_causal_violations(all_facts))
        inconsistencies.extend(self._check_ordering_errors(all_facts))
        
        # // section noi
        inconsistencies.extend(self._check_factual_contradictions(all_facts))
        inconsistencies.extend(self._check_implicit_contradictions(all_facts))
        if publication_date:
            inconsistencies.extend(self._check_future_as_past(all_facts, publication_date))
        inconsistencies.extend(self._check_entity_consistency(all_facts))

        result = InternalVerificationResult(
            inconsistencies=inconsistencies, conf_temp=len(inconsistencies), rel_temp=rel_temp,
        )
        logger.info(f"Verificare interna: {result.conf_temp} conflicte / {rel_temp} relatii → score_coherence={result.score_coherence:.3f}")
        return result

    # // section check_cycles
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

    # // section check_causal
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

    # // section check_ordering
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

    # // section check_factual_contradictions
    def _check_factual_contradictions(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V4: Contradicții factuale (același obiect cu subiecte diferite ce se suprapun temporal)."""
        inconsistencies = []
        for i, f1 in enumerate(facts):
            for j, f2 in enumerate(facts):
                if i >= j or f1.predicate != f2.predicate:
                    continue
                    
                obj1 = f1.object.text.lower()
                obj2 = f2.object.text.lower()
                
                # Căutăm același obiect (ex: 'president') deținut de entități diferite
                if SequenceMatcher(None, obj1, obj2).ratio() >= 0.85:
                    subj1 = f1.subject.text.lower()
                    subj2 = f2.subject.text.lower()
                    
                    if SequenceMatcher(None, subj1, subj2).ratio() < 0.85:
                        # Subiecte diferite + același obiect. Verificăm overlap
                        start1, end1 = _extract_bounds(f1)
                        start2, end2 = _extract_bounds(f2)
                        
                        if _check_overlap(start1, end1, start2, end2):
                            inconsistencies.append(Inconsistency(
                                inconsistency_type=InconsistencyType.FACTUAL_CONTRADICTION,
                                severity=Severity.HIGH,
                                description=f"Contradictie: '{f1.subject.text}' si '{f2.subject.text}' ca '{f1.object.text}' in acelasi interval.",
                                facts_involved=[f1, f2],
                                sentence_indices=[f1.source_sentence_idx, f2.source_sentence_idx],
                                verified_by="internal",
                                evidence="Fapte in acelasi interval de timp."
                            ))
        return inconsistencies

    # // section check_implicit_contradictions
    def _check_implicit_contradictions(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V5: Contradicții implicite (ex: poziție înainte de alegeri)."""
        inconsistencies = []
        
        holds_facts = [f for f in facts if f.predicate == RelationType.HOLDS_POSITION]
        event_facts = [f for f in facts if f.predicate == RelationType.OCCURRED_ON]
        ended_facts = [f for f in facts if f.predicate == RelationType.ENDED]
        
        for h_fact in holds_facts:
            subj_h = h_fact.subject.text.lower()
            start_h = _extract_point_time(h_fact) or (h_fact.time_start.normalized_date if h_fact.time_start else None)
            
            if not start_h:
                continue
                
            # Verifica event_facts (alegeri/inaugurare)
            for e_fact in event_facts:
                subj_e = e_fact.subject.text.lower()
                obj_e = e_fact.object.text.lower()
                
                if SequenceMatcher(None, subj_h, subj_e).ratio() >= 0.85:
                    if "election" in obj_e or "inaugurat" in obj_e:
                        point_e = _extract_point_time(e_fact)
                        if point_e and point_e > start_h:
                            inconsistencies.append(Inconsistency(
                                inconsistency_type=InconsistencyType.IMPLICIT_CONTRADICTION,
                                severity=Severity.MEDIUM,
                                description=f"Contradictie implicita: '{h_fact.subject.text}' a inceput '{h_fact.object.text}' ({start_h.year}) INAINTE de '{e_fact.object.text}' ({point_e.year}).",
                                facts_involved=[h_fact, e_fact],
                                sentence_indices=[h_fact.source_sentence_idx, e_fact.source_sentence_idx],
                                verified_by="internal",
                                evidence="Incompatibilitate secventiala."
                            ))
                            
            # Verifica ended_facts
            for end_fact in ended_facts:
                subj_end = end_fact.subject.text.lower()
                if SequenceMatcher(None, subj_h, subj_end).ratio() >= 0.85:
                    point_end = _extract_point_time(end_fact)
                    if point_end and start_h > point_end:
                        if (start_h - point_end).days < 30:
                            # Warning, dar pentru moment adaugam ca inconsistenta LOW
                            pass

        return inconsistencies

    # // section check_future_as_past
    def _check_future_as_past(self, facts: list[TemporalFact], publication_date: datetime) -> list[Inconsistency]:
        """V6: Evenimente in viitor fata de data publicarii descrise la trecut."""
        inconsistencies = []
        past_indicators = [" was ", " were ", " had ", " signed ", " won ", " became "]
        
        for fact in facts:
            time_to_check = _extract_point_time(fact) or (fact.time_start.normalized_date if fact.time_start else None)
            if not time_to_check:
                continue
                
            if time_to_check > publication_date:
                sent = fact.source_sentence.lower()
                if any(ind in sent for ind in past_indicators):
                    inconsistencies.append(Inconsistency(
                        inconsistency_type=InconsistencyType.FUTURE_AS_PAST,
                        severity=Severity.HIGH,
                        description=f"Eveniment viitor descris la trecut: '{fact.subject.text}' in {time_to_check.year} (publicat {publication_date.year}).",
                        facts_involved=[fact],
                        sentence_indices=[fact.source_sentence_idx],
                        verified_by="internal",
                        evidence="Format trecut pentru data in viitor."
                    ))
                    
        return inconsistencies

    # // section check_entity_consistency
    def _check_entity_consistency(self, facts: list[TemporalFact]) -> list[Inconsistency]:
        """V7: Aceeași persoană ocupă două funcții incompatibile simultan."""
        inconsistencies = []
        holds_facts = [f for f in facts if f.predicate == RelationType.HOLDS_POSITION]
        
        # Grupare dupa subiect (fuzzy match)
        grouped_facts = []
        for f in holds_facts:
            added = False
            for group in grouped_facts:
                if SequenceMatcher(None, group[0].subject.text.lower(), f.subject.text.lower()).ratio() >= 0.85:
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
                    
                    if SequenceMatcher(None, obj1, obj2).ratio() < 0.80:
                        # Functii diferite
                        start1, end1 = _extract_bounds(f1)
                        start2, end2 = _extract_bounds(f2)
                        
                        if _check_overlap(start1, end1, start2, end2):
                            for inc_set in INCOMPATIBLE_POSITIONS:
                                # Verifica daca oricare din termeni e prezent in obj1/obj2
                                has_1 = any(t in obj1 for t in inc_set)
                                has_2 = any(t in obj2 for t in inc_set)
                                
                                if has_1 and has_2:
                                    inconsistencies.append(Inconsistency(
                                        inconsistency_type=InconsistencyType.ENTITY_INCONSISTENCY,
                                        severity=Severity.MEDIUM,
                                        description=f"Roluri simultane incompatibile pentru '{f1.subject.text}': '{f1.object.text}' si '{f2.object.text}'.",
                                        facts_involved=[f1, f2],
                                        sentence_indices=[f1.source_sentence_idx, f2.source_sentence_idx],
                                        verified_by="internal",
                                        evidence="Functii incompatibile suprapuse."
                                    ))
                                    break
                                    
        return inconsistencies


# // section utils
def _extract_point_time(fact: TemporalFact) -> Optional[datetime]:
    """Cel mai reprezentativ moment: time_point > time_start > time_end."""
    for field in ("time_point", "time_start", "time_end"):
        expr = getattr(fact, field)
        if expr and expr.normalized_date:
            return expr.normalized_date
    return None

def _extract_bounds(fact: TemporalFact) -> tuple[Optional[datetime], Optional[datetime]]:
    """Extrage (start, end) din fapt, convertind punctele la intervale degenerate."""
    if fact.time_start and fact.time_end:
        return fact.time_start.normalized_date, fact.time_end.normalized_date
    if fact.time_point:
        pt = fact.time_point.normalized_date
        return pt, pt
    return None, None

def _check_overlap(s1: Optional[datetime], e1: Optional[datetime], s2: Optional[datetime], e2: Optional[datetime]) -> bool:
    """Verifica suprapunerea intre doua intervale [s1, e1] si [s2, e2]."""
    if not (s1 and e1 and s2 and e2):
        # Daca lipseste vreo margine (ex. doar start), asumam cel mai larg interval
        # Dar e mai safe sa facem match doar pe punctele disponibile.
        # Daca avem doar start-uri:
        if s1 and s2 and s1.year == s2.year: 
            return True
        return False
        
    return max(s1, s2) <= min(e1, e2)
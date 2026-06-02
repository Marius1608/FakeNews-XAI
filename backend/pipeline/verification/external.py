"""C3b — External Verification: compares TKG against Wikidata and the Reference KG."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from difflib import SequenceMatcher

from backend.config import REFERENCE_KG_DIR
from backend.pipeline.graph.models import (
    EntityType, InconsistencyType, RelationType, Severity, TemporalFact, Inconsistency,
)
from backend.pipeline.graph.store import TemporalKnowledgeGraph
from backend.pipeline.verification.wikidata import WikidataClient, WikidataFact
from backend.pipeline.verification.web_search import verify_temporal_fact
from backend.pipeline.verification.rss_verifier import RSSVerifier

logger = logging.getLogger(__name__)

REFERENCE_KG_FILE = REFERENCE_KG_DIR / "verified_events.json"
DATE_TOLERANCE_DAYS = 400

# Relations that can be verified against external sources
EXTERNALLY_VERIFIABLE_RELATIONS = {
    RelationType.HOLDS_POSITION,
    RelationType.MEMBER_OF,
    RelationType.OCCURRED_ON,
    RelationType.STARTED,
    RelationType.ENDED,
}

RELATION_TO_WIKIDATA_PROPS = {
    RelationType.HOLDS_POSITION: ["P39"],
    RelationType.MEMBER_OF: ["P463"],
    RelationType.OCCURRED_ON: ["P585", "P580"],
    RelationType.STARTED: ["P571", "P580", "P1619"],
    RelationType.ENDED: ["P576", "P582"],
}


@dataclass
class ExternalVerificationResult:
    inconsistencies: list[Inconsistency] = field(default_factory=list)
    facts_checked: int = 0
    facts_matched: int = 0
    wikidata_queries: int = 0
    web_search_queries: int = 0


class ExternalVerifier:
    """Verifies facts against the Reference KG and Wikidata."""

    def __init__(
        self,
        wikidata_client: Optional[WikidataClient] = None,
        reference_kg_path: Path = REFERENCE_KG_FILE,
        use_wikidata: bool = True,
        use_web_search: bool = False,
        persistent_store=None,
        use_rss: bool = False,
    ):
        self.client = wikidata_client or WikidataClient()
        self.use_wikidata = use_wikidata
        self.use_web_search = use_web_search
        self._reference_kg: dict = self._load_reference_kg(reference_kg_path)
        self._wikidata_cache: dict[str, list[WikidataFact]] = {}
        self._persistent_store = persistent_store
        self._rss_verifier: Optional[RSSVerifier] = RSSVerifier() if use_rss else None

    def verify(self, tkg: TemporalKnowledgeGraph) -> ExternalVerificationResult:
        result = ExternalVerificationResult()

        verifiable = [f for f in tkg.get_all_facts() if f.predicate in EXTERNALLY_VERIFIABLE_RELATIONS and _has_temporal_anchor(f)]
        result.facts_checked = len(verifiable)
        logger.info(f"External verification: {len(verifiable)} eligible facts out of {tkg.fact_count} total.")

        for fact in verifiable:
            result.inconsistencies.extend(self._verify_fact(fact, result))

        # Wikipedia secondary pass: check GENERIC facts from PERSON entities
        # These are excluded from EXTERNALLY_VERIFIABLE_RELATIONS but may still
        # contain verifiable temporal claims about political figures.
        if self.use_web_search:
            generic_person_facts = [
                f for f in tkg.get_all_facts()
                if f.predicate == RelationType.GENERIC
                and f.subject.entity_type.value in ("PERSON", "PER")
                and _has_temporal_anchor(f)
                and f not in verifiable
            ]
            for fact in generic_person_facts:
                result.inconsistencies.extend(
                    self._verify_with_wikipedia(fact, result)
                )

        logger.info(
            f"External verification: {len(result.inconsistencies)} inconsistencies, "
            f"{result.wikidata_queries} Wikidata queries, "
            f"{result.web_search_queries} Wikipedia lookups."
        )
        return result

    # Fact verification
    def _verify_fact(self, fact: TemporalFact, result: ExternalVerificationResult) -> list[Inconsistency]:
        subject_name = fact.subject.text.lower().strip()
        props = RELATION_TO_WIKIDATA_PROPS.get(fact.predicate, [])

        logger.debug(f"External verification [{fact.predicate.value}]: '{fact.subject.text}' -> props={props}")

        # 1. Local Reference KG
        ref_pairs = self._find_in_reference_kg(subject_name)
        # Keep only pairs where the KG entity is actually the same entity as the article subject.
        # The fuzzy match in _find_in_reference_kg uses a substring shortcut that can conflate
        # "clinton" with both "bill clinton" and "hillary clinton". A SequenceMatcher ratio > 0.85
        # on the full names prevents cross-entity comparisons (e.g. Clinton vs Obama facts).
        relevant_ref = [
            ref_fact for kg_key, ref_fact in ref_pairs
            if SequenceMatcher(None, subject_name, kg_key).ratio() > 0.85
            and ref_fact.get("relation") == fact.predicate.value
        ]
        if relevant_ref:
            result.facts_matched += 1
            return self._compare_with_reference(fact, relevant_ref)
        # If Reference KG has no relevant facts, continue to Wikidata

        # 2. Wikidata
        wikidata_confirmed = False
        if self.use_wikidata:
            wikidata_facts = self._fetch_from_wikidata(fact, result)
            if wikidata_facts:
                wikidata_confirmed = True
                result.facts_matched += 1
                direct_incons = self._compare_with_wikidata(fact, wikidata_facts)
                if direct_incons:
                    return direct_incons
                if fact.predicate == RelationType.HOLDS_POSITION:
                    inverse_incons = self._verify_inverse_wikidata(fact, wikidata_facts)
                    if inverse_incons:
                        return inverse_incons

        # 3. Wikipedia fallback (always runs if enabled, regardless of Wikidata result)
        if self.use_web_search:
            return self._verify_with_wikipedia(fact, result)

        # Level 5: RSS Stream — fallback for recent facts not yet in Wikidata
        if self._rss_verifier and not wikidata_confirmed:
            rss_result = self._rss_verifier.verify_fact(fact)
            if rss_result and rss_result.get("found"):
                result.web_search_queries += 1
                logger.info(f"RSS: confirmed '{fact.subject.text}' via {rss_result['source']}")

        return []

    def _verify_with_wikipedia(
        self,
        fact: TemporalFact,
        result: ExternalVerificationResult,
    ) -> list[Inconsistency]:
        """Fallback verification using Wikipedia REST API.

        Runs for any fact with a non-trivial object text and a temporal anchor.
        Accuracy: 83.3% on test cases (confirmed + conflict detection).
        """
        if not fact.object or not fact.object.text or len(fact.object.text.strip()) < 3:
            return []

        fact_year: Optional[int] = None
        if fact.time_point and fact.time_point.normalized_date:
            fact_year = fact.time_point.normalized_date.year
        elif fact.time_start and fact.time_start.normalized_date:
            fact_year = fact.time_start.normalized_date.year
        elif fact.time_end and fact.time_end.normalized_date:
            fact_year = fact.time_end.normalized_date.year

        if not fact_year:
            return []

        result.web_search_queries += 1
        logger.debug(
            f"Wikipedia lookup: {fact.subject.text} as {fact.object.text} in {fact_year}"
        )

        outcome, evidence = verify_temporal_fact(
            entity_name=fact.subject.text,
            position=fact.object.text,
            claimed_year=fact_year,
        )

        if outcome != "conflict":
            return []

        return [
            Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH,
                severity=Severity.MEDIUM,
                description=(
                    f"Wikipedia suggests '{fact.subject.text}' did not hold "
                    f"'{fact.object.text}' in {fact_year}."
                ),
                facts_involved=[fact],
                sentence_indices=[fact.source_sentence_idx],
                verified_by="wikipedia",
                evidence=f"Wikipedia: {evidence or 'no evidence text'}",
            )
        ]

    def _subject_matches_wikidata_entity(self, fact_subject: str, wikidata_entity_label: str) -> bool:
        """Returns True if the fact subject matches the Wikidata entity.
        Prevents cross-entity false positives (e.g. 'Biden' vs 'Obama')."""
        fact_lower = fact_subject.lower().strip()
        wiki_lower = wikidata_entity_label.lower().strip()

        if not fact_lower or not wiki_lower:
            return True

        if fact_lower in wiki_lower or wiki_lower in fact_lower:
            return True

        fact_last = fact_lower.split()[-1] if fact_lower.split() else ""
        wiki_last = wiki_lower.split()[-1] if wiki_lower.split() else ""
        if fact_last and wiki_last and fact_last == wiki_last:
            return True

        return False

    def _find_in_reference_kg(self, subject_name: str) -> list[tuple[str, dict]]:
        """Search the Reference KG — returns (kg_entity_key, fact_dict) pairs."""
        pairs: list[tuple[str, dict]] = []
        for key, facts in self._reference_kg.items():
            if _fuzzy_entity_match(subject_name, key):
                for fact in facts:
                    pairs.append((key, fact))
        return pairs

    # Wikidata fetch with 3-level cache
    def _fetch_from_wikidata(self, fact: TemporalFact, result: ExternalVerificationResult) -> list[WikidataFact]:
        cache_key = fact.subject.text.lower().strip()

        logger.debug(f"Wikidata cache {'HIT' if cache_key in self._wikidata_cache else 'MISS'} for entity '{cache_key}'")

        # 1. In-memory cache (fastest)
        if cache_key in self._wikidata_cache:
            return self._wikidata_cache[cache_key]

        # 2. Neo4j persistent cache (if available)
        if self._persistent_store and hasattr(self._persistent_store, "get_cached_wikidata"):
            cached = self._persistent_store.get_cached_wikidata(cache_key)
            if cached is not None:
                wf_list = [_dict_to_wikidata_fact(d) for d in cached]
                self._wikidata_cache[cache_key] = wf_list
                logger.debug(f"Wikidata Neo4j cache hit: '{cache_key}' ({len(wf_list)} facts)")
                return wf_list

        # 3. Live Wikidata SPARQL query
        # search_entity_full returns {id, label, description} — same API call as
        # search_entity, but includes the real label ("Barack Obama", not just QID "Q76").
        search_results = self.client.search_entity_full(fact.subject.text)
        result.wikidata_queries += 1
        if not search_results:
            self._wikidata_cache[cache_key] = []
            return []

        entity_id = search_results[0]["id"]
        wikidata_entity_label = search_results[0].get("label", "")

        # Cross-entity guard: verify Wikidata returned the correct entity before
        # running SPARQL — saves an API call if there is a mismatch.
        # Correct: "Biden" vs "Joe Biden" → True (last-word match)
        # False positive: "Biden" vs "Barack Obama" → False (skip)
        if not self._subject_matches_wikidata_entity(fact.subject.text, wikidata_entity_label):
            logger.debug(
                f"Cross-entity skip: '{fact.subject.text}' vs Wikidata '{wikidata_entity_label}' — fapte ignorate"
            )
            self._wikidata_cache[cache_key] = []
            return []

        # Inverse Wikidata: fetch ALL temporal facts for the entity at once
        # (P39=positions held, P463=member of) — not just the matched relation.
        # This allows detecting contradictions even when C1 misclassifies the relation.
        wikidata_facts = self.client.get_temporal_facts(entity_id, ["P39", "P463"])
        result.wikidata_queries += 1

        for wf in wikidata_facts:
            wf.entity_label = fact.subject.text

        self._wikidata_cache[cache_key] = wikidata_facts

        # Persist result to Neo4j cache after live fetch
        if self._persistent_store and hasattr(self._persistent_store, "cache_wikidata_result"):
            try:
                serialized = [_wikidata_fact_to_dict(wf) for wf in wikidata_facts]
                self._persistent_store.cache_wikidata_result(cache_key, serialized)
            except Exception as e:
                logger.debug(f"Wikidata Neo4j cache write failed: {e}")

        return wikidata_facts

    # Comparison helpers
    def _compare_with_reference(self, fact: TemporalFact, ref_facts: list[dict]) -> list[Inconsistency]:
        inconsistencies = []
        for ref in ref_facts:
            if ref.get("relation") != fact.predicate.value:
                continue
            incons = _compare_temporal_intervals(
                fact=fact,
                ext_start=_parse_date_str(ref.get("time_start")),
                ext_end=_parse_date_str(ref.get("time_end")),
                ext_point=_parse_date_str(ref.get("time_point")),
                source="reference_kg",
                evidence=f"Reference KG: {ref.get('value', '')} [{ref.get('time_start', '?')} -> {ref.get('time_end', '?')}]",
            )
            if incons:
                inconsistencies.append(incons)
        return inconsistencies

    def _compare_with_wikidata(self, fact: TemporalFact, wikidata_facts: list[WikidataFact]) -> list[Inconsistency]:
        inconsistencies = []
        obj_text = fact.object.text.lower()

        if fact.predicate == RelationType.HOLDS_POSITION:
            # For HOLDS_POSITION only compare against similar positions — no fallback
            # to all entity positions (avoids false positives: Biden VP vs Biden Senator).
            relevant = [
                wf for wf in wikidata_facts
                if SequenceMatcher(None, obj_text, wf.value_label.lower()).ratio() > 0.6
                or obj_text in wf.value_label.lower()
                or wf.value_label.lower() in obj_text
            ]
            if not relevant:
                logger.debug(f"  HOLDS_POSITION skip: no similar position for '{fact.object.text}' in Wikidata")
                return []
        else:
            relevant = [wf for wf in wikidata_facts if _fuzzy_entity_match(obj_text, wf.value_label)]
            if not relevant:
                relevant = wikidata_facts

        for wf in relevant[:3]:
            logger.debug(f"  Wikidata match: {wf.value_label} [{wf.time_start} -> {wf.time_end}]")
            incons = _compare_temporal_intervals(
                fact=fact, ext_start=wf.time_start, ext_end=wf.time_end, ext_point=wf.time_point,
                source="wikidata",
                evidence=f"Wikidata ({wf.entity_id}): {wf.property_label} = {wf.value_label} [{wf.time_start.year if wf.time_start else '?'} -> {wf.time_end.year if wf.time_end else '?'}]",
            )
            if incons:
                f_s = fact.time_start.normalized_date.year if fact.time_start and fact.time_start.normalized_date else "?"
                f_e = fact.time_end.normalized_date.year if fact.time_end and fact.time_end.normalized_date else "?"
                w_s = wf.time_start.year if wf.time_start else "?"
                w_e = wf.time_end.year if wf.time_end else "?"
                logger.debug(f"  MISMATCH: article={f_s}->{f_e} vs wikidata={w_s}->{w_e}")
                inconsistencies.append(incons)

        return inconsistencies

    def _verify_inverse_wikidata(
        self, fact: TemporalFact, wikidata_facts: list[WikidataFact]
    ) -> list[Inconsistency]:
        """
        Inverse check: verifies that no Wikidata fact for this entity
        directly contradicts what the article claims.

        Detects two patterns:
        - CONFLICT: Wikidata has the same position but with a different interval
        - NOT_FOUND: article claims a position that does not exist in Wikidata at all
        """
        if not wikidata_facts:
            return []

        obj_text = fact.object.text.lower().strip()
        inconsistencies = []

        # Find Wikidata facts that mention the same position/role
        matching = [
            wf for wf in wikidata_facts
            if _word_overlap(obj_text, wf.value_label.lower())
        ]

        if not matching:
            # Position not found in Wikidata at all — flag as LOW severity
            # (Wikidata may be incomplete, so don't flag as HIGH)
            fact_time = (
                fact.time_point.normalized_date if fact.time_point else
                fact.time_start.normalized_date if fact.time_start else None
            )
            if fact_time:
                inconsistencies.append(Inconsistency(
                    inconsistency_type=InconsistencyType.ENTITY_INCONSISTENCY,
                    severity=Severity.LOW,
                    description=f"Position '{fact.object.text}' for '{fact.subject.text}' not found in Wikidata.",
                    facts_involved=[fact],
                    sentence_indices=[fact.source_sentence_idx],
                    verified_by="wikidata_inverse",
                    evidence=f"Wikidata has {len(wikidata_facts)} facts for this entity; none match '{fact.object.text}'.",
                ))
            return inconsistencies

        # Check if the article's time falls within any matching Wikidata interval
        fact_time = (
            fact.time_point.normalized_date if fact.time_point else
            fact.time_start.normalized_date if fact.time_start else None
        )
        if not fact_time:
            return []

        confirmed = False
        for wf in matching:
            wf_start = wf.time_start
            wf_end = wf.time_end or datetime(datetime.now().year + 1, 1, 1)
            if wf_start and wf_start <= fact_time <= wf_end:
                confirmed = True
                break

        if not confirmed:
            # The position exists in Wikidata but not in the claimed period
            best = matching[0]
            wf_start_y = best.time_start.year if best.time_start else "?"
            wf_end_y = best.time_end.year if best.time_end else "present"
            inconsistencies.append(Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH,
                severity=Severity.HIGH,
                description=(
                    f"'{fact.subject.text}' as '{fact.object.text}' in {fact_time.year} "
                    f"conflicts with Wikidata: that position held [{wf_start_y} -> {wf_end_y}]."
                ),
                facts_involved=[fact],
                sentence_indices=[fact.source_sentence_idx],
                verified_by="wikidata_inverse",
                evidence=f"Wikidata: {best.value_label} [{wf_start_y} -> {wf_end_y}].",
            ))

        return inconsistencies

    # Reference KG loading
    def _load_reference_kg(self, path: Path) -> dict:
        if not path.exists():
            logger.warning(f"Reference KG not found at {path}.")
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            normalized = {k.lower(): v for k, v in data.items()}
            logger.info(f"Reference KG loaded: {len(normalized)} entities.")
            return normalized
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Reference KG load error: {e}")
            return {}


# Helper functions
def _fuzzy_entity_match(name1: str, name2: str, threshold: float = 0.80) -> bool:
    """Compare two entity names using fuzzy matching."""
    n1, n2 = name1.lower().strip(), name2.lower().strip()
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    if n1 in n2 or n2 in n1:
        return True
    return SequenceMatcher(None, n1, n2).ratio() >= threshold

def _compare_temporal_intervals(
    fact: TemporalFact, ext_start: Optional[datetime], ext_end: Optional[datetime],
    ext_point: Optional[datetime], source: str, evidence: str,
) -> Optional[Inconsistency]:
    """Compare the article interval against an external source."""
    tolerance = timedelta(days=DATE_TOLERANCE_DAYS)
    fact_start = fact.time_start.normalized_date if fact.time_start else None
    fact_end = fact.time_end.normalized_date if fact.time_end else None
    fact_point = fact.time_point.normalized_date if fact.time_point else None

    if fact_point and ext_start and ext_end:
        if not (ext_start - tolerance <= fact_point <= ext_end + tolerance):
            return Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH, severity=Severity.HIGH,
                description=f"Article date ({fact_point.year}) does not match {source} interval [{ext_start.year} -> {ext_end.year}].",
                facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                verified_by=source, evidence=evidence,
            )

    if fact_start and fact_end and ext_start and ext_end:
        if fact_end < ext_start - tolerance or fact_start > ext_end + tolerance:
            return Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH, severity=Severity.HIGH,
                description=f"Interval [{fact_start.year} -> {fact_end.year}] does not overlap with {source} [{ext_start.year} -> {ext_end.year}].",
                facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                verified_by=source, evidence=evidence,
            )

    if fact_point and ext_point:
        if abs((fact_point - ext_point).days) > DATE_TOLERANCE_DAYS:
            return Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH, severity=Severity.MEDIUM,
                description=f"Article date ({fact_point.year}) differs from {source} ({ext_point.year}).",
                facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                verified_by=source, evidence=evidence,
            )
    return None

def _has_temporal_anchor(fact: TemporalFact) -> bool:
    return any(getattr(fact, f) and getattr(fact, f).normalized_date for f in ("time_point", "time_start", "time_end"))

def _word_overlap(text1: str, text2: str, min_overlap: int = 1) -> bool:
    """True if the two strings share at least min_overlap meaningful words."""
    STOPWORDS = {"of", "the", "a", "an", "and", "or", "in", "at", "to", "for",
                 "united", "states", "u.s.", "us"}
    words1 = {w for w in text1.lower().split() if w not in STOPWORDS and len(w) > 2}
    words2 = {w for w in text2.lower().split() if w not in STOPWORDS and len(w) > 2}
    return len(words1 & words2) >= min_overlap

def _parse_date_str(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


# Wikidata serialization helpers

def _wikidata_fact_to_dict(wf: WikidataFact) -> dict:
    return {
        "entity_id": wf.entity_id,
        "entity_label": wf.entity_label,
        "property_id": wf.property_id,
        "property_label": wf.property_label,
        "value_label": wf.value_label,
        "time_start": wf.time_start.isoformat() if wf.time_start else None,
        "time_end": wf.time_end.isoformat() if wf.time_end else None,
        "time_point": wf.time_point.isoformat() if wf.time_point else None,
    }


def _dict_to_wikidata_fact(d: dict) -> WikidataFact:
    def parse_iso(s: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(s) if s else None
    return WikidataFact(
        entity_id=d.get("entity_id", ""),
        entity_label=d.get("entity_label", ""),
        property_id=d.get("property_id", ""),
        property_label=d.get("property_label", ""),
        value_label=d.get("value_label", ""),
        time_start=parse_iso(d.get("time_start")),
        time_end=parse_iso(d.get("time_end")),
        time_point=parse_iso(d.get("time_point")),
    )

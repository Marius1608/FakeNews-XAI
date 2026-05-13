"""C3b — Verificare Externa: compara TKG cu Wikidata si Reference KG."""

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

logger = logging.getLogger(__name__)

REFERENCE_KG_FILE = REFERENCE_KG_DIR / "verified_events.json"
DATE_TOLERANCE_DAYS = 365

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


class ExternalVerifier:
    """Verifies facts against the Reference KG and Wikidata."""

    def __init__(
        self,
        wikidata_client: Optional[WikidataClient] = None,
        reference_kg_path: Path = REFERENCE_KG_FILE,
        use_wikidata: bool = True,
        persistent_store=None,
    ):
        self.client = wikidata_client or WikidataClient()
        self.use_wikidata = use_wikidata
        self._reference_kg: dict = self._load_reference_kg(reference_kg_path)
        self._wikidata_cache: dict[str, list[WikidataFact]] = {}
        self._persistent_store = persistent_store

    def verify(self, tkg: TemporalKnowledgeGraph) -> ExternalVerificationResult:
        result = ExternalVerificationResult()

        verifiable = [f for f in tkg.get_all_facts() if f.predicate in EXTERNALLY_VERIFIABLE_RELATIONS and _has_temporal_anchor(f)]
        result.facts_checked = len(verifiable)
        logger.info(f"External verification: {len(verifiable)} eligible facts out of {tkg.fact_count} total.")

        for fact in verifiable:
            result.inconsistencies.extend(self._verify_fact(fact, result))

        logger.info(f"External verification: {len(result.inconsistencies)} inconsistencies, {result.wikidata_queries} Wikidata queries.")
        return result

    # Fact verification
    def _verify_fact(self, fact: TemporalFact, result: ExternalVerificationResult) -> list[Inconsistency]:
        subject_name = fact.subject.text.lower().strip()
        props = RELATION_TO_WIKIDATA_PROPS.get(fact.predicate, [])

        logger.debug(f"External verification [{fact.predicate.value}]: '{fact.subject.text}' -> props={props}")

        # 1. Local Reference KG
        ref_facts = self._find_in_reference_kg(subject_name)
        # Filter to facts with the same relation
        relevant_ref = [r for r in ref_facts if r.get("relation") == fact.predicate.value]
        if relevant_ref:
            result.facts_matched += 1
            return self._compare_with_reference(fact, relevant_ref)
        # If Reference KG has no relevant facts, continue to Wikidata

        # 2. Wikidata
        if not self.use_wikidata:
            return []

        wikidata_facts = self._fetch_from_wikidata(fact, result)
        if wikidata_facts:
            result.facts_matched += 1
            return self._compare_with_wikidata(fact, wikidata_facts)

        return []

    def _find_in_reference_kg(self, subject_name: str) -> list[dict]:
        """Search the Reference KG using fuzzy matching."""
        facts = []
        for key, value in self._reference_kg.items():
            if _fuzzy_entity_match(subject_name, key):
                facts.extend(value)
        return facts

    # Wikidata fetch with 3-level cache
    def _fetch_from_wikidata(self, fact: TemporalFact, result: ExternalVerificationResult) -> list[WikidataFact]:
        cache_key = fact.subject.text.lower().strip()

        # 1. In-memory cache (fastest)
        if cache_key in self._wikidata_cache:
            logger.debug(f"Wikidata cache hit (memory): '{cache_key}'")
            return self._wikidata_cache[cache_key]

        # 2. Neo4j persistent cache (if available)
        if self._persistent_store and hasattr(self._persistent_store, "get_cached_wikidata"):
            cached = self._persistent_store.get_cached_wikidata(cache_key)
            if cached is not None:
                wf_list = [_dict_to_wikidata_fact(d) for d in cached]
                self._wikidata_cache[cache_key] = wf_list
                logger.debug(f"Wikidata cache hit (Neo4j): '{cache_key}' ({len(wf_list)} facts)")
                return wf_list

        # 3. Live Wikidata SPARQL query
        entity_id = self.client.search_entity(fact.subject.text)
        result.wikidata_queries += 1
        if not entity_id:
            self._wikidata_cache[cache_key] = []
            return []

        props = RELATION_TO_WIKIDATA_PROPS.get(fact.predicate, [])
        wikidata_facts = self.client.get_temporal_facts(entity_id, props)
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

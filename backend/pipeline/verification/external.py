"""C3b — Verificare Externa: compara TKG cu Wikidata si Reference KG."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from backend.config import REFERENCE_KG_DIR
from backend.pipeline.graph.models import (
    EntityType, InconsistencyType, RelationType, Severity, TemporalFact, Inconsistency,
)
from backend.pipeline.graph.store import TemporalKnowledgeGraph
from backend.pipeline.verification.wikidata import WikidataClient, WikidataFact

logger = logging.getLogger(__name__)

REFERENCE_KG_FILE = REFERENCE_KG_DIR / "verified_events.json"
DATE_TOLERANCE_DAYS = 365  # toleranta 1 an pentru articole care mentioneaza doar anul

# Doar aceste relatii au proprietati Wikidata verificabile
EXTERNALLY_VERIFIABLE_RELATIONS = {RelationType.HOLDS_POSITION, RelationType.MEMBER_OF}
RELATION_TO_WIKIDATA_PROPS = {
    RelationType.HOLDS_POSITION: ["P39"],
    RelationType.MEMBER_OF: ["P463"],
}


@dataclass
class ExternalVerificationResult:
    inconsistencies: list[Inconsistency] = field(default_factory=list)
    facts_checked: int = 0
    facts_matched: int = 0
    wikidata_queries: int = 0


class ExternalVerifier:
    """
    Verifica fapte HOLDS_POSITION/MEMBER_OF contra:
    1. Reference KG local (verified_events.json) — fara request
    2. Wikidata SPARQL — daca nu gaseste in Reference KG
    """

    def __init__(self, wikidata_client: Optional[WikidataClient] = None, reference_kg_path: Path = REFERENCE_KG_FILE, use_wikidata: bool = True):
        self.client = wikidata_client or WikidataClient()
        self.use_wikidata = use_wikidata
        self._reference_kg: dict = self._load_reference_kg(reference_kg_path)

    def verify(self, tkg: TemporalKnowledgeGraph) -> ExternalVerificationResult:
        result = ExternalVerificationResult()

        verifiable = [f for f in tkg.get_all_facts() if f.predicate in EXTERNALLY_VERIFIABLE_RELATIONS and _has_temporal_anchor(f)]
        result.facts_checked = len(verifiable)
        logger.info(f"Verificare externa: {len(verifiable)} fapte eligibile din {tkg.fact_count} total.")

        for fact in verifiable:
            result.inconsistencies.extend(self._verify_fact(fact, result))

        logger.info(f"Verificare externa: {len(result.inconsistencies)} inconsistente, {result.wikidata_queries} query-uri Wikidata.")
        return result

    def _verify_fact(self, fact: TemporalFact, result: ExternalVerificationResult) -> list[Inconsistency]:
        """Consulta Reference KG apoi Wikidata pentru un fapt."""
        subject_name = fact.subject.text.lower().strip()

        # 1. Reference KG local
        ref_facts = self._reference_kg.get(subject_name, [])
        if ref_facts:
            result.facts_matched += 1
            return self._compare_with_reference(fact, ref_facts)

        # 2. Wikidata
        if not self.use_wikidata:
            return []
        wikidata_facts = self._fetch_from_wikidata(fact, result)
        if wikidata_facts:
            result.facts_matched += 1
            return self._compare_with_wikidata(fact, wikidata_facts)
        return []

    def _fetch_from_wikidata(self, fact: TemporalFact, result: ExternalVerificationResult) -> list[WikidataFact]:
        candidates = self.client.search_entity(fact.subject.text)
        result.wikidata_queries += 1
        if not candidates:
            return []

        entity_id = candidates[0]["id"]
        entity_label = candidates[0]["label"]
        props = RELATION_TO_WIKIDATA_PROPS.get(fact.predicate, [])
        wikidata_facts = self.client.get_temporal_facts(entity_id, props)
        result.wikidata_queries += 1

        for wf in wikidata_facts:
            wf.entity_label = entity_label
        return wikidata_facts

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
                evidence=f"Reference KG: {ref.get('value', '')} [{ref.get('time_start', '?')} → {ref.get('time_end', '?')}]",
            )
            if incons:
                inconsistencies.append(incons)
        return inconsistencies

    def _compare_with_wikidata(self, fact: TemporalFact, wikidata_facts: list[WikidataFact]) -> list[Inconsistency]:
        inconsistencies = []
        obj_text = fact.object.text.lower()
        relevant = [wf for wf in wikidata_facts if obj_text in wf.value_label.lower() or wf.value_label.lower() in obj_text]
        if not relevant:
            relevant = wikidata_facts

        for wf in relevant[:3]:
            incons = _compare_temporal_intervals(
                fact=fact, ext_start=wf.time_start, ext_end=wf.time_end, ext_point=wf.time_point,
                source="wikidata",
                evidence=f"Wikidata ({wf.entity_id}): {wf.property_label} = {wf.value_label} [{wf.time_start.year if wf.time_start else '?'} → {wf.time_end.year if wf.time_end else '?'}]",
            )
            if incons:
                inconsistencies.append(incons)
        return inconsistencies

    def _load_reference_kg(self, path: Path) -> dict:
        if not path.exists():
            logger.warning(f"Reference KG negasit la {path}.")
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            normalized = {k.lower(): v for k, v in data.items()}
            logger.info(f"Reference KG incarcat: {len(normalized)} entitati.")
            return normalized
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Eroare Reference KG: {e}")
            return {}


# ── Helpers ──
def _compare_temporal_intervals(
    fact: TemporalFact, ext_start: Optional[datetime], ext_end: Optional[datetime],
    ext_point: Optional[datetime], source: str, evidence: str,
) -> Optional[Inconsistency]:
    """Compara interval articol vs sursa externa (cu toleranta DATE_TOLERANCE_DAYS)."""
    tolerance = timedelta(days=DATE_TOLERANCE_DAYS)
    fact_start = fact.time_start.normalized_date if fact.time_start else None
    fact_end = fact.time_end.normalized_date if fact.time_end else None
    fact_point = fact.time_point.normalized_date if fact.time_point else None

    # Caz 1: articolul are time_point, sursa are interval
    if fact_point and ext_start and ext_end:
        if not (ext_start - tolerance <= fact_point <= ext_end + tolerance):
            return Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH, severity=Severity.HIGH,
                description=f"Data din articol ({fact_point.year}) nu corespunde intervalului {source} [{ext_start.year} → {ext_end.year}].",
                facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                verified_by=source, evidence=evidence,
            )

    # Caz 2: ambele au interval — verificam suprapunerea
    if fact_start and fact_end and ext_start and ext_end:
        if fact_end < ext_start - tolerance or fact_start > ext_end + tolerance:
            return Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH, severity=Severity.HIGH,
                description=f"Intervalul [{fact_start.year} → {fact_end.year}] nu se suprapune cu {source} [{ext_start.year} → {ext_end.year}].",
                facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                verified_by=source, evidence=evidence,
            )

    # Caz 3: ambele au time_point
    if fact_point and ext_point:
        if abs((fact_point - ext_point).days) > DATE_TOLERANCE_DAYS:
            return Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH, severity=Severity.MEDIUM,
                description=f"Data din articol ({fact_point.year}) difera de {source} ({ext_point.year}).",
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
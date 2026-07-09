"""C3b — External Verification: compares TKG against Wikidata and the Reference KG."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from difflib import SequenceMatcher

from backend import runtime_settings
from backend.config import REFERENCE_KG_DIR
from backend.pipeline.graph.models import (
    InconsistencyType, RelationType, Severity, TemporalFact, Inconsistency,
)
from backend.pipeline.graph.store import TemporalKnowledgeGraph
from backend.pipeline.verification.wikidata import WikidataClient, WikidataFact
from backend.pipeline.verification.web_search import verify_temporal_fact
from backend.pipeline.verification.rss_verifier import RSSVerifier

logger = logging.getLogger(__name__)

# Sentinel: distinguishes "argument not passed to verify()" (keep the value set
# in the constructor) from an explicit None (e.g. persistent_store=None).
_UNSET = object()

REFERENCE_KG_FILE = REFERENCE_KG_DIR / "verified_events.json"

# Reserved key under which canonical events (historical_events) are stored
# in the loaded Reference KG dict — not a real entity name.
_EVENTS_KG_KEY = "__historical_events__"

# Metadata keys from the verified_events.json wrapper — not entities.
_REFERENCE_KG_META_KEYS = {
    "generated_at", "total_entities", "total_facts", "failed_count",
    "failed", "manual_facts_count", "updated_at",
}

# Wikidata property -> normalized relation (for facts in the `entities` list).
_WIKIDATA_PROP_TO_RELATION = {
    "P39": "holds_position",
    "P463": "member_of",
}

# Common words ignored when matching event names in _check_event_date.
# Without them, overlaps like "the"/"of" would count as distinctive matches.
_EVENT_MATCH_STOPWORDS = {
    "the", "a", "an", "of", "in", "to", "and", "or", "for", "by",
    "as", "at", "on", "was", "were", "had", "has", "been",
}

# Action verbs and event nouns required in the fact object — a person name
# without action context (e.g. "Trump") does not describe a datable event;
# event nouns (attack, riot) are equally distinctive.
_EVENT_ACTION_VERBS = {
    "signed", "passed", "killed", "created", "founded", "started", "ended",
    "adopted", "confirmed", "authorized", "launched", "collapsed", "attacked",
    "invaded", "approved", "agreed", "established", "resigned", "released",
    "ruled", "fell", "won", "elected", "inaugurated", "nominated", "impeached",
    "acquitted", "ratified", "enacted", "declared", "withdrawn", "withdrew",
    "deployed", "negotiated", "concluded", "reached", "achieved", "overthrown",
    "liberated",
    # substantive-eveniment distincte — nu apar in simple nume de persoane
    "attack", "riot", "bombing", "massacre", "assassination", "siege",
    "coup", "uprising", "invasion", "crash", "collapse", "scandal",
}

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
    rss_verifications: list[dict] = field(default_factory=list)


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

    def verify(
        self,
        tkg: TemporalKnowledgeGraph,
        persistent_store=_UNSET,
        use_web_search=_UNSET,
        use_rss=_UNSET,
    ) -> ExternalVerificationResult:
        """Verify the TKG facts against external sources.

        Request-scoped options (store, web search, RSS) can be passed per call;
        the orchestrator passes them on every run, so the long-lived verifier
        instance never keeps a store that a router has already closed. Callers
        that omit them (notebooks, direct use) keep the constructor values.
        """
        if persistent_store is not _UNSET:
            self._persistent_store = persistent_store
        if use_web_search is not _UNSET:
            self.use_web_search = use_web_search
        if use_rss is not _UNSET:
            if use_rss:
                # Keep an existing verifier so its feed cache survives across requests
                self._rss_verifier = self._rss_verifier or RSSVerifier()
            else:
                self._rss_verifier = None

        result = ExternalVerificationResult()

        verifiable = [f for f in tkg.get_all_facts() if f.predicate in EXTERNALLY_VERIFIABLE_RELATIONS and _has_temporal_anchor(f)]
        result.facts_checked = len(verifiable)
        logger.info(f"External verification: {len(verifiable)} eligible facts out of {tkg.fact_count} total.")

        for fact in verifiable:
            result.inconsistencies.extend(self._verify_fact(fact, result, prefetched_facts={}))

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
    def _verify_fact(self, fact: TemporalFact, result: ExternalVerificationResult, prefetched_facts=None) -> list[Inconsistency]:
        subject_name = fact.subject.text.lower().strip()
        props = RELATION_TO_WIKIDATA_PROPS.get(fact.predicate, [])

        logger.debug(f"External verification [{fact.predicate.value}]: '{fact.subject.text}' -> props={props}")

        # 0. Canonical event dates (OCCURRED_ON / GENERIC only) — runs before the
        # standard Reference KG lookup so a misdated historical event is caught
        # even when the subject is the event name rather than a known entity.
        if fact.predicate in {RelationType.OCCURRED_ON, RelationType.GENERIC}:
            event_incons = self._check_event_date(fact, result)
            if event_incons:
                return event_incons

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

        # 1b. Cross-entity overlap in Reference KG (HOLDS_POSITION only)
        if fact.predicate == RelationType.HOLDS_POSITION:
            cross_incons = self._check_cross_entity_overlap(fact, result)
            if cross_incons:
                return cross_incons

        # 2. Wikidata
        wikidata_confirmed = False
        if self.use_wikidata:
            wikidata_facts = self._fetch_from_wikidata(fact, result, prefetched_facts=prefetched_facts)
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

        # Wikipedia fallback — disabled in production (introduced false positives)
        if self.use_web_search:
            return self._verify_with_wikipedia(fact, result)

        # Level 5: RSS Stream — fallback for recent facts not yet in Wikidata
        if self._rss_verifier and not wikidata_confirmed:
            rss_result = self._rss_verifier.verify_fact(fact)
            if rss_result and rss_result.get("found"):
                result.web_search_queries += 1
                logger.info(f"RSS: confirmed '{fact.subject.text}' via {rss_result['feed_url']}")
                result.rss_verifications.append(rss_result)

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

    @staticmethod
    def _same_role_category(role1: str, role2: str) -> bool:
        US_ROLES = {"president of the united states", "vice president of the united states"}
        UK_ROLES = {"prime minister of the united kingdom"}
        EU_ROLES = {"president of france", "prime minister of poland", "president of the european council"}

        r1 = role1.lower()
        r2 = role2.lower()
        for role_set in [US_ROLES, UK_ROLES, EU_ROLES]:
            if any(r in r1 for r in role_set) and any(r in r2 for r in role_set):
                return True
        return False

    def _check_cross_entity_overlap(self, fact: TemporalFact, result: ExternalVerificationResult) -> list[Inconsistency]:
        subject_name = fact.subject.text.lower().strip()
        fact_start = fact.time_start.normalized_date if fact.time_start else None
        fact_end = fact.time_end.normalized_date if fact.time_end else None
        fact_point = fact.time_point.normalized_date if fact.time_point else None

        # Normalise to an interval for the article claim
        interval_start = fact_start or fact_point
        interval_end = fact_end or fact_point
        if not interval_start or not interval_end:
            return []

        for kg_key, kg_facts in self._reference_kg.items():
            if not isinstance(kg_facts, list):
                continue
            # Skip same-entity entries
            if SequenceMatcher(None, subject_name, kg_key).ratio() > 0.85:
                continue
            for kg_fact in kg_facts:
                if not isinstance(kg_fact, dict):
                    continue
                if kg_fact.get("relation") != fact.predicate.value:
                    continue
                other_start = _parse_date_str(kg_fact.get("time_start"))
                other_end = _parse_date_str(kg_fact.get("time_end"))
                if not other_start or not other_end:
                    continue
                # Only compare roles in the same country/category to avoid
                # false positives like Reagan (US) vs Thatcher (UK) overlap.
                fact_role = fact.object.text if fact.object else ""
                other_role = kg_fact.get("value", "")
                if not self._same_role_category(fact_role, other_role):
                    continue
                # Article interval must fall fully inside the other entity's mandate
                if other_start <= interval_start and other_end >= interval_end:
                    fs = interval_start.year
                    fe = interval_end.year
                    os_ = other_start.year
                    oe = other_end.year
                    other_entity = kg_fact.get("value", kg_key)
                    logger.debug(
                        f"Cross-entity overlap: '{fact.subject.text}' [{fs}->{fe}] "
                        f"inside '{other_entity}' mandate [{os_}->{oe}]"
                    )
                    return [Inconsistency(
                        inconsistency_type=InconsistencyType.DATE_MISMATCH,
                        severity=Severity.HIGH,
                        description=(
                            f"Interval [{fs} -> {fe}] for '{fact.subject.text}' "
                            f"overlaps with {other_entity}'s known mandate [{os_} -> {oe}]."
                        ),
                        facts_involved=[fact],
                        sentence_indices=[fact.source_sentence_idx],
                        verified_by="reference_kg_cross",
                        evidence=f"Reference KG: {other_entity} held this position [{os_} -> {oe}].",
                    )]
        return []

    def _check_event_date(self, fact: TemporalFact, result: ExternalVerificationResult) -> list[Inconsistency]:
        """Check OCCURRED_ON/GENERIC facts against canonical event dates in Reference KG."""
        if not fact.object or not fact.object.text:
            return []
        obj_text = fact.object.text.lower().strip()
        logger.debug(f"_check_event_date: object='{fact.object.text}' predicate={fact.predicate.value}")

        # Filter 1: minimum 2 words — single-word objects ("Trump") produce too
        # many false positives; 2 distinctive words ("Capitol attack") are safe.
        if len(obj_text.split()) < 2:
            logger.debug(f"  skip: object '{obj_text}' has <2 words (Filter 1)")
            return []

        # Filter 5: object must contain an action verb or event noun; otherwise
        # it is just an entity name ("Bill Clinton") with no datable event context.
        if not (set(obj_text.split()) & _EVENT_ACTION_VERBS):
            logger.debug(f"  skip: object '{obj_text}' has no action keyword (Filter 5)")
            return []

        fact_time = None
        if fact.time_point and fact.time_point.normalized_date:
            fact_time = fact.time_point.normalized_date
        elif fact.time_start and fact.time_start.normalized_date:
            fact_time = fact.time_start.normalized_date
        if not fact_time:
            logger.debug(f"  skip: object '{obj_text}' has no normalized date")
            return []

        logger.debug(f"  candidate event '{obj_text}' @ {fact_time.date()} — scanning canonical events")
        event_tolerance_days = runtime_settings.get_value("canonical_event_tolerance_days")
        event_similarity_threshold = runtime_settings.get_value("canonical_event_similarity_threshold")

        for kg_key, kg_facts in self._reference_kg.items():
            if not isinstance(kg_facts, list):
                continue
            for kg_fact in kg_facts:
                if not isinstance(kg_fact, dict):
                    continue
                if kg_fact.get("relation") != "occurred_on":
                    continue
                kg_value = kg_fact.get("value", "").lower()
                if not kg_value:
                    continue

                # Filter 4: at least 2 distinctive words (excluding stopwords) must overlap.
                words_obj = set(obj_text.split())
                words_kg = set(kg_value.split())
                shared = (words_obj & words_kg) - _EVENT_MATCH_STOPWORDS
                if len(shared) < 2:
                    continue

                # Filter 2/3: high thresholds — fuzzy ratio >= threshold OR word overlap
                # >= 0.65 of the article object words.
                ratio = SequenceMatcher(None, obj_text, kg_value).ratio()
                overlap = len(words_obj & words_kg) / max(len(words_obj), 1)
                if ratio < event_similarity_threshold and overlap < 0.65:
                    logger.debug(
                        f"    skip kg='{kg_value}': shared={shared} but ratio={ratio:.2f} "
                        f"<{event_similarity_threshold} and overlap={overlap:.2f} <0.65 (Filter 2/3)"
                    )
                    continue

                logger.debug(
                    f"    matched kg='{kg_value}' shared={shared} ratio={ratio:.2f} overlap={overlap:.2f}"
                )
                kg_point = _parse_date_str(kg_fact.get("time_point"))
                if not kg_point:
                    logger.debug(f"    skip kg='{kg_value}': no parseable time_point")
                    continue
                delta = abs((fact_time - kg_point).days)
                if delta > event_tolerance_days:
                    logger.debug(
                        f"    DATE_MISMATCH: article={fact_time.year} vs kg={kg_point.year} "
                        f"(delta={delta}d > {event_tolerance_days})"
                    )
                    result.wikidata_queries += 1
                    return [Inconsistency(
                        inconsistency_type=InconsistencyType.DATE_MISMATCH,
                        severity=Severity.HIGH,
                        description=f"Event '{fact.object.text}' dated {fact_time.year} in article but actually occurred {kg_point.year} ({kg_fact.get('value', '')}).",
                        facts_involved=[fact],
                        sentence_indices=[fact.source_sentence_idx],
                        verified_by="reference_kg_event",
                        evidence=f"Reference KG: {kg_fact.get('value')} = {kg_point.date()}",
                    )]
                logger.debug(
                    f"    within tolerance: article={fact_time.year} vs kg={kg_point.year} "
                    f"(delta={delta}d <= {event_tolerance_days}) — no mismatch"
                )
        return []

    def _find_in_reference_kg(self, subject_name: str) -> list[tuple[str, dict]]:
        """Search the Reference KG — returns (kg_entity_key, fact_dict) pairs."""
        pairs: list[tuple[str, dict]] = []
        for key, facts in self._reference_kg.items():
            if _fuzzy_entity_match(subject_name, key):
                for fact in facts:
                    pairs.append((key, fact))
        return pairs

    # Wikidata fetch with 3-level cache
    def _fetch_from_wikidata(self, fact: TemporalFact, result: ExternalVerificationResult, prefetched_facts=None) -> list[WikidataFact]:
        cache_key = fact.subject.text.lower().strip()

        # 0. Entity-level prefetch cache (populated by verify() before the main loop)
        for key, facts in (prefetched_facts or {}).items():
            if SequenceMatcher(None, cache_key, key.lower()).ratio() > 0.85:
                return facts

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
        if search_results is None:
            # Transient network error — do NOT negative-cache, so the entity
            # can be retried on a later request
            return []
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
                f"Cross-entity skip: '{fact.subject.text}' vs Wikidata '{wikidata_entity_label}' — entity mismatch, facts ignored"
            )
            self._wikidata_cache[cache_key] = []
            return []

        # Inverse Wikidata: fetch ALL temporal facts for the entity at once
        # (P39=positions held, P463=member of) — not just the matched relation.
        # This allows detecting contradictions even when C1 misclassifies the relation.
        wikidata_facts = self.client.get_temporal_facts(entity_id, ["P39", "P463"])
        result.wikidata_queries += 1
        if wikidata_facts is None:
            # Transient SPARQL error — do NOT cache (neither in memory nor Neo4j)
            return []

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
        obj_text = (fact.object.text if fact.object else "").lower().strip()
        for ref in ref_facts:
            if ref.get("relation") != fact.predicate.value:
                continue
            # Skip if the roles are clearly different (e.g. article says "President"
            # but KG has "Minister of Interior" — no shared content words).
            # Using _word_overlap (not _value_matches) because _value_matches falls
            # back to substring when token sets are empty, producing false positives
            # (e.g. obj_text="the" is a substring of "president of the united states").
            ref_value = ref.get("value", "").lower()
            if obj_text and ref_value and not _word_overlap(obj_text, ref_value, min_overlap=1):
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
            # _word_overlap handles short-form titles like "President United States"
            # matching "President of the United States" via shared content words.
            relevant = [
                wf for wf in wikidata_facts
                if SequenceMatcher(None, obj_text, wf.value_label.lower()).ratio() > 0.5
                or obj_text in wf.value_label.lower()
                or wf.value_label.lower() in obj_text
                or _word_overlap(obj_text, wf.value_label.lower(), min_overlap=2)
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
        """Load the Reference KG from the verified_events.json wrapper.

        The file mixes three fact representations:
          - inline per-entity keys (manual facts, normalized schema
            relation/value/time_start/time_end/time_point);
          - `entities` list (Wikidata facts, schema property/position/start_date),
            which holds the bulk of facts;
          - `historical_events` list (canonical events, occurred_on).
        Flattens everything into a single {entity_name: [normalized_facts]} dict
        that the rest of the code can query uniformly.
        """
        logger.info(f"Loading Reference KG from: {path.resolve()}")
        if not path.exists():
            logger.warning(f"Reference KG not found at {path}.")
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Reference KG load error: {e}")
            return {}

        if not isinstance(data, dict):
            logger.error(f"Reference KG has unexpected top-level type: {type(data).__name__}")
            return {}

        logger.debug(f"Reference KG top-level keys: {list(data.keys())}")

        kg: dict[str, list] = {}
        fact_count = 0

        # 1. Inline per-entity keys (manual facts, already in normalized schema).
        for key, value in data.items():
            if key in _REFERENCE_KG_META_KEYS or key in ("entities", "historical_events"):
                continue
            if isinstance(value, list):
                kg.setdefault(key.lower().strip(), []).extend(value)
                fact_count += len(value)

        # 2. `entities` list — Wikidata facts mapped to normalized schema.
        for ent in data.get("entities", []):
            if not isinstance(ent, dict):
                continue
            name = (ent.get("name") or "").lower().strip()
            if not name:
                continue
            entry = kg.setdefault(name, [])
            for wf in ent.get("facts", []):
                relation = _WIKIDATA_PROP_TO_RELATION.get(wf.get("property"))
                if not relation:
                    continue
                entry.append({
                    "subject": ent.get("name", ""),
                    "relation": relation,
                    "value": wf.get("position", ""),
                    "time_start": wf.get("start_date"),
                    "time_end": wf.get("end_date"),
                    "time_point": wf.get("point_date"),
                    "source": "wikidata",
                })
                fact_count += 1

        # 3. Canonical events — stored under a reserved key; _check_event_date
        # iterates all list values so no per-entity key is needed.
        events = [e for e in data.get("historical_events", []) if isinstance(e, dict)]
        if events:
            kg[_EVENTS_KG_KEY] = events
            fact_count += len(events)

        entity_records = len(kg) - (1 if events else 0)
        logger.info(
            f"Reference KG loaded: {entity_records} entity records, {fact_count} facts "
            f"({len(events)} canonical events; declared total_facts={data.get('total_facts')}) "
            f"from {path.name}."
        )
        return kg


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
    """Compare the article interval against an external source.

    Two precision rules avoid false positives:
    - corrupted external intervals (end before start) never yield a verdict;
    - when the article date is year-granular (a bare year normalises to Jan 1),
      the comparison is done at year granularity, so "2021" is not flagged
      against a precise external date of 2021-11-15.
    """
    # Guard: corrupted external data (e.g. Wikidata end before start).
    if ext_start and ext_end and ext_start > ext_end:
        return None

    tolerance = timedelta(days=runtime_settings.get_value("external_date_tolerance_days"))
    fact_start = fact.time_start.normalized_date if fact.time_start else None
    fact_end = fact.time_end.normalized_date if fact.time_end else None
    fact_point = fact.time_point.normalized_date if fact.time_point else None

    year_only = _is_year_granular(fact.time_point) or _is_year_granular(fact.time_start)

    if fact_point and ext_start and ext_end:
        mismatch = (
            not (ext_start.year <= fact_point.year <= ext_end.year)
            if year_only
            else not (ext_start - tolerance <= fact_point <= ext_end + tolerance)
        )
        if mismatch:
            return Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH, severity=Severity.HIGH,
                description=f"Article date ({fact_point.year}) does not match {source} interval [{ext_start.year} -> {ext_end.year}].",
                facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                verified_by=source, evidence=evidence,
            )

    if fact_start and fact_end and ext_start and ext_end:
        mismatch = (
            fact_end.year < ext_start.year or fact_start.year > ext_end.year
            if year_only
            else fact_end < ext_start - tolerance or fact_start > ext_end + tolerance
        )
        if mismatch:
            return Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH, severity=Severity.HIGH,
                description=f"Interval [{fact_start.year} -> {fact_end.year}] does not overlap with {source} [{ext_start.year} -> {ext_end.year}].",
                facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                verified_by=source, evidence=evidence,
            )

    if fact_point and ext_point:
        mismatch = (
            fact_point.year != ext_point.year
            if year_only
            else abs((fact_point - ext_point).days) > tolerance.days
        )
        if mismatch:
            return Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH, severity=Severity.MEDIUM,
                description=f"Article date ({fact_point.year}) differs from {source} ({ext_point.year}).",
                facts_involved=[fact], sentence_indices=[fact.source_sentence_idx],
                verified_by=source, evidence=evidence,
            )
    return None


_BARE_YEAR_RE = re.compile(r"^\s*(?:circa|around|about|c\.)?\s*\d{4}\s*$", re.IGNORECASE)


def _is_year_granular(expr) -> bool:
    """True when a temporal expression carries only year precision.

    A bare year ("2021") or an approximate expression normalises to Jan 1 and
    must not be compared against a precise external date with a day tolerance.
    """
    if expr is None or expr.normalized_date is None:
        return False
    raw = (expr.raw_text or "").strip()
    if _BARE_YEAR_RE.match(raw):
        return True
    if getattr(expr, "is_approximate", False):
        return True
    # Bare years normalise to Jan 1 with reduced confidence in the parser.
    nd = expr.normalized_date
    if nd.month == 1 and nd.day == 1 and getattr(expr, "confidence", 1.0) <= 0.6:
        return True
    return False


# Generic words shared by unrelated roles/events — matching on these alone would
# conflate distinct facts (e.g. "Infrastructure Act" vs "Tax Cuts and Jobs Act").
_VALUE_STOPWORDS = {
    "act", "signing", "bill", "law", "jobs", "reform", "and", "of", "the",
    "a", "an", "or", "to", "for", "in", "on", "united", "states", "u.s.", "us",
}


def _value_tokens(text: str) -> set[str]:
    return {
        w for w in re.split(r"[^a-z0-9]+", text.lower())
        if w and w not in _VALUE_STOPWORDS and len(w) > 2
    }


def _value_matches(article_obj: str, kg_value: str) -> bool:
    """True when the article object refers to the same role/event as a KG value.

    Requires overlap on a *distinctive* token (bill name, office) so an entity's
    unrelated same-relation facts are not cross-compared.
    """
    a = (article_obj or "").lower().strip()
    k = (kg_value or "").lower().strip()
    if not a or not k:
        return False
    ta, tk = _value_tokens(a), _value_tokens(k)
    if ta & tk:
        return True
    # No distinctive tokens on one side (e.g. a bare fragment) — fall back to substring.
    if not ta or not tk:
        return a in k or k in a
    return False

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

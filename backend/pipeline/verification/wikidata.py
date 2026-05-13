"""C3 — Client SPARQL pentru Wikidata (cautare entitati + fapte temporale P580/P582/P585)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

from backend.config import WIKIDATA_ENDPOINT

logger = logging.getLogger(__name__)

WIKIDATA_USER_AGENT = "FakeNewsXAI/1.0 (UTCN Bachelor Thesis; github.com/FakeNews-XAI)"
SPARQL_TIMEOUT_SECONDS = 30
RATE_LIMIT_DELAY_SECONDS = 1.0


@dataclass
class WikidataFact:
    """A temporal fact returned by Wikidata, used by external.py for comparison."""
    entity_id: str
    entity_label: str
    property_id: str
    property_label: str
    value_label: str
    # P580: start time
    time_start: Optional[datetime] = None
    # P582: end time
    time_end: Optional[datetime] = None
    # P585: point in time
    time_point: Optional[datetime] = None

    def __repr__(self) -> str:
        time_info = ""
        if self.time_point:
            time_info = f" @{self.time_point.year}"
        elif self.time_start:
            end_year = self.time_end.year if self.time_end else "?"
            time_info = f" [{self.time_start.year}->{end_year}]"
        return f"WikidataFact({self.entity_label} | {self.property_label}: {self.value_label}{time_info})"


class WikidataClient:
    """SPARQL client for Wikidata: search_entity(name) + get_temporal_facts(Q-ID)."""

    def __init__(self, endpoint: str = WIKIDATA_ENDPOINT, timeout: int = SPARQL_TIMEOUT_SECONDS, rate_limit_delay: float = RATE_LIMIT_DELAY_SECONDS):
        self.endpoint = endpoint
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0

    # Entity search — returns a QID string or None
    def search_entity(self, name: str, language: str = "en") -> Optional[str]:
        """Search for a Wikidata Q-ID by label. Returns the first match (e.g. 'Q76') or None."""
        self._wait_rate_limit()
        url = "https://www.wikidata.org/w/api.php"
        params = {"action": "wbsearchentities", "search": name, "language": language, "format": "json", "limit": 5}

        try:
            response = requests.get(url, params=params, headers={"User-Agent": WIKIDATA_USER_AGENT}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            results = data.get("search", [])
            if results:
                qid = results[0].get("id", "")
                logger.debug(f"Wikidata: '{name}' -> {qid}")
                return qid
            logger.debug(f"Wikidata: '{name}' -> no match")
            return None
        except requests.RequestException as e:
            logger.warning(f"Wikidata search failed for '{name}': {e}")
            return None

    def search_entity_full(self, name: str, language: str = "en") -> list[dict]:
        """Full search with id, label, description. Useful for debugging/notebooks."""
        self._wait_rate_limit()
        url = "https://www.wikidata.org/w/api.php"
        params = {"action": "wbsearchentities", "search": name, "language": language, "format": "json", "limit": 5}

        try:
            response = requests.get(url, params=params, headers={"User-Agent": WIKIDATA_USER_AGENT}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return [{"id": item.get("id", ""), "label": item.get("label", ""), "description": item.get("description", "")} for item in data.get("search", [])]
        except requests.RequestException as e:
            logger.warning(f"Wikidata search failed for '{name}': {e}")
            return []

    # Temporal facts — SPARQL query
    def get_temporal_facts(self, entity_id: str, relation_properties: Optional[list[str]] = None) -> list[WikidataFact]:
        """Query facts with P580/P582/P585 qualifiers for an entity (QID, e.g. 'Q76')."""
        self._wait_rate_limit()
        query = self._build_temporal_query(entity_id, relation_properties)
        logger.debug(f"SPARQL query for {entity_id}:\n{query}")

        try:
            response = requests.get(
                self.endpoint, params={"query": query, "format": "json"},
                headers={"User-Agent": WIKIDATA_USER_AGENT, "Accept": "application/sparql-results+json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            bindings = data.get("results", {}).get("bindings", [])
            logger.debug(f"SPARQL: {len(bindings)} results for {entity_id}")
            return self._parse_sparql_results(data, entity_id)
        except requests.RequestException as e:
            logger.warning(f"Wikidata SPARQL failed for {entity_id}: {e}")
            return []

    def get_position_held(self, entity_id: str) -> list[WikidataFact]:
        """P39 — positions held."""
        return self.get_temporal_facts(entity_id, relation_properties=["P39"])

    def get_membership(self, entity_id: str) -> list[WikidataFact]:
        """P463 — member of."""
        return self.get_temporal_facts(entity_id, relation_properties=["P463"])

    # SPARQL query construction
    def _build_temporal_query(self, entity_id: str, relation_properties: Optional[list[str]]) -> str:
        """
        Build a SPARQL query extracting facts with temporal qualifiers.
        Pattern: wd:Qxxx p:Pxx ?stmt . ?stmt ps:Pxx ?value . ?stmt pq:P580 ?start .
        """
        if relation_properties:
            # Specific query: one property per UNION block
            unions = []
            for prop in relation_properties:
                unions.append(f"""    {{
      wd:{entity_id} p:{prop} ?statement .
      ?statement ps:{prop} ?value .
      BIND("{prop}" AS ?propId)
    }}""")
            body = "\n    UNION\n".join(unions)
        else:
            # General query: all properties with temporal qualifiers
            body = f"""    wd:{entity_id} ?propClaim ?statement .
    ?statement ?psValue ?value .
    ?propEntity wikibase:claim ?propClaim .
    ?propEntity wikibase:statementProperty ?psValue .
    BIND(REPLACE(STR(?propEntity), ".*/(P\\\\d+)$", "$1") AS ?propId)"""

        return f"""SELECT ?propId ?value ?valueLabel ?startTime ?endTime ?pointInTime
WHERE {{
{body}
  OPTIONAL {{ ?statement pq:P580 ?startTime . }}
  OPTIONAL {{ ?statement pq:P582 ?endTime . }}
  OPTIONAL {{ ?statement pq:P585 ?pointInTime . }}
  FILTER(BOUND(?startTime) || BOUND(?endTime) || BOUND(?pointInTime))
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
LIMIT 50""".strip()

    def _parse_sparql_results(self, data: dict, entity_id: str) -> list[WikidataFact]:
        """Parse a SPARQL response and return WikidataFact objects."""
        facts = []
        for row in data.get("results", {}).get("bindings", []):
            # propId arrives as a literal string ("P39") or as a URI
            prop_raw = row.get("propId", {}).get("value", "")
            prop_id = _extract_prop_id(prop_raw) if "/" in prop_raw else prop_raw
            value_label = row.get("valueLabel", {}).get("value", "")
            if not value_label or not prop_id:
                continue

            t_start = _parse_wikidata_date(row.get("startTime", {}).get("value"))
            t_end = _parse_wikidata_date(row.get("endTime", {}).get("value"))
            t_point = _parse_wikidata_date(row.get("pointInTime", {}).get("value"))

            if not any([t_start, t_end, t_point]):
                continue

            facts.append(WikidataFact(
                entity_id=entity_id, entity_label=entity_id,
                property_id=prop_id,
                property_label=prop_id,
                value_label=value_label,
                time_start=t_start, time_end=t_end, time_point=t_point,
            ))
        return facts

    def _wait_rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()


# Utility functions
def _parse_wikidata_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse Wikidata ISO 8601 date (e.g. '+2009-01-20T00:00:00Z')."""
    if not date_str:
        return None
    clean = date_str.lstrip("+-")
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y"):
        try:
            return datetime.strptime(clean[:len(fmt.replace('%', 'X').replace('X', ''))], fmt)
        except ValueError:
            continue
    # Fallback: try first 10 characters (YYYY-MM-DD)
    try:
        return datetime.strptime(clean[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _extract_prop_id(uri: str) -> str:
    """'http://www.wikidata.org/entity/P39' -> 'P39'."""
    return uri.rsplit("/", 1)[-1] if "/" in uri else uri

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
SPARQL_TIMEOUT_SECONDS = 15
RATE_LIMIT_DELAY_SECONDS = 1.0


@dataclass
class WikidataFact:
    """Un fapt temporal returnat de Wikidata. Folosit de external.py pentru comparatie."""
    entity_id: str
    entity_label: str
    property_id: str
    property_label: str
    value_label: str
    time_start: Optional[datetime] = None   # P580
    time_end: Optional[datetime] = None     # P582
    time_point: Optional[datetime] = None   # P585

    def __repr__(self) -> str:
        time_info = ""
        if self.time_point:
            time_info = f" @{self.time_point.year}"
        elif self.time_start:
            end_year = self.time_end.year if self.time_end else "?"
            time_info = f" [{self.time_start.year}→{end_year}]"
        return f"WikidataFact({self.entity_label} | {self.property_label}: {self.value_label}{time_info})"


class WikidataClient:
    """Client SPARQL Wikidata: search_entity(name) + get_temporal_facts(Q-ID)."""

    def __init__(self, endpoint: str = WIKIDATA_ENDPOINT, timeout: int = SPARQL_TIMEOUT_SECONDS, rate_limit_delay: float = RATE_LIMIT_DELAY_SECONDS):
        self.endpoint = endpoint
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0

    def search_entity(self, name: str, language: str = "en") -> list[dict]:
        """Cauta Q-ID Wikidata dupa label (wbsearchentities API)."""
        self._wait_rate_limit()
        url = "https://www.wikidata.org/w/api.php"
        params = {"action": "wbsearchentities", "search": name, "language": language, "format": "json", "limit": 5}

        try:
            response = requests.get(url, params=params, headers={"User-Agent": WIKIDATA_USER_AGENT}, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return [{"id": item.get("id", ""), "label": item.get("label", ""), "description": item.get("description", "")} for item in data.get("search", [])]
        except requests.RequestException as e:
            logger.warning(f"Wikidata search esuat pentru '{name}': {e}")
            return []

    def get_temporal_facts(self, entity_id: str, relation_properties: Optional[list[str]] = None) -> list[WikidataFact]:
        """Interogheaza fapte cu P580/P582/P585 pentru o entitate."""
        self._wait_rate_limit()
        query = self._build_temporal_query(entity_id, relation_properties)

        try:
            response = requests.get(
                self.endpoint, params={"query": query, "format": "json"},
                headers={"User-Agent": WIKIDATA_USER_AGENT, "Accept": "application/sparql-results+json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return self._parse_sparql_results(response.json(), entity_id)
        except requests.RequestException as e:
            logger.warning(f"Wikidata SPARQL esuat pentru {entity_id}: {e}")
            return []

    def get_position_held(self, entity_id: str) -> list[WikidataFact]:
        """P39 — pozitii detinute."""
        return self.get_temporal_facts(entity_id, relation_properties=["P39"])

    def get_membership(self, entity_id: str) -> list[WikidataFact]:
        """P463 — member of."""
        return self.get_temporal_facts(entity_id, relation_properties=["P463"])

    def _build_temporal_query(self, entity_id: str, relation_properties: Optional[list[str]]) -> str:
        prop_filter = ""
        if relation_properties:
            prop_uris = " ".join(f"wdt:{p}" for p in relation_properties)
            prop_filter = f"VALUES ?prop {{ {prop_uris} }}"

        return f"""
SELECT ?prop ?propLabel ?value ?valueLabel ?startTime ?endTime ?pointInTime
WHERE {{
  {prop_filter}
  wd:{entity_id} ?prop ?value .
  wd:{entity_id} ?propDirect [] .
  OPTIONAL {{
    wd:{entity_id} p:?propId ?statement .
    ?statement ps:?propId ?value .
    OPTIONAL {{ ?statement pq:P580 ?startTime. }}
    OPTIONAL {{ ?statement pq:P582 ?endTime. }}
    OPTIONAL {{ ?statement pq:P585 ?pointInTime. }}
    FILTER(BOUND(?startTime) || BOUND(?endTime) || BOUND(?pointInTime))
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
LIMIT 50
""".strip()

    def _parse_sparql_results(self, data: dict, entity_id: str) -> list[WikidataFact]:
        facts = []
        for row in data.get("results", {}).get("bindings", []):
            prop_id = _extract_uri_id(row.get("prop", {}).get("value", ""))
            value_label = row.get("valueLabel", {}).get("value", "")
            if not value_label:
                continue

            t_start = _parse_wikidata_date(row.get("startTime", {}).get("value"))
            t_end = _parse_wikidata_date(row.get("endTime", {}).get("value"))
            t_point = _parse_wikidata_date(row.get("pointInTime", {}).get("value"))

            if not any([t_start, t_end, t_point]):
                continue

            facts.append(WikidataFact(
                entity_id=entity_id, entity_label=entity_id,
                property_id=prop_id, property_label=row.get("propLabel", {}).get("value", prop_id),
                value_label=value_label, time_start=t_start, time_end=t_end, time_point=t_point,
            ))
        return facts

    def _wait_rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()


def _parse_wikidata_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parseaza ISO 8601 Wikidata (ex: '+2009-01-20T00:00:00Z')."""
    if not date_str:
        return None
    clean = date_str.lstrip("+-")
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y"]:
        try:
            return datetime.strptime(clean[:len(fmt)], fmt)
        except ValueError:
            continue
    return None


def _extract_uri_id(uri: str) -> str:
    """'http://www.wikidata.org/prop/P39' → 'P39'."""
    return uri.rsplit("/", 1)[-1] if "/" in uri else uri
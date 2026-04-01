"""C1 — Pipeline B: extractie de fapte temporale prin LLM local (Ollama)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

import requests

from backend.config import OLLAMA_HOST, OLLAMA_MODEL
from backend.pipeline.extraction.base import AbstractExtractor
from backend.pipeline.extraction.temporal_parser import TemporalParser
from backend.pipeline.graph.models import (
    Article,
    Entity,
    EntityType,
    RelationType,
    TemporalExpression,
    TemporalFact,
)

logger = logging.getLogger(__name__)


# Prompt template - instructiuni pentru LLM
SYSTEM_PROMPT = """\
You are a temporal fact extraction system. Given a news article, extract ALL temporal facts.

For each fact, return a JSON object with:
- "subject": the main entity (person, organization, location)
- "subject_type": one of PERSON, ORG, GPE, EVENT, NORP, PRODUCT, OTHER
- "predicate": the relationship (e.g. "holds_position", "member_of", "occurred_on", "caused", "preceded", "followed", "generic")
- "object": the related entity or context
- "object_type": same types as subject_type
- "time_expression": the temporal expression exactly as it appears in the text
- "time_start": start date if it's a range (ISO format YYYY-MM-DD or null)
- "time_end": end date if it's a range (ISO format YYYY-MM-DD or null)
- "time_point": specific date if it's a single point (ISO format or null)
- "confidence": your confidence 0.0–1.0

Return ONLY a JSON array. No explanations, no markdown fences.\
"""

USER_PROMPT_TEMPLATE = """\
Extract all temporal facts from this article:

Title: {title}
Publication date: {pub_date}

Text:
{text}\
"""

# Mapari LLM → modele interne
_ENTITY_TYPE_MAP: dict[str, EntityType] = {
    "PERSON": EntityType.PERSON,
    "ORG": EntityType.ORGANIZATION,
    "GPE": EntityType.LOCATION,
    "LOC": EntityType.LOCATION,
    "EVENT": EntityType.EVENT,
    "DATE": EntityType.DATE,
    "NORP": EntityType.NORP,
    "PRODUCT": EntityType.PRODUCT,
}

_RELATION_TYPE_MAP: dict[str, RelationType] = {
    "holds_position": RelationType.HOLDS_POSITION,
    "member_of": RelationType.MEMBER_OF,
    "located_in": RelationType.LOCATED_IN,
    "occurred_on": RelationType.OCCURRED_ON,
    "started": RelationType.STARTED,
    "ended": RelationType.ENDED,
    "caused": RelationType.CAUSED,
    "preceded": RelationType.PRECEDED,
    "followed": RelationType.FOLLOWED,
}

# Timeout si retry
OLLAMA_TIMEOUT_SECONDS = 120
MAX_RETRIES = 2


class LLMExtractor(AbstractExtractor):
    """Pipeline B — extragere prin prompting LLM local (Ollama)."""

    def __init__(
        self,
        host: str = OLLAMA_HOST,
        model: str = OLLAMA_MODEL,
        timeout: int = OLLAMA_TIMEOUT_SECONDS,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temporal_parser = TemporalParser()

    def get_name(self) -> str:
        return "llm"


    # Metoda principala
    def extract(self, article: Article) -> list[TemporalFact]:
        """Trimite articolul la Ollama, parseaza raspunsul JSON, returneaza TemporalFact."""
        pub_date_str = (
            article.publication_date.strftime("%Y-%m-%d")
            if article.publication_date else "unknown"
        )

        user_prompt = USER_PROMPT_TEMPLATE.format(
            title=article.title,
            pub_date=pub_date_str,
            text=article.text[:4000],  # limita context window
        )

        raw_response = self._call_ollama(user_prompt)
        if raw_response is None:
            logger.warning("LLMExtractor: Ollama nu a raspuns. Returnez lista goala.")
            return []

        raw_facts = self._parse_json_response(raw_response)
        if not raw_facts:
            logger.warning("LLMExtractor: raspuns JSON invalid sau gol.")
            return []

        facts = self._convert_to_temporal_facts(raw_facts, article.publication_date)
        logger.info(f"LLMExtractor: {len(facts)} fapte din {len(raw_facts)} extrase de LLM")
        return facts


    # Comunicare cu Ollama
    def _call_ollama(self, user_prompt: str) -> Optional[str]:
        """Apel HTTP catre Ollama /api/chat. Retry la esec."""
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,     # deterministic
                "num_predict": 4096,    # output suficient pentru JSON
            },
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                if content:
                    return content
                logger.warning(f"LLMExtractor: raspuns gol (tentativa {attempt})")
            except requests.ConnectionError:
                logger.error(f"LLMExtractor: Ollama indisponibil la {self.host} (tentativa {attempt})")
            except requests.Timeout:
                logger.error(f"LLMExtractor: timeout {self.timeout}s (tentativa {attempt})")
            except requests.RequestException as e:
                logger.error(f"LLMExtractor: eroare HTTP (tentativa {attempt}): {e}")

        return None


    # Parsare raspuns JSON
    def _parse_json_response(self, raw: str) -> list[dict[str, Any]]:
        """Extrage array JSON din raspunsul LLM (tolereaza markdown fences)."""
        # Elimina fences ```json ... ```
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = cleaned.rstrip("`").strip()

        # Incearca parsarea directa
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            pass

        # Fallback: cauta primul [...] din raspuns
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        logger.debug(f"LLMExtractor: nu s-a putut parsa JSON: {raw[:200]}...")
        return []


    # Conversie in TemporalFact
    def _convert_to_temporal_facts(
        self, raw_facts: list[dict], pub_date: Optional[datetime],
    ) -> list[TemporalFact]:
        """Converteste dictionarele extrase de LLM in TemporalFact."""
        facts = []
        for i, raw in enumerate(raw_facts):
            try:
                fact = self._single_fact(raw, i, pub_date)
                if fact is not None:
                    facts.append(fact)
            except Exception as e:
                logger.debug(f"LLMExtractor: fapt #{i} invalid — {e}")
        return facts

    def _single_fact(
        self, raw: dict, idx: int, pub_date: Optional[datetime],
    ) -> Optional[TemporalFact]:
        """Converteste un dict LLM in TemporalFact. None daca lipsesc campuri esentiale."""
        subj_text = raw.get("subject", "").strip()
        obj_text = raw.get("object", "").strip()
        if not subj_text:
            return None

        subject = Entity(
            text=subj_text,
            entity_type=_ENTITY_TYPE_MAP.get(raw.get("subject_type", ""), EntityType.OTHER),
            start_char=0, end_char=0,
        )
        obj = Entity(
            text=obj_text or "[context]",
            entity_type=_ENTITY_TYPE_MAP.get(raw.get("object_type", ""), EntityType.OTHER),
            start_char=0, end_char=0,
        )

        predicate = _RELATION_TYPE_MAP.get(
            raw.get("predicate", ""), RelationType.GENERIC,
        )

        # Parsare expresii temporale
        time_point = self._parse_time_field(raw, "time_point", pub_date)
        time_start = self._parse_time_field(raw, "time_start", pub_date)
        time_end = self._parse_time_field(raw, "time_end", pub_date)

        # Fallback: time_expression din text
        if not any([time_point, time_start, time_end]):
            raw_expr = raw.get("time_expression", "")
            if raw_expr:
                time_point = self._parse_raw_expression(raw_expr, pub_date)

        # Minim o ancora temporala
        if not any([time_point, time_start, time_end]):
            return None

        confidence = float(raw.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))

        return TemporalFact(
            subject=subject,
            predicate=predicate,
            object=obj,
            time_start=time_start,
            time_end=time_end,
            time_point=time_point if not time_start else None,
            source_sentence=raw.get("time_expression", ""),
            source_sentence_idx=idx,
            extraction_confidence=confidence,
            extractor="llm",
        )


    # Parsare campuri temporale individuale
    def _parse_time_field(
        self, raw: dict, field: str, pub_date: Optional[datetime],
    ) -> Optional[TemporalExpression]:
        """Parseaza un camp temporal (time_point/time_start/time_end) din dict."""
        value = raw.get(field)
        if not value or value == "null" or value == "None":
            return None
        return self._parse_raw_expression(str(value), pub_date)

    def _parse_raw_expression(
        self, raw_text: str, pub_date: Optional[datetime],
    ) -> Optional[TemporalExpression]:
        """Parseaza o expresie temporala string prin TemporalParser."""
        results = self.temporal_parser.parse_all_in_sentence(
            sentence=raw_text,
            date_spans=[(0, len(raw_text), raw_text)],
            reference_date=pub_date,
        )
        return results[0] if results else None


    # Verificare disponibilitate Ollama
    def is_available(self) -> bool:
        """Verifica daca Ollama ruleaza si modelul e disponibil."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            available = any(m.get("name", "").startswith(self.model) for m in models)
            if not available:
                logger.warning(f"LLMExtractor: model '{self.model}' nu e instalat in Ollama.")
            return available
        except requests.RequestException:
            logger.warning(f"LLMExtractor: Ollama indisponibil la {self.host}")
            return False
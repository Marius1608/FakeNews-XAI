"""C1 — Pipeline B: extracție de fapte temporale prin LLM local (Ollama)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

import requests

from backend.config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS
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

# // prompt
SYSTEM_PROMPT = """\
You are a temporal fact extraction system. Extract ALL temporal facts, not just positions. Include: elections, votes, treaties, appointments, resignations, deaths, wars, sanctions, legislation signing, inaugurations.

For each fact, return a JSON object with:
- "subject": the main entity (person, organization, location)
- "subject_type": one of PERSON, ORG, GPE, EVENT, NORP, PRODUCT, OTHER
- "predicate": the relationship (e.g. "holds_position", "member_of", "occurred_on", "caused", "preceded", "followed", "generic")
- "object": the related entity or context
- "object_type": same types as subject_type
- "time_expression": the temporal expression exactly as it appears in the text
- "time_start": start date if it's a range (format YYYY-MM-DD, YYYY, YYYY-MM or null)
- "time_end": end date if it's a range (format YYYY-MM-DD, YYYY, YYYY-MM or null)
- "time_point": specific date if it's a single point (format YYYY-MM-DD, YYYY, YYYY-MM or null)
- "source_sentence": the original sentence from the article that contains this fact
- "confidence": your confidence 0.0–1.0

Rules:
- Acceptable date formats: "YYYY-MM-DD", "YYYY", "YYYY-MM".
- If an article says 'last year' and the publication date is 2020-03-15, resolve it to 2019.
- Return ONLY a JSON array. No markdown fences, no explanations, no preamble.\
"""

USER_PROMPT_TEMPLATE = """\
Extract all temporal facts from this article:

Title: {title}
Publication date: {pub_date}

Text:
{text}\
"""

# // examples
EXAMPLE_INPUTS = [
    # Exemplu 1: Pozitie politica cu interval
    "Extract all temporal facts from this article:\nTitle: Obama Presidency\nPublication date: 2017-02-01\nText: Obama served as president from 2009 to 2017.",
    # Exemplu 2: Eveniment cu data punctuala
    "Extract all temporal facts from this article:\nTitle: Healthcare Reform\nPublication date: 2010-03-24\nText: The Affordable Care Act was signed into law on March 23, 2010.",
    # Exemplu 3: Alegeri
    "Extract all temporal facts from this article:\nTitle: 2016 Election Results\nPublication date: 2016-11-09\nText: Trump won the 2016 presidential election on November 8, defeating Hillary Clinton.",
    # Exemplu 4: Tratat/legislatie
    "Extract all temporal facts from this article:\nTitle: Climate Agreement\nPublication date: 2016-11-05\nText: The Paris Agreement was adopted on December 12, 2015 and entered into force on November 4, 2016.",
    # Exemplu 5: Eveniment cu consecinta temporala
    "Extract all temporal facts from this article:\nTitle: Fall of Soviet Union\nPublication date: 2000-01-01\nText: After the Soviet Union dissolved in December 1991, Boris Yeltsin became president of Russia and served until 1999."
]

EXAMPLE_OUTPUTS = [
    # Exemplu 1
    '[{"subject": "Obama", "subject_type": "PERSON", "predicate": "holds_position", "object": "president", "object_type": "OTHER", "time_expression": "from 2009 to 2017", "time_start": "2009", "time_end": "2017", "time_point": null, "source_sentence": "Obama served as president from 2009 to 2017.", "confidence": 0.95}]',
    # Exemplu 2
    '[{"subject": "Affordable Care Act", "subject_type": "EVENT", "predicate": "occurred_on", "object": "signed into law", "object_type": "EVENT", "time_expression": "March 23, 2010", "time_start": null, "time_end": null, "time_point": "2010-03-23", "source_sentence": "The Affordable Care Act was signed into law on March 23, 2010.", "confidence": 0.95}]',
    # Exemplu 3
    '[{"subject": "Trump", "subject_type": "PERSON", "predicate": "occurred_on", "object": "presidential election", "object_type": "EVENT", "time_expression": "2016", "time_start": null, "time_end": null, "time_point": "2016-11-08", "source_sentence": "Trump won the 2016 presidential election on November 8, defeating Hillary Clinton.", "confidence": 0.9}, {"subject": "Hillary Clinton", "subject_type": "PERSON", "predicate": "occurred_on", "object": "presidential election", "object_type": "EVENT", "time_expression": "2016", "time_start": null, "time_end": null, "time_point": "2016-11-08", "source_sentence": "Trump won the 2016 presidential election on November 8, defeating Hillary Clinton.", "confidence": 0.9}]',
    # Exemplu 4
    '[{"subject": "Paris Agreement", "subject_type": "EVENT", "predicate": "occurred_on", "object": "adopted", "object_type": "EVENT", "time_expression": "December 12, 2015", "time_start": null, "time_end": null, "time_point": "2015-12-12", "source_sentence": "The Paris Agreement was adopted on December 12, 2015 and entered into force on November 4, 2016.", "confidence": 0.95}, {"subject": "Paris Agreement", "subject_type": "EVENT", "predicate": "occurred_on", "object": "entered into force", "object_type": "EVENT", "time_expression": "November 4, 2016", "time_start": null, "time_end": null, "time_point": "2016-11-04", "source_sentence": "The Paris Agreement was adopted on December 12, 2015 and entered into force on November 4, 2016.", "confidence": 0.95}]',
    # Exemplu 5
    '[{"subject": "Soviet Union", "subject_type": "GPE", "predicate": "occurred_on", "object": "dissolved", "object_type": "EVENT", "time_expression": "December 1991", "time_start": null, "time_end": null, "time_point": "1991-12", "source_sentence": "After the Soviet Union dissolved in December 1991, Boris Yeltsin became president of Russia and served until 1999.", "confidence": 0.9}, {"subject": "Boris Yeltsin", "subject_type": "PERSON", "predicate": "holds_position", "object": "president of Russia", "object_type": "OTHER", "time_expression": "until 1999", "time_start": "1991-12", "time_end": "1999", "time_point": null, "source_sentence": "After the Soviet Union dissolved in December 1991, Boris Yeltsin became president of Russia and served until 1999.", "confidence": 0.9}, {"subject": "dissolved", "subject_type": "EVENT", "predicate": "caused", "object": "president of Russia", "object_type": "OTHER", "time_expression": "December 1991", "time_start": null, "time_end": null, "time_point": null, "source_sentence": "After the Soviet Union dissolved in December 1991, Boris Yeltsin became president of Russia and served until 1999.", "confidence": 0.8}]'
]

# // mapping
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

MAX_RETRIES = 2


class LLMExtractor(AbstractExtractor):
    """Pipeline B — extracție prin prompting LLM local."""

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

    # // main_extraction
    def extract(self, article: Article) -> list[TemporalFact]:
        """Trimite articolul la API, parsează răspunsul JSON, returnează lista de fapte."""
        pub_date_str = (
            article.publication_date.strftime("%Y-%m-%d")
            if article.publication_date else "unknown"
        )

        user_prompt = USER_PROMPT_TEMPLATE.format(
            title=article.title,
            pub_date=pub_date_str,
            text=article.text[:4000],
        )

        raw_response = self._call_ollama(user_prompt)
        if raw_response is None:
            logger.warning("LLMExtractor: Răspuns absent. Se returnează listă goală.")
            return []

        logger.debug(f"LLMExtractor raw response (first 500 chars): {raw_response[:500]}")

        raw_facts = self._parse_json_response(raw_response)
        if not raw_facts:
            logger.warning("LLMExtractor: Răspuns JSON invalid/gol.")
            return []

        facts = self._convert_to_temporal_facts(raw_facts, article.publication_date)
        
        parsed_count = len(facts)
        rejected_count = len(raw_facts) - parsed_count
        logger.info(f"LLMExtractor: Extrase {parsed_count} fapte valide, {rejected_count} respinse.")
        
        return facts

    # // ollama_communication
    def _call_ollama(self, user_prompt: str) -> Optional[str]:
        """Apel HTTP către API. Include few-shot examples."""
        url = f"{self.host}/api/chat"
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for user_msg, asst_msg in zip(EXAMPLE_INPUTS, EXAMPLE_OUTPUTS):
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": asst_msg})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
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
                logger.warning(f"LLMExtractor: Răspuns gol (încercarea {attempt})")
            except requests.ConnectionError:
                logger.error(f"LLMExtractor: Conexiune eșuată la {self.host} (încercarea {attempt})")
            except requests.Timeout:
                logger.error(f"LLMExtractor: Timeout la {self.timeout}s (încercarea {attempt})")
            except requests.RequestException as e:
                logger.error(f"LLMExtractor: Eroare HTTP (încercarea {attempt}): {e}")

        return None

    # // response_parsing
    def _parse_json_response(self, raw: str) -> list[dict[str, Any]]:
        """Extrage array JSON din răspuns (ignoră markdown fences)."""
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = cleaned.rstrip("`").strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            pass

        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        logger.debug(f"LLMExtractor: Eșec parsare JSON: {raw[:200]}...")
        return []

    # // conversion
    def _convert_to_temporal_facts(
        self, raw_facts: list[dict], pub_date: Optional[datetime],
    ) -> list[TemporalFact]:
        """Convertește dicționare în TemporalFact. Filtrează intrările invalide."""
        facts = []
        for i, raw in enumerate(raw_facts):
            try:
                fact = self._single_fact(raw, i, pub_date)
                if fact is not None:
                    facts.append(fact)
            except Exception as e:
                logger.debug(f"LLMExtractor: Fapt #{i} eroare - {e}")
        return facts

    def _single_fact(
        self, raw: dict, idx: int, pub_date: Optional[datetime],
    ) -> Optional[TemporalFact]:
        """Procesează un singur fapt. Returnează None la validare eșuată."""
        subj_text = raw.get("subject", "").strip()
        obj_text = raw.get("object", "").strip()
        
        if not subj_text:
            logger.debug(f"LLMExtractor: Fapt respins. Lipsă subiect: {raw}")
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

        time_point = self._parse_time_field(raw, "time_point", pub_date)
        time_start = self._parse_time_field(raw, "time_start", pub_date)
        time_end = self._parse_time_field(raw, "time_end", pub_date)

        if not any([time_point, time_start, time_end]):
            raw_expr = raw.get("time_expression", "")
            if raw_expr:
                time_point = self._parse_raw_expression(raw_expr, pub_date)

        if not any([time_point, time_start, time_end]):
            logger.debug(f"LLMExtractor: Fapt respins. Lipsă ancoră temporală: {raw}")
            return None

        confidence = float(raw.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))

        source_sent = raw.get("source_sentence", "").strip()
        if not source_sent:
            source_sent = raw.get("time_expression", "")

        return TemporalFact(
            subject=subject,
            predicate=predicate,
            object=obj,
            time_start=time_start,
            time_end=time_end,
            time_point=time_point if not time_start else None,
            source_sentence=source_sent,
            source_sentence_idx=idx,
            extraction_confidence=confidence,
            extractor="llm",
        )

    # // temporal_parsing
    def _parse_time_field(
        self, raw: dict, field: str, pub_date: Optional[datetime],
    ) -> Optional[TemporalExpression]:
        """Parsează câmp temporal specific."""
        value = raw.get(field)
        if not value or value == "null" or value == "None":
            return None
        return self._parse_raw_expression(str(value), pub_date)

    def _parse_raw_expression(
        self, raw_text: str, pub_date: Optional[datetime],
    ) -> Optional[TemporalExpression]:
        """Parsează expresie temporală string."""
        results = self.temporal_parser.parse_all_in_sentence(
            sentence=raw_text,
            date_spans=[(0, len(raw_text), raw_text)],
            reference_date=pub_date,
        )
        return results[0] if results else None

    # // availability
    def is_available(self) -> bool:
        """Verifică disponibilitatea API-ului și a modelului."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            available = any(m.get("name", "").startswith(self.model) for m in models)
            if not available:
                logger.warning(f"LLMExtractor: Model '{self.model}' indisponibil.")
            return available
        except requests.RequestException:
            logger.warning(f"LLMExtractor: API indisponibil la {self.host}")
            return False
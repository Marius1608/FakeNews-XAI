"""C1 — Pipeline B: temporal fact extraction via spacy-llm + Qwen3-1.7B."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional

import spacy

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

QWEN_MODEL_ID = os.getenv("QWEN_MODEL_ID", "Qwen/Qwen3-1.7B")
_qwen_model = None
_qwen_tokenizer = None
_load_failed = False

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

EXAMPLE_INPUTS = [
    "Extract all temporal facts from this article:\nTitle: Obama Presidency\nPublication date: 2017-02-01\nText: Obama served as president from 2009 to 2017.",
    "Extract all temporal facts from this article:\nTitle: Healthcare Reform\nPublication date: 2010-03-24\nText: The Affordable Care Act was signed into law on March 23, 2010.",
    "Extract all temporal facts from this article:\nTitle: 2016 Election Results\nPublication date: 2016-11-09\nText: Trump won the 2016 presidential election on November 8, defeating Hillary Clinton.",
    "Extract all temporal facts from this article:\nTitle: Climate Agreement\nPublication date: 2016-11-05\nText: The Paris Agreement was adopted on December 12, 2015 and entered into force on November 4, 2016.",
    "Extract all temporal facts from this article:\nTitle: Fall of Soviet Union\nPublication date: 2000-01-01\nText: After the Soviet Union dissolved in December 1991, Boris Yeltsin became president of Russia and served until 1999.",
]

EXAMPLE_OUTPUTS = [
    '[{"subject": "Obama", "subject_type": "PERSON", "predicate": "holds_position", "object": "president", "object_type": "OTHER", "time_expression": "from 2009 to 2017", "time_start": "2009", "time_end": "2017", "time_point": null, "source_sentence": "Obama served as president from 2009 to 2017.", "confidence": 0.95}]',
    '[{"subject": "Affordable Care Act", "subject_type": "EVENT", "predicate": "occurred_on", "object": "signed into law", "object_type": "EVENT", "time_expression": "March 23, 2010", "time_start": null, "time_end": null, "time_point": "2010-03-23", "source_sentence": "The Affordable Care Act was signed into law on March 23, 2010.", "confidence": 0.95}]',
    '[{"subject": "Trump", "subject_type": "PERSON", "predicate": "occurred_on", "object": "presidential election", "object_type": "EVENT", "time_expression": "2016", "time_start": null, "time_end": null, "time_point": "2016-11-08", "source_sentence": "Trump won the 2016 presidential election on November 8, defeating Hillary Clinton.", "confidence": 0.9}, {"subject": "Hillary Clinton", "subject_type": "PERSON", "predicate": "occurred_on", "object": "presidential election", "object_type": "EVENT", "time_expression": "2016", "time_start": null, "time_end": null, "time_point": "2016-11-08", "source_sentence": "Trump won the 2016 presidential election on November 8, defeating Hillary Clinton.", "confidence": 0.9}]',
    '[{"subject": "Paris Agreement", "subject_type": "EVENT", "predicate": "occurred_on", "object": "adopted", "object_type": "EVENT", "time_expression": "December 12, 2015", "time_start": null, "time_end": null, "time_point": "2015-12-12", "source_sentence": "The Paris Agreement was adopted on December 12, 2015 and entered into force on November 4, 2016.", "confidence": 0.95}, {"subject": "Paris Agreement", "subject_type": "EVENT", "predicate": "occurred_on", "object": "entered into force", "object_type": "EVENT", "time_expression": "November 4, 2016", "time_start": null, "time_end": null, "time_point": "2016-11-04", "source_sentence": "The Paris Agreement was adopted on December 12, 2015 and entered into force on November 4, 2016.", "confidence": 0.95}]',
    '[{"subject": "Soviet Union", "subject_type": "GPE", "predicate": "occurred_on", "object": "dissolved", "object_type": "EVENT", "time_expression": "December 1991", "time_start": null, "time_end": null, "time_point": "1991-12", "source_sentence": "After the Soviet Union dissolved in December 1991, Boris Yeltsin became president of Russia and served until 1999.", "confidence": 0.9}, {"subject": "Boris Yeltsin", "subject_type": "PERSON", "predicate": "holds_position", "object": "president of Russia", "object_type": "OTHER", "time_expression": "until 1999", "time_start": "1991-12", "time_end": "1999", "time_point": null, "source_sentence": "After the Soviet Union dissolved in December 1991, Boris Yeltsin became president of Russia and served until 1999.", "confidence": 0.9}, {"subject": "dissolved", "subject_type": "EVENT", "predicate": "caused", "object": "president of Russia", "object_type": "OTHER", "time_expression": "December 1991", "time_start": null, "time_end": null, "time_point": null, "source_sentence": "After the Soviet Union dissolved in December 1991, Boris Yeltsin became president of Russia and served until 1999.", "confidence": 0.8}]',
]

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

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _load_qwen() -> bool:
    global _qwen_model, _qwen_tokenizer, _load_failed
    if _qwen_model is not None:
        return True
    if _load_failed:
        return False
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        _qwen_tokenizer = AutoTokenizer.from_pretrained(QWEN_MODEL_ID)
        _qwen_model = AutoModelForCausalLM.from_pretrained(
            QWEN_MODEL_ID, dtype=dtype, device_map="auto"
        )
        logger.info(f"Qwen model loaded: {QWEN_MODEL_ID}")
        return True
    except Exception as e:
        _load_failed = True
        logger.error(f"Failed to load Qwen model '{QWEN_MODEL_ID}': {e}")
        return False


def generate_json(messages: list[dict]) -> str | None:
    """Generate text via Qwen3-1.7B and strip markdown fences from the output."""
    global _qwen_model, _qwen_tokenizer
    if _qwen_model is None:
        if not _load_qwen():
            return None
    try:
        import torch
        text = _qwen_tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = _qwen_tokenizer([text], return_tensors="pt").to(_qwen_model.device)
        with torch.no_grad():
            outputs = _qwen_model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.1,
                do_sample=True,
                pad_token_id=_qwen_tokenizer.eos_token_id,
            )
        input_len = inputs["input_ids"].shape[1]
        generated = outputs[0][input_len:]
        result = _qwen_tokenizer.decode(generated, skip_special_tokens=True).strip()
        result = re.sub(r"```(?:json)?\s*", "", result).strip()
        result = result.rstrip("`").strip()
        return result if result else None
    except Exception as e:
        logger.error(f"generate_json error: {e}")
        return None


class SpacyLLMExtractor(AbstractExtractor):
    """Pipeline B — spaCy NER + Qwen3-1.7B few-shot temporal extraction."""

    def __init__(self, model_name: str = "en_core_web_trf"):
        self.model_name = model_name
        self._nlp: Optional[spacy.Language] = None
        self.temporal_parser = TemporalParser()

    @property
    def nlp(self) -> spacy.Language:
        if self._nlp is None:
            logger.info(f"Loading spaCy model: {self.model_name}")
            self._nlp = spacy.load(self.model_name)
        return self._nlp

    def get_name(self) -> str:
        return "llm"

    def is_available(self) -> bool:
        return _load_qwen()

    def extract(self, article: Article) -> list[TemporalFact]:
        doc = self.nlp(article.text)

        pub_date_str = (
            article.publication_date.strftime("%Y-%m-%d")
            if article.publication_date else "unknown"
        )

        accumulated: list[TemporalFact] = []

        for sent_idx, sent in enumerate(doc.sents):
            if not _YEAR_RE.search(sent.text):
                continue

            user_prompt = USER_PROMPT_TEMPLATE.format(
                title=article.title,
                pub_date=pub_date_str,
                text=sent.text,
            )

            messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
            for user_msg, asst_msg in zip(EXAMPLE_INPUTS, EXAMPLE_OUTPUTS):
                messages.append({"role": "user", "content": user_msg})
                messages.append({"role": "assistant", "content": asst_msg})
            messages.append({"role": "user", "content": user_prompt})

            raw_response = generate_json(messages)
            if not raw_response:
                continue

            raw_facts = self._parse_json_response(raw_response)
            if not raw_facts:
                continue

            facts = self._convert_to_temporal_facts(raw_facts, article.publication_date, sent_idx)
            accumulated.extend(facts)

        seen: set[tuple[str, str, str]] = set()
        result: list[TemporalFact] = []
        for fact in accumulated:
            key = (
                fact.subject.text.lower(),
                fact.predicate.value,
                fact.object.text.lower(),
            )
            if key not in seen:
                seen.add(key)
                result.append(fact)

        logger.info(
            f"SpacyLLMExtractor: {len(result)} facts "
            f"({len(accumulated)} before dedup, {len(list(doc.sents))} sentences)"
        )
        return result

    def _parse_json_response(self, raw: str) -> list[dict[str, Any]]:
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

        logger.debug(f"SpacyLLMExtractor: JSON parse failed: {raw[:200]}...")
        return []

    def _convert_to_temporal_facts(
        self, raw_facts: list[dict], pub_date: Optional[datetime], sent_idx: int,
    ) -> list[TemporalFact]:
        facts = []
        for i, raw in enumerate(raw_facts):
            try:
                fact = self._single_fact(raw, i, pub_date, sent_idx)
                if fact is not None:
                    facts.append(fact)
            except Exception as e:
                logger.debug(f"SpacyLLMExtractor: fact #{i} error - {e}")
        return facts

    def _single_fact(
        self, raw: dict, idx: int, pub_date: Optional[datetime], sent_idx: int,
    ) -> Optional[TemporalFact]:
        subj_text = raw.get("subject", "").strip()
        obj_text = raw.get("object", "").strip()

        if not subj_text:
            logger.debug(f"LLM fact #{idx}: REJECT — empty subject")
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
            logger.debug(f"LLM fact #{idx}: REJECT — no temporal anchor for '{subj_text}'")
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
            # Index of the sentence in the article (spaCy doc.sents order), not
            # the index of the fact inside the LLM JSON response — TextHighlight
            # and fact_annotations map on this value
            source_sentence_idx=sent_idx,
            extraction_confidence=confidence,
            extractor="llm",
        )

    def _parse_time_field(
        self, raw: dict, field: str, pub_date: Optional[datetime],
    ) -> Optional[TemporalExpression]:
        value = raw.get(field)
        if not value or value == "null" or value == "None":
            return None
        return self._parse_raw_expression(str(value), pub_date)

    def _parse_raw_expression(
        self, raw_text: str, pub_date: Optional[datetime],
    ) -> Optional[TemporalExpression]:
        results = self.temporal_parser.parse_all_in_sentence(
            sentence=raw_text,
            date_spans=[(0, len(raw_text), raw_text)],
            reference_date=pub_date,
        )
        return results[0] if results else None

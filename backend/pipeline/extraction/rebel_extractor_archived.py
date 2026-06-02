# Archived — REBEL-large removed in v1.0 (F1=0.038, not worth the overhead)
# Kept for thesis documentation purposes.
"""C1 — Pipeline C: relation extraction via REBEL-large (Babelscape)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from backend.pipeline.extraction.base import AbstractExtractor
from backend.pipeline.graph.models import (
    Article, Entity, EntityType, RelationType, TemporalFact,
)

logger = logging.getLogger(__name__)

REBEL_RELATION_MAP: dict[str, RelationType] = {
    "position held": RelationType.HOLDS_POSITION,
    "member of": RelationType.MEMBER_OF,
    "employer": RelationType.HOLDS_POSITION,
    "office held by head of government": RelationType.HOLDS_POSITION,
    "head of government": RelationType.HOLDS_POSITION,
    "head of state": RelationType.HOLDS_POSITION,
    "legislative body": RelationType.MEMBER_OF,
    "political party": RelationType.MEMBER_OF,
    "country of citizenship": RelationType.LOCATED_IN,
    "place of birth": RelationType.LOCATED_IN,
    "located in": RelationType.LOCATED_IN,
    "part of": RelationType.MEMBER_OF,
}

DEFAULT_RELATION = RelationType.GENERIC

LOCATION_KEYWORDS = {
    "united states", "russia", "china", "congress", "senate",
    "house", "washington", "new york",
}
EVENT_KEYWORDS = {
    "election", "summit", "conference", "war", "crisis",
    "reform", "act", "bill", "agreement",
}

# ~450 tokens — safety margin below the 512-token limit
_MAX_CHUNK_CHARS = 1800


class RebelExtractor(AbstractExtractor):
    """REBEL-large extractor: extracts relation triplets from English text."""

    def __init__(self) -> None:
        self._pipe = None

    def get_name(self) -> str:
        return "rebel"

    def is_available(self) -> bool:
        """Checks that the rebel-large model is present in the HuggingFace cache."""
        cache = Path.home() / ".cache" / "huggingface" / "hub"
        if not cache.exists():
            return False
        return any("rebel-large" in str(p) for p in cache.iterdir())

    def _load_pipeline(self) -> None:
        """Lazy load: instantiates the REBEL pipeline on the first extract() call."""
        import importlib
        transformers = importlib.import_module("transformers")
        hf_pipeline = getattr(transformers, "pipeline")
        self._pipe = hf_pipeline(
            "text2text-generation",
            model="Babelscape/rebel-large",
            tokenizer="Babelscape/rebel-large",
        )
        logger.info("REBEL pipeline loaded.")

    def extract(self, article: Article) -> list[TemporalFact]:
        """Extracts facts from article: chunking → REBEL → triplet parsing → TemporalFact."""
        if self._pipe is None:
            try:
                self._load_pipeline()
            except Exception as exc:
                logger.warning(f"REBEL: unable to load model — {exc}")
                return []

        chunks = self._split_into_chunks(article.text)
        facts: list[TemporalFact] = []
        seen: set[tuple[str, str, str]] = set()

        for sent_idx, chunk in enumerate(chunks):
            try:
                outputs = self._pipe(chunk, max_length=512, num_beams=3)
                raw_text = outputs[0]["generated_text"] if outputs else ""
            except Exception as exc:
                logger.warning(f"REBEL: error on chunk {sent_idx} — {exc}")
                continue

            if not raw_text:
                continue

            triplets = self._parse_rebel_output(raw_text)
            for triplet in triplets:
                if triplet["subject"].lower() == triplet["object"].lower():
                    continue

                key = (
                    triplet["subject"].lower(),
                    triplet["relation"].lower(),
                    triplet["object"].lower(),
                )
                if key in seen:
                    continue
                seen.add(key)

                fact = self._triplet_to_fact(triplet, article, sent_idx)
                if fact is not None:
                    facts.append(fact)

        return facts

    def _split_into_chunks(self, text: str) -> list[str]:
        """Splits text into chunks of max ~512 tokens by splitting on sentence boundaries."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        chunks: list[str] = []
        current = ""

        for sent in sentences:
            if not sent:
                continue
            if current and len(current) + 1 + len(sent) > _MAX_CHUNK_CHARS:
                chunks.append(current.strip())
                current = sent
            else:
                current = (current + " " + sent).strip() if current else sent

        if current:
            chunks.append(current.strip())

        return chunks

    def _parse_rebel_output(self, text: str) -> list[dict]:
        """Parses REBEL output — format uses double spaces as separators."""
        triplets = []
        # Real format: ' subject  object  relation' (separators = 2+ spaces)
        import re
        parts = [p.strip() for p in re.split(r'\s{2,}', text.strip()) if p.strip()]
        # Group every 3: subject, object, relation
        for i in range(0, len(parts) - 2, 3):
            subject = parts[i]
            obj = parts[i + 1]
            relation = parts[i + 2]
            if subject and obj and relation and subject.lower() != obj.lower():
                triplets.append({
                    "subject": subject,
                    "object": obj,
                    "relation": relation,
                })
        return triplets

    def _triplet_to_fact(
        self, triplet: dict, article: Article, sent_idx: int
    ) -> Optional[TemporalFact]:
        """Converts a REBEL triplet to a TemporalFact with confidence 0.75."""
        subject = Entity(
            text=triplet["subject"],
            entity_type=EntityType.PERSON,
            start_char=0,
            end_char=len(triplet["subject"]),
        )
        obj = Entity(
            text=triplet["object"],
            entity_type=self._detect_type(triplet["object"]),
            start_char=0,
            end_char=len(triplet["object"]),
        )
        predicate = REBEL_RELATION_MAP.get(triplet["relation"].lower(), DEFAULT_RELATION)

        return TemporalFact(
            subject=subject,
            predicate=predicate,
            object=obj,
            time_point=None,
            source_sentence="",
            source_sentence_idx=sent_idx,
            extraction_confidence=0.75,
            extractor="rebel",
        )

    def _detect_type(self, text: str) -> EntityType:
        """Detects the object entity type based on known keywords."""
        lower = text.lower()
        if any(kw in lower for kw in LOCATION_KEYWORDS):
            return EntityType.LOCATION
        if any(kw in lower for kw in EVENT_KEYWORDS):
            return EntityType.EVENT
        return EntityType.ORGANIZATION

"""C1 — Pipeline A: extractie deterministica de fapte temporale cu spaCy (en_core_web_trf)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import spacy
from spacy.tokens import Doc, Span, Token

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

# Mapari NER si dependency
# Mapare de la labelurile NER ale spaCy la EntityType intern
SPACY_TO_ENTITY_TYPE = {
    "PERSON": EntityType.PERSON,
    "ORG": EntityType.ORGANIZATION,
    "GPE": EntityType.LOCATION,
    "LOC": EntityType.LOCATION,
    "EVENT": EntityType.EVENT,
    "DATE": EntityType.DATE,
    "NORP": EntityType.NORP,
    "PRODUCT": EntityType.PRODUCT,
}

# Dependency labels care indica rolul de subiect / obiect
SUBJECT_DEPS = {"nsubj", "nsubjpass", "agent"}
OBJECT_DEPS = {"dobj", "attr", "pobj", "oprd", "appos"}


# Clasificare relatii pe baza lemei verbului
POSITION_VERBS = {
    "serve", "elect", "appoint", "become", "lead", "head", "chair",
    "run", "name", "install", "retain",
}

MEMBERSHIP_VERBS = {
    "join", "belong", "member", "found", "establish",
    "leave", "resign", "quit", "exit",
}

EVENT_VERBS = {
    "occur", "happen", "take", "hold", "begin", "start", "end", "sign",
    "win", "announce", "publish", "launch", "release", "open", "close", "award",
}

CAUSAL_VERBS = {"cause", "lead", "result", "trigger", "spark"}


class SpacyExtractor(AbstractExtractor):
    """Pipeline A — extractor deterministic (NER + dependency parsing + reguli)."""

    def __init__(self, model_name: str = "en_core_web_trf"):
        self.model_name = model_name
        self._nlp: Optional[spacy.Language] = None
        self.temporal_parser = TemporalParser()

    @property
    def nlp(self) -> spacy.Language:
        """Lazy-load: incarca modelul spaCy doar la prima folosire."""
        if self._nlp is None:
            logger.info(f"Se incarca modelul spaCy: {self.model_name}")
            self._nlp = spacy.load(self.model_name)
        return self._nlp

    def get_name(self) -> str:
        return "spacy"


    # Metoda principala
    def extract(self, article: Article) -> list[TemporalFact]:
        """Extrage fapte temporale din articol: spaCy NLP → propozitii → dependency → TemporalFact."""
        doc = self.nlp(article.text)
        facts: list[TemporalFact] = []

        for sent_idx, sent in enumerate(doc.sents):
            sent_facts = self._extract_from_sentence(sent, sent_idx, article.publication_date)
            facts.extend(sent_facts)

        logger.info(f"SpacyExtractor: {len(facts)} fapte din {len(list(doc.sents))} propozitii")
        return facts


    # Extractie la nivel de propozitie
    def _extract_from_sentence(
        self, sent: Span, sent_idx: int, pub_date: Optional[datetime],
    ) -> list[TemporalFact]:
        """Extrage fapte dintr-o singura propozitie. Fallback la asociere simpla daca dep. parse esueaza."""

        # Entitati non-DATE
        entities = [self._span_to_entity(ent) for ent in sent.ents if ent.label_ != "DATE"]

        # Expresii temporale (DATE → parsare cu temporal_parser)
        date_spans = [
            (ent.start_char, ent.end_char, ent.text)
            for ent in sent.ents if ent.label_ == "DATE"
        ]
        temporal_exprs = self.temporal_parser.parse_all_in_sentence(
            sent.text, date_spans, reference_date=pub_date,
        )

        # Minim o entitate SI o expresie temporala
        if not entities or not temporal_exprs:
            return []

        # Incercare prin dependency parsing; fallback daca nu gaseste structura
        facts = self._extract_via_dependencies(sent, entities, temporal_exprs, sent_idx)
        if not facts:
            facts = self._fallback_entity_date_pairs(entities, temporal_exprs, sent, sent_idx)

        return facts


    # Extractie structurata prin dependency parsing
    def _extract_via_dependencies(
        self, sent: Span, entities: list[Entity],
        temporal_exprs: list[TemporalExpression], sent_idx: int,
    ) -> list[TemporalFact]:
        """Extrage triple subj-pred-obj din arborele de dependente si le leaga de expresii temporale."""
        # Verbul radacina al propozitiei
        root = next((t for t in sent if t.dep_ == "ROOT" and t.pos_ == "VERB"), None)
        if root is None:
            return []

        subjects = self._find_entities_by_dep(root, SUBJECT_DEPS, entities)
        if not subjects:
            return []

        objects = self._find_entities_by_dep(root, OBJECT_DEPS, entities)
        relation = self._classify_relation(root)
        time_start, time_end, time_point = self._assign_temporal(temporal_exprs)

        # Fapt pentru fiecare pereche subiect-obiect
        facts = []
        for subj in subjects:
            for obj in objects:
                facts.append(TemporalFact(
                    subject=subj,
                    predicate=relation,
                    object=obj,
                    time_start=time_start,
                    time_end=time_end,
                    time_point=time_point if not time_start else None,
                    source_sentence=sent.text,
                    source_sentence_idx=sent_idx,
                    extraction_confidence=0.8,
                    extractor="spacy",
                ))
        return facts

    def _find_entities_by_dep(
        self, root: Token, dep_labels: set[str], entities: list[Entity],
    ) -> list[Entity]:
        """
        Gaseste entitatile legate de radacina prin dependency labels specifice.
        Parcurge copiii directi, apoi sub-arborii (fraze prepozitionale).
        Deduplicare prin (start_char, end_char).
        """
        matched = []
        seen_spans: set[tuple[int, int]] = set()

        def _try_add(entity: Entity) -> None:
            key = (entity.start_char, entity.end_char)
            if key not in seen_spans:
                seen_spans.add(key)
                matched.append(entity)

        for child in root.children:
            if child.dep_ in dep_labels:
                # Match direct pe token
                for entity in entities:
                    if entity.start_char <= child.idx < entity.end_char or (
                        entity.start_char <= child.idx + len(child.text)
                        and entity.end_char >= child.idx
                    ):
                        _try_add(entity)
                        break
                # Sub-arbore (fraze prepozitionale complexe)
                for desc in child.subtree:
                    for entity in entities:
                        if entity.start_char <= desc.idx < entity.end_char:
                            _try_add(entity)
        return matched


    # Clasificare relatie si asignare temporala
    def _classify_relation(self, verb: Token) -> RelationType:
        """Determina tipul relatiei pe baza lemei verbului."""
        lemma = verb.lemma_.lower()

        if lemma in POSITION_VERBS:
            return RelationType.HOLDS_POSITION
        elif lemma in MEMBERSHIP_VERBS:
            return RelationType.MEMBER_OF
        elif lemma in EVENT_VERBS:
            return RelationType.OCCURRED_ON
        elif lemma in CAUSAL_VERBS:
            return RelationType.CAUSED
        elif lemma in {"precede", "before"}:
            return RelationType.PRECEDED
        elif lemma in {"follow", "after", "succeed"}:
            return RelationType.FOLLOWED
        else:
            return RelationType.GENERIC

    def _assign_temporal(
        self, exprs: list[TemporalExpression],
    ) -> tuple[Optional[TemporalExpression], Optional[TemporalExpression], Optional[TemporalExpression]]:
        """
        Asignare expresii temporale la roluri start/end/point.
        1 data → point; 2+ date → prima = start, a doua = end (sortate dupa pozitie).
        """
        if len(exprs) == 0:
            return None, None, None
        elif len(exprs) == 1:
            return None, None, exprs[0]
        else:
            sorted_exprs = sorted(exprs, key=lambda e: e.start_char)
            return sorted_exprs[0], sorted_exprs[1], None


    # Fallback: asociere simpla entitate-data
    def _fallback_entity_date_pairs(
        self, entities: list[Entity], temporal_exprs: list[TemporalExpression],
        sent: Span, sent_idx: int,
    ) -> list[TemporalFact]:
        """Fallback: asociere simpla intre prima entitate si expresiile temporale. Confidence = 0.5."""
        if not entities or not temporal_exprs:
            return []

        primary_entity = entities[0]
        time_start, time_end, time_point = self._assign_temporal(temporal_exprs)

        obj = entities[1] if len(entities) > 1 else Entity(
            text="[context]", entity_type=EntityType.OTHER,
            start_char=0, end_char=0,
        )

        return [TemporalFact(
            subject=primary_entity,
            predicate=RelationType.GENERIC,
            object=obj,
            time_start=time_start,
            time_end=time_end,
            time_point=time_point if not time_start else None,
            source_sentence=sent.text,
            source_sentence_idx=sent_idx,
            extraction_confidence=0.5,
            extractor="spacy",
        )]


    # Utilitare
    def _span_to_entity(self, ent: Span) -> Entity:
        """Converteste un span NER spaCy in Entity intern."""
        entity_type = SPACY_TO_ENTITY_TYPE.get(ent.label_, EntityType.OTHER)
        return Entity(
            text=ent.text, entity_type=entity_type,
            start_char=ent.start_char, end_char=ent.end_char,
        )
"""
Pipeline A: Extractie deterministica de fapte temporale cu spaCy.

Foloseste en_core_web_trf pentru:
  - Named Entity Recognition (PERSON, ORG, GPE, DATE, EVENT, etc.)
  - Dependency parsing ca sa lege entitatile de expresii temporale
  - Segmentare pe propozitii

Flow:
  1. Proceseaza articolul cu spaCy
  2. Pentru fiecare propozitie, extrage entitati si expresii temporale
  3. Foloseste dependency parsing ca sa lege subject -> predicat -> obiect
  4. Asociaza relatiile cu expresiile temporale
  5. Returneaza lista de TemporalFact
"""

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

# Mapare de la labelurile NER ale spaCy la EntityType-urile noastre
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

# Dependency labels care indica rolul de subiect/obiect
SUBJECT_DEPS = {"nsubj", "nsubjpass", "agent"}
OBJECT_DEPS = {"dobj", "attr", "pobj", "oprd", "appos"}

# Verbe asociate cu diferite tipuri de relatii temporale
POSITION_VERBS = {"serve", "elect", "appoint", "become", "lead", "head", "chair"}
MEMBERSHIP_VERBS = {"join", "belong", "member", "found", "establish"}
EVENT_VERBS = {"occur", "happen", "take", "hold", "begin", "start", "end", "sign"}
CAUSAL_VERBS = {"cause", "lead", "result", "trigger", "spark"}


class SpacyExtractor(AbstractExtractor):
    """
    Extractor deterministic de fapte temporale folosind spaCy NLP.

    Acesta e Pipeline A — extractorul baseline care foloseste
    NLP pur statistic/rule-based, fara LLM.
    """

    def __init__(self, model_name: str = "en_core_web_trf"):
        self.model_name = model_name
        self._nlp: Optional[spacy.Language] = None
        self.temporal_parser = TemporalParser()

    @property
    def nlp(self) -> spacy.Language:
        """Lazy-load — incarca modelul spaCy doar la prima folosire."""
        if self._nlp is None:
            logger.info(f"Se incarca modelul spaCy: {self.model_name}")
            self._nlp = spacy.load(self.model_name)
        return self._nlp

    def get_name(self) -> str:
        return "spacy"

    def extract(self, article: Article) -> list[TemporalFact]:
        """
        Extrage fapte temporale dintr-un articol.

        Pasi:
          1. Ruleaza spaCy pe textul complet
          2. Pentru fiecare propozitie, gaseste entitati si date
          3. Incearca sa lege entitatile prin arborele de dependente
          4. Asociaza cu expresii temporale → TemporalFact
        """
        doc = self.nlp(article.text)
        facts: list[TemporalFact] = []

        for sent_idx, sent in enumerate(doc.sents):
            sent_facts = self._extract_from_sentence(
                sent, sent_idx, article.publication_date
            )
            facts.extend(sent_facts)

        logger.info(
            f"S-au extras {len(facts)} fapte temporale "
            f"({len(list(doc.sents))} propozitii)"
        )
        return facts

    def _extract_from_sentence(
        self,
        sent: Span,
        sent_idx: int,
        pub_date: Optional[datetime],
    ) -> list[TemporalFact]:
        """Extrage fapte temporale dintr-o singura propozitie."""

        # 1. Colecteaza entitatile non-DATE
        entities = [
            self._span_to_entity(ent)
            for ent in sent.ents
            if ent.label_ != "DATE"
        ]

        # 2. Colecteaza entitatile DATE → parseaza cu temporal_parser
        date_spans = [
            (ent.start_char, ent.end_char, ent.text)
            for ent in sent.ents
            if ent.label_ == "DATE"
        ]
        temporal_exprs = self.temporal_parser.parse_all_in_sentence(
            sent.text, date_spans, reference_date=pub_date
        )

        if not entities or not temporal_exprs:
            # Trebuie minim o entitate SI o expresie temporala
            return []

        # 3. Incearca extractie structurata prin dependency parsing
        facts = self._extract_via_dependencies(
            sent, entities, temporal_exprs, sent_idx
        )

        # 4. Fallback: daca nu gaseste structura, creeaza asocieri simple
        if not facts:
            facts = self._fallback_entity_date_pairs(
                entities, temporal_exprs, sent, sent_idx
            )

        return facts

    def _extract_via_dependencies(
        self,
        sent: Span,
        entities: list[Entity],
        temporal_exprs: list[TemporalExpression],
        sent_idx: int,
    ) -> list[TemporalFact]:
        """
        Foloseste dependency parsing ca sa extraga triple
        subiect-predicat-obiect si sa le asocieze cu expresii temporale.
        """
        facts = []

        # Gaseste verbul radacina al propozitiei
        root = None
        for token in sent:
            if token.dep_ == "ROOT" and token.pos_ == "VERB":
                root = token
                break

        if root is None:
            return []

        # Gaseste subiectul si obiectul prin relatii de dependenta
        subjects = self._find_entities_by_dep(root, SUBJECT_DEPS, entities)
        objects = self._find_entities_by_dep(root, OBJECT_DEPS, entities)

        if not subjects:
            return []

        # Determina tipul relatiei din verb
        relation = self._classify_relation(root)

        # Asigneaza expresiile temporale
        time_start, time_end, time_point = self._assign_temporal(temporal_exprs)

        # Creeaza fapte pentru fiecare pereche subiect-obiect
        for subj in subjects:
            for obj in objects:
                fact = TemporalFact(
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
                )
                facts.append(fact)

        return facts

    def _find_entities_by_dep(
        self,
        root: Token,
        dep_labels: set[str],
        entities: list[Entity],
    ) -> list[Entity]:
        """Gaseste entitatile legate de radacina prin dependency labels specifice."""
        matched = []
        for child in root.children:
            if child.dep_ in dep_labels:
                # Verifica daca vreo entitate acopera acest token
                for entity in entities:
                    if (
                        child.idx >= entity.start_char
                        and child.idx < entity.end_char
                    ) or (
                        entity.start_char <= child.idx + len(child.text)
                        and entity.end_char >= child.idx
                    ):
                        matched.append(entity)
                        break
                # Verifica si sub-arborele (pentru fraze prepozitionale)
                for desc in child.subtree:
                    for entity in entities:
                        if (
                            desc.idx >= entity.start_char
                            and desc.idx < entity.end_char
                            and entity not in matched
                        ):
                            matched.append(entity)
        return matched

    def _classify_relation(self, verb: Token) -> RelationType:
        """Clasifica tipul relatiei pe baza lemei verbului."""
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
        self, exprs: list[TemporalExpression]
    ) -> tuple[
        Optional[TemporalExpression],
        Optional[TemporalExpression],
        Optional[TemporalExpression],
    ]:
        """
        Asigneaza expresiile temporale la roluri start/end/point.

        Regula:
          - 1 data  → time_point
          - 2 date  → prima e start, a doua e end
          - 3+ date → primele doua sunt start/end, restul ignorate
        """
        if len(exprs) == 0:
            return None, None, None
        elif len(exprs) == 1:
            return None, None, exprs[0]
        else:
            # Sorteaza dupa pozitia in text
            sorted_exprs = sorted(exprs, key=lambda e: e.start_char)
            return sorted_exprs[0], sorted_exprs[1], None

    def _fallback_entity_date_pairs(
        self,
        entities: list[Entity],
        temporal_exprs: list[TemporalExpression],
        sent: Span,
        sent_idx: int,
    ) -> list[TemporalFact]:
        """
        Fallback: cand dependency parsing nu gaseste structura,
        creeaza asocieri simple intre prima entitate si expresiile temporale.
        Confidence mai mic (0.5) — indica ca e o aproximare.
        """
        if not entities or not temporal_exprs:
            return []

        primary_entity = entities[0]
        time_start, time_end, time_point = self._assign_temporal(temporal_exprs)

        # Foloseste a doua entitate ca obiect, sau placeholder
        obj = entities[1] if len(entities) > 1 else Entity(
            text="[context]",
            entity_type=EntityType.OTHER,
            start_char=0,
            end_char=0,
        )

        return [
            TemporalFact(
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
            )
        ]

    def _span_to_entity(self, ent: Span) -> Entity:
        """Converteste un span spaCy in Entity-ul nostru."""
        entity_type = SPACY_TO_ENTITY_TYPE.get(ent.label_, EntityType.OTHER)
        return Entity(
            text=ent.text,
            entity_type=entity_type,
            start_char=ent.start_char,
            end_char=ent.end_char,
        )
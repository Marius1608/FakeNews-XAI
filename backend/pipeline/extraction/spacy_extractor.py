"""C1 — Pipeline A: extracție deterministică de fapte temporale cu spaCy (en_core_web_trf)."""

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

# spaCy label to internal EntityType mapping
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

SUBJECT_DEPS = {"nsubj", "nsubjpass", "agent"}
OBJECT_DEPS = {"dobj", "attr", "pobj", "oprd", "appos"}

# Verb sets for relation classification
POSITION_VERBS = {
    "serve", "elect", "appoint", "become", "lead", "head", "chair",
    "run", "name", "install", "retain",
    "inaugurate", "swear", "govern", "preside", "oversee", "nominate", "confirm", "impeach"
}

MEMBERSHIP_VERBS = {
    "join", "belong", "member", "found", "establish",
    "leave", "resign", "quit", "exit",
    "enroll", "affiliate", "associate", "expel", "suspend", "withdraw"
}

EVENT_VERBS = {
    "occur", "happen", "take", "hold", "begin", "start", "end", "sign",
    "win", "announce", "publish", "launch", "release", "open", "close", "award",
    "vote", "ratify", "negotiate", "sanction", "invade", "withdraw", "deploy", "assassinate", "die", "born", "graduate", "marry", "divorce", "arrest", "convict", "acquit", "pardon", "pass", "repeal", "amend", "declare", "inaugurate", "summit", "strike", "protest", "collapse", "merge", "acquire"
}

CAUSAL_VERBS = {
    "cause", "lead", "result", "trigger", "spark",
    "provoke", "enable", "prevent", "force", "motivate", "prompt"
}

TEMPORAL_VERBS = {
    "last", "continue", "resume", "extend", "postpone", "delay",
    "schedule", "plan", "expire", "renew",
}


class SpacyExtractor(AbstractExtractor):
    """Pipeline A — deterministic extractor (NER + dependency parsing + rules)."""

    def __init__(self, model_name: str = "en_core_web_trf"):
        self.model_name = model_name
        self._nlp: Optional[spacy.Language] = None
        self.temporal_parser = TemporalParser()

    @property
    def nlp(self) -> spacy.Language:
        """Load the spaCy model on first use (lazy load)."""
        if self._nlp is None:
            logger.info(f"Loading spaCy model: {self.model_name}")
            self._nlp = spacy.load(self.model_name)
        return self._nlp

    def get_name(self) -> str:
        return "spacy"

    # Main extraction entry point
    def extract(self, article: Article) -> list[TemporalFact]:
        """Extract temporal facts from an article by processing each sentence."""
        doc = self.nlp(article.text)
        facts: list[TemporalFact] = []

        dep_count = 0
        nominal_count = 0
        fallback_count = 0
        sent_count = len(list(doc.sents))

        for sent_idx, sent in enumerate(doc.sents):
            s_facts, d_cnt, n_cnt, f_cnt = self._extract_from_sentence(sent, sent_idx, article.publication_date)
            facts.extend(s_facts)
            dep_count += d_cnt
            nominal_count += n_cnt
            fallback_count += f_cnt

        logger.info(f"SpacyExtractor: {len(facts)} facts from {sent_count} sentences "
                    f"(dep: {dep_count}, nominal: {nominal_count}, fallback: {fallback_count})")
        return facts

    # Sentence-level extraction
    def _extract_from_sentence(
        self, sent: Span, sent_idx: int, pub_date: Optional[datetime],
    ) -> tuple[list[TemporalFact], int, int, int]:
        """Extract facts from one sentence; falls back if parsing yields nothing."""
        entities = [self._span_to_entity(ent) for ent in sent.ents if ent.label_ != "DATE"]

        date_spans = [
            (ent.start_char, ent.end_char, ent.text)
            for ent in sent.ents if ent.label_ == "DATE"
        ]
        temporal_exprs = self.temporal_parser.parse_all_in_sentence(
            sent.text, date_spans, reference_date=pub_date,
        )

        facts = []
        dep_cnt, nom_cnt, fall_cnt = 0, 0, 0

        logger.debug(f"Sent[{sent_idx}]: {len(entities)} entities, {len(temporal_exprs)} dates")
        if not entities:
            logger.debug(f"Sent[{sent_idx}]: SKIP — no non-DATE entities")
            return facts, dep_cnt, nom_cnt, fall_cnt
        if not temporal_exprs:
            logger.debug(f"Sent[{sent_idx}]: SKIP — no temporal expressions")
            return facts, dep_cnt, nom_cnt, fall_cnt

        # 1. Dependency parsing
        dep_facts = self._extract_via_dependencies(sent, entities, temporal_exprs, sent_idx)
        facts.extend(dep_facts)
        dep_cnt = len(dep_facts)

        # 2. Nominal phrases
        nom_facts = self._extract_nominal_facts(sent, entities, temporal_exprs, sent_idx)
        for nf in nom_facts:
            if not any(f.subject.text == nf.subject.text and f.time_point == nf.time_point for f in facts):
                facts.append(nf)
                nom_cnt += 1

        # 3. Fallback: raw entity-date pairing
        if not facts:
            fall_facts = self._fallback_entity_date_pairs(entities, temporal_exprs, sent, sent_idx)
            facts.extend(fall_facts)
            fall_cnt = len(fall_facts)

        return facts, dep_cnt, nom_cnt, fall_cnt

    # Dependency-based extraction
    def _extract_via_dependencies(
        self, sent: Span, entities: list[Entity],
        temporal_exprs: list[TemporalExpression], sent_idx: int,
    ) -> list[TemporalFact]:
        """Extract triples from the dependency tree associated with temporal expressions."""
        root = next((t for t in sent if t.dep_ == "ROOT" and t.pos_ == "VERB"), None)
        if root is None:
            return []

        subjects = self._find_entities_by_dep(root, SUBJECT_DEPS, entities)
        if not subjects:
            return []

        objects = self._find_entities_by_dep(root, OBJECT_DEPS, entities)
        relation = self._classify_relation(root)
        time_start, time_end, time_point = self._assign_temporal(temporal_exprs)

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
        """Find entities linked to the root token via the given dependency labels."""
        matched = []
        seen_spans: set[tuple[int, int]] = set()

        def _try_add(entity: Entity) -> None:
            key = (entity.start_char, entity.end_char)
            if key not in seen_spans:
                seen_spans.add(key)
                matched.append(entity)

        for child in root.children:
            if child.dep_ in dep_labels:
                for entity in entities:
                    if entity.start_char <= child.idx < entity.end_char or (
                        entity.start_char <= child.idx + len(child.text)
                        and entity.end_char >= child.idx
                    ):
                        _try_add(entity)
                        break
                for desc in child.subtree:
                    for entity in entities:
                        if entity.start_char <= desc.idx < entity.end_char:
                            _try_add(entity)
        return matched

    # Nominal phrase extraction
    def _extract_nominal_facts(
        self, sent: Span, entities: list[Entity], temporal_exprs: list[TemporalExpression], sent_idx: int,
    ) -> list[TemporalFact]:
        """Detect entity-date associations in the absence of a clear verb."""
        facts = []
        for temp_expr in temporal_exprs:
            temp_token = next((t for t in sent if t.idx >= temp_expr.start_char and t.idx < temp_expr.end_char), None)
            if not temp_token:
                continue

            for token in sent:
                if token.pos_ in {"NOUN", "PROPN"}:
                    if abs(token.i - temp_token.i) <= 2:
                        subj = min(entities, key=lambda e: abs(e.start_char - temp_expr.start_char), default=None)
                        if subj:
                            obj = Entity(
                                text=token.text, entity_type=EntityType.OTHER,
                                start_char=token.idx, end_char=token.idx + len(token.text),
                            )
                            facts.append(TemporalFact(
                                subject=subj, predicate=RelationType.GENERIC, object=obj,
                                time_point=temp_expr, source_sentence=sent.text,
                                source_sentence_idx=sent_idx, extraction_confidence=0.6,
                                extractor="spacy",
                            ))
                            break
        return facts

    # Relation classification
    def _classify_relation(self, verb: Token) -> RelationType:
        """Determine the relation type based on the verb lemma."""
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
        elif lemma in TEMPORAL_VERBS:
            return RelationType.GENERIC
        else:
            return RelationType.GENERIC

    def _assign_temporal(
        self, exprs: list[TemporalExpression],
    ) -> tuple[Optional[TemporalExpression], Optional[TemporalExpression], Optional[TemporalExpression]]:
        """Assign temporal expressions to interval start/end or a single time point."""
        if len(exprs) == 0:
            return None, None, None
        elif len(exprs) == 1:
            return None, None, exprs[0]
        else:
            sorted_exprs = sorted(exprs, key=lambda e: e.start_char)
            return sorted_exprs[0], sorted_exprs[1], None

    # Fallback extraction
    def _fallback_entity_date_pairs(
        self, entities: list[Entity], temporal_exprs: list[TemporalExpression],
        sent: Span, sent_idx: int,
    ) -> list[TemporalFact]:
        """Raw entity-date pairing. Limited to 5 facts per sentence."""
        if not entities or not temporal_exprs:
            return []

        time_start, time_end, time_point = self._assign_temporal(temporal_exprs)
        facts = []

        for i, subj in enumerate(entities):
            if len(facts) >= 5:
                break

            obj = entities[i+1] if i + 1 < len(entities) else Entity(
                text="[context]", entity_type=EntityType.OTHER,
                start_char=0, end_char=0,
            )

            facts.append(TemporalFact(
                subject=subj,
                predicate=RelationType.GENERIC,
                object=obj,
                time_start=time_start,
                time_end=time_end,
                time_point=time_point if not time_start else None,
                source_sentence=sent.text,
                source_sentence_idx=sent_idx,
                extraction_confidence=0.5,
                extractor="spacy",
            ))

        return facts

    # Utilities
    def _span_to_entity(self, ent: Span) -> Entity:
        """Convert a spaCy span to the internal Entity format."""
        entity_type = SPACY_TO_ENTITY_TYPE.get(ent.label_, EntityType.OTHER)
        return Entity(
            text=ent.text, entity_type=entity_type,
            start_char=ent.start_char, end_char=ent.end_char,
        )

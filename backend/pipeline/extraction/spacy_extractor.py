"""C1 — Pipeline A: deterministic temporal fact extraction with spaCy (en_core_web_trf)."""

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

SEQUENCE_VERBS = {
    "precede", "predate", "antedate",
    "follow", "succeed",
}

SEQUENCE_COMPOUND_PHRASES = [
    ("come before",   RelationType.PRECEDED),
    ("prior to",      RelationType.PRECEDED),
    ("before sign",   RelationType.PRECEDED),
    ("before pass",   RelationType.PRECEDED),
    ("before approv", RelationType.PRECEDED),
    ("before vote",   RelationType.PRECEDED),
    ("precede sign",  RelationType.PRECEDED),
    ("come after",    RelationType.FOLLOWED),
    ("follow from",   RelationType.FOLLOWED),
    ("result from",   RelationType.FOLLOWED),
    ("come follow",   RelationType.FOLLOWED),
]


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

        coref_map = self._resolve_coreference(doc)

        for sent_idx, sent in enumerate(doc.sents):
            s_facts, d_cnt, n_cnt, f_cnt = self._extract_from_sentence(sent, sent_idx, article.publication_date, coref_map)
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
        coref_map: Optional[dict] = None,
    ) -> tuple[list[TemporalFact], int, int, int]:
        """Extract facts from one sentence; falls back if parsing yields nothing."""
        entities = [self._span_to_entity(ent) for ent in sent.ents if ent.label_ != "DATE"]

        # Coreference: add resolved entities if the sentence contains no PERSON entity
        if coref_map and not any(e.entity_type == EntityType.PERSON for e in entities):
            added_texts = {e.text for e in entities}
            for token in sent:
                if token.i in coref_map:
                    resolved = coref_map[token.i]
                    if resolved.text not in added_texts:
                        entities.append(resolved)
                        added_texts.add(resolved.text)

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
        # Also traverse the subtree of prep children (e.g. "served as President")
        for child in root.children:
            if child.dep_ == "prep":
                for grandchild in child.children:
                    if grandchild.dep_ in dep_labels:
                        for entity in entities:
                            if entity.start_char <= grandchild.idx < entity.end_char:
                                _try_add(entity)
                                break
                        for desc in grandchild.subtree:
                            for entity in entities:
                                if entity.start_char <= desc.idx < entity.end_char:
                                    _try_add(entity)

        # Prefer PERSON/ORG as subject — GPE/LOC are objects, not actors
        if dep_labels == SUBJECT_DEPS:
            person_org = [e for e in matched if e.entity_type in {EntityType.PERSON, EntityType.ORGANIZATION}]
            return person_org if person_org else matched
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
                        # Prefer PERSON/ORG as subject in nominal facts
                        person_entities = [e for e in entities if e.entity_type in {EntityType.PERSON, EntityType.ORGANIZATION}]
                        candidates = person_entities if person_entities else entities
                        subj = min(candidates, key=lambda e: abs(e.start_char - temp_expr.start_char), default=None)
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
        """Determine the relation type based on the verb lemma and compound phrases."""
        lemma = verb.lemma_.lower()

        # Compound verb phrases take priority over single-lemma lookup
        phrase = " ".join(t.lemma_.lower() for t in verb.subtree if t.dep_ in {"aux", "prt", "compound"} or t == verb)
        if any(p in phrase for p in ("swear in", "take office", "be elect", "be appoint", "be inaugurate", "step down", "take over")):
            return RelationType.HOLDS_POSITION
        if any(p in phrase for p in ("win election", "win race", "defeat opponent")):
            return RelationType.HOLDS_POSITION

        # Sequence compound phrases
        for frag, rel in SEQUENCE_COMPOUND_PHRASES:
            if frag in phrase:
                return rel

        if lemma in POSITION_VERBS:
            return RelationType.HOLDS_POSITION
        elif lemma in {"win", "defeat", "beat"}:
            return RelationType.HOLDS_POSITION
        elif lemma in MEMBERSHIP_VERBS:
            return RelationType.MEMBER_OF
        elif lemma in EVENT_VERBS:
            return RelationType.OCCURRED_ON
        elif lemma in CAUSAL_VERBS:
            return RelationType.CAUSED
        elif lemma in {"precede", "predate", "antedate"}:
            return RelationType.PRECEDED
        elif lemma in {"follow", "succeed"}:
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

        # Sorting: PERSON and ORG have priority over GPE/LOC
        priority_order = {EntityType.PERSON: 0, EntityType.ORGANIZATION: 1}
        sorted_entities = sorted(
            entities,
            key=lambda e: priority_order.get(e.entity_type, 2)
        )

        for i, subj in enumerate(sorted_entities):
            if len(facts) >= 5:
                break

            obj = sorted_entities[i+1] if i + 1 < len(sorted_entities) else Entity(
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

    # Coreference rule-based
    def _resolve_coreference(self, doc: Doc) -> dict[int, Entity]:
        """Maps pronouns to the most recent PERSON entity seen in prior context."""
        coref_map: dict[int, Entity] = {}
        last_person: Optional[Entity] = None
        PRONOUNS = {"he", "she", "they", "his", "her", "their", "him", "them", "it"}

        for token in doc:
            # Update last_person when a PERSON entity is found
            for ent in doc.ents:
                if ent.start == token.i and ent.label_ == "PERSON":
                    last_person = Entity(
                        text=ent.text,
                        entity_type=EntityType.PERSON,
                        start_char=ent.start_char,
                        end_char=ent.end_char,
                    )
            # Map pronoun to last_person
            if token.pos_ == "PRON" and token.lemma_.lower() in PRONOUNS:
                if last_person is not None:
                    coref_map[token.i] = last_person

        return coref_map

    # Utilities
    def _span_to_entity(self, ent: Span) -> Entity:
        """Convert a spaCy span to the internal Entity format."""
        entity_type = SPACY_TO_ENTITY_TYPE.get(ent.label_, EntityType.OTHER)
        return Entity(
            text=ent.text, entity_type=entity_type,
            start_char=ent.start_char, end_char=ent.end_char,
        )

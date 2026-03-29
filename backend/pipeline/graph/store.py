"""C2 — Temporal Knowledge Graph Storage: G = (E, R, T, F) pe networkx MultiDiGraph."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import networkx as nx

from backend.pipeline.graph.models import (
    Entity, EntityType, RelationType, TemporalExpression, TemporalFact,
)

logger = logging.getLogger(__name__)


class TemporalKnowledgeGraph:
    """
    Graf temporal conform Cai et al. (2024): G = (E, R, T, F).
    Noduri = entitati, Muchii = relatii cu metadata temporala.
    """

    def __init__(self) -> None:
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._facts: list[TemporalFact] = []

    # ── Adaugare ──
    def add_fact(self, fact: TemporalFact) -> None:
        """Adauga un TemporalFact ca nod+muchie in graf."""
        subj_id = _entity_id(fact.subject)
        obj_id = _entity_id(fact.object)

        if not self._graph.has_node(subj_id):
            self._graph.add_node(subj_id, **_node_attrs(fact.subject))
        if not self._graph.has_node(obj_id):
            self._graph.add_node(obj_id, **_node_attrs(fact.object))

        edge_attrs = _edge_attrs(fact)
        self._graph.add_edge(subj_id, obj_id, **edge_attrs)
        self._facts.append(fact)

    def add_facts(self, facts: list[TemporalFact]) -> None:
        for fact in facts:
            self.add_fact(fact)
        logger.info(f"TKG: {len(facts)} fapte adaugate. Noduri: {self.node_count}, Muchii: {self.edge_count}")

    # ── Interogare noduri ──
    def get_entities_by_type(self, entity_type: EntityType) -> list[str]:
        return [nid for nid, attrs in self._graph.nodes(data=True) if attrs.get("entity_type") == entity_type.value]

    def get_node_attrs(self, entity_id: str) -> dict:
        return dict(self._graph.nodes.get(entity_id, {}))

    # ── Interogare fapte ──
    def get_all_facts(self) -> list[TemporalFact]:
        return list(self._facts)

    def get_facts_for_entity(self, entity_name: str) -> list[TemporalFact]:
        """Faptele in care entitatea apare ca subiect sau obiect."""
        entity_id = entity_name.lower().strip()
        return [f for f in self._facts if _entity_id(f.subject) == entity_id or _entity_id(f.object) == entity_id]

    def get_edges_in_interval(self, t_start: datetime, t_end: datetime) -> list[dict]:
        """Muchiile active in intervalul [t_start, t_end]."""
        result = []
        for src, tgt, data in self._graph.edges(data=True):
            if _edge_active_in_interval(data, t_start, t_end):
                result.append({"source": src, "target": tgt, **data})
        return result

    def get_edges_by_relation(self, relation: RelationType) -> list[dict]:
        return [{"source": s, "target": t, **d} for s, t, d in self._graph.edges(data=True) if d.get("relation") == relation.value]

    def has_edge(self, subject: str, obj: str, relation: Optional[RelationType] = None) -> bool:
        if not self._graph.has_edge(subject, obj):
            return False
        if relation is None:
            return True
        edge_data = self._graph.get_edge_data(subject, obj)
        return any(attrs.get("relation") == relation.value for attrs in edge_data.values())

    # ── Snapshot temporal ──
    def snapshot(self, t: datetime) -> nx.MultiDiGraph:
        """Subgraful activ la momentul t: F_t = { f in F | t in interval(f) }."""
        sub = nx.MultiDiGraph()
        for src, tgt, data in self._graph.edges(data=True):
            if _edge_active_at(data, t):
                if not sub.has_node(src):
                    sub.add_node(src, **self._graph.nodes[src])
                if not sub.has_node(tgt):
                    sub.add_node(tgt, **self._graph.nodes[tgt])
                sub.add_edge(src, tgt, **data)
        return sub

    # ── Statistici ──
    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    @property
    def fact_count(self) -> int:
        return len(self._facts)

    def summary(self) -> dict:
        relation_counts: dict[str, int] = {}
        for _, _, data in self._graph.edges(data=True):
            rel = data.get("relation", "unknown")
            relation_counts[rel] = relation_counts.get(rel, 0) + 1
        return {"nodes": self.node_count, "edges": self.edge_count, "facts": self.fact_count, "relations": relation_counts}

    def __repr__(self) -> str:
        return f"TemporalKnowledgeGraph(nodes={self.node_count}, edges={self.edge_count}, facts={self.fact_count})"


# ── Helpers ──
def _entity_id(entity: Entity) -> str:
    """ID nod: wikidata_id daca exista, altfel text lowercase."""
    if entity.wikidata_id:
        return entity.wikidata_id
    return entity.text.lower().strip()


def _node_attrs(entity: Entity) -> dict:
    return {"text": entity.text, "entity_type": entity.entity_type.value, "normalized": entity.normalized or entity.text, "wikidata_id": entity.wikidata_id}


def _edge_attrs(fact: TemporalFact) -> dict:
    attrs: dict = {
        "relation": fact.predicate.value,
        "source_sentence_idx": fact.source_sentence_idx,
        "confidence": fact.extraction_confidence,
        "extractor": fact.extractor,
        "fact_idx": -1,
    }
    for prefix, field in [("time_start", fact.time_start), ("time_end", fact.time_end), ("time_point", fact.time_point)]:
        if field and field.normalized_date:
            attrs[prefix] = field.normalized_date
            attrs[f"{prefix}_str"] = field.date_string
        else:
            attrs[prefix] = None
            attrs[f"{prefix}_str"] = None
    return attrs


def _edge_active_at(data: dict, t: datetime) -> bool:
    """Muchia e activa la momentul t?"""
    t_start, t_end, t_point = data.get("time_start"), data.get("time_end"), data.get("time_point")
    if t_start and t_end:
        return t_start <= t <= t_end
    if t_start:
        return t >= t_start
    if t_point:
        return t_point.year == t.year
    return True  # fara ancora temporala = mereu activ


def _edge_active_in_interval(data: dict, t_start: datetime, t_end: datetime) -> bool:
    """Muchia se suprapune cu intervalul [t_start, t_end]?"""
    edge_start, edge_end, edge_point = data.get("time_start"), data.get("time_end"), data.get("time_point")
    if edge_point:
        return t_start <= edge_point <= t_end
    if edge_start and edge_end:
        return not (edge_end < t_start or edge_start > t_end)
    if edge_start:
        return edge_start <= t_end
    return True


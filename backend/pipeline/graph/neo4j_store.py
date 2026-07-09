"""Persistent TKG storage using Neo4j Community Edition."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from backend.config import NEO4J_DATABASE
from backend.pipeline.graph.base_store import AbstractTKGStore
from backend.pipeline.graph.models import (
    Entity, EntityType, RelationType, TemporalExpression, TemporalFact,
)
from backend.pipeline.graph.store import _entity_id

if TYPE_CHECKING:
    from neo4j import Driver

logger = logging.getLogger(__name__)

# Fields returned by every fact-fetching query — defined once to avoid repetition.
# wikidata_id is intentionally omitted: it is an optional property and querying
# non-existent properties emits spurious Neo4j warnings.
_FACT_RETURN = """
    s.entity_id  AS s_id,   s.text AS s_text,   s.entity_type AS s_type,
    o.entity_id  AS o_id,   o.text AS o_text,   o.entity_type AS o_type,
    r.relation        AS relation,
    r.time_start_iso  AS time_start_iso,  r.time_start_str  AS time_start_str,
    r.time_end_iso    AS time_end_iso,    r.time_end_str    AS time_end_str,
    r.time_point_iso  AS time_point_iso,  r.time_point_str  AS time_point_str,
    r.source_sentence_idx AS sentence_idx,
    r.confidence AS confidence,
    r.extractor  AS extractor
"""


class Neo4jTKGStore(AbstractTKGStore):
    """Persistent TKG storage using Neo4j."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase
        self._uri = uri
        self._user = user
        self._password = password
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        self._ensure_indexes()
        logger.info(f"Neo4jTKGStore connected to {uri}")

    def _ensure_connected(self) -> None:
        """Reconnects the driver if it has been closed."""
        try:
            self._driver.verify_connectivity()
        except Exception:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
            logger.info("Neo4jTKGStore: driver reconnected.")

    def _ensure_indexes(self) -> None:
        """Create indexes on first run so lookups on entity_id and article_id are fast."""
        with self._driver.session(database=NEO4J_DATABASE) as session:
            session.run("CREATE INDEX IF NOT EXISTS FOR (e:Entity) ON (e.entity_id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (a:Article) ON (a.article_id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (c:WikidataCache) ON (c.entity_key)")

    def close(self) -> None:
        self._driver.close()

    # Write operations

    def add_fact(
        self,
        fact: TemporalFact,
        article_id: str | None = None,
        title: str | None = None,
        source: str | None = None,
    ) -> None:
        """Store a fact as two Entity nodes + a TEMPORAL_RELATION edge."""
        self._ensure_connected()
        with self._driver.session(database=NEO4J_DATABASE) as session:
            session.execute_write(self._create_fact_tx, fact, article_id, title, source)

    @staticmethod
    def _create_fact_tx(
        tx, fact: TemporalFact, article_id: str | None,
        title: str | None = None, source: str | None = None,
    ) -> None:
        def to_iso(expr: TemporalExpression | None) -> str | None:
            if expr and expr.normalized_date:
                return expr.normalized_date.isoformat()
            return None

        def to_str(expr: TemporalExpression | None) -> str | None:
            return expr.date_string if expr else None

        params = {
            "subj_id":      _entity_id(fact.subject),
            "subj_text":    fact.subject.text,
            "subj_type":    fact.subject.entity_type.value,
            "subj_wikidata": fact.subject.wikidata_id,
            "obj_id":       _entity_id(fact.object),
            "obj_text":     fact.object.text,
            "obj_type":     fact.object.entity_type.value,
            "obj_wikidata": fact.object.wikidata_id,
            "relation":         fact.predicate.value,
            "time_start_iso":   to_iso(fact.time_start),
            "time_start_str":   to_str(fact.time_start),
            "time_end_iso":     to_iso(fact.time_end),
            "time_end_str":     to_str(fact.time_end),
            "time_point_iso":   to_iso(fact.time_point),
            "time_point_str":   to_str(fact.time_point),
            "sentence_idx":     fact.source_sentence_idx,
            "confidence":       fact.extraction_confidence,
            "extractor":        fact.extractor,
            "article_id":       article_id,
        }

        # MERGE entity nodes so the same entity is never duplicated across articles
        tx.run("""
            MERGE (s:Entity {entity_id: $subj_id})
            ON CREATE SET s.text = $subj_text, s.entity_type = $subj_type,
                          s.wikidata_id = $subj_wikidata
            MERGE (o:Entity {entity_id: $obj_id})
            ON CREATE SET o.text = $obj_text, o.entity_type = $obj_type,
                          o.wikidata_id = $obj_wikidata
            CREATE (s)-[:TEMPORAL_RELATION {
                relation:          $relation,
                time_start_iso:    $time_start_iso,
                time_start_str:    $time_start_str,
                time_end_iso:      $time_end_iso,
                time_end_str:      $time_end_str,
                time_point_iso:    $time_point_iso,
                time_point_str:    $time_point_str,
                source_sentence_idx: $sentence_idx,
                confidence:        $confidence,
                extractor:         $extractor,
                article_id:        $article_id
            }]->(o)
        """, **params)

        if article_id:
            tx.run("""
                MERGE (a:Article {article_id: $article_id})
                ON CREATE SET a.title = $title,
                              a.source = $source,
                              a.analyzed_at = $analyzed_at
            """,
            article_id=article_id,
            title=title or "",
            source=source or "",
            analyzed_at=datetime.utcnow().isoformat(),
            )

    def add_facts(
        self,
        facts: list[TemporalFact],
        article_id: str | None = None,
        title: str | None = None,
        source: str | None = None,
    ) -> None:
        for fact in facts:
            self.add_fact(fact, article_id, title=title, source=source)
        logger.info(
            f"Neo4jTKGStore: {len(facts)} facts written"
            + (f" for article {article_id}" if article_id else "")
        )

    # Read operations

    def get_all_facts(self, article_id: str | None = None) -> list[TemporalFact]:
        """Retrieve facts, optionally filtered by article_id."""
        self._ensure_connected()
        if article_id:
            query = f"""
                MATCH (s:Entity)-[r:TEMPORAL_RELATION {{article_id: $article_id}}]->(o:Entity)
                RETURN {_FACT_RETURN}
            """
            params: dict = {"article_id": article_id}
        else:
            query = f"""
                MATCH (s:Entity)-[r:TEMPORAL_RELATION]->(o:Entity)
                RETURN {_FACT_RETURN}
            """
            params = {}

        with self._driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query, **params)
            return [_record_to_fact(r) for r in result]

    def get_facts_for_entity(self, entity_name: str) -> list[TemporalFact]:
        """All facts across ALL articles where the entity text fuzzy-matches the name.

        Uses bidirectional substring matching so "Jackson" matches stored
        "Ketanji Brown Jackson" and vice versa. The caller is responsible for
        further filtering (e.g. relation type, object similarity).
        """
        self._ensure_connected()
        name_lower = entity_name.lower().strip()
        query = f"""
            MATCH (s:Entity)-[r:TEMPORAL_RELATION]->(o:Entity)
            WHERE toLower(s.text) CONTAINS $name
               OR $name CONTAINS toLower(s.text)
               OR toLower(o.text) CONTAINS $name
               OR $name CONTAINS toLower(o.text)
            RETURN {_FACT_RETURN}
        """
        with self._driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query, name=name_lower)
            facts = [_record_to_fact(r) for r in result]
        logger.debug(
            f"get_facts_for_entity('{entity_name}'): {len(facts)} facts retrieved"
        )
        return facts

    def get_articles(self) -> list[dict]:
        """List all analyzed articles with their fact counts."""
        self._ensure_connected()
        with self._driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (a:Article)
                OPTIONAL MATCH ()-[r:TEMPORAL_RELATION {article_id: a.article_id}]->()
                RETURN a.article_id  AS article_id,
                       a.title       AS title,
                       a.source      AS source,
                       a.analyzed_at AS analyzed_at,
                       count(r)      AS fact_count
                ORDER BY a.analyzed_at DESC
            """)
            return [dict(record) for record in result]

    def delete_article(self, article_id: str) -> bool:
        """Delete an article node and all TEMPORAL_RELATION edges that belong to it."""
        self._ensure_connected()
        with self._driver.session(database=NEO4J_DATABASE) as session:
            check = session.run(
                "MATCH (a:Article {article_id: $id}) RETURN count(a) > 0 AS found",
                id=article_id,
            ).single()
            if not (check and check["found"]):
                return False
            session.run(
                "MATCH ()-[r:TEMPORAL_RELATION {article_id: $id}]->() DELETE r",
                id=article_id,
            )
            session.run(
                "MATCH (a:Article {article_id: $id}) DELETE a",
                id=article_id,
            )
            return True

    # Wikidata cache

    def cache_wikidata_result(self, entity_name: str, wikidata_facts: list[dict]) -> None:
        """Store a Wikidata query result in Neo4j for persistent caching."""
        self._ensure_connected()
        import json
        cache_key = entity_name.lower().strip()
        with self._driver.session(database=NEO4J_DATABASE) as session:
            session.run("""
                MERGE (c:WikidataCache {entity_key: $key})
                SET c.facts_json = $facts_json,
                    c.cached_at = datetime(),
                    c.entity_name = $entity_name
            """, key=cache_key, facts_json=json.dumps(wikidata_facts), entity_name=entity_name)

    def get_cached_wikidata(self, entity_name: str, max_age_hours: int = 168) -> list[dict] | None:
        """Retrieve a cached Wikidata result. Returns None if absent or expired (default 7 days)."""
        self._ensure_connected()
        import json
        cache_key = entity_name.lower().strip()
        with self._driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (c:WikidataCache {entity_key: $key})
                WHERE duration.between(c.cached_at, datetime()).hours < $max_hours
                RETURN c.facts_json AS facts_json
            """, key=cache_key, max_hours=max_age_hours).single()

            if result and result["facts_json"]:
                try:
                    return json.loads(result["facts_json"])
                except json.JSONDecodeError:
                    return None
        return None

    def save_human_verdict(
        self,
        article_id: str,
        verdict: str,
        confidence: float = 1.0,
        notes: str = "",
        annotator: str = "human",
    ) -> bool:
        """Saves the human verdict on the Article node in Neo4j."""
        self._ensure_connected()
        query = """
        MATCH (a:Article {article_id: $article_id})
        SET a.human_verdict = $verdict,
            a.human_confidence = $confidence,
            a.human_notes = $notes,
            a.human_annotator = $annotator,
            a.verified_at = $verified_at
        RETURN a.article_id AS id
        """
        with self._driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query, {
                "article_id": article_id,
                "verdict": verdict,
                "confidence": confidence,
                "notes": notes,
                "annotator": annotator,
                "verified_at": datetime.now().isoformat(),
            })
            return result.single() is not None

    def summary(self) -> dict:
        self._ensure_connected()
        with self._driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH (e:Entity) WITH count(e) AS nodes
                MATCH ()-[r:TEMPORAL_RELATION]->() WITH nodes, count(r) AS edges
                OPTIONAL MATCH (a:Article) WITH nodes, edges, count(a) AS articles
                RETURN nodes, edges, articles
            """).single()
            if result is None:
                return {"nodes": 0, "edges": 0, "articles": 0}
            return {
                "nodes":    result["nodes"],
                "edges":    result["edges"],
                "articles": result["articles"],
            }


# Helpers

def _record_to_fact(record) -> TemporalFact:
    """Reconstruct a TemporalFact from a Neo4j query record."""

    def parse_entity_type(val: str) -> EntityType:
        try:
            return EntityType(val)
        except ValueError:
            return EntityType.OTHER

    def parse_relation_type(val: str) -> RelationType:
        try:
            return RelationType(val)
        except ValueError:
            return RelationType.GENERIC

    def parse_temporal_expr(
        iso: str | None, date_str: str | None
    ) -> TemporalExpression | None:
        if iso is None:
            return None
        try:
            dt: datetime | None = datetime.fromisoformat(iso)
        except (ValueError, TypeError):
            dt = None
        return TemporalExpression(raw_text=date_str or "", normalized_date=dt, date_string=date_str)

    subject = Entity(
        text=record["s_text"],
        entity_type=parse_entity_type(record["s_type"]),
        start_char=0,
        end_char=0,
    )
    obj = Entity(
        text=record["o_text"],
        entity_type=parse_entity_type(record["o_type"]),
        start_char=0,
        end_char=0,
    )

    return TemporalFact(
        subject=subject,
        predicate=parse_relation_type(record["relation"]),
        object=obj,
        time_start=parse_temporal_expr(record.get("time_start_iso"), record.get("time_start_str")),
        time_end=parse_temporal_expr(record.get("time_end_iso"), record.get("time_end_str")),
        time_point=parse_temporal_expr(record.get("time_point_iso"), record.get("time_point_str")),
        source_sentence_idx=record.get("sentence_idx") or 0,
        extraction_confidence=record.get("confidence") or 1.0,
        extractor=record.get("extractor") or "unknown",
    )

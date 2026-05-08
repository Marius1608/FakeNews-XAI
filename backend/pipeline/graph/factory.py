"""Factory for creating TKG storage backends."""

from __future__ import annotations

import logging

from backend.pipeline.graph.base_store import AbstractTKGStore

logger = logging.getLogger(__name__)


def create_persistent_store() -> AbstractTKGStore | None:
    """Return a Neo4jTKGStore if NEO4J_ENABLED=true, otherwise None."""
    from backend.config import NEO4J_ENABLED, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER

    if not NEO4J_ENABLED:
        logger.debug("NEO4J_ENABLED=false — persistent store disabled")
        return None

    from backend.pipeline.graph.neo4j_store import Neo4jTKGStore

    try:
        store = Neo4jTKGStore(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        logger.info(f"Persistent Neo4j store created at {NEO4J_URI}")
        return store
    except Exception as exc:
        logger.error(f"Failed to connect to Neo4j at {NEO4J_URI}: {exc}")
        return None

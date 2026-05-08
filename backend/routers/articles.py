"""Router — GET /articles, DELETE /articles/{article_id}: article management via Neo4j."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.pipeline.graph.factory import create_persistent_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["articles"])


@router.get("/articles")
async def list_articles():
    """List all previously analyzed articles stored in Neo4j."""
    store = create_persistent_store()
    if store is None:
        return {"articles": [], "neo4j_enabled": False}
    try:
        articles = store.get_articles()
        return {"articles": articles, "neo4j_enabled": True}
    except Exception as e:
        logger.error(f"GET /articles error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve articles from Neo4j.")
    finally:
        store.close()


@router.delete("/articles/{article_id}")
async def delete_article(article_id: str):
    """Delete an article and all its facts from Neo4j."""
    store = create_persistent_store()
    if store is None:
        raise HTTPException(status_code=503, detail="Neo4j not enabled.")
    try:
        deleted = store.delete_article(article_id)
        if not deleted:
            raise HTTPException(
                status_code=404, detail=f"Article '{article_id}' not found."
            )
        return {"deleted": True, "article_id": article_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"DELETE /articles/{article_id} error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete article from Neo4j.")
    finally:
        store.close()

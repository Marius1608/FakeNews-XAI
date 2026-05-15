"""Router — GET /articles, DELETE /articles/{article_id}: article management via Neo4j."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.pipeline.graph.factory import create_persistent_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["articles"])


class CrossArticleConflict(BaseModel):
    entity: str
    description: str
    conflicting_article_title: str
    conflicting_article_date: str


class CrossArticleResponse(BaseModel):
    article_id: str
    conflicts: list[CrossArticleConflict]
    checked_against: int


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


@router.get("/articles/cross-check", response_model=CrossArticleResponse)
async def cross_check_article(article_id: str) -> CrossArticleResponse:
    """Run cross-article verification for a previously analyzed article."""
    store = create_persistent_store()
    if store is None:
        return CrossArticleResponse(article_id=article_id, conflicts=[], checked_against=0)

    try:
        facts = store.get_all_facts(article_id=article_id)
        if not facts:
            raise HTTPException(status_code=404, detail="Article not found in Neo4j.")

        from backend.pipeline.verification.cross_article import CrossArticleVerifier
        verifier = CrossArticleVerifier(store)
        raw_conflicts = verifier.verify(facts, article_id)

        conflicts = [
            CrossArticleConflict(
                entity=c.facts_involved[0].subject.text if c.facts_involved else "",
                description=c.description,
                conflicting_article_title=c.evidence or "",
                conflicting_article_date="",
            )
            for c in raw_conflicts
        ]

        total_articles = store.summary().get("articles", 1)
        return CrossArticleResponse(
            article_id=article_id,
            conflicts=conflicts,
            checked_against=max(0, total_articles - 1),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GET /articles/cross-check error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Cross-article verification failed.")
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

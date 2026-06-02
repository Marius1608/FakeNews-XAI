"""Router — POST /articles/{article_id}/verify: HITL manual validation."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import NEO4J_ENABLED
from backend.pipeline.graph.factory import create_persistent_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["articles"])


class VerifyRequest(BaseModel):
    verdict: str = Field(..., description="'true' or 'fake'")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    notes: str = Field(default="", description="Optional notes")
    annotator: str = Field(default="human", description="Annotator identifier")


class VerifyResponse(BaseModel):
    article_id: str
    verdict: str
    saved: bool
    message: str


@router.post("/articles/{article_id}/verify", response_model=VerifyResponse)
async def verify_article(article_id: str, req: VerifyRequest) -> VerifyResponse:
    """Saves the human verdict (true/fake) on a previously analyzed article."""
    if req.verdict not in ("true", "fake"):
        raise HTTPException(status_code=400, detail="verdict must be 'true' or 'fake'.")

    if not NEO4J_ENABLED:
        return VerifyResponse(
            article_id=article_id,
            verdict=req.verdict,
            saved=False,
            message="Neo4j is not available — verdict could not be saved.",
        )

    store = create_persistent_store()
    if store is None:
        return VerifyResponse(
            article_id=article_id,
            verdict=req.verdict,
            saved=False,
            message="Neo4j is not available — verdict could not be saved.",
        )

    try:
        saved = store.save_human_verdict(
            article_id=article_id,
            verdict=req.verdict,
            confidence=req.confidence,
            notes=req.notes,
            annotator=req.annotator,
        )
        if not saved:
            raise HTTPException(status_code=404, detail=f"Article '{article_id}' not found in Neo4j.")
        logger.info(f"HITL verdict '{req.verdict}' saved for article_id={article_id}")
        return VerifyResponse(
            article_id=article_id,
            verdict=req.verdict,
            saved=True,
            message=f"Article marked as {req.verdict.upper()}.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"POST /articles/{article_id}/verify error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error saving verdict to Neo4j.")
    finally:
        store.close()

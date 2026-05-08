"""Router — POST /analyze-batch: analyze multiple articles with optional Neo4j persistence."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.pipeline.graph.models import Article
from backend.routers.analyze import InconsistencyResponse, _to_inconsistency_response
from backend.routers.dependencies import explainer, get_orchestrator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batch"])


class BatchArticle(BaseModel):
    text: str = Field(..., min_length=20)
    title: str = Field(default="")
    publication_date: Optional[str] = None
    source: str = Field(default="")


class BatchRequest(BaseModel):
    articles: list[BatchArticle] = Field(..., min_length=1, max_length=50)
    pipeline: str = Field(default="spacy")
    model: Optional[str] = None
    persist: bool = Field(
        default=True,
        description="Save to Neo4j for cross-article analysis",
    )


class BatchArticleResult(BaseModel):
    article_id: str
    title: str
    score: float
    label: str
    summary: str
    n_claims: int
    n_inconsistencies: int
    n_cross_article_inconsistencies: int
    cross_article_conflicts: list[InconsistencyResponse]
    processing_time_ms: float
    error: Optional[str] = None


class BatchResponse(BaseModel):
    results: list[BatchArticleResult]
    total_articles: int
    total_cross_article_conflicts: int
    avg_score: float
    neo4j_enabled: bool
    persisted: bool


@router.post("/analyze-batch", response_model=BatchResponse)
async def analyze_batch(req: BatchRequest) -> BatchResponse:
    """Analyze multiple articles. Persist to Neo4j and run cross-article verification when enabled."""
    from backend.config import AVAILABLE_MODELS, NEO4J_ENABLED

    if req.pipeline not in ("spacy", "llm"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown pipeline '{req.pipeline}'. Options: 'spacy', 'llm'.",
        )
    if req.model:
        available = AVAILABLE_MODELS.get(req.pipeline, {}).get("models", [])
        if req.model not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{req.model}' not available for pipeline '{req.pipeline}'. Options: {available}",
            )

    persist = req.persist and NEO4J_ENABLED

    # open one shared store connection for the whole batch
    store = None
    if persist:
        from backend.pipeline.graph.factory import create_persistent_store
        store = create_persistent_store()
        if store is None:
            persist = False

    results: list[BatchArticleResult] = []
    total_cross_conflicts = 0

    try:
        for batch_article in req.articles:
            article_id = str(uuid.uuid4())

            pub_date: Optional[datetime] = None
            if batch_article.publication_date:
                try:
                    pub_date = datetime.strptime(batch_article.publication_date, "%Y-%m-%d")
                except ValueError:
                    pass

            article = Article(
                text=batch_article.text,
                title=batch_article.title,
                publication_date=pub_date,
                source=batch_article.source,
            )

            try:
                orchestrator = get_orchestrator(req.pipeline, req.model)
                result = orchestrator.run(article)
            except Exception as e:
                logger.error(
                    f"/analyze-batch: pipeline error on '{batch_article.title}': {e}",
                    exc_info=True,
                )
                results.append(
                    BatchArticleResult(
                        article_id=article_id,
                        title=batch_article.title,
                        score=0.0,
                        label="Error",
                        summary="Pipeline error — see server logs.",
                        n_claims=0,
                        n_inconsistencies=0,
                        n_cross_article_inconsistencies=0,
                        cross_article_conflicts=[],
                        processing_time_ms=0.0,
                        error=str(e)[:300],
                    )
                )
                continue

            explanation = explainer.explain_structured(result)

            cross_conflicts: list[InconsistencyResponse] = []
            if store is not None:
                from backend.pipeline.verification.cross_article import CrossArticleVerifier

                try:
                    # verify BEFORE persisting so current article is not in the store yet
                    verifier = CrossArticleVerifier(store)
                    raw_conflicts = verifier.verify(result.facts, article_id)
                    store.add_facts(result.facts, article_id=article_id)
                    cross_conflicts = [_to_inconsistency_response(c) for c in raw_conflicts]
                    total_cross_conflicts += len(cross_conflicts)
                except Exception as e:
                    logger.error(
                        f"/analyze-batch: persistence error for {article_id}: {e}",
                        exc_info=True,
                    )

            results.append(
                BatchArticleResult(
                    article_id=article_id,
                    title=batch_article.title,
                    score=result.score,
                    label=result.label,
                    summary=explanation["summary"],
                    n_claims=result.n_temporal_claims,
                    n_inconsistencies=result.n_inconsistencies,
                    n_cross_article_inconsistencies=len(cross_conflicts),
                    cross_article_conflicts=cross_conflicts,
                    processing_time_ms=result.processing_time_ms,
                )
            )
    finally:
        if store is not None:
            store.close()

    successful = [r for r in results if r.error is None]
    avg_score = (
        round(sum(r.score for r in successful) / len(successful), 4)
        if successful else 0.0
    )

    return BatchResponse(
        results=results,
        total_articles=len(results),
        total_cross_article_conflicts=total_cross_conflicts,
        avg_score=avg_score,
        neo4j_enabled=NEO4J_ENABLED,
        persisted=persist,
    )

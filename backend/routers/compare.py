"""Router — POST /compare: any-2-model comparison side-by-side."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.pipeline.graph.models import Article
from backend.dependencies import get_orchestrator, explainer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["compare"])


class CompareRequest(BaseModel):
    """Input: article to compare across any two models."""
    text: str = Field(..., min_length=20, description="Article text")
    title: str = Field(default="", description="Article title")
    publication_date: Optional[str] = Field(default=None, description="Publication date (YYYY-MM-DD)")
    source: str = Field(default="", description="Article source")
    pipeline_a: str = Field(default="spacy", description="Pipeline A: 'spacy' or 'llm'")
    model_a: Optional[str] = Field(default=None, description="Specific model A (None = default)")
    pipeline_b: str = Field(default="llm", description="Pipeline B: 'spacy' or 'llm'")
    model_b: Optional[str] = Field(default=None, description="Specific model B (None = default)")


class PipelineResult(BaseModel):
    """Result from a single pipeline run."""
    pipeline: str
    model: str
    score: float
    label: str
    summary: str
    n_claims: int
    n_inconsistencies: int
    coherence_factor: float
    inconsistency_details: list[dict]
    fact_annotations: list[dict]
    timeline: list[dict]
    processing_time_ms: float


class CompareResponse(BaseModel):
    """Output: two pipeline results side-by-side + delta."""
    pipeline_a: PipelineResult
    pipeline_b: PipelineResult
    score_delta: float = Field(description="pipeline_a.score - pipeline_b.score")
    agreement: str = Field(description="Agreement level between the two pipelines")
    model_a: str = Field(description="Model A used")
    model_b: str = Field(description="Model B used")


_explainer = explainer


# Endpoint
@router.post("/compare", response_model=CompareResponse)
async def compare_pipelines(req: CompareRequest) -> CompareResponse:
    """Run two pipeline/model combinations on the same article and compare them."""
    from backend.config import AVAILABLE_MODELS

    # Validate pipeline_a
    if req.pipeline_a not in ("spacy", "llm"):
        raise HTTPException(status_code=400, detail=f"Unknown pipeline_a: '{req.pipeline_a}'. Options: 'spacy', 'llm'.")

    # Validate pipeline_b
    if req.pipeline_b not in ("spacy", "llm"):
        raise HTTPException(status_code=400, detail=f"Unknown pipeline_b: '{req.pipeline_b}'. Options: 'spacy', 'llm'.")

    # Validate model_a
    if req.model_a:
        available_a = AVAILABLE_MODELS.get(req.pipeline_a, {}).get("models", [])
        if req.model_a not in available_a:
            raise HTTPException(status_code=400, detail=f"Model A '{req.model_a}' not available for pipeline '{req.pipeline_a}'. Options: {available_a}")

    # Validate model_b
    if req.model_b:
        available_b = AVAILABLE_MODELS.get(req.pipeline_b, {}).get("models", [])
        if req.model_b not in available_b:
            raise HTTPException(status_code=400, detail=f"Model B '{req.model_b}' not available for pipeline '{req.pipeline_b}'. Options: {available_b}")

    pub_date = None
    if req.publication_date:
        try:
            pub_date = datetime.strptime(req.publication_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    article = Article(
        text=req.text, title=req.title,
        publication_date=pub_date, source=req.source,
    )

    resolved_model_a = req.model_a or AVAILABLE_MODELS[req.pipeline_a]["default"]
    resolved_model_b = req.model_b or AVAILABLE_MODELS[req.pipeline_b]["default"]

    logger.info(
        f"/compare: '{article.title[:50]}' ({len(article.text)} chars) | "
        f"A={req.pipeline_a}:{resolved_model_a} vs B={req.pipeline_b}:{resolved_model_b}"
    )

    # Run pipeline A
    try:
        orch_a = get_orchestrator(req.pipeline_a, req.model_a)
        result_a = orch_a.run(article)
    except Exception as e:
        logger.error(f"/compare: pipeline A error ({req.pipeline_a}:{resolved_model_a}) — {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline A error '{req.pipeline_a}:{resolved_model_a}': {e}")

    # Run pipeline B
    try:
        orch_b = get_orchestrator(req.pipeline_b, req.model_b)
        result_b = orch_b.run(article)
    except Exception as e:
        logger.error(f"/compare: pipeline B error ({req.pipeline_b}:{resolved_model_b}) — {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline B error '{req.pipeline_b}:{resolved_model_b}': {e}")

    expl_a = _explainer.explain_structured(result_a)
    expl_b = _explainer.explain_structured(result_b)

    def _to_pipeline_result(result, explanation, pipeline_name, model_name) -> PipelineResult:
        return PipelineResult(
            pipeline=f"{pipeline_name}:{model_name}",
            model=model_name,
            score=result.score,
            label=result.label,
            summary=explanation["summary"],
            n_claims=result.n_temporal_claims,
            n_inconsistencies=result.n_inconsistencies,
            coherence_factor=result.coherence_factor,
            inconsistency_details=explanation["inconsistency_details"],
            fact_annotations=explanation["fact_annotations"],
            timeline=result.timeline,
            processing_time_ms=result.processing_time_ms,
        )

    res_a = _to_pipeline_result(result_a, expl_a, req.pipeline_a, resolved_model_a)
    res_b = _to_pipeline_result(result_b, expl_b, req.pipeline_b, resolved_model_b)

    delta = res_a.score - res_b.score
    agreement = _compute_agreement(result_a.score, result_b.score)

    return CompareResponse(
        pipeline_a=res_a,
        pipeline_b=res_b,
        score_delta=round(delta, 4),
        agreement=agreement,
        model_a=resolved_model_a,
        model_b=resolved_model_b,
    )


def _compute_agreement(score_a: float, score_b: float) -> str:
    """Assess agreement between the two pipeline results."""
    delta = abs(score_a - score_b)
    if delta < 0.1:
        return "Strong agreement — both pipelines reach similar conclusions."
    elif delta < 0.3:
        return "Moderate agreement — minor differences in temporal extraction."
    else:
        return "Weak agreement — significant divergence between pipelines. Manual review recommended."

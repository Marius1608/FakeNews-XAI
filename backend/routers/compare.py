"""Router — POST /compare: Pipeline A vs Pipeline B side-by-side."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.pipeline.graph.models import Article
from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.routers.dependencies import get_orchestrator, explainer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["compare"])

# Pydantic schemas
class CompareRequest(BaseModel):
    """Input: articol de comparat pe ambele pipeline-uri."""
    text: str = Field(..., min_length=20, description="Textul articolului")
    title: str = Field(default="", description="Titlul articolului")
    publication_date: Optional[str] = Field(default=None, description="Data publicarii (YYYY-MM-DD)")
    source: str = Field(default="", description="Sursa articolului")


class PipelineResult(BaseModel):
    """Rezultatul unui singur pipeline."""
    pipeline: str
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
    """Output: doua rezultate side-by-side + delta."""
    pipeline_a: PipelineResult
    pipeline_b: PipelineResult
    score_delta: float = Field(description="pipeline_a.score - pipeline_b.score")
    agreement: str = Field(description="Concordanta intre pipeline-uri")


_explainer = explainer


# Endpoint
@router.post("/compare", response_model=CompareResponse)
async def compare_pipelines(req: CompareRequest) -> CompareResponse:
    """Ruleaza Pipeline A (spaCy) si Pipeline B (LLM) pe acelasi articol."""
    pub_date = None
    if req.publication_date:
        try:
            pub_date = datetime.strptime(req.publication_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Format data invalid. Foloseste YYYY-MM-DD.")

    article = Article(
        text=req.text, title=req.title,
        publication_date=pub_date, source=req.source,
    )

    logger.info(f"/compare: '{article.title[:50]}' ({len(article.text)} chars)")

    # Ruleaza ambele pipeline-uri
    results = {}
    for pipeline_name in ("spacy", "llm"):
        try:
            orchestrator = get_orchestrator(pipeline_name)
            results[pipeline_name] = orchestrator.run(article)
        except Exception as e:
            logger.error(f"/compare: eroare {pipeline_name} — {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Eroare la pipeline '{pipeline_name}': {e}",
            )

    # Genereaza explicatii
    expl_a = _explainer.explain_structured(results["spacy"])
    expl_b = _explainer.explain_structured(results["llm"])

    def _to_pipeline_result(result, explanation, name) -> PipelineResult:
        return PipelineResult(
            pipeline=name,
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

    res_a = _to_pipeline_result(results["spacy"], expl_a, "spacy")
    res_b = _to_pipeline_result(results["llm"], expl_b, "llm")

    delta = res_a.score - res_b.score
    agreement = _compute_agreement(results["spacy"].score, results["llm"].score)

    return CompareResponse(
        pipeline_a=res_a,
        pipeline_b=res_b,
        score_delta=round(delta, 4),
        agreement=agreement,
    )


def _compute_agreement(score_a: float, score_b: float) -> str:
    """Evalueaza concordanta celor doua pipeline-uri."""
    delta = abs(score_a - score_b)
    if delta < 0.1:
        return "Strong agreement — both pipelines reach similar conclusions."
    elif delta < 0.3:
        return "Moderate agreement — minor differences in temporal extraction."
    else:
        return "Weak agreement — significant divergence between pipelines. Manual review recommended."
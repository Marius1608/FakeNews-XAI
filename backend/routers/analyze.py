"""Router — POST /analyze: primeste articol, returneaza TCS + explicatii."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.pipeline.graph.models import Article
from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.pipeline.scoring.explainer import TCSExplainer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analyze"])


# Pydantic schemas (request / response)
class AnalyzeRequest(BaseModel):
    """Input: text articol + metadata optionala."""
    text: str = Field(..., min_length=20, description="Textul articolului")
    title: str = Field(default="", description="Titlul articolului")
    publication_date: Optional[str] = Field(default=None, description="Data publicarii (YYYY-MM-DD)")
    source: str = Field(default="", description="Sursa articolului")
    pipeline: str = Field(default="spacy", description="Pipeline: 'spacy' sau 'llm'")


class InconsistencyResponse(BaseModel):
    type: str
    severity: str
    severity_label: str
    description: str
    evidence: Optional[str]
    verified_by: str
    sentence_indices: list[int]


class FactAnnotationResponse(BaseModel):
    sentence_idx: int
    subject: str
    predicate: str
    object: str
    time: str
    status: str
    color: str
    confidence: float
    extractor: str
    inconsistencies: list[str]


class AnalyzeResponse(BaseModel):
    """Output: scor TCS + explicatii structurate."""
    score: float
    label: str
    summary: str
    n_claims: int
    n_inconsistencies: int
    coherence_factor: float
    inconsistency_details: list[InconsistencyResponse]
    fact_annotations: list[FactAnnotationResponse]
    timeline: list[dict]
    pipeline: str
    processing_time_ms: float


# Singleton-uri (lazy init)
_orchestrators: dict[str, PipelineOrchestrator] = {}
_explainer = TCSExplainer()


def _get_orchestrator(pipeline: str) -> PipelineOrchestrator:
    """Un orchestrator per pipeline variant, reutilizat intre request-uri."""
    if pipeline not in _orchestrators:
        _orchestrators[pipeline] = PipelineOrchestrator(
            use_wikidata=True, extractor_name=pipeline,
        )
    return _orchestrators[pipeline]


# Endpoint
@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_article(req: AnalyzeRequest) -> AnalyzeResponse:
    """Analizeaza un articol si returneaza scorul TCS cu explicatii."""
    # Valideaza pipeline
    if req.pipeline not in ("spacy", "llm"):
        raise HTTPException(status_code=400, detail=f"Pipeline necunoscut: '{req.pipeline}'. Optiuni: 'spacy', 'llm'.")

    # Parseaza data publicarii
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

    logger.info(f"/analyze: '{article.title[:50]}' ({len(article.text)} chars, pipeline={req.pipeline})")

    try:
        orchestrator = _get_orchestrator(req.pipeline)
        result = orchestrator.run(article)
    except Exception as e:
        logger.error(f"/analyze: eroare pipeline — {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Eroare interna la procesare.")

    # Genereaza explicatii structurate
    explanation = _explainer.explain_structured(result)

    return AnalyzeResponse(
        score=result.score,
        label=result.label,
        summary=explanation["summary"],
        n_claims=result.n_temporal_claims,
        n_inconsistencies=result.n_inconsistencies,
        coherence_factor=result.coherence_factor,
        inconsistency_details=explanation["inconsistency_details"],
        fact_annotations=explanation["fact_annotations"],
        timeline=result.timeline,
        pipeline=result.pipeline_variant,
        processing_time_ms=result.processing_time_ms,
    )
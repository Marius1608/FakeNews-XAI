"""Router — POST /analyze: primeste articol, returneaza TCS + explicatii."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.pipeline.graph.models import Article, Inconsistency
from backend.dependencies import get_orchestrator, explainer

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
    model: Optional[str] = Field(default=None, description="Model specific: en_core_web_trf, llama3, mistral, etc. None = default per pipeline")
    persist: bool = Field(default=False, description="Save facts to Neo4j for cross-article analysis")


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
    model: str = Field(default="", description="Model folosit")
    processing_time_ms: float
    article_id: Optional[str] = Field(default=None, description="Neo4j article ID (set when persist=True)")
    cross_article_inconsistencies: list[InconsistencyResponse] = Field(default_factory=list)


_explainer = explainer


def _to_inconsistency_response(inc: Inconsistency) -> InconsistencyResponse:
    """Serialize an Inconsistency dataclass to the API response model."""
    return InconsistencyResponse(
        type=inc.inconsistency_type.value,
        severity=inc.severity.value,
        severity_label=inc.severity.value.title(),
        description=inc.description,
        evidence=inc.evidence,
        verified_by=inc.verified_by,
        sentence_indices=inc.sentence_indices,
    )


# Endpoint
@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_article(req: AnalyzeRequest) -> AnalyzeResponse:
    """Analizeaza un articol si returneaza scorul TCS cu explicatii."""
    from backend.config import AVAILABLE_MODELS

    # Valideaza pipeline
    if req.pipeline not in ("spacy", "llm"):
        raise HTTPException(status_code=400, detail=f"Pipeline necunoscut: '{req.pipeline}'. Optiuni: 'spacy', 'llm'.")

    # Valideaza model (daca e furnizat)
    if req.model:
        available = AVAILABLE_MODELS.get(req.pipeline, {}).get("models", [])
        if req.model not in available:
            raise HTTPException(status_code=400, detail=f"Model '{req.model}' nu e disponibil pentru pipeline '{req.pipeline}'. Optiuni: {available}")

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

    logger.info(f"/analyze: '{article.title[:50]}' ({len(article.text)} chars, pipeline={req.pipeline}, model={req.model or 'default'})")

    try:
        orchestrator = get_orchestrator(req.pipeline, req.model)
        result = orchestrator.run(article)
    except Exception as e:
        logger.error(f"/analyze: eroare pipeline — {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Eroare interna la procesare.")

    # optional: persist to Neo4j and run cross-article verification
    article_id: Optional[str] = None
    cross_article_inconsistencies: list[InconsistencyResponse] = []

    if req.persist:
        from backend.config import NEO4J_ENABLED
        if NEO4J_ENABLED:
            from backend.pipeline.graph.factory import create_persistent_store
            from backend.pipeline.verification.cross_article import CrossArticleVerifier

            article_id = str(uuid.uuid4())
            store = create_persistent_store()
            if store is not None:
                try:
                    verifier = CrossArticleVerifier(store)
                    cross_incs = verifier.verify(result.facts, article_id)
                    store.add_facts(result.facts, article_id=article_id)
                    cross_article_inconsistencies = [
                        _to_inconsistency_response(c) for c in cross_incs
                    ]
                    logger.info(
                        f"/analyze: persisted {len(result.facts)} facts as {article_id}, "
                        f"{len(cross_incs)} cross-article conflicts"
                    )
                except Exception as e:
                    logger.error(f"/analyze: persistence error — {e}", exc_info=True)
                finally:
                    store.close()
        else:
            logger.warning("/analyze: persist=True but NEO4J_ENABLED=false — skipping")

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
        model=req.model or AVAILABLE_MODELS[req.pipeline]["default"],
        processing_time_ms=result.processing_time_ms,
        article_id=article_id,
        cross_article_inconsistencies=cross_article_inconsistencies,
    )
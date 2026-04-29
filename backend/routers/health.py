"""Router — GET /health: status server si disponibilitate componente."""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import AVAILABLE_MODELS, OLLAMA_HOST, OLLAMA_MODEL, SPACY_MODEL

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Returneaza statusul serverului si configuratia componentelor."""
    return {
        "status": "ok",
        "components": {
            "pipeline_a": {"model": SPACY_MODEL, "type": "spacy"},
            "pipeline_b": {"host": OLLAMA_HOST, "model": OLLAMA_MODEL, "type": "ollama"},
        },
    }


@router.get("/models")
async def list_models() -> dict:
    """Returneaza modelele disponibile per pipeline."""
    return AVAILABLE_MODELS
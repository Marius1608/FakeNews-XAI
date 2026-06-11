"""Router — GET /health: server status and component availability."""

from __future__ import annotations

from fastapi import APIRouter

from backend.config import AVAILABLE_MODELS, QWEN_MODEL_ID, SPACY_MODEL

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Return server status and component configuration."""
    return {
        "status": "ok",
        "components": {
            "pipeline_a": {"model": SPACY_MODEL, "type": "spacy"},
            "pipeline_b": {"model": QWEN_MODEL_ID, "type": "qwen"},
        },
    }


@router.get("/models")
async def list_models() -> dict:
    """Return available models per pipeline."""
    return AVAILABLE_MODELS

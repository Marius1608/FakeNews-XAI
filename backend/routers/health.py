"""Router — GET /health: server status and component availability."""

from __future__ import annotations

from fastapi import APIRouter

from urllib.parse import urlparse

from backend.config import (
    AVAILABLE_MODELS, NEO4J_DATABASE, NEO4J_ENABLED, NEO4J_URI, QWEN_MODEL_ID, SPACY_MODEL,
)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Return server status and component configuration."""
    return {
        "status": "ok",
        "components": {
            "pipeline_a": {"model": SPACY_MODEL, "type": "spacy"},
            "pipeline_b": {"model": QWEN_MODEL_ID, "type": "qwen"},
            # host only — never expose credentials
            "neo4j": {
                "enabled": NEO4J_ENABLED,
                "host": urlparse(NEO4J_URI).hostname if NEO4J_ENABLED else None,
                "database": NEO4J_DATABASE if NEO4J_ENABLED else None,
            },
        },
    }


@router.get("/models")
async def list_models() -> dict:
    """Return available models per pipeline."""
    return AVAILABLE_MODELS

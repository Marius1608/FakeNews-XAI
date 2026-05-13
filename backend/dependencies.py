"""Dependinte partajate — singleton-uri reutilizate de routers (analyze, compare)."""

from __future__ import annotations

from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.pipeline.scoring.explainer import TCSExplainer


# One orchestrator per pipeline variant, shared across routers
_orchestrators: dict[str, PipelineOrchestrator] = {}

# Single explainer instance, shared across routers
explainer = TCSExplainer()


def get_orchestrator(pipeline: str, model: str | None = None) -> PipelineOrchestrator:
    """Return the orchestrator for the requested pipeline+model. Creates it on first call."""
    key = f"{pipeline}:{model}" if model else pipeline
    if key not in _orchestrators:
        _orchestrators[key] = PipelineOrchestrator(
            use_wikidata=True, extractor_name=pipeline, model_name=model,
        )
    return _orchestrators[key]

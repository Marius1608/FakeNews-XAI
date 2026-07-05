"""Shared dependencies — singletons reused by the analyze and compare routers."""

from __future__ import annotations

from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.pipeline.scoring.explainer import TCSExplainer


# One orchestrator per pipeline variant, shared across routers.
# The cached instance holds only expensive-to-build objects (spaCy/Qwen models,
# extractors, Reference KG); request-scoped state (store, persist, RSS, web
# search) is passed as arguments to run() and never stored on the instance.
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

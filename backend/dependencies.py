"""Dependinte partajate — singleton-uri reutilizate de routers (analyze, compare)."""

from __future__ import annotations

from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.pipeline.scoring.explainer import TCSExplainer


# Un singur orchestrator per pipeline variant, partajat intre routers
_orchestrators: dict[str, PipelineOrchestrator] = {}

# Un singur explainer, partajat intre routers
explainer = TCSExplainer()


def get_orchestrator(pipeline: str, model: str | None = None) -> PipelineOrchestrator:
    """Returneaza orchestratorul pentru pipeline+model cerut. Creeaza la prima invocare."""
    key = f"{pipeline}:{model}" if model else pipeline
    if key not in _orchestrators:
        _orchestrators[key] = PipelineOrchestrator(
            use_wikidata=True, extractor_name=pipeline, model_name=model,
        )
    return _orchestrators[key]
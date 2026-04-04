"""Dependinte partajate — singleton-uri reutilizate de routers (analyze, compare)."""

from __future__ import annotations

from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.pipeline.scoring.explainer import TCSExplainer


# Un singur orchestrator per pipeline variant, partajat intre routers
_orchestrators: dict[str, PipelineOrchestrator] = {}

# Un singur explainer, partajat intre routers
explainer = TCSExplainer()


def get_orchestrator(pipeline: str) -> PipelineOrchestrator:
    """Returneaza orchestratorul pentru pipeline-ul cerut. Creeaza la prima invocare."""
    if pipeline not in _orchestrators:
        _orchestrators[pipeline] = PipelineOrchestrator(
            use_wikidata=True, extractor_name=pipeline,
        )
    return _orchestrators[pipeline]
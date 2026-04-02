"""Pipeline Orchestrator — leaga C1→C2→C3→C4 end-to-end: Article → TCSResult."""

from __future__ import annotations

import logging
import time
from typing import Optional

from backend.pipeline.extraction.base import AbstractExtractor
from backend.pipeline.graph.builder import TKGBuilder
from backend.pipeline.graph.models import Article, TCSResult
from backend.pipeline.graph.store import TemporalKnowledgeGraph
from backend.pipeline.scoring.tcs import TCSCalculator
from backend.pipeline.verification.external import ExternalVerifier
from backend.pipeline.verification.internal import InternalVerifier

logger = logging.getLogger(__name__)

_EXTRACTOR_FACTORIES: dict[str, type] = {}

def _get_extractor_class(name: str) -> type:
    """Import lazy: incarca clasa extractorului doar cand e cerut."""
    if not _EXTRACTOR_FACTORIES:
        from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
        from backend.pipeline.extraction.llm_extractor import LLMExtractor
        _EXTRACTOR_FACTORIES["spacy"] = SpacyExtractor
        _EXTRACTOR_FACTORIES["llm"] = LLMExtractor
    if name not in _EXTRACTOR_FACTORIES:
        raise ValueError(f"Extractor necunoscut: '{name}'. Optiuni: {list(_EXTRACTOR_FACTORIES)}")
    return _EXTRACTOR_FACTORIES[name]


class PipelineOrchestrator:
    """
    Orchestreaza pipeline-ul TCS complet:
      C1 (SpacyExtractor | LLMExtractor) → C2 (TKGBuilder) → C3 (Verificare) → C4 (TCSCalculator)
    """

    def __init__(self, use_wikidata: bool = True, extractor_name: str = "spacy"):
        self.use_wikidata = use_wikidata
        self.extractor_name = extractor_name

        self._extractor: Optional[AbstractExtractor] = None
        self._builder = TKGBuilder()
        self._internal_verifier = InternalVerifier()
        self._external_verifier: Optional[ExternalVerifier] = None
        self._calculator = TCSCalculator()

    @property
    def extractor(self) -> AbstractExtractor:
        """Lazy-load: instantiaza extractorul ales (spacy sau llm) o singura data."""
        if self._extractor is None:
            cls = _get_extractor_class(self.extractor_name)
            logger.info(f"Orchestrator: initializare {cls.__name__}...")
            self._extractor = cls()
        return self._extractor

    @property
    def external_verifier(self) -> ExternalVerifier:
        if self._external_verifier is None:
            self._external_verifier = ExternalVerifier(use_wikidata=self.use_wikidata)
        return self._external_verifier

    def run(self, article: Article) -> TCSResult:
        """Ruleaza pipeline-ul complet pe un articol."""
        start_ms = time.monotonic() * 1000
        logger.info(f"Pipeline START [{self.extractor_name}]: '{article.title[:60]}' ({len(article.text)} chars)")

        # C1: Extractie
        facts = self.extractor.extract(article)
        logger.info(f"C1 ✓ — {len(facts)} fapte extrase ({self.extractor_name})")

        # C2: Constructie TKG
        tkg: TemporalKnowledgeGraph = self._builder.build(facts)
        logger.info(f"C2 ✓ — TKG: {tkg.node_count} noduri, {tkg.edge_count} muchii, {tkg.fact_count} fapte")

        if tkg.fact_count == 0:
            logger.warning("TKG gol — articolul nu contine fapte temporale verificabile.")
            return _empty_result(article, self.extractor_name, start_ms)

        # C3a: Verificare interna
        internal = self._internal_verifier.verify(tkg)
        logger.info(f"C3a ✓ — {len(internal.inconsistencies)} inconsistente, coherence={internal.score_coherence:.3f}")

        # C3b: Verificare externa
        external = self.external_verifier.verify(tkg)
        logger.info(f"C3b ✓ — {len(external.inconsistencies)} inconsistente ({external.wikidata_queries} query-uri)")

        # C4: Calcul TCS
        result = self._calculator.compute(
            tkg=tkg, internal=internal, external=external,
            pipeline_variant=self.extractor_name, start_time_ms=start_ms,
        )
        logger.info(f"Pipeline DONE — TCS={result.score:.3f} ({result.label}) in {result.processing_time_ms:.0f}ms")
        return result

    def run_batch(self, articles: list[Article]) -> list[TCSResult]:
        """Ruleaza pipeline-ul pe o lista de articole (pentru evaluare dataset)."""
        results = []
        for i, article in enumerate(articles):
            logger.info(f"Batch [{self.extractor_name}] {i + 1}/{len(articles)}: {article.title[:50]}")
            try:
                result = self.run(article)
            except Exception as e:
                logger.error(f"Eroare procesare '{article.title}': {e}", exc_info=True)
                result = _empty_result(article, self.extractor_name)
            results.append(result)

        avg = sum(r.score for r in results) / len(results) if results else 0
        logger.info(f"Batch complet [{self.extractor_name}]: {len(results)} articole, TCS mediu: {avg:.3f}")
        return results


def _empty_result(article: Article, pipeline_variant: str, start_ms: Optional[float] = None) -> TCSResult:
    """TCSResult gol: n_temporal_claims=0 semnaleaza lipsa fapte, nu consistenta."""
    processing_time = 0.0
    if start_ms is not None:
        processing_time = (time.monotonic() * 1000) - start_ms

    return TCSResult(
        score=0.0, n_inconsistencies=0, n_temporal_claims=0, coherence_factor=1.0,
        inconsistencies=[], facts=[],
        explanation_text="Nu s-au putut extrage fapte temporale verificabile din acest articol.",
        timeline=[], pipeline_variant=pipeline_variant, processing_time_ms=processing_time,
    )
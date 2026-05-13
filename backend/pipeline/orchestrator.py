"""Pipeline Orchestrator — leaga C1→C2→C3→C4 end-to-end: Article → TCSResult."""

from __future__ import annotations

import logging
import time
from typing import Optional

from backend.pipeline.extraction.base import AbstractExtractor
from backend.pipeline.graph.base_store import AbstractTKGStore
from backend.pipeline.graph.builder import TKGBuilder
from backend.pipeline.graph.models import Article, TCSResult
from backend.pipeline.graph.store import TemporalKnowledgeGraph
from backend.pipeline.scoring.tcs import TCSCalculator
from backend.pipeline.verification.cross_article import CrossArticleVerifier
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

    def __init__(
        self,
        use_wikidata: bool = True,
        extractor_name: str = "spacy",
        model_name: str | None = None,
        persistent_store: Optional[AbstractTKGStore] = None,
        enable_cross_article: bool = True,
    ):
        self.use_wikidata = use_wikidata
        self.extractor_name = extractor_name
        self.model_name = model_name

        self._persistent_store = persistent_store
        self._enable_cross_article = enable_cross_article

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
            kwargs = {}
            if self.model_name:
                if self.extractor_name == "spacy":
                    kwargs["model_name"] = self.model_name
                elif self.extractor_name == "llm":
                    kwargs["model"] = self.model_name
            logger.info(f"Orchestrator: initializare {cls.__name__} ({self.model_name or 'default'})...")
            self._extractor = cls(**kwargs)
        return self._extractor

    @property
    def llm_explainer(self):
        """Lazy-load: instanta LLMExplainer creata doar la primul apel."""
        if not hasattr(self, "_llm_explainer"):
            from backend.pipeline.scoring.llm_explainer import LLMExplainer
            self._llm_explainer = LLMExplainer()
        return self._llm_explainer

    @property
    def external_verifier(self) -> ExternalVerifier:
        if self._external_verifier is None:
            self._external_verifier = ExternalVerifier(
                use_wikidata=self.use_wikidata,
                persistent_store=self._persistent_store,
            )
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
        internal = self._internal_verifier.verify(tkg, publication_date=article.publication_date)
        logger.info(f"C3a ✓ — {len(internal.inconsistencies)} inconsistente, coherence={internal.score_coherence:.3f}")

        # C3b: Verificare externa
        external = self.external_verifier.verify(tkg)
        logger.info(f"C3b ✓ — {len(external.inconsistencies)} inconsistente ({external.wikidata_queries} query-uri)")

        all_facts = tkg.get_all_facts()
        all_inconsistencies = internal.inconsistencies + external.inconsistencies

        # C3c: Verificare cross-article (optional, necesita Neo4j)
        cross_article_incs: list = []
        article_id = None
        if self._persistent_store and self._enable_cross_article:
            import uuid
            article_id = str(uuid.uuid4())
            cross_verifier = CrossArticleVerifier(self._persistent_store)
            cross_article_incs = cross_verifier.verify(all_facts, article_id)
            logger.info(f"C3c ✓ — {len(cross_article_incs)} conflicte cross-article")
            all_inconsistencies.extend(cross_article_incs)

        # C4: Calcul TCS
        facts_verified = external.facts_checked
        facts_total = len(all_facts)

        result = self._calculator.compute(
            n_claims=len(all_facts),
            inconsistencies=all_inconsistencies,
            score_coherence=internal.score_coherence,
            facts_verified=facts_verified,
            facts_total=facts_total,
            facts=all_facts,
            pipeline_variant=self.extractor_name,
            start_time_ms=start_ms,
        )

        result.article_id = article_id
        result.cross_article_inconsistencies = cross_article_incs

        # Persistare dupa calcul TCS
        if self._persistent_store and article_id:
            try:
                self._persistent_store.add_facts(all_facts, article_id=article_id)
                logger.info(f"Neo4j: {len(all_facts)} fapte persistate (article_id={article_id})")
            except Exception as e:
                logger.error(f"Neo4j persistare esuata: {e}")

        # XAI: Explicatie LLM (optional, daca Ollama e disponibil)
        if self.llm_explainer.is_available():
            explanation = self.llm_explainer.explain(result, article_text=article.text, article_title=article.title)
            if explanation:
                result.explanation_text = explanation
                logger.info("XAI ✓ — Explicatie LLM generata")
            else:
                logger.info("XAI — Fallback pe template static")
        else:
            logger.info("XAI — Ollama indisponibil, folosim template static")

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
        score=0.5, n_inconsistencies=0, n_temporal_claims=0, coherence_factor=1.0,
        inconsistencies=[], facts=[],
        explanation_text="Nu s-au putut extrage fapte temporale verificabile din acest articol.",
        timeline=[], pipeline_variant=pipeline_variant, processing_time_ms=processing_time,
    )
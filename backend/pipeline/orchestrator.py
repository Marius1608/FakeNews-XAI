"""Pipeline Orchestrator — links C1→C2→C3→C4 end-to-end: Article → TCSResult."""

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
    """Lazy import: loads the extractor class only when first requested."""
    if not _EXTRACTOR_FACTORIES:
        from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
        from backend.pipeline.extraction.spacy_llm_extractor import SpacyLLMExtractor
        _EXTRACTOR_FACTORIES["spacy"] = SpacyExtractor
        _EXTRACTOR_FACTORIES["llm"] = SpacyLLMExtractor
    if name not in _EXTRACTOR_FACTORIES:
        raise ValueError(f"Unknown extractor: '{name}'. Options: {list(_EXTRACTOR_FACTORIES)}")
    return _EXTRACTOR_FACTORIES[name]


class PipelineOrchestrator:
    """
    Orchestrates the full TCS pipeline:
      C1 (SpacyExtractor | SpacyLLMExtractor) -> C2 (TKGBuilder) -> C3 (Verification) -> C4 (TCSCalculator)
    """

    def __init__(
        self,
        use_wikidata: bool = True,
        extractor_name: str = "spacy",
        model_name: str | None = None,
        persistent_store: Optional[AbstractTKGStore] = None,
        enable_cross_article: bool = True,
        use_web_search: bool = False,
        persist: bool = False,
        use_rss: bool = False,
    ):
        self.use_wikidata = use_wikidata
        self.use_web_search = use_web_search
        self.extractor_name = extractor_name
        self.model_name = model_name
        self.persist = persist
        self.use_rss = use_rss

        self._persistent_store = persistent_store
        self._enable_cross_article = enable_cross_article

        self._extractor: Optional[AbstractExtractor] = None
        self._builder = TKGBuilder()
        self._internal_verifier = InternalVerifier()
        self._external_verifier: Optional[ExternalVerifier] = None
        self._calculator = TCSCalculator()

    @property
    def extractor(self) -> AbstractExtractor:
        """Lazy-load: instantiates the chosen extractor (spacy or llm) once."""
        if self._extractor is None:
            cls = _get_extractor_class(self.extractor_name)
            kwargs = {}
            if self.model_name and self.extractor_name == "spacy":
                kwargs["model_name"] = self.model_name
            logger.info(f"Orchestrator: initializing {cls.__name__} ({self.model_name or 'default'})...")
            self._extractor = cls(**kwargs)
        return self._extractor

    @property
    def llm_explainer(self):
        """Lazy-load: LLMExplainer instance created on first access."""
        if not hasattr(self, "_llm_explainer"):
            from backend.pipeline.scoring.llm_explainer import LLMExplainer
            self._llm_explainer = LLMExplainer()
        return self._llm_explainer

    @property
    def external_verifier(self) -> ExternalVerifier:
        if self._external_verifier is None:
            self._external_verifier = ExternalVerifier(
                use_wikidata=self.use_wikidata,
                use_web_search=self.use_web_search,
                persistent_store=self._persistent_store,
                use_rss=self.use_rss,
            )
        return self._external_verifier

    def run(self, article: Article) -> TCSResult:
        """Run the full pipeline on a single article."""
        start_ms = time.monotonic() * 1000
        logger.info(f"Pipeline START [{self.extractor_name}]: '{article.title[:60]}' ({len(article.text)} chars)")

        # C1: extraction
        facts = self.extractor.extract(article)
        logger.info(f"C1 done — {len(facts)} facts extracted ({self.extractor_name})")

        # C2: TKG construction
        tkg: TemporalKnowledgeGraph = self._builder.build(facts)
        logger.info(f"C2 done — TKG: {tkg.node_count} nodes, {tkg.edge_count} edges, {tkg.fact_count} facts")

        if tkg.fact_count == 0:
            logger.warning("Empty TKG — article contains no verifiable temporal facts.")
            return _empty_result(article, self.extractor_name, start_ms)

        # C3a: internal verification
        internal = self._internal_verifier.verify(tkg, publication_date=article.publication_date)
        logger.info(f"C3a done — {len(internal.inconsistencies)} inconsistencies, coherence={internal.score_coherence:.3f}")

        # C3b: external verification
        external = self.external_verifier.verify(tkg)
        logger.info(f"C3b done — {len(external.inconsistencies)} inconsistencies ({external.wikidata_queries} Wikidata queries)")

        all_facts = tkg.get_all_facts()
        all_inconsistencies = internal.inconsistencies + external.inconsistencies

        # C3c: cross-article verification (optional, requires Neo4j)
        cross_article_incs: list = []
        article_id = None
        if self._persistent_store:
            import uuid
            article_id = str(uuid.uuid4())
        if self._persistent_store and self._enable_cross_article:
            cross_verifier = CrossArticleVerifier(self._persistent_store)
            cross_article_incs = cross_verifier.verify(all_facts, article_id)
            logger.info(f"C3c done — {len(cross_article_incs)} cross-article conflicts")
            all_inconsistencies.extend(cross_article_incs)

        # C4: TCS computation
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
        result.rss_verifications = external.rss_verifications

        # Persist facts after scoring (only when persist=True; store may still be used for Wikidata cache)
        if self._persistent_store is not None and self.persist:
            try:
                self._persistent_store.add_facts(
                    all_facts,
                    article_id=article_id,
                    title=article.title or "",
                    source=article.source or "",
                )
                logger.info(f"Neo4j: {len(all_facts)} facts persisted (article_id={article_id})")
            except Exception as e:
                logger.error(f"Neo4j persistence failed: {e}")

        # XAI: LLM explanation (optional, requires Qwen)
        if self.llm_explainer.is_available():
            explanation = self.llm_explainer.explain(result, article_text=article.text, article_title=article.title)
            if explanation:
                result.explanation_text = explanation
                logger.info("XAI done — LLM explanation generated")
            else:
                logger.info("XAI — falling back to static template")
        else:
            logger.info("XAI — Qwen unavailable, using static template")

        logger.info(f"Pipeline DONE — TCS={result.score:.3f} ({result.label}) in {result.processing_time_ms:.0f}ms")
        return result

    def run_batch(self, articles: list[Article]) -> list[TCSResult]:
        """Run the pipeline on a list of articles (for dataset evaluation)."""
        results = []
        for i, article in enumerate(articles):
            logger.info(f"Batch [{self.extractor_name}] {i + 1}/{len(articles)}: {article.title[:50]}")
            try:
                result = self.run(article)
            except Exception as e:
                logger.error(f"Processing error for '{article.title}': {e}", exc_info=True)
                result = _empty_result(article, self.extractor_name)
            results.append(result)

        avg = sum(r.score for r in results) / len(results) if results else 0
        logger.info(f"Batch complete [{self.extractor_name}]: {len(results)} articles, avg TCS: {avg:.3f}")
        return results


def _generate_auto_title(text: str, max_words: int = 8) -> str:
    """Generates a short title from the first meaningful words of the article."""
    STOPWORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "was", "were", "be",
        "been", "being", "have", "has", "had", "that", "this", "these",
        "those", "it", "its", "he", "she", "they", "we", "i", "you",
    }
    words = text.strip().split()
    meaningful = [w.strip(".,;:!?\"'") for w in words if w.lower().strip(".,;:!?\"'") not in STOPWORDS]
    title_words = meaningful[:max_words]
    return " ".join(title_words) + "..." if len(meaningful) > max_words else " ".join(title_words)


def _empty_result(article: Article, pipeline_variant: str, start_ms: Optional[float] = None) -> TCSResult:
    """Empty TCSResult: n_temporal_claims=0 signals no facts found, not consistency."""
    processing_time = 0.0
    if start_ms is not None:
        processing_time = (time.monotonic() * 1000) - start_ms

    return TCSResult(
        score=0.5, n_inconsistencies=0, n_temporal_claims=0, coherence_factor=1.0,
        inconsistencies=[], facts=[],
        explanation_text="No verifiable temporal facts could be extracted from this article.",
        timeline=[], pipeline_variant=pipeline_variant, processing_time_ms=processing_time,
    )

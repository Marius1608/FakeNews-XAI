"""Pytest tests for the TCS pipeline.

Run: pytest backend/tests/test_pipeline.py -v
Does not require Qwen3 or Neo4j to be running.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from backend.pipeline.extraction.temporal_parser import TemporalParser
from backend.pipeline.graph.builder import TKGBuilder
from backend.pipeline.graph.models import (
    Article, Entity, EntityType, InconsistencyType, RelationType,
    Severity, TemporalExpression, TemporalFact,
)
from backend.pipeline.graph.store import TemporalKnowledgeGraph
from backend.pipeline.scoring.tcs import TCSCalculator
from backend.pipeline.verification.internal import InternalVerifier

# // section fixtures

OBAMA_ARTICLE = Article(
    title="Barack Obama — Presidency",
    text=(
        "Barack Obama served as the 44th President of the United States from January 2009 "
        "to January 2017. During his presidency, he signed the Affordable Care Act into law "
        "in March 2010. Before becoming president, Obama was a senator from Illinois starting "
        "in January 2005. He announced his presidential campaign in February 2007."
    ),
    publication_date=datetime(2020, 1, 1),
    source="test",
)


def _make_entity(text: str, etype: EntityType = EntityType.PERSON) -> Entity:
    return Entity(text=text, entity_type=etype, start_char=0, end_char=len(text))


def _make_expr(year: int, month: int = 1, day: int = 1) -> TemporalExpression:
    dt = datetime(year, month, day)
    return TemporalExpression(
        raw_text=str(year),
        normalized_date=dt,
        date_string=dt.strftime("%Y-%m-%d"),
    )


def _make_fact(
    subject: str,
    predicate: RelationType,
    obj: str,
    time_point: Optional[datetime] = None,
    time_start: Optional[datetime] = None,
    time_end: Optional[datetime] = None,
    sentence_idx: int = 0,
    source_sentence: str = "",
) -> TemporalFact:
    def _wrap(dt: Optional[datetime]) -> Optional[TemporalExpression]:
        if dt is None:
            return None
        return TemporalExpression(
            raw_text=str(dt.year),
            normalized_date=dt,
            date_string=dt.strftime("%Y-%m-%d"),
        )

    return TemporalFact(
        subject=_make_entity(subject),
        predicate=predicate,
        object=_make_entity(obj, EntityType.OTHER),
        time_point=_wrap(time_point),
        time_start=_wrap(time_start),
        time_end=_wrap(time_end),
        source_sentence_idx=sentence_idx,
        source_sentence=source_sentence,
    )


# // section test_temporal_parser

class TestTemporalParser:
    """Tests for temporal expression normalization."""

    def setup_method(self):
        self.parser = TemporalParser()

    def test_bare_year(self):
        result = self.parser.parse("2009")
        assert result is not None
        assert result.normalized_date is not None
        assert result.normalized_date.year == 2009

    def test_month_and_year(self):
        result = self.parser.parse("January 2009")
        assert result is not None
        assert result.normalized_date is not None
        assert result.normalized_date.year == 2009
        assert result.normalized_date.month == 1

    def test_early_decade(self):
        result = self.parser.parse("early 2000s")
        assert result is not None
        assert result.normalized_date is not None
        # "early 2000s" → 2000
        assert result.normalized_date.year == 2000
        assert result.is_approximate is True

    def test_mid_decade(self):
        result = self.parser.parse("mid 1990s")
        assert result is not None
        assert result.normalized_date is not None
        assert result.normalized_date.year == 1995
        assert result.is_approximate is True

    def test_late_decade(self):
        result = self.parser.parse("late 1980s")
        assert result is not None
        assert result.normalized_date is not None
        assert result.normalized_date.year == 1989
        assert result.is_approximate is True

    def test_full_date_confidence(self):
        result = self.parser.parse("March 23, 2010")
        assert result is not None
        # Full date -> confidence >= 0.9
        assert result.confidence >= 0.9

    def test_bare_year_confidence_lower(self):
        result = self.parser.parse("2009")
        assert result is not None
        # Year only -> confidence <= 0.6
        assert result.confidence <= 0.6

    def test_empty_string_returns_none(self):
        assert self.parser.parse("") is None
        assert self.parser.parse("   ") is None

    def test_unparseable_returns_expr_with_none_date(self):
        result = self.parser.parse("some random text without date")
        # Returns a TemporalExpression but with normalized_date=None
        assert result is not None
        assert result.normalized_date is None
        assert result.confidence == 0.0


# // section test_spacy_extractor

def _first_available_spacy_model() -> Optional[str]:
    """Returns the first installed spaCy model, or None if none is installed."""
    import spacy
    installed = spacy.util.get_installed_models()
    if not installed:
        return None
    # Preference order: trf > lg > sm > any other
    for preferred in ("en_core_web_trf", "en_core_web_lg", "en_core_web_sm"):
        if preferred in installed:
            return preferred
    return installed[0]


_SPACY_MODEL = _first_available_spacy_model()
_spacy_available = pytest.mark.skipif(
    _SPACY_MODEL is None,
    reason="No spaCy model installed",
)


class TestSpacyExtractor:
    """Tests for the spaCy extractor on the Obama article.

    Uses the first available spaCy model (not necessarily en_core_web_trf).
    Skipped if no spaCy model is installed.
    """

    @_spacy_available
    def test_extracts_at_least_one_fact(self):
        from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
        extractor = SpacyExtractor(model_name=_SPACY_MODEL)
        facts = extractor.extract(OBAMA_ARTICLE)
        assert len(facts) >= 1, "Extractor must find at least one temporal fact"

    @_spacy_available
    def test_facts_have_temporal_anchor(self):
        from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
        extractor = SpacyExtractor(model_name=_SPACY_MODEL)
        facts = extractor.extract(OBAMA_ARTICLE)
        temporal = [
            f for f in facts
            if f.time_point or f.time_start or f.time_end
        ]
        assert len(temporal) >= 1, "At least one fact must have a temporal anchor"

    @_spacy_available
    def test_facts_have_valid_predicates(self):
        from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
        extractor = SpacyExtractor(model_name=_SPACY_MODEL)
        facts = extractor.extract(OBAMA_ARTICLE)
        valid_predicates = set(RelationType)
        for fact in facts:
            assert fact.predicate in valid_predicates

    @_spacy_available
    def test_extractor_field_is_set(self):
        from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
        extractor = SpacyExtractor(model_name=_SPACY_MODEL)
        facts = extractor.extract(OBAMA_ARTICLE)
        for fact in facts:
            assert fact.extractor == "spacy"


# // section test_tcs_formula

class TestTCSFormula:
    """Tests for the TCS formula in TCSCalculator.compute()."""

    def setup_method(self):
        self.calc = TCSCalculator()

    def test_no_inconsistencies_gives_high_score(self):
        result = self.calc.compute(
            n_claims=5,
            inconsistencies=[],
            score_coherence=1.0,
            facts_verified=5,
            facts_total=5,
        )
        assert result.score >= 0.8

    def test_zero_claims_returns_score_half(self):
        # n_claims=0 → special case: score 0.5 (insufficient data)
        result = self.calc.compute(
            n_claims=0,
            inconsistencies=[],
            score_coherence=1.0,
        )
        assert result.score == 0.5
        assert result.n_temporal_claims == 0

    def test_many_critical_inconsistencies_gives_low_score(self):
        from backend.pipeline.graph.models import Inconsistency

        inconsistencies = [
            Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH,
                severity=Severity.CRITICAL,
                description=f"Inconsistency {i}",
                verified_by="internal",
            )
            for i in range(4)
        ]
        result = self.calc.compute(
            n_claims=4,
            inconsistencies=inconsistencies,
            score_coherence=0.0,
            facts_verified=4,
            facts_total=4,
        )
        assert result.score < 0.5

    def test_score_clamped_to_zero_one(self):
        from backend.pipeline.graph.models import Inconsistency

        # Force extreme conditions
        inc = Inconsistency(
            inconsistency_type=InconsistencyType.TEMPORAL_CYCLE,
            severity=Severity.CRITICAL,
            description="test",
            verified_by="internal",
        )
        result = self.calc.compute(
            n_claims=1,
            inconsistencies=[inc] * 10,
            score_coherence=0.0,
            facts_verified=1,
            facts_total=1,
        )
        assert 0.0 <= result.score <= 1.0

    def test_result_fields_populated(self):
        result = self.calc.compute(
            n_claims=3,
            inconsistencies=[],
            score_coherence=1.0,
            facts_verified=3,
            facts_total=3,
            pipeline_variant="spacy",
        )
        assert result.n_temporal_claims == 3
        assert result.n_inconsistencies == 0
        assert result.pipeline_variant == "spacy"
        assert isinstance(result.timeline, list)

    def test_higher_severity_lowers_score_more(self):
        from backend.pipeline.graph.models import Inconsistency

        def score_with_severity(sev: Severity) -> float:
            inc = Inconsistency(
                inconsistency_type=InconsistencyType.DATE_MISMATCH,
                severity=sev,
                description="test",
                verified_by="internal",
            )
            return self.calc.compute(
                n_claims=4, inconsistencies=[inc],
                score_coherence=1.0, facts_verified=4, facts_total=4,
            ).score

        assert score_with_severity(Severity.LOW) > score_with_severity(Severity.HIGH)


# // section test_internal_verifier

class TestInternalVerifier:
    """Tests for InternalVerifier: V7 entity consistency and V6 future_as_past."""

    def setup_method(self):
        self.verifier = InternalVerifier()
        self.builder = TKGBuilder()

    def _build_tkg(self, facts: list[TemporalFact]) -> TemporalKnowledgeGraph:
        return self.builder.build(facts)

    def test_v7_entity_compound_incompatible_roles(self):
        # Obama as "Senator and Governor" simultaneously — incompatible roles in a single fact
        fact = _make_fact(
            subject="Barack Obama",
            predicate=RelationType.HOLDS_POSITION,
            obj="Senator and Governor",
            time_start=datetime(2005, 1, 1),
            time_end=datetime(2008, 1, 1),
        )
        tkg = self._build_tkg([fact])
        result = self.verifier.verify(tkg)
        entity_incs = [
            i for i in result.inconsistencies
            if i.inconsistency_type == InconsistencyType.ENTITY_INCONSISTENCY
        ]
        assert len(entity_incs) >= 1
        assert any("Obama" in i.description for i in entity_incs)

    def test_v7_entity_separate_incompatible_roles_overlap(self):
        # Two separate facts: Obama Senator 2005-2008, Obama Governor 2005-2008
        fact_senator = _make_fact(
            subject="Barack Obama",
            predicate=RelationType.HOLDS_POSITION,
            obj="Senator",
            time_start=datetime(2005, 1, 1),
            time_end=datetime(2008, 1, 1),
        )
        fact_governor = _make_fact(
            subject="Barack Obama",
            predicate=RelationType.HOLDS_POSITION,
            obj="Governor",
            time_start=datetime(2005, 1, 1),
            time_end=datetime(2008, 1, 1),
            sentence_idx=1,
        )
        tkg = self._build_tkg([fact_senator, fact_governor])
        result = self.verifier.verify(tkg)
        entity_incs = [
            i for i in result.inconsistencies
            if i.inconsistency_type == InconsistencyType.ENTITY_INCONSISTENCY
        ]
        assert len(entity_incs) >= 1

    def test_v7_compatible_roles_no_inconsistency(self):
        # Senator and Professor — compatible roles (not in INCOMPATIBLE_POSITIONS)
        fact1 = _make_fact(
            subject="John Doe",
            predicate=RelationType.HOLDS_POSITION,
            obj="Senator",
            time_start=datetime(2005, 1, 1),
            time_end=datetime(2008, 1, 1),
        )
        fact2 = _make_fact(
            subject="John Doe",
            predicate=RelationType.HOLDS_POSITION,
            obj="Professor",
            time_start=datetime(2005, 1, 1),
            time_end=datetime(2008, 1, 1),
            sentence_idx=1,
        )
        tkg = self._build_tkg([fact1, fact2])
        result = self.verifier.verify(tkg)
        entity_incs = [
            i for i in result.inconsistencies
            if i.inconsistency_type == InconsistencyType.ENTITY_INCONSISTENCY
        ]
        assert len(entity_incs) == 0

    def test_v6_future_as_past_detected(self):
        # Article published in 2020, fact dated 2025 with no future tense indicators
        pub_date = datetime(2020, 1, 1)
        fact = _make_fact(
            subject="John Smith",
            predicate=RelationType.HOLDS_POSITION,
            obj="President",
            time_point=datetime(2025, 6, 1),
            source_sentence="John Smith was inaugurated as President in June 2025.",
        )
        tkg = self._build_tkg([fact])
        result = self.verifier.verify(tkg, publication_date=pub_date)
        future_incs = [
            i for i in result.inconsistencies
            if i.inconsistency_type == InconsistencyType.FUTURE_AS_PAST
        ]
        assert len(future_incs) >= 1
        assert "2025" in future_incs[0].description
        assert "2020" in future_incs[0].description

    def test_v6_future_indicator_skipped(self):
        # Same future date, but the sentence contains "will be" — not an inconsistency
        pub_date = datetime(2020, 1, 1)
        fact = _make_fact(
            subject="John Smith",
            predicate=RelationType.HOLDS_POSITION,
            obj="President",
            time_point=datetime(2025, 6, 1),
            source_sentence="John Smith will be inaugurated as President in June 2025.",
        )
        tkg = self._build_tkg([fact])
        result = self.verifier.verify(tkg, publication_date=pub_date)
        future_incs = [
            i for i in result.inconsistencies
            if i.inconsistency_type == InconsistencyType.FUTURE_AS_PAST
        ]
        assert len(future_incs) == 0

    def test_v6_past_fact_no_inconsistency(self):
        # Fact in the past relative to publication date — must not be flagged as future_as_past
        pub_date = datetime(2020, 1, 1)
        fact = _make_fact(
            subject="Barack Obama",
            predicate=RelationType.HOLDS_POSITION,
            obj="President",
            time_point=datetime(2009, 1, 20),
        )
        tkg = self._build_tkg([fact])
        result = self.verifier.verify(tkg, publication_date=pub_date)
        future_incs = [
            i for i in result.inconsistencies
            if i.inconsistency_type == InconsistencyType.FUTURE_AS_PAST
        ]
        assert len(future_incs) == 0

    def test_coherence_score_range(self):
        # score_coherence must be in [0, 1] regardless of input
        fact = _make_fact(
            subject="A", predicate=RelationType.HOLDS_POSITION, obj="B",
            time_start=datetime(2010, 1, 1), time_end=datetime(2009, 1, 1),  # inversat
        )
        tkg = self._build_tkg([fact])
        result = self.verifier.verify(tkg)
        assert 0.0 <= result.score_coherence <= 1.0


# // section test_orchestrator_no_neo4j

# Predefined Obama facts used by the mock orchestrator — independent of spaCy
_OBAMA_FACTS = [
    _make_fact(
        subject="Barack Obama",
        predicate=RelationType.HOLDS_POSITION,
        obj="President",
        time_start=datetime(2009, 1, 20),
        time_end=datetime(2017, 1, 20),
        sentence_idx=0,
    ),
    _make_fact(
        subject="Barack Obama",
        predicate=RelationType.STARTED,
        obj="Affordable Care Act",
        time_point=datetime(2010, 3, 23),
        sentence_idx=1,
    ),
    _make_fact(
        subject="Barack Obama",
        predicate=RelationType.HOLDS_POSITION,
        obj="Senator",
        time_start=datetime(2005, 1, 1),
        time_end=datetime(2008, 11, 16),
        sentence_idx=2,
    ),
]


class TestOrchestratorNoNeo4j:
    """End-to-end orchestrator tests without Neo4j, Qwen3, or spaCy (extractor is mocked)."""

    @pytest.fixture(autouse=True)
    def mock_dependencies(self):
        # Mock LLMExplainer.is_available() -> False to skip Qwen3 inference
        # Mock spaCy extractor: extract() -> predefined Obama facts
        with (
            patch(
                "backend.pipeline.scoring.llm_explainer.LLMExplainer.is_available",
                return_value=False,
            ),
            patch(
                "backend.pipeline.extraction.spacy_extractor.SpacyExtractor.extract",
                return_value=_OBAMA_FACTS,
            ),
        ):
            yield

    def test_run_returns_tcs_result(self):
        from backend.pipeline.orchestrator import PipelineOrchestrator
        from backend.pipeline.graph.models import TCSResult

        orch = PipelineOrchestrator(
            use_wikidata=False,
            extractor_name="spacy",
            persistent_store=None,
        )
        result = orch.run(OBAMA_ARTICLE)
        assert isinstance(result, TCSResult)

    def test_run_score_in_range(self):
        from backend.pipeline.orchestrator import PipelineOrchestrator

        orch = PipelineOrchestrator(use_wikidata=False, extractor_name="spacy")
        result = orch.run(OBAMA_ARTICLE)
        assert 0.0 <= result.score <= 1.0

    def test_run_no_neo4j_article_id_is_none(self):
        from backend.pipeline.orchestrator import PipelineOrchestrator

        orch = PipelineOrchestrator(
            use_wikidata=False,
            extractor_name="spacy",
            persistent_store=None,
        )
        result = orch.run(OBAMA_ARTICLE)
        # Without Neo4j, article_id must be None
        assert result.article_id is None

    def test_run_cross_article_empty_without_store(self):
        from backend.pipeline.orchestrator import PipelineOrchestrator

        orch = PipelineOrchestrator(
            use_wikidata=False,
            extractor_name="spacy",
            persistent_store=None,
        )
        result = orch.run(OBAMA_ARTICLE)
        assert result.cross_article_inconsistencies == []

    def test_run_consistent_article_high_score(self):
        from backend.pipeline.orchestrator import PipelineOrchestrator

        orch = PipelineOrchestrator(use_wikidata=False, extractor_name="spacy")
        result = orch.run(OBAMA_ARTICLE)
        # Consistent article — score must be > 0.4
        assert result.score > 0.4, f"Score too low for a consistent article: {result.score}"

    def test_run_empty_article_returns_empty_result(self):
        from backend.pipeline.orchestrator import PipelineOrchestrator

        # Override the autouse mock with an empty list for this test
        with patch(
            "backend.pipeline.extraction.spacy_extractor.SpacyExtractor.extract",
            return_value=[],
        ):
            orch = PipelineOrchestrator(use_wikidata=False, extractor_name="spacy")
            article_no_dates = Article(
                title="No dates here",
                text="This is a generic statement about nothing in particular.",
                publication_date=datetime(2020, 1, 1),
                source="test",
            )
            result = orch.run(article_no_dates)
            # No temporal facts: n_temporal_claims=0
            assert result.n_temporal_claims == 0

    def test_run_with_mock_neo4j_store(self):
        from backend.pipeline.orchestrator import PipelineOrchestrator
        from backend.pipeline.graph.base_store import AbstractTKGStore

        # Mock store: get_facts_for_entity returns an empty list (required by CrossArticleVerifier)
        mock_store = MagicMock(spec=AbstractTKGStore)
        mock_store.get_facts_for_entity.return_value = []
        mock_store.get_all_facts.return_value = []

        orch = PipelineOrchestrator(
            use_wikidata=False,
            extractor_name="spacy",
            persistent_store=mock_store,
            enable_cross_article=True,
            persist=True,
        )
        result = orch.run(OBAMA_ARTICLE)

        # With persistent_store set and facts extracted, add_facts must be called
        assert result.n_temporal_claims > 0
        mock_store.add_facts.assert_called_once()
        assert result.article_id is not None

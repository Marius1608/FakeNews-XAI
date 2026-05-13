"""Teste pytest pentru pipeline-ul TCS.

Rulare: pytest backend/tests/test_pipeline.py -v
Nu necesita Ollama sau Neo4j pornite.
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
    """Teste pentru normalizarea expresiilor temporale."""

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
        # Data completa -> confidence >= 0.9
        assert result.confidence >= 0.9

    def test_bare_year_confidence_lower(self):
        result = self.parser.parse("2009")
        assert result is not None
        # Doar an -> confidence <= 0.6
        assert result.confidence <= 0.6

    def test_empty_string_returns_none(self):
        assert self.parser.parse("") is None
        assert self.parser.parse("   ") is None

    def test_unparseable_returns_expr_with_none_date(self):
        result = self.parser.parse("some random text without date")
        # Returneaza TemporalExpression, dar normalized_date=None
        assert result is not None
        assert result.normalized_date is None
        assert result.confidence == 0.0


# // section test_spacy_extractor

def _first_available_spacy_model() -> Optional[str]:
    """Returneaza primul model spaCy instalat, sau None daca nu exista niciunul."""
    import spacy
    installed = spacy.util.get_installed_models()
    if not installed:
        return None
    # Preferinta: trf > lg > sm > orice altceva
    for preferred in ("en_core_web_trf", "en_core_web_lg", "en_core_web_sm"):
        if preferred in installed:
            return preferred
    return installed[0]


_SPACY_MODEL = _first_available_spacy_model()
_spacy_available = pytest.mark.skipif(
    _SPACY_MODEL is None,
    reason="Niciun model spaCy instalat",
)


class TestSpacyExtractor:
    """Teste extractor spaCy pe articolul Obama.

    Foloseste primul model spaCy disponibil (nu neaparat en_core_web_trf).
    Sarind daca niciun model nu e instalat.
    """

    @_spacy_available
    def test_extracts_at_least_one_fact(self):
        from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
        extractor = SpacyExtractor(model_name=_SPACY_MODEL)
        facts = extractor.extract(OBAMA_ARTICLE)
        assert len(facts) >= 1, "Extractor trebuie sa gaseasca cel putin un fapt temporal"

    @_spacy_available
    def test_facts_have_temporal_anchor(self):
        from backend.pipeline.extraction.spacy_extractor import SpacyExtractor
        extractor = SpacyExtractor(model_name=_SPACY_MODEL)
        facts = extractor.extract(OBAMA_ARTICLE)
        temporal = [
            f for f in facts
            if f.time_point or f.time_start or f.time_end
        ]
        assert len(temporal) >= 1, "Cel putin un fapt trebuie sa aiba ancora temporala"

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
    """Teste pentru formula TCS din TCSCalculator.compute()."""

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
        # n_claims=0 → caz special: scor 0.5 (insufficient data)
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
                description=f"Inconsistenta {i}",
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

        # Forteaza conditii extreme
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
    """Teste pentru InternalVerifier: V7 entity consistency si V6 future_as_past."""

    def setup_method(self):
        self.verifier = InternalVerifier()
        self.builder = TKGBuilder()

    def _build_tkg(self, facts: list[TemporalFact]) -> TemporalKnowledgeGraph:
        return self.builder.build(facts)

    def test_v7_entity_compound_incompatible_roles(self):
        # Obama ca "Senator and Governor" simultan — roluri incompatibile intr-un singur fapt
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
        # Doua fapte separate: Obama Senator 2005-2008, Obama Governor 2005-2008
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
        # Senator si Profesor — roluri compatibile (nu sunt in INCOMPATIBLE_POSITIONS)
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
        # Articol publicat in 2020, fapt cu data 2025 fara indicatori de viitor
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
        # Aceeasi data viitoare, dar propozitia contine "will be" — nu e inconsistenta
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
        # Fapt in trecut fata de data publicarii — nu trebuie detectat ca future_as_past
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
        # score_coherence trebuie sa fie in [0, 1] indiferent de input
        fact = _make_fact(
            subject="A", predicate=RelationType.HOLDS_POSITION, obj="B",
            time_start=datetime(2010, 1, 1), time_end=datetime(2009, 1, 1),  # inversat
        )
        tkg = self._build_tkg([fact])
        result = self.verifier.verify(tkg)
        assert 0.0 <= result.score_coherence <= 1.0


# // section test_orchestrator_no_neo4j

# Fapte Obama predefinite folosite de orchestrator mock — independente de spaCy
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
    """Teste orchestrator end-to-end fara Neo4j, fara Ollama, fara spaCy (extractorul e mockat)."""

    @pytest.fixture(autouse=True)
    def mock_dependencies(self):
        # Mock Ollama: LLMExplainer.is_available() -> False
        # Mock spaCy extractor: extract() -> fapte Obama predefinite
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
        # Fara Neo4j, article_id trebuie sa fie None
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
        # Articol consistent — scor trebuie sa fie > 0.4
        assert result.score > 0.4, f"Scor prea mic pentru articol consistent: {result.score}"

    def test_run_empty_article_returns_empty_result(self):
        from backend.pipeline.orchestrator import PipelineOrchestrator

        # Suprascrie mock-ul autouse cu o lista goala pentru acest test
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
            # Fara fapte temporale: n_temporal_claims=0
            assert result.n_temporal_claims == 0

    def test_run_with_mock_neo4j_store(self):
        from backend.pipeline.orchestrator import PipelineOrchestrator
        from backend.pipeline.graph.base_store import AbstractTKGStore

        # Mock store: get_facts_for_entity returneaza lista goala (necesar pentru CrossArticleVerifier)
        mock_store = MagicMock(spec=AbstractTKGStore)
        mock_store.get_facts_for_entity.return_value = []
        mock_store.get_all_facts.return_value = []

        orch = PipelineOrchestrator(
            use_wikidata=False,
            extractor_name="spacy",
            persistent_store=mock_store,
            enable_cross_article=True,
        )
        result = orch.run(OBAMA_ARTICLE)

        # Cu persistent_store setat si fapte extrase, add_facts trebuie apelat
        assert result.n_temporal_claims > 0
        mock_store.add_facts.assert_called_once()
        assert result.article_id is not None

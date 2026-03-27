"""
Clasa abstracta pentru extractoarele de informatii temporale.

Ambele pipeline-uri (A: spaCy deterministic si B: LLM-based)
implementeaza aceasta interfata.

De ce exista?
-------------
Permite rularea ambelor pipeline-uri cu acelasi cod:
    extractor = SpacyExtractor()   # sau LlmExtractor()
    facts = extractor.extract(article)
Codul din orchestrator nu trebuie sa stie CE extractor foloseste.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.pipeline.graph.models import Article, TemporalFact


class AbstractExtractor(ABC):
    """Interfata comuna pentru extractoarele de fapte temporale."""

    @abstractmethod
    def extract(self, article: Article) -> list[TemporalFact]:
        """
        Extrage fapte temporale dintr-un articol.

        Args:
            article: articolul de analizat

        Returns:
            Lista de TemporalFact extrase din text.
        """
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Returneaza numele extractorului (ex: 'spacy', 'llm')."""
        ...
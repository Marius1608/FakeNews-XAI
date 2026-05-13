"""C1 — Interfata abstracta pentru extractoarele de fapte temporale."""

from __future__ import annotations
from abc import ABC, abstractmethod
from backend.pipeline.graph.models import Article, TemporalFact


class AbstractExtractor(ABC):
    """Common interface: Pipeline A (spaCy) and Pipeline B (LLM) both implement it."""

    @abstractmethod
    def extract(self, article: Article) -> list[TemporalFact]:
        """Extract temporal facts from an article."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Return the extractor name ('spacy' or 'llm')."""
        ...

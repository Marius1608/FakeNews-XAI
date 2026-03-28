"""C1 — Interfata abstracta pentru extractoarele de fapte temporale."""

from __future__ import annotations
from abc import ABC, abstractmethod
from backend.pipeline.graph.models import Article, TemporalFact


class AbstractExtractor(ABC):
    """Interfata comuna: Pipeline A (spaCy) si Pipeline B (LLM) o implementeaza."""

    @abstractmethod
    def extract(self, article: Article) -> list[TemporalFact]:
        """Extrage fapte temporale dintr-un articol."""
        ...

    @abstractmethod
    def get_name(self) -> str:
        """Returneaza numele extractorului ('spacy' sau 'llm')."""
        ...
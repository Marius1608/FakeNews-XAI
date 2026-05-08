"""Abstract interface for Temporal Knowledge Graph storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.pipeline.graph.models import TemporalFact


class AbstractTKGStore(ABC):
    """Interface for Temporal Knowledge Graph storage backends."""

    @abstractmethod
    def add_fact(self, fact: TemporalFact, article_id: str | None = None) -> None: ...

    @abstractmethod
    def add_facts(self, facts: list[TemporalFact], article_id: str | None = None) -> None: ...

    @abstractmethod
    def get_all_facts(self, article_id: str | None = None) -> list[TemporalFact]: ...

    @abstractmethod
    def get_facts_for_entity(self, entity_name: str) -> list[TemporalFact]: ...

    @abstractmethod
    def get_articles(self) -> list[dict]: ...

    @abstractmethod
    def delete_article(self, article_id: str) -> bool: ...

    @abstractmethod
    def summary(self) -> dict: ...

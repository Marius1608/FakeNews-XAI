"""Structuri de date partajate de toate cele 4 componente TCS."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── Enums ──
class EntityType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORG"
    LOCATION = "GPE"
    EVENT = "EVENT"
    DATE = "DATE"
    NORP = "NORP"           # Nationalitati, grupuri religioase/politice
    PRODUCT = "PRODUCT"
    OTHER = "OTHER"


class RelationType(str, Enum):
    HOLDS_POSITION = "holds_position"
    MEMBER_OF = "member_of"
    LOCATED_IN = "located_in"
    OCCURRED_ON = "occurred_on"
    STARTED = "started"
    ENDED = "ended"
    CAUSED = "caused"
    PRECEDED = "preceded"
    FOLLOWED = "followed"
    GENERIC = "generic"


class InconsistencyType(str, Enum):
    TEMPORAL_CYCLE = "temporal_cycle"
    CAUSAL_VIOLATION = "causal_violation"
    ORDERING_ERROR = "ordering_error"
    DATE_MISMATCH = "date_mismatch"
    ANACHRONISM = "anachronism"
    DURATION_IMPLAUSIBLE = "duration_implausible"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── C1: Extraction output ──
@dataclass
class Entity:
    """O entitate extrasa din text."""
    text: str
    entity_type: EntityType
    start_char: int
    end_char: int
    wikidata_id: Optional[str] = None
    normalized: Optional[str] = None

    def __repr__(self) -> str:
        return f"Entity({self.text!r}, {self.entity_type.value})"


@dataclass
class TemporalExpression:
    """O expresie temporala normalizata (output dateparser)."""
    raw_text: str
    normalized_date: Optional[datetime] = None
    date_string: Optional[str] = None
    start_char: int = 0
    end_char: int = 0
    is_relative: bool = False
    is_approximate: bool = False
    confidence: float = 1.0

    def __repr__(self) -> str:
        date_str = self.date_string or "unparsed"
        return f"TemporalExpr({self.raw_text!r} -> {date_str})"


@dataclass
class TemporalFact:
    """
    Un fapt temporal — unitatea de baza a pipeline-ului.
    Circula de la C1 (Extraction) la C2 (Graph).
    """
    subject: Entity
    predicate: RelationType
    object: Entity
    time_start: Optional[TemporalExpression] = None
    time_end: Optional[TemporalExpression] = None
    time_point: Optional[TemporalExpression] = None

    source_sentence: str = ""
    source_sentence_idx: int = 0
    extraction_confidence: float = 1.0
    extractor: str = "spacy"

    def __repr__(self) -> str:
        time_info = ""
        if self.time_point:
            time_info = f" @{self.time_point.date_string}"
        elif self.time_start:
            end = self.time_end.date_string if self.time_end else "?"
            time_info = f" [{self.time_start.date_string} -> {end}]"
        return (
            f"Fact({self.subject.text} "
            f"—{self.predicate.value}-> "
            f"{self.object.text}{time_info})"
        )


# ── Input ──
@dataclass
class Article:
    """Un articol de analizat."""
    text: str
    title: str = ""
    publication_date: Optional[datetime] = None
    source: str = ""
    url: str = ""
    label: Optional[str] = None       # ground truth: "true", "false", etc.
    dataset: Optional[str] = None


# ── C3: Verification output ──
@dataclass
class Inconsistency:
    """O inconsistenta temporala detectata de C3 (Verification)."""
    inconsistency_type: InconsistencyType
    severity: Severity
    description: str
    facts_involved: list[TemporalFact] = field(default_factory=list)
    sentence_indices: list[int] = field(default_factory=list)
    verified_by: str = "internal"      # "internal", "wikidata", "reference_kg"
    evidence: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"Inconsistency({self.inconsistency_type.value}, "
            f"{self.severity.value}: {self.description[:60]}...)"
        )


# ── C4: Scoring output ──
@dataclass
class TCSResult:
    """
    Rezultatul final al pipeline-ului.
    TCS = 1 - (inconsist_detected / claims_temporal) x score_coherence
    """
    score: float                       # [0, 1] — 1.0 = consistent, 0.0 = suspect

    n_inconsistencies: int
    n_temporal_claims: int
    coherence_factor: float

    inconsistencies: list[Inconsistency] = field(default_factory=list)
    facts: list[TemporalFact] = field(default_factory=list)

    explanation_text: str = ""
    timeline: list[dict] = field(default_factory=list)

    pipeline_variant: str = "spacy"
    processing_time_ms: float = 0.0

    @property
    def label(self) -> str:
        """Eticheta de consistenta conform Score Interpretation."""
        if self.n_temporal_claims == 0:
            return "Insufficient Temporal Data"
        elif self.score >= 0.8:
            return "Highly Consistent (Likely True)"
        elif self.score >= 0.5:
            return "Moderately Consistent"
        elif self.score >= 0.2:
            return "Multiple Inconsistencies (Suspicious)"
        else:
            return "Severe Violations (Likely Fake)"
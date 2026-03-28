"""
Data models pentru pipeline-ul TCS.

Aceste dataclasses definesc structurile de date care circula prin toate cele 4 componente:
  1. Extraction → TemporalFact, TemporalExpression
  2. Graph Construction → foloseste TemporalFact ca sa construiasca TKG
  3. Verification → Inconsistency
  4. Scoring → TCSResult
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


#Enums
class EntityType(str, Enum):
    """Tipuri de entitati relevante pentru fact-checking temporal."""
    PERSON = "PERSON"
    ORGANIZATION = "ORG"
    LOCATION = "GPE"
    EVENT = "EVENT"
    DATE = "DATE"
    NORP = "NORP"           # Nationalitati, grupuri religioase/politice
    PRODUCT = "PRODUCT"
    OTHER = "OTHER"


class RelationType(str, Enum):
    """Tipuri de relatii temporale intre entitati."""
    HOLDS_POSITION = "holds_position"       # ex: "X is president of Y"
    MEMBER_OF = "member_of"                 # ex: "X is member of Y"
    LOCATED_IN = "located_in"               # ex: "X happened in Y"
    OCCURRED_ON = "occurred_on"             # ex: "Event X on date Y"
    STARTED = "started"                     # ex: "X started in Y"
    ENDED = "ended"                         # ex: "X ended in Y"
    CAUSED = "caused"                       # ex: "X caused Y"
    PRECEDED = "preceded"                   # ex: "X happened before Y"
    FOLLOWED = "followed"                   # ex: "X happened after Y"
    GENERIC = "generic"                     # fallback


class InconsistencyType(str, Enum):
    """Tipuri de inconsistente temporale detectabile."""
    TEMPORAL_CYCLE = "temporal_cycle"                # A inainte de B inainte de A
    CAUSAL_VIOLATION = "causal_violation"            # efect inainte de cauza
    ORDERING_ERROR = "ordering_error"                # ordine cronologica gresita
    DATE_MISMATCH = "date_mismatch"                  # data contrazice fapte cunoscute
    ANACHRONISM = "anachronism"                      # entitate nu exista la data mentionata
    DURATION_IMPLAUSIBLE = "duration_implausible"    # interval de timp nerealist


class Severity(str, Enum):
    """Cat de grava e o inconsistenta pentru credibilitate."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


#Extraction Output
@dataclass
class Entity:
    """O entitate extrasa din text (persoana, organizatie, loc, etc.)."""
    text: str                              # forma din text: "Barack Obama"
    entity_type: EntityType                # PERSON, ORG, etc.
    start_char: int                        # offset caracter in textul sursa
    end_char: int
    wikidata_id: Optional[str] = None      # ex: Q76 pentru Barack Obama
    normalized: Optional[str] = None       # forma canonica dupa rezolutie

    def __repr__(self) -> str:
        return f"Entity({self.text!r}, {self.entity_type.value})"


@dataclass
class TemporalExpression:
    """O expresie temporala extrasa si normalizata din text."""
    raw_text: str                          # "last January", "in 2019"
    normalized_date: Optional[datetime] = None  # datetime parsat
    date_string: Optional[str] = None      # "2019-01-01" (format ISO)
    start_char: int = 0
    end_char: int = 0
    is_relative: bool = False              # "yesterday", "last week"
    is_approximate: bool = False           # "around 2015", "early 2000s"
    confidence: float = 1.0                # cat de sigur e parserul

    def __repr__(self) -> str:
        date_str = self.date_string or "unparsed"
        return f"TemporalExpr({self.raw_text!r} -> {date_str})"


@dataclass
class TemporalFact:
    """
    Un fapt temporal extras din text — unitatea de baza a pipeline-ului.

    Circula de la Componenta 1 (Extraction) la Componenta 2 (Graph).

    Exemplu:
        "Barack Obama served as president from 2009 to 2017"
        -> subject: Entity("Barack Obama", PERSON)
           predicate: RelationType.HOLDS_POSITION
           object: Entity("president", OTHER)
           time_start: 2009-01-20
           time_end: 2017-01-20
    """
    subject: Entity
    predicate: RelationType
    object: Entity
    time_start: Optional[TemporalExpression] = None
    time_end: Optional[TemporalExpression] = None
    time_point: Optional[TemporalExpression] = None  # pentru evenimente punctuale

    # Provenienta — din ce propozitie si cu ce extractor
    source_sentence: str = ""
    source_sentence_idx: int = 0
    extraction_confidence: float = 1.0
    extractor: str = "spacy"               # "spacy" sau "llm"

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


#Article Input
@dataclass
class Article:
    """Un articol care va fi analizat de pipeline-ul TCS."""
    text: str
    title: str = ""
    publication_date: Optional[datetime] = None
    source: str = ""                       # "reuters", "liar-dataset", etc.
    url: str = ""

    # Ground truth (pentru evaluare)
    label: Optional[str] = None            # "true", "false", "half-true", etc.
    dataset: Optional[str] = None          # "LIAR", "FakeNewsNet", etc.


#Verification Output
@dataclass
class Inconsistency:
    """
    O inconsistenta temporala detectata de Componenta 3 (Verification).
    Fiecare inconsistenta contribuie la scaderea scorului TCS.
    """
    inconsistency_type: InconsistencyType
    severity: Severity
    description: str                       # explicatie lizibila
    facts_involved: list[TemporalFact] = field(default_factory=list)

    # Pentru highlight in UI
    sentence_indices: list[int] = field(default_factory=list)

    # Sursa verificarii
    verified_by: str = "internal"          # "internal", "wikidata", "reference_kg"
    evidence: Optional[str] = None         # ex: proprietatea Wikidata care contrazice

    def __repr__(self) -> str:
        return (
            f"Inconsistency({self.inconsistency_type.value}, "
            f"{self.severity.value}: {self.description[:60]}...)"
        )


#Scoring Output
@dataclass
class TCSResult:
    """
    Rezultatul final al pipeline-ului TCS (Componenta 4).

    Formula: TCS = (N_inconsist / C_temporal) x S_coherence
    Normalizat la [0, 1] unde:
        1.0 = complet consistent (fara inconsistente)
        0.0 = foarte inconsistent
    """
    score: float                           # scor TCS [0, 1]

    # Componentele scorului
    n_inconsistencies: int                 # cate inconsistente s-au gasit
    n_temporal_claims: int                 # cate afirmatii temporale s-au extras
    coherence_factor: float                # multiplicator S_coherence

    # Detalii
    inconsistencies: list[Inconsistency] = field(default_factory=list)
    facts: list[TemporalFact] = field(default_factory=list)

    # Explicatie
    explanation_text: str = ""             # explicatie in limbaj natural
    timeline: list[dict] = field(default_factory=list)  # pentru vizualizare UI

    # Metadata
    pipeline_variant: str = "spacy"        # "spacy" sau "llm"
    processing_time_ms: float = 0.0

    @property
    def label(self) -> str:
        """
        Eticheta de consistenta lizibila.

        TCS e un scor de consistenta: mare = bun, mic = suspect.
            1.0 = zero inconsistente detectate → articol consistent
            0.0 = toate faptele inconsistente  → articol suspect

        Formula: TCS = 1 - (inconsist_detected / claims_temporal) × score_coherence

        Praguri conform sectiunii Score Interpretation:
            0.8–1.0: Highly consistent (likely true)
            0.5–0.7: Moderately consistent
            0.2–0.4: Multiple inconsistencies (suspicious)
            0.0–0.2: Severe violations (likely fake)
        """
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
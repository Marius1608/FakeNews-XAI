"""C4 — Explainer: generare explicatii in limbaj natural pentru rezultatul TCS."""

from __future__ import annotations

import logging
from typing import Optional

from backend.pipeline.graph.models import (
    Inconsistency,
    InconsistencyType,
    Severity,
    TCSResult,
    TemporalFact,
)
from backend.pipeline.graph.store import TemporalKnowledgeGraph
from backend.pipeline.verification.internal import InternalVerificationResult
from backend.pipeline.verification.external import ExternalVerificationResult

logger = logging.getLogger(__name__)


# Template-uri explicatii
_SCORE_TEMPLATES = {
    "high": (
        "The article's temporal claims are highly consistent (TCS = {score:.2f}). "
        "Out of {n_claims} temporal claims, {n_inc} inconsistencies were detected."
    ),
    "moderate": (
        "The article shows moderate temporal consistency (TCS = {score:.2f}). "
        "{n_inc} inconsistencies were found among {n_claims} temporal claims."
    ),
    "suspicious": (
        "Multiple temporal inconsistencies detected (TCS = {score:.2f}). "
        "{n_inc} out of {n_claims} temporal claims are problematic."
    ),
    "severe": (
        "Severe temporal violations detected (TCS = {score:.2f}). "
        "{n_inc} inconsistencies found in {n_claims} temporal claims — "
        "the article's timeline is unreliable."
    ),
    "no_data": (
        "Insufficient temporal data to compute a reliability score. "
        "The article contains no verifiable temporal claims."
    ),
}

_INCONSISTENCY_TEMPLATES = {
    InconsistencyType.TEMPORAL_CYCLE: "Temporal cycle: {desc}",
    InconsistencyType.CAUSAL_VIOLATION: "Causal violation: {desc}",
    InconsistencyType.ORDERING_ERROR: "Ordering error: {desc}",
    InconsistencyType.DATE_MISMATCH: "Date mismatch: {desc}",
    InconsistencyType.ANACHRONISM: "Anachronism: {desc}",
    InconsistencyType.DURATION_IMPLAUSIBLE: "Implausible duration: {desc}",
}

_SEVERITY_LABELS = {
    Severity.LOW: "minor",
    Severity.MEDIUM: "moderate",
    Severity.HIGH: "significant",
    Severity.CRITICAL: "critical",
}


class TCSExplainer:
    """Genereaza explicatii text si structurate pentru TCSResult."""

    def explain(self, result: TCSResult) -> str:
        """Explicatie completa: sumar scor + detalii inconsistente."""
        parts = [self._explain_score(result)]

        if result.inconsistencies:
            parts.append(self._explain_inconsistencies(result.inconsistencies))

        if result.facts:
            parts.append(self._explain_coverage(result))

        return "\n\n".join(parts)

    def explain_structured(self, result: TCSResult) -> dict:
        """
        Explicatie structurata pentru frontend (JSON-serializable).
        Contine: summary, inconsistency_details, fact_annotations, metadata.
        """
        return {
            "summary": self._explain_score(result),
            "score": result.score,
            "label": result.label,
            "n_claims": result.n_temporal_claims,
            "n_inconsistencies": result.n_inconsistencies,
            "coherence_factor": result.coherence_factor,
            "inconsistency_details": [
                self._inconsistency_detail(inc) for inc in result.inconsistencies
            ],
            "fact_annotations": [
                self._fact_annotation(fact, result.inconsistencies)
                for fact in result.facts
            ],
            "pipeline": result.pipeline_variant,
            "processing_time_ms": result.processing_time_ms,
        }


    # Explicatie scor
    def _explain_score(self, result: TCSResult) -> str:
        """Selecteaza template-ul potrivit pe baza scorului."""
        if result.n_temporal_claims == 0:
            return _SCORE_TEMPLATES["no_data"]

        if result.score >= 0.8:
            key = "high"
        elif result.score >= 0.5:
            key = "moderate"
        elif result.score >= 0.2:
            key = "suspicious"
        else:
            key = "severe"

        return _SCORE_TEMPLATES[key].format(
            score=result.score,
            n_claims=result.n_temporal_claims,
            n_inc=result.n_inconsistencies,
        )


    # Explicatii inconsistente
    def _explain_inconsistencies(self, inconsistencies: list[Inconsistency]) -> str:
        """Lista inconsistentelor cu severitate si detalii."""
        lines = ["Detected inconsistencies:"]

        # Sorteaza dupa severitate (critical primele)
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
        sorted_inc = sorted(inconsistencies, key=lambda i: severity_order.get(i.severity, 4))

        for i, inc in enumerate(sorted_inc, 1):
            severity_label = _SEVERITY_LABELS.get(inc.severity, "unknown")
            template = _INCONSISTENCY_TEMPLATES.get(
                inc.inconsistency_type, "{desc}"
            )
            desc = template.format(desc=inc.description)
            source = f" [verified by {inc.verified_by}]" if inc.verified_by != "internal" else ""
            lines.append(f"  {i}. [{severity_label}] {desc}{source}")

        return "\n".join(lines)

    def _inconsistency_detail(self, inc: Inconsistency) -> dict:
        """Detalii structurate pentru o singura inconsistenta (frontend)."""
        return {
            "type": inc.inconsistency_type.value,
            "severity": inc.severity.value,
            "severity_label": _SEVERITY_LABELS.get(inc.severity, "unknown"),
            "description": inc.description,
            "evidence": inc.evidence,
            "verified_by": inc.verified_by,
            "sentence_indices": inc.sentence_indices,
        }


    # Adnotari per fapt (pentru highlight in UI)
    def _fact_annotation(
        self, fact: TemporalFact, inconsistencies: list[Inconsistency],
    ) -> dict:
        """Adnotare per fapt: status (consistent/inconsistent/verified) + detalii."""
        # Gaseste inconsistentele legate de acest fapt (dupa sentence_idx)
        related = [
            inc for inc in inconsistencies
            if fact.source_sentence_idx in inc.sentence_indices
        ]

        if related:
            worst_severity = max(related, key=lambda i: _severity_rank(i.severity))
            status = "inconsistent"
            color = _severity_color(worst_severity.severity)
        else:
            status = "consistent"
            color = "green"

        time_str = _fact_time_string(fact)

        return {
            "sentence_idx": fact.source_sentence_idx,
            "subject": fact.subject.text,
            "predicate": fact.predicate.value,
            "object": fact.object.text,
            "time": time_str,
            "status": status,
            "color": color,
            "confidence": fact.extraction_confidence,
            "extractor": fact.extractor,
            "inconsistencies": [inc.description for inc in related],
        }


    # Sumar acoperire (cate fapte, cate verificate extern)
    def _explain_coverage(self, result: TCSResult) -> str:
        """Rezumat: fapte extrase, distributia extractor-ilor, verificare externa."""
        n_total = len(result.facts)
        extractors = {}
        for f in result.facts:
            extractors[f.extractor] = extractors.get(f.extractor, 0) + 1

        extractor_str = ", ".join(f"{k}: {v}" for k, v in extractors.items())

        # Fapte cu verificare externa
        ext_verified = sum(
            1 for inc in result.inconsistencies if inc.verified_by != "internal"
        )

        return (
            f"Coverage: {n_total} temporal facts extracted ({extractor_str}). "
            f"{ext_verified} externally verified inconsistencies."
        )


# Utilitare
def _severity_rank(severity: Severity) -> int:
    return {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2, Severity.CRITICAL: 3}.get(severity, 0)


def _severity_color(severity: Severity) -> str:
    """Culoare pentru frontend highlight."""
    return {
        Severity.LOW: "yellow",
        Severity.MEDIUM: "orange",
        Severity.HIGH: "red",
        Severity.CRITICAL: "red",
    }.get(severity, "gray")


def _fact_time_string(fact: TemporalFact) -> str:
    """Formateaza timpul unui fapt ca string lizibil."""
    if fact.time_point and fact.time_point.date_string:
        return fact.time_point.date_string
    parts = []
    if fact.time_start and fact.time_start.date_string:
        parts.append(fact.time_start.date_string)
    if fact.time_end and fact.time_end.date_string:
        parts.append(fact.time_end.date_string)
    return " → ".join(parts) if parts else "unknown"
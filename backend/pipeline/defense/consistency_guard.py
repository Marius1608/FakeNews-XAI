"""5.1 Cross-pipeline consistency guard.

Idea (defence in depth, anchored in determinism):
  Pipeline A (spaCy, rules) parses syntax and has no notion of instructions, so text
  inside an article cannot steer it. Pipeline B (LLM) can be steered. When B is the
  active extractor, A is run on the same article as an independent witness and the
  two are reconciled per sentence:

    * a B fact that A supports (same sentence, compatible date, overlapping names) is kept;
    * a B fact that contradicts what A found (same entities, incompatible date) is
      QUARANTINED (it does not reach the verdict); a B fact about other entities than
      A's facts is not a contradiction and is kept as unverified;
    * an A fact that B did not reproduce is RECOVERED, so what the deterministic
      pipeline sees is always part of the verdict ("A is the floor, B only adds");
    * sentences where B is silent but A found facts are flagged as suppression;
    * B facts in sentences A does not cover are kept but marked unverified (this
      preserves B's recall on implicit claims; it is the residual risk, see report).

  Any disagreement raises an informational LOW signal (no TCS penalty), so benign
  extractor differences do not change scores, while an attack is neutralised by the
  recovery/quarantine itself and made visible to the user.

Second part: `check_explanation` verifies that the dates in the LLM narrative are
backed by the structured evidence; otherwise the static template is used. This
removes hallucinated dates (observed once in the thesis) and dates planted by an
injection into the explainer. The verdict never depends on the narrative.

Everything here is pure Python on TemporalFact objects: no model, no network.
"""

from __future__ import annotations

import copy
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

from backend.pipeline.graph.models import (
    Inconsistency, InconsistencyType, RelationType, Severity, TemporalExpression, TemporalFact,
)

logger = logging.getLogger(__name__)

# A facts below this confidence are used as witnesses but are not re-injected as recovered
# facts (nominal/fallback strategies are noisier than dependency-based extraction).
DEFAULT_MIN_RECOVER_CONFIDENCE = 0.6

_STOPWORDS = frozenset(
    "the of and for in on a an to at by from with as is was were be been his her its their "
    "united states state states".split()
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")
_ISO_MONTH_RE = re.compile(r"^\s*(\d{4})-(\d{2})")


# Date helpers (year, month|None) -------------------------------------------------------

def _expr_key(expr: Optional[TemporalExpression]) -> Optional[tuple[int, Optional[int]]]:
    """(year, month) of a temporal expression; month is None when only the year is known."""
    if expr is None:
        return None
    ds = expr.date_string or ""
    m = _ISO_MONTH_RE.match(ds)
    if m:
        return int(m.group(1)), int(m.group(2))
    if expr.normalized_date is not None:
        # a bare year ("2009") normalises to Jan 1: do not claim month precision
        return expr.normalized_date.year, None
    y = _YEAR_RE.search(ds) or _YEAR_RE.search(expr.raw_text or "")
    return (int(y.group(1)), None) if y else None


def _time_keys(fact: TemporalFact) -> set[tuple[int, Optional[int]]]:
    keys = {_expr_key(e) for e in (fact.time_point, fact.time_start, fact.time_end)}
    return {k for k in keys if k is not None}


def _dates_compatible(a: TemporalFact, b: TemporalFact) -> bool:
    ka, kb = _time_keys(a), _time_keys(b)
    if not ka and not kb:
        return True
    if not ka or not kb:
        return False
    for ya, ma in ka:
        for yb, mb in kb:
            if ya == yb and (ma is None or mb is None or ma == mb):
                return True
    return False


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 3 and t not in _STOPWORDS}


def _names_overlap(a: TemporalFact, b: TemporalFact) -> bool:
    sa, oa = _tokens(a.subject.text), _tokens(a.object.text)
    sb, ob = _tokens(b.subject.text), _tokens(b.object.text)
    return bool((sa & sb) or (oa & ob) or (sa & ob) or (oa & sb))


def facts_agree(llm_fact: TemporalFact, det_fact: TemporalFact) -> bool:
    """True when the deterministic fact backs the LLM fact (same sentence, date, entities)."""
    return (
        llm_fact.source_sentence_idx == det_fact.source_sentence_idx
        and _dates_compatible(llm_fact, det_fact)
        and _names_overlap(llm_fact, det_fact)
    )


def _allowed_years(sentence_years: set[int], publication_year: Optional[int]) -> set[int]:
    allowed = set(sentence_years)
    # The publication year explains "last week"-style dates, but only when every year the
    # sentence states is not later than it: an explicit year after the publication date is
    # itself suspicious and must not be explained away by the publication year.
    if publication_year is not None and sentence_years and max(sentence_years) <= publication_year:
        allowed.add(publication_year)
    return allowed


def _sentence_years(fact: TemporalFact) -> set[int]:
    return {int(y) for y in _YEAR_RE.findall(fact.source_sentence or "")}


def is_date_grounded(fact: TemporalFact, publication_year: Optional[int] = None) -> bool:
    """Date grounding: when the sentence states explicit years, every year of the extracted
    fact must be one of them (or the publication year, for "last week" style claims when
    no stated year is later than it).

    A model steered by an injection can rewrite a date; the rewritten year is then not in
    the sentence. This check needs no second extractor. Sentences without an explicit year
    cannot be judged and pass.
    """
    years = _sentence_years(fact)
    if not years:
        return True
    fact_years = {y for (y, _m) in _time_keys(fact)}
    return fact_years <= _allowed_years(years, publication_year)


def repair_date(fact: TemporalFact, publication_year: Optional[int] = None) -> Optional[TemporalFact]:
    """Re-ground an ungrounded date. Only possible when the sentence states exactly ONE year:
    that year is then the only date the sentence supports, so the extracted date is replaced
    by it (year precision). Returns a repaired copy, or None when the sentence is ambiguous.
    """
    years = _sentence_years(fact)
    if len(years) != 1:
        return None
    year = next(iter(years))
    allowed = _allowed_years(years, publication_year)
    fixed = copy.copy(fact)
    changed = False
    for attr in ("time_point", "time_start", "time_end"):
        expr = getattr(fixed, attr)
        key = _expr_key(expr)
        if expr is not None and key is not None and key[0] not in allowed:
            setattr(fixed, attr, TemporalExpression(
                raw_text=str(year), normalized_date=datetime(year, 1, 1), date_string=str(year),
                confidence=expr.confidence,
            ))
            changed = True
    return fixed if changed else None


# Guard ---------------------------------------------------------------------------------

@dataclass
class GuardReport:
    n_llm: int = 0
    n_deterministic: int = 0
    supported: list[TemporalFact] = field(default_factory=list)
    quarantined: list[TemporalFact] = field(default_factory=list)
    recovered: list[TemporalFact] = field(default_factory=list)
    repaired: list[TemporalFact] = field(default_factory=list)
    unverified: list[TemporalFact] = field(default_factory=list)
    suppressed_sentences: list[int] = field(default_factory=list)

    @property
    def attack_suspected(self) -> bool:
        """Disagreement that cannot be explained by B simply extracting more than A."""
        return bool(self.quarantined or self.repaired or self.suppressed_sentences)

    @property
    def disagreement(self) -> bool:
        return bool(self.quarantined or self.repaired or self.suppressed_sentences or self.recovered)

    def to_dict(self) -> dict:
        return {
            "n_llm": self.n_llm,
            "n_deterministic": self.n_deterministic,
            "n_supported": len(self.supported),
            "n_quarantined": len(self.quarantined),
            "n_recovered": len(self.recovered),
            "n_repaired": len(self.repaired),
            "n_unverified": len(self.unverified),
            "suppressed_sentences": list(self.suppressed_sentences),
            "attack_suspected": self.attack_suspected,
        }


def _tag(facts: Iterable[TemporalFact], status: str) -> None:
    for f in facts:
        f.guard_status = status  # type: ignore[attr-defined]


def apply_guard(
    llm_facts: list[TemporalFact],
    det_facts: list[TemporalFact],
    min_recover_confidence: float = DEFAULT_MIN_RECOVER_CONFIDENCE,
    publication_year: Optional[int] = None,
) -> tuple[list[TemporalFact], GuardReport]:
    """Reconcile Pipeline B (llm_facts) with Pipeline A (det_facts). Returns (facts, report)."""
    report = GuardReport(n_llm=len(llm_facts), n_deterministic=len(det_facts))

    by_llm: dict[int, list[TemporalFact]] = defaultdict(list)
    by_det: dict[int, list[TemporalFact]] = defaultdict(list)
    for f in llm_facts:
        by_llm[f.source_sentence_idx].append(f)
    for f in det_facts:
        by_det[f.source_sentence_idx].append(f)

    for sent in sorted(set(by_llm) | set(by_det)):
        llm_all = by_llm.get(sent, [])
        # date grounding first: an LLM date that is not in the sentence is not trusted
        llm_here = []
        for f in llm_all:
            if is_date_grounded(f, publication_year):
                llm_here.append(f)
                continue
            fixed = repair_date(f, publication_year)
            if fixed is not None:
                report.repaired.append(fixed)   # re-grounded in the sentence's own year
                llm_here.append(fixed)
            else:
                report.quarantined.append(f)
        # Only specific relations witness: A's GENERIC fallback facts are noisy (e.g. it reads
        # "G20" as a date), so they neither contradict B nor get re-injected.
        det_here = [g for g in by_det.get(sent, []) if g.predicate != RelationType.GENERIC]

        if not det_here:
            # A has no reliable fact for this sentence: nothing to compare against.
            report.unverified.extend(llm_here)
            continue

        covered: set[int] = set()
        for f in llm_here:
            hits = [i for i, g in enumerate(det_here) if facts_agree(f, g)]
            if hits:
                covered.update(hits)
                report.supported.append(f)
            elif any(_names_overlap(f, g) and not _dates_compatible(f, g) for g in det_here):
                # same entities, incompatible dates: a real contradiction -> quarantine
                report.quarantined.append(f)
            else:
                # A says nothing about this claim (different entities): not a contradiction
                report.unverified.append(f)

        if not llm_all:
            report.suppressed_sentences.append(sent)

        for i, g in enumerate(det_here):
            if i not in covered and g.extraction_confidence >= min_recover_confidence:
                report.recovered.append(g)

    _tag(report.supported, "supported")
    _tag(report.recovered, "recovered")
    _tag(report.unverified, "unverified-llm")
    _tag(report.quarantined, "quarantined")
    _tag(report.repaired, "repaired")

    kept = report.supported + report.recovered + report.unverified
    kept.sort(key=lambda f: f.source_sentence_idx)

    if report.disagreement:
        logger.warning(
            "Consistency guard: %d supported, %d quarantined, %d recovered, "
            "suppression in sentences %s",
            len(report.supported), len(report.quarantined), len(report.recovered),
            report.suppressed_sentences,
        )
    return kept, report


def guard_inconsistency(report: GuardReport) -> Optional[Inconsistency]:
    """Informational LOW signal (weight 0 in the TCS formula) when the pipelines disagree."""
    if not report.attack_suspected:
        return None
    parts = []
    if report.quarantined:
        parts.append(f"{len(report.quarantined)} LLM-extracted fact(s) contradicted the deterministic "
                     f"extractor or carry a date that is not in the sentence, and were excluded from the verdict")
    if report.repaired:
        parts.append(f"{len(report.repaired)} LLM-extracted fact(s) had a date that is not in the sentence; "
                     f"the sentence's own year was used instead")
    if report.suppressed_sentences:
        parts.append(f"the LLM returned no facts for sentence(s) "
                     f"{report.suppressed_sentences} where the deterministic extractor found some")
    if report.recovered:
        parts.append(f"{len(report.recovered)} deterministic fact(s) were restored")
    return Inconsistency(
        inconsistency_type=InconsistencyType.EXTRACTION_DISAGREEMENT,
        severity=Severity.LOW,
        description="Extraction pipelines disagree - possible manipulation of the LLM extractor: "
                    + "; ".join(parts) + ".",
        facts_involved=list((report.quarantined + report.repaired)[:3]),
        sentence_indices=sorted({f.source_sentence_idx for f in report.quarantined + report.repaired}
                                | set(report.suppressed_sentences)),
        verified_by="cross_pipeline_guard",
        evidence=str(report.to_dict()),
    )


# Explanation check ---------------------------------------------------------------------

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MDY_RE = re.compile(rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
_DMY_RE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_ALT})\.?,?\s+(\d{{4}})\b", re.I)
_MY_RE = re.compile(rf"\b({_MONTH_ALT})\.?,?\s+(\d{{4}})\b", re.I)

DateKey = tuple[int, Optional[int], Optional[int]]  # (year, month|None, day|None)


def extract_dates(text: str) -> set[DateKey]:
    """All dates mentioned in `text`, each at the precision it is written with."""
    found: set[DateKey] = set()
    for m in _ISO_RE.finditer(text):
        found.add((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in _MDY_RE.finditer(text):
        found.add((int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2))))
    for m in _DMY_RE.finditer(text):
        found.add((int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1))))
    for m in _MY_RE.finditer(text):
        found.add((int(m.group(2)), _MONTHS[m.group(1).lower()], None))
    for m in _YEAR_RE.finditer(text):
        found.add((int(m.group(1)), None, None))
    return found


def _date_supported(d: DateKey, allowed: set[DateKey]) -> bool:
    y, m, day = d
    for ay, am, aday in allowed:
        if ay != y:
            continue
        if m is None:
            return True
        if am is None or am != m:
            continue
        if day is None or aday == day:
            return True
    return False


@dataclass
class ExplanationCheck:
    ok: bool
    checked: int = 0
    unsupported: list[str] = field(default_factory=list)


def _fmt(d: DateKey) -> str:
    y, m, day = d
    return f"{y}" if m is None else (f"{y}-{m:02d}" if day is None else f"{y}-{m:02d}-{day:02d}")


def evidence_dates(
    facts: Iterable[TemporalFact],
    inconsistencies: Iterable[Inconsistency],
    publication_date: Optional[datetime] = None,
) -> set[DateKey]:
    """Every date the structured evidence of an analysis supports."""
    texts: list[str] = []

    def add_fact(f: TemporalFact) -> None:
        texts.append(f.source_sentence or "")
        for e in (f.time_point, f.time_start, f.time_end):
            if e is not None:
                texts.extend([e.raw_text or "", e.date_string or ""])

    for f in facts:
        add_fact(f)
    for inc in inconsistencies:
        texts.extend([inc.description or "", inc.evidence or ""])
        for f in inc.facts_involved:
            add_fact(f)
    allowed: set[DateKey] = set()
    for t in texts:
        allowed |= extract_dates(t)
    if publication_date is not None:
        allowed.add((publication_date.year, publication_date.month, publication_date.day))
    return allowed


def check_explanation(
    narrative: str,
    facts: Iterable[TemporalFact],
    inconsistencies: Iterable[Inconsistency],
    publication_date: Optional[datetime] = None,
) -> ExplanationCheck:
    """Accept the LLM narrative only if every date it states is backed by structured evidence."""
    mentioned = extract_dates(narrative or "")
    allowed = evidence_dates(list(facts), list(inconsistencies), publication_date)
    unsupported = sorted(_fmt(d) for d in mentioned if not _date_supported(d, allowed))
    return ExplanationCheck(ok=not unsupported, checked=len(mentioned), unsupported=unsupported)

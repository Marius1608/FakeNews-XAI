"""C1 — Parser expresii temporale (wrapper dateparser)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import dateparser

from backend.pipeline.graph.models import TemporalExpression


RELATIVE_PATTERNS = re.compile(
    r"\b(yesterday|today|tomorrow|ago|last|next|previous|"
    r"this\s+(week|month|year)|"
    r"(\d+)\s+(days?|weeks?|months?|years?)\s+(ago|from\s+now))\b",
    re.IGNORECASE,
)

APPROXIMATE_PATTERNS = re.compile(
    r"\b(around|approximately|circa|roughly|about|early|late|mid|"
    r"\d{3}0s)\b",
    re.IGNORECASE,
)

# "early 2000s", "mid-1990s", "late 1980s"
DECADE_PATTERN = re.compile(
    r"\b(?:(early|mid|late)[- ])?((?:1[0-9]|20)\d{2})s\b",
    re.IGNORECASE,
)


class TemporalParser:
    """Normalizeaza expresii temporale in datetime folosind dateparser."""

    def __init__(
        self,
        prefer_dates_from: str = "past",
        languages: list[str] | None = None,
    ):
        self.settings = {
            "PREFER_DATES_FROM": prefer_dates_from,
            "RETURN_AS_TIMEZONE_AWARE": False,
            "REQUIRE_PARTS": ["year"],
        }
        self.languages = languages or ["en"]

    def parse(
        self,
        text: str,
        reference_date: Optional[datetime] = None,
        start_char: int = 0,
        end_char: int = 0,
    ) -> Optional[TemporalExpression]:
        """Parseaza o expresie temporala. reference_date = publication_date al articolului."""
        if not text or not text.strip():
            return None

        clean_text = text.strip()
        is_relative = bool(RELATIVE_PATTERNS.search(clean_text))
        is_approximate = bool(APPROXIMATE_PATTERNS.search(clean_text))

        settings = {**self.settings}
        if reference_date:
            settings["RELATIVE_BASE"] = reference_date

        # Pre-procesare decade patterns ("early 2000s" -> "2000")
        normalized_text, was_normalized = self._normalize_approximate(clean_text)

        parsed_date = dateparser.parse(
            normalized_text,
            languages=self.languages,
            settings=settings,
        )

        if parsed_date is None:
            return TemporalExpression(
                raw_text=clean_text, normalized_date=None, date_string=None,
                start_char=start_char, end_char=end_char,
                is_relative=is_relative, is_approximate=is_approximate,
                confidence=0.0,
            )

        if was_normalized:
            is_approximate = True

        confidence = self._estimate_confidence(clean_text, is_relative, is_approximate)

        return TemporalExpression(
            raw_text=clean_text,
            normalized_date=parsed_date,
            date_string=parsed_date.strftime("%Y-%m-%d"),
            start_char=start_char, end_char=end_char,
            is_relative=is_relative, is_approximate=is_approximate,
            confidence=confidence,
        )

    def parse_all_in_sentence(
        self,
        sentence: str,
        date_spans: list[tuple[int, int, str]],
        reference_date: Optional[datetime] = None,
    ) -> list[TemporalExpression]:
        """Parseaza mai multe expresii temporale dintr-o propozitie."""
        results = []
        for start, end, text in date_spans:
            expr = self.parse(text, reference_date, start, end)
            if expr is not None:
                results.append(expr)
        return results

    def _normalize_approximate(self, text: str) -> tuple[str, bool]:
        """Converteste decade patterns: early 2000s->2000, mid 1990s->1995, late 1980s->1989."""
        match = DECADE_PATTERN.search(text)
        if not match:
            return text, False

        modifier = (match.group(1) or "").lower()
        decade_start = int(match.group(2))

        if modifier == "mid":
            year = decade_start + 5
        elif modifier == "late":
            year = decade_start + 9
        else:
            year = decade_start

        return str(year), True

    def _estimate_confidence(self, text: str, is_relative: bool, is_approximate: bool) -> float:
        """Estimeaza confidence: date complete=high, relative=medium, aproximative=low."""
        confidence = 1.0

        if is_approximate:
            confidence -= 0.3
        if is_relative:
            confidence -= 0.2

        # Date complete (zi + luna + an)
        if re.search(r"\d{1,2}\s+\w+\s+\d{4}", text) or re.search(
            r"\w+\s+\d{1,2},?\s+\d{4}", text
        ):
            confidence = min(confidence + 0.1, 1.0)

        # Doar anul
        if re.fullmatch(r"\d{4}", text.strip()):
            confidence = min(confidence, 0.6)

        return max(confidence, 0.1)
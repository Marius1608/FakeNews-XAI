"""
Parser pentru expresii temporale — wrapper peste dateparser.

Transforma expresii temporale gasite in articole de stiri
in date concrete (datetime).

Folosit de ambele pipeline-uri (A: spaCy si B: LLM).

Exemple:
    "January 2019"       -> 2019-01-01
    "last Tuesday"       -> rezolvat relativ la publication_date
    "early 2000s"        -> 2000-01-01 (aproximativ)
    "three days ago"     -> rezolvat relativ la publication_date
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import dateparser

from backend.pipeline.graph.models import TemporalExpression


# Pattern-uri care indica date relative (depind de un moment de referinta)
RELATIVE_PATTERNS = re.compile(
    r"\b(yesterday|today|tomorrow|ago|last|next|previous|"
    r"this\s+(week|month|year)|"
    r"(\d+)\s+(days?|weeks?|months?|years?)\s+(ago|from\s+now))\b",
    re.IGNORECASE,
)

# Pattern-uri care indica date aproximative (nu sunt precise)
APPROXIMATE_PATTERNS = re.compile(
    r"\b(around|approximately|circa|roughly|about|early|late|mid|"
    r"\d{3}0s)\b",  # ex: "2000s", "1990s"
    re.IGNORECASE,
)


class TemporalParser:
    """
    Parseaza si normalizeaza expresii temporale din text.

    Foloseste dateparser ca motor principal

    Datele relative se rezolva fata de o data de referinta
    (de obicei publication_date al articolului).
    """

    def __init__(
        self,
        prefer_dates_from: str = "past",
        languages: list[str] | None = None,
    ):
        self.settings = {
            "PREFER_DATES_FROM": prefer_dates_from,
            "RETURN_AS_TIMEZONE_AWARE": False,
            "REQUIRE_PARTS": ["year"],  # minim anul trebuie sa existe
        }
        self.languages = languages or ["en"]

    def parse(
        self,
        text: str,
        reference_date: Optional[datetime] = None,
        start_char: int = 0,
        end_char: int = 0,
    ) -> Optional[TemporalExpression]:
        """
        Parseaza o expresie temporala intr-un TemporalExpression.

        Args:
            text: textul brut ("January 2019", "last week")
            reference_date: data fata de care se rezolva expresiile relative.
                           De obicei publication_date al articolului.
            start_char: offset caracter in textul sursa
            end_char: offset caracter sfarsit

        Returns:
            TemporalExpression daca parsarea reuseste, None daca textul e gol.
        """
        if not text or not text.strip():
            return None

        clean_text = text.strip()
        is_relative = bool(RELATIVE_PATTERNS.search(clean_text))
        is_approximate = bool(APPROXIMATE_PATTERNS.search(clean_text))

        # Configurez dateparser
        settings = {**self.settings}
        if reference_date:
            settings["RELATIVE_BASE"] = reference_date

        parsed_date = dateparser.parse(
            clean_text,
            languages=self.languages,
            settings=settings,
        )

        if parsed_date is None:
            # Parsarea a esuat — returnez expresia cu confidence 0
            return TemporalExpression(
                raw_text=clean_text,
                normalized_date=None,
                date_string=None,
                start_char=start_char,
                end_char=end_char,
                is_relative=is_relative,
                is_approximate=is_approximate,
                confidence=0.0,
            )

        confidence = self._estimate_confidence(clean_text, is_relative, is_approximate)

        return TemporalExpression(
            raw_text=clean_text,
            normalized_date=parsed_date,
            date_string=parsed_date.strftime("%Y-%m-%d"),
            start_char=start_char,
            end_char=end_char,
            is_relative=is_relative,
            is_approximate=is_approximate,
            confidence=confidence,
        )

    def parse_all_in_sentence(
        self,
        sentence: str,
        date_spans: list[tuple[int, int, str]],
        reference_date: Optional[datetime] = None,
    ) -> list[TemporalExpression]:
        """
        Parseaza mai multe expresii temporale dintr-o propozitie.

        Args:
            sentence: textul complet al propozitiei
            date_spans: lista de (start_char, end_char, text) — de obicei
                       de la spaCy NER sau regex extraction
            reference_date: pentru rezolvare date relative

        Returns:
            Lista de TemporalExpression parsate.
        """
        results = []
        for start, end, text in date_spans:
            expr = self.parse(text, reference_date, start, end)
            if expr is not None:
                results.append(expr)
        return results

    def _estimate_confidence(
        self,
        text: str,
        is_relative: bool,
        is_approximate: bool,
    ) -> float:
        """
        Estimeaza cat de sigura e parsarea pe baza tipului expresiei.

        Date complete ("January 20, 2009") -> confidence high
        Date relative ("last week") -> confidence medium
        Date aproximative ("early 2000s") -> confidence low
        """
        confidence = 1.0

        if is_approximate:
            confidence -= 0.3
        if is_relative:
            confidence -= 0.2

        # Pentru date specifice (au zi + luna + an)
        if re.search(r"\d{1,2}\s+\w+\s+\d{4}", text) or re.search(
            r"\w+\s+\d{1,2},?\s+\d{4}", text
        ):
            confidence = min(confidence + 0.1, 1.0)

        # Doar anul — mai putin precis
        if re.fullmatch(r"\d{4}", text.strip()):
            confidence = min(confidence, 0.6)

        return max(confidence, 0.1)
"""Test script for Wikipedia REST API web search integration.

Uses the Wikipedia REST API (free, no key required) to fetch entity summaries
and extract temporal information for verification in C3b.

Usage:
    python scripts/test_web_search.py
    python scripts/test_web_search.py --entity "Matt Gaetz"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# section: constants
WIKIPEDIA_API  = "https://en.wikipedia.org/api/rest_v1/page/summary/{name}"
WIKIPEDIA_SEARCH = "https://en.wikipedia.org/w/api.php"
REQUEST_TIMEOUT = 10
QUERY_DELAY     = 0.5

YEAR_PATTERN = re.compile(r"\b(1[89]\d{2}|20[012]\d)\b")
MONTH_YEAR_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|"
    r"August|September|October|November|December)"
    r"\s+(1[89]\d{2}|20[012]\d)\b",
    re.IGNORECASE,
)

HEADERS = {"User-Agent": "FakeNews-XAI/1.0 (UTCN Bachelor Thesis)"}

# section: test cases
# Format: (entity, position, claimed_year, expected_result)
TEST_CASES = [
    # should be CONFIRMED — correct facts
    ("Barack Obama",    "President",           2012, "confirmed"),
    ("Joe Biden",       "Senator",             2005, "confirmed"),
    ("Hillary Clinton", "Secretary of State",  2011, "confirmed"),
    ("Donald Trump",    "President",           2019, "confirmed"),
    ("Nancy Pelosi",    "Speaker",             2019, "confirmed"),
    ("Matt Gaetz",      "Representative",      2020, "confirmed"),
    ("Angela Merkel",   "Chancellor",          2015, "confirmed"),

    # should detect CONFLICT — wrong years
    ("Barack Obama",    "President",           2005, "conflict"),
    ("Joe Biden",       "Senator",             2015, "conflict"),  # was VP 2009-2017
    ("Bill Clinton",    "President",           2004, "conflict"),  # term ended 2001
    ("Matt Gaetz",      "Congressman",         2013, "conflict"),  # elected 2017
    ("Stacey Abrams",   "Governor",            2019, "conflict"),  # lost election
]


@dataclass
class WikipediaResult:
    """Result from Wikipedia REST API."""
    entity:       str
    wiki_title:   str
    extract:      str
    years_found:  list[int] = field(default_factory=list)
    dates_found:  list[str] = field(default_factory=list)


def _normalize_name(name: str) -> str:
    """Convert entity name to Wikipedia URL format."""
    return name.strip().replace(" ", "_")


def search_wikipedia_title(name: str) -> Optional[str]:
    """Search Wikipedia for the best matching article title."""
    try:
        resp = requests.get(
            WIKIPEDIA_SEARCH,
            params={
                "action":   "query",
                "list":     "search",
                "srsearch": name,
                "srlimit":  1,
                "format":   "json",
            },
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()
        results = data.get("query", {}).get("search", [])
        if results:
            return results[0]["title"].replace(" ", "_")
    except Exception:
        pass
    return _normalize_name(name)


def fetch_wikipedia_summary(entity_name: str) -> Optional[WikipediaResult]:
    """Fetch Wikipedia summary for an entity and extract temporal info."""
    # try direct URL first
    wiki_name = _normalize_name(entity_name)
    url = WIKIPEDIA_API.format(name=wiki_name)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            # try search fallback
            wiki_name = search_wikipedia_title(entity_name)
            if not wiki_name:
                return None
            url = WIKIPEDIA_API.format(name=wiki_name)
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [ERROR] Wikipedia fetch failed for '{entity_name}': {e}")
        return None

    extract = data.get("extract", "").strip()
    title   = data.get("title", entity_name)

    if not extract:
        return None

    # extract years and dates from the summary
    years = sorted(set(
        int(y) for y in YEAR_PATTERN.findall(extract)
        if 1900 <= int(y) <= 2030
    ))
    dates = [
        f"{m.group(1)} {m.group(2)}"
        for m in MONTH_YEAR_PATTERN.finditer(extract)
    ]

    return WikipediaResult(
        entity=entity_name,
        wiki_title=title,
        extract=extract,
        years_found=years,
        dates_found=dates[:5],
    )


# position synonyms for matching
POSITION_SYNONYMS: dict[str, list[str]] = {
    "president":          ["president", "presidency", "presidential", "commander"],
    "senator":            ["senator", "senate", "senatorial"],
    "representative":     ["representative", "congressman", "congresswoman", "congress", "house"],
    "congressman":        ["congressman", "congresswoman", "representative", "congress", "house"],
    "governor":           ["governor", "gubernatorial"],
    "speaker":            ["speaker", "house"],
    "secretary of state": ["secretary", "state department", "foreign"],
    "chancellor":         ["chancellor", "bundeskanzler"],
    "prime minister":     ["prime minister", "premier"],
    "vice president":     ["vice president", "vp"],
}


def _position_in_extract(position: str, extract: str) -> bool:
    """Check if a position (or its synonyms) is mentioned in the Wikipedia extract."""
    extract_lower = extract.lower()
    position_lower = position.lower()
    if position_lower in extract_lower:
        return True
    synonyms = POSITION_SYNONYMS.get(position_lower, [])
    if any(s in extract_lower for s in synonyms):
        return True
    skip = {"of", "the", "a", "an", "us", "u.s.", "united", "states"}
    words = [w for w in position_lower.split() if w not in skip and len(w) > 2]
    return any(w in extract_lower for w in words)


def _extract_position_interval(position: str, extract: str) -> tuple[int, int] | None:
    """Try to extract explicit start-end interval for a position from Wikipedia text.

    Looks for patterns like:
    - "served as X from 2009 to 2017"
    - "X from 2017 until his resignation in 2024"
    - "elected X in 2016"
    """
    extract_lower = extract.lower()
    position_lower = position.lower()
    synonyms = POSITION_SYNONYMS.get(position_lower, [position_lower])
    all_terms = [position_lower] + synonyms

    # pattern: "from YEAR to YEAR" or "from YEAR until YEAR"
    from_to = re.compile(
        r"from\s+(1[89]\d{2}|20[012]\d)\s+(?:to|until|through)\s+(1[89]\d{2}|20[012]\d)"
    )
    # pattern: "from YEAR" (open ended)
    from_only = re.compile(r"from\s+(1[89]\d{2}|20[012]\d)")
    # pattern: "since YEAR"
    since = re.compile(r"since\s+(1[89]\d{2}|20[012]\d)")
    # pattern: "in YEAR" (point in time)
    in_year = re.compile(r"in\s+(1[89]\d{2}|20[012]\d)")

    # search in sentences that mention the position
    sentences = re.split(r"[.!?]", extract)
    for sent in sentences:
        sent_lower = sent.lower()
        if not any(t in sent_lower for t in all_terms):
            continue
        # try from-to first
        m = from_to.search(sent)
        if m:
            return int(m.group(1)), int(m.group(2))
        # try from only
        m = from_only.search(sent)
        if m:
            return int(m.group(1)), 2030  # open-ended
        # try since
        m = since.search(sent)
        if m:
            return int(m.group(1)), 2030
        # try in YEAR
        m = in_year.search(sent)
        if m:
            y = int(m.group(1))
            return y, y  # point in time

    return None


def evaluate_result(
    result: Optional[WikipediaResult],
    position: str,
    claimed_year: int,
    tolerance: int = 2,
) -> str:
    """Evaluate whether Wikipedia confirms, conflicts, or is inconclusive.

    Strategy:
    1. Try to extract explicit "from YEAR to YEAR" interval for the position
    2. If found, check if claimed_year falls within interval
    3. If not found, fall back to year proximity check with ±2 tolerance
    """
    if result is None or not result.years_found:
        return "not_found"
    if not _position_in_extract(position, result.extract):
        return "not_found"

    # strategy 1: explicit interval extraction
    interval = _extract_position_interval(position, result.extract)
    if interval:
        start, end = interval
        if start <= claimed_year <= end + 1:  # +1 for transition year
            return "confirmed"
        elif claimed_year < start - 2 or claimed_year > end + 2:
            return "conflict"
        return "inconclusive"

    # strategy 2: proximity to any year in extract
    political_years = [y for y in result.years_found if 1940 <= y <= 2030]
    if not political_years:
        return "not_found"
    if any(abs(y - claimed_year) <= tolerance for y in political_years):
        return "confirmed"
    closest = min(political_years, key=lambda y: abs(y - claimed_year))
    if abs(closest - claimed_year) >= 3:
        return "conflict"
    return "inconclusive"
def main(args: argparse.Namespace) -> None:
    if args.entity:
        # single entity lookup
        print(f"\nFetching Wikipedia summary for: '{args.entity}'")
        result = fetch_wikipedia_summary(args.entity)
        if result:
            print(f"Title    : {result.wiki_title}")
            print(f"Years    : {result.years_found}")
            print(f"Dates    : {result.dates_found}")
            print(f"Extract  :\n  {result.extract[:500]}")
        else:
            print("No result found.")
        return

    # run all test cases
    print("\n" + "=" * 78)
    print("  WIKIPEDIA REST API — VERIFICATION TEST")
    print("=" * 78)
    print(f"\n  {'Entity':<25} {'Position':<22} {'Year':>5}   "
          f"{'Expected':<12} {'Got':<12} {'Years found'}")
    print(f"  {'-'*90}")

    correct = 0
    total   = len(TEST_CASES)
    results = []

    for entity, position, year, expected in TEST_CASES:
        result = fetch_wikipedia_summary(entity)
        got    = evaluate_result(result, position, year)
        match  = "✓" if got == expected else "✗"
        if got == expected:
            correct += 1

        years_display = result.years_found[:6] if result else []
        print(
            f"  {match} {entity:<24} {position:<22} {year:>5}   "
            f"{expected:<12} {got:<12} {years_display}"
        )

        results.append({
            "entity":       entity,
            "position":     position,
            "claimed_year": year,
            "expected":     expected,
            "got":          got,
            "match":        got == expected,
            "years_found":  years_display,
            "wiki_title":   result.wiki_title if result else None,
            "extract":      result.extract[:300] if result else None,
        })

        time.sleep(QUERY_DELAY)

    # summary
    print(f"\n  Accuracy: {correct}/{total} = {correct/total:.1%}")
    print(f"\n  Breakdown:")
    for outcome in ["confirmed", "conflict", "not_found", "inconclusive"]:
        n = sum(1 for r in results if r["got"] == outcome)
        correct_in = sum(1 for r in results if r["got"] == outcome and r["match"])
        print(f"    {outcome:<15}: {n:>2}  (correct: {correct_in})")

    # save results
    out_path = (_PROJECT_ROOT / "evaluation" / "results"
                / f"web_search_test_{datetime.now().strftime('%Y-%m-%d')}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "source":       "wikipedia_rest_api",
            "accuracy":     correct / total,
            "results":      results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test Wikipedia REST API for temporal fact verification"
    )
    parser.add_argument(
        "--entity", type=str, default=None,
        help="Fetch Wikipedia summary for a single entity (e.g. 'Matt Gaetz')"
    )
    args = parser.parse_args()
    main(args)
"""Runtime-mutable configuration — RSS feeds and operational thresholds exposed via /config/*.

In-memory only (module-level state): the app runs on HuggingFace Spaces where
restarts are frequent, so no persistence layer is introduced for this. Every
default below is the exact value that was previously hardcoded as a module
constant elsewhere in the pipeline — see PARAMETER_SPECS for the original
file:line each one came from.

NOT included here (intentionally out of scope): SEVERITY_WEIGHTS and the
0.85/0.15 coverage-bonus coefficients (pipeline/scoring/tcs.py) — the TCS
formula itself stays hardcoded and non-editable from the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Optional
from urllib.parse import urlparse

# RSS feeds
# Moved here (previously module constants in rss_verifier.py) so the effective
# feed list can be mutated at runtime without rss_verifier importing back into
# a config module that itself needs the feed list.

DEFAULT_FEEDS: list[str] = [
    "http://feeds.bbci.co.uk/news/politics/rss.xml",
    "https://feeds.npr.org/1014/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "https://thehill.com/homenews/feed/",
    "https://rss.politico.com/politics-news.xml",
    "https://www.theguardian.com/politics/rss",
    "https://www.theguardian.com/us-news/rss",
    "https://feeds.skynews.com/feeds/rss/politics.xml",
]

FEED_NAMES: dict[str, str] = {
    "http://feeds.bbci.co.uk/news/politics/rss.xml": "BBC Politics",
    "https://feeds.npr.org/1014/rss.xml": "NPR Politics",
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml": "NYT Politics",
    "https://thehill.com/homenews/feed/": "The Hill",
    "https://rss.politico.com/politics-news.xml": "Politico",
    "https://www.theguardian.com/politics/rss": "The Guardian Politics",
    "https://www.theguardian.com/us-news/rss": "The Guardian US",
    "https://feeds.skynews.com/feeds/rss/politics.xml": "Sky News Politics",
}

_rss_lock = Lock()
_predefined_enabled: dict[str, bool] = {url: True for url in DEFAULT_FEEDS}
_custom_feeds: list[str] = []


def feed_name(url: str) -> str:
    return FEED_NAMES.get(url, url.split("/")[2] if "/" in url else url)


def get_rss_feeds() -> dict:
    """Returns {"predefined": [{"url","name","enabled"}, ...8], "custom": [urls]}."""
    with _rss_lock:
        return {
            "predefined": [
                {"url": url, "name": feed_name(url), "enabled": _predefined_enabled[url]}
                for url in DEFAULT_FEEDS
            ],
            "custom": list(_custom_feeds),
        }


def get_effective_feed_urls() -> list[str]:
    """(enabled predefined) union (custom) — the list RSSVerifier actually queries."""
    with _rss_lock:
        enabled = [url for url in DEFAULT_FEEDS if _predefined_enabled.get(url, True)]
        return enabled + list(_custom_feeds)


def set_predefined_enabled(flags: dict[str, bool]) -> None:
    """flags must map exactly the 8 predefined URLs to booleans."""
    if set(flags.keys()) != set(DEFAULT_FEEDS):
        raise ValueError("Must specify the enabled flag for exactly the 8 predefined feed URLs.")
    with _rss_lock:
        for url, enabled in flags.items():
            _predefined_enabled[url] = bool(enabled)


def add_custom_feed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid feed URL: '{url}'. Must be a well-formed http(s) URL.")
    with _rss_lock:
        _custom_feeds.append(url)


def remove_custom_feed(index: int) -> None:
    with _rss_lock:
        if index < 0 or index >= len(_custom_feeds):
            raise IndexError(f"Custom feed index {index} out of range (0..{len(_custom_feeds) - 1}).")
        _custom_feeds.pop(index)


def reset_rss_feeds() -> None:
    with _rss_lock:
        for url in DEFAULT_FEEDS:
            _predefined_enabled[url] = True
        _custom_feeds.clear()


# Operational parameters (Table 5.4 minus severity weights / Wikidata cache TTL / batch size)

@dataclass(frozen=True)
class ParameterSpec:
    key: str
    label: str
    group: str  # "classification" | "internal" | "external"
    unit: str  # "score" | "days" | "years"
    default: float
    min: float
    max: float
    step: float


PARAMETER_SPECS: dict[str, ParameterSpec] = {
    "fake_threshold": ParameterSpec(
        "fake_threshold", "Classification Threshold FAKE/TRUE (θ)", "classification", "score",
        default=0.75, min=0.0, max=1.0, step=0.05,
    ),
    "tcs_very_consistent": ParameterSpec(
        "tcs_very_consistent", 'TCS Threshold "Highly Consistent"', "classification", "score",
        default=0.80, min=0.0, max=1.0, step=0.05,
    ),
    "tcs_moderate": ParameterSpec(
        "tcs_moderate", 'TCS Threshold "Moderate"', "classification", "score",
        default=0.50, min=0.0, max=1.0, step=0.05,
    ),
    "tcs_suspicious": ParameterSpec(
        "tcs_suspicious", 'TCS Threshold "Suspicious"', "classification", "score",
        default=0.20, min=0.0, max=1.0, step=0.05,
    ),
    "inverted_interval_tolerance_days": ParameterSpec(
        "inverted_interval_tolerance_days", "Inverted Interval Tolerance (V3)", "internal", "days",
        default=30, min=0, max=90, step=10,
    ),
    "max_plausible_tenure_years": ParameterSpec(
        "max_plausible_tenure_years", "Maximum Plausible Duration (V3)", "internal", "years",
        default=50, min=0, max=100, step=10,
    ),
    "absurd_duration_years": ParameterSpec(
        "absurd_duration_years", "Duration Excluded from Analysis (V3)", "internal", "years",
        default=80, min=0, max=150, step=10,
    ),
    "election_to_office_buffer_days": ParameterSpec(
        "election_to_office_buffer_days", "Election-to-Office Buffer (V5)", "internal", "days",
        default=180, min=0, max=365, step=10,
    ),
    "action_before_office_buffer_days": ParameterSpec(
        "action_before_office_buffer_days", "Action-Before-Office Buffer (V8)", "internal", "days",
        default=90, min=0, max=180, step=10,
    ),
    "text_similarity_threshold_v4": ParameterSpec(
        "text_similarity_threshold_v4", "Text Similarity Threshold (V4)", "internal", "score",
        default=0.85, min=0.0, max=1.0, step=0.05,
    ),
    "min_fact_confidence": ParameterSpec(
        "min_fact_confidence", "Minimum Fact Confidence Threshold (C2)", "internal", "score",
        default=0.30, min=0.0, max=1.0, step=0.05,
    ),
    "external_date_tolerance_days": ParameterSpec(
        "external_date_tolerance_days", "External Date Tolerance (L1, L3)", "external", "days",
        default=200, min=0, max=400, step=10,
    ),
    "canonical_event_tolerance_days": ParameterSpec(
        "canonical_event_tolerance_days", "Canonical Event Tolerance (L1)", "external", "days",
        default=100, min=0, max=200, step=10,
    ),
    "canonical_event_similarity_threshold": ParameterSpec(
        "canonical_event_similarity_threshold", "Canonical Event Lexical Similarity Threshold (L1)", "external", "score",
        default=0.75, min=0.0, max=1.0, step=0.05,
    ),
    "cross_article_similarity_threshold": ParameterSpec(
        "cross_article_similarity_threshold", "Cross-Article Similarity Threshold (L2)", "external", "score",
        default=0.80, min=0.0, max=1.0, step=0.05,
    ),
}

_param_lock = Lock()
_param_values: dict[str, float] = {key: spec.default for key, spec in PARAMETER_SPECS.items()}


def get_value(key: str) -> float:
    """Read a parameter's current value — call at point of use, not at import time."""
    return _param_values[key]


def get_parameters() -> list[dict]:
    with _param_lock:
        return [
            {
                "key": key,
                "label": spec.label,
                "group": spec.group,
                "unit": spec.unit,
                "value": _param_values[key],
                "default": spec.default,
                "min": spec.min,
                "max": spec.max,
                "step": spec.step,
            }
            for key, spec in PARAMETER_SPECS.items()
        ]


def _validate(key: str, value: float) -> None:
    if key not in PARAMETER_SPECS:
        raise ValueError(f"Unknown parameter: '{key}'.")
    spec = PARAMETER_SPECS[key]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"'{key}' must be numeric (got {type(value).__name__}).")
    if not (spec.min <= value <= spec.max):
        raise ValueError(f"'{key}' must be between {spec.min} and {spec.max} (got {value}).")
    steps = (value - spec.min) / spec.step
    if abs(steps - round(steps)) > 1e-9:
        raise ValueError(
            f"'{key}' must land on the increment grid: {spec.min} + n*{spec.step} (got {value})."
        )


def set_parameters(updates: dict[str, float]) -> None:
    """Validates every update against [min,max] and the increment grid before applying any of them."""
    for key, value in updates.items():
        _validate(key, value)
    with _param_lock:
        _param_values.update(updates)


def reset_parameters() -> None:
    with _param_lock:
        _param_values.clear()
        _param_values.update({key: spec.default for key, spec in PARAMETER_SPECS.items()})

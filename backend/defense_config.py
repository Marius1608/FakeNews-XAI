"""Switches for the security defences described in the RC report (chapter 5).

Each defence can be turned on independently so that "before" and "after" can be
measured and shown on the same code base:

  DEFENSE_CROSS_PIPELINE    5.1  cross-pipeline consistency guard + explanation check
  DEFENSE_PROMPT_HARDENING  5.1  data/instruction separation in the LLM prompts (first layer)
  DEFENSE_TRUST_TIERS       5.2  trust-tiered knowledge graph (+ strict entity match, HITL read)
  DEFENSE_TITLE_ISOLATION   5.1  the article title (free text, copied into every per-sentence
                                 prompt) is not sent to the extraction model

Shortcut: DEFENSES=all turns on every defence that is not set explicitly,
DEFENSES=none (default) leaves them off. An explicit DEFENSE_* variable wins.

Values are read at call time, never at import time, so a demo or an experiment
can flip them without restarting (see `override`).
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

FLAGS: dict[str, str] = {
    "cross_pipeline": "DEFENSE_CROSS_PIPELINE",
    "prompt_hardening": "DEFENSE_PROMPT_HARDENING",
    "trust_tiers": "DEFENSE_TRUST_TIERS",
    "title_isolation": "DEFENSE_TITLE_ISOLATION",
    "api_hardening": "DEFENSE_API_HARDENING",
}

_TRUE = {"1", "true", "yes", "on"}
_lock = threading.Lock()
_overrides: dict[str, bool] = {}


def _env_default() -> bool:
    return os.getenv("DEFENSES", "none").strip().lower() == "all"


def is_enabled(flag: str) -> bool:
    """True when the named defence is active (override > DEFENSE_* env > DEFENSES env)."""
    if flag not in FLAGS:
        raise KeyError(f"Unknown defence flag: {flag!r} (known: {sorted(FLAGS)})")
    with _lock:
        if flag in _overrides:
            return _overrides[flag]
    raw = os.getenv(FLAGS[flag])
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() in _TRUE
    return _env_default()


def snapshot() -> dict[str, bool]:
    return {flag: is_enabled(flag) for flag in FLAGS}


def set_flags(**flags: bool) -> None:
    """Persistently override flags for this process (used by the demo toggle route)."""
    with _lock:
        for flag, value in flags.items():
            if flag not in FLAGS:
                raise KeyError(f"Unknown defence flag: {flag!r}")
            _overrides[flag] = bool(value)


def clear_overrides() -> None:
    with _lock:
        _overrides.clear()


@contextmanager
def override(**flags: bool) -> Iterator[None]:
    """Temporarily set flags, e.g. `with override(cross_pipeline=True): ...`."""
    with _lock:
        previous = dict(_overrides)
        for flag, value in flags.items():
            if flag not in FLAGS:
                raise KeyError(f"Unknown defence flag: {flag!r}")
            _overrides[flag] = bool(value)
    try:
        yield
    finally:
        with _lock:
            _overrides.clear()
            _overrides.update(previous)


def all_on() -> dict[str, bool]:
    return {flag: True for flag in FLAGS}


def all_off() -> dict[str, bool]:
    return {flag: False for flag in FLAGS}

"""Safe file resolution for serving the built SPA (frontend/build)."""

from __future__ import annotations

from pathlib import Path


def safe_build_path(root: Path, requested: str) -> Path | None:
    """Resolve `requested` inside `root`; None if it escapes root or is not a file.

    The SPA catch-all receives the URL path already percent-decoded, so
    "/..%2f..%2f.env" arrives as "../../.env". Without this check the route
    served arbitrary files (path traversal, e.g. /proc/self/environ with secrets).
    """
    base = root.resolve()
    try:
        candidate = (base / requested).resolve()
    except (OSError, ValueError):
        return None
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return None
    return candidate

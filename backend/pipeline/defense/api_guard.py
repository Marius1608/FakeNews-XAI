"""5.3 API hardening (flag: DEFENSE_API_HARDENING). Targets V-01/V-07/V-08 (no auth on
state-changing routes), V-10 (SSRF through custom RSS feeds) and V-11 (unbounded input).

Everything here is pure and testable without a server or a model. With the flag off the
original behaviour is unchanged.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import socket
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException

from backend import defense_config

MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "50000"))
MAX_BATCH_ARTICLES = int(os.getenv("MAX_BATCH_ARTICLES", "20"))

# state-changing routes that need the admin key (method, path prefix)
_ADMIN = (
    ("DELETE", "/articles/"),
    ("POST", "/articles/"),          # /articles/{id}/verify
    ("PUT", "/config/"),
    ("POST", "/config/"),
    ("DELETE", "/config/"),
    ("PUT", "/defenses"),
)


def enabled() -> bool:
    return defense_config.is_enabled("api_hardening")


def is_admin_request(method: str, path: str) -> bool:
    return any(method.upper() == m and path.startswith(p) for m, p in _ADMIN)


def key_ok(presented: Optional[str]) -> bool:
    """Constant-time check. Fails closed when ADMIN_API_KEY is not configured."""
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


def require_key(presented: Optional[str]) -> None:
    if enabled() and not key_ok(presented):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key.")


def check_persist(persist: bool, presented: Optional[str]) -> None:
    """Writing to the shared knowledge graph is a privileged action (V-04)."""
    if persist:
        require_key(presented)


def check_text_size(*texts: str, n_articles: int = 1) -> None:
    if not enabled():
        return
    if n_articles > MAX_BATCH_ARTICLES:
        raise HTTPException(status_code=413, detail=f"At most {MAX_BATCH_ARTICLES} articles per batch.")
    if any(len(t) > MAX_TEXT_CHARS for t in texts):
        raise HTTPException(status_code=413, detail=f"Text longer than {MAX_TEXT_CHARS} characters.")


def _is_internal(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%")[0])
    return (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
            or a.is_multicast or a.is_unspecified)


def assert_public_feed_url(url: str) -> None:
    """Rejects feed URLs whose host is, or resolves to, an internal address (V-10)."""
    host = urlparse(url).hostname or ""
    if host.lower() in ("localhost", "localhost.localdomain") or host.endswith(".internal"):
        raise ValueError(f"Feed host '{host}' is not allowed.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_internal(host):
            raise ValueError(f"Feed host '{host}' is an internal address.")
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return  # not resolvable here; the fetch fails on its own
    for info in infos:
        if _is_internal(info[4][0]):
            raise ValueError(f"Feed host '{host}' resolves to an internal address.")

"""C3b Level 5 — RSS Stream verifier: searches for facts in recent news feeds."""

from __future__ import annotations

import logging
import time
import urllib.request
from typing import Optional

import feedparser

from backend.pipeline.graph.models import RelationType, TemporalFact
from backend.runtime_settings import feed_name, get_effective_feed_urls

logger = logging.getLogger(__name__)

RELATION_KEYWORDS: dict[RelationType, list[str]] = {
    RelationType.HOLDS_POSITION: ["president", "senator", "governor", "minister", "appointed", "elected"],
    RelationType.MEMBER_OF: ["member", "joined", "party", "coalition"],
    RelationType.OCCURRED_ON: ["signed", "passed", "announced", "held"],
}

_CACHE_TTL_SECONDS = 30 * 60


class RSSVerifier:
    """Searches for facts in recent RSS news feeds (C3b Level 5)."""

    def __init__(self, feeds: list[str] = None):
        # None -> read the effective (predefined enabled + custom) list from
        # runtime_settings on every call, so UI changes take effect immediately.
        # An explicit list locks the instance to that list (used by callers that
        # want a fixed feed set regardless of runtime config).
        self._feeds: Optional[list[str]] = feeds
        self._cache: dict[str, list[dict]] = {}
        self._cache_ts: dict[str, float] = {}

    def _effective_feeds(self) -> list[str]:
        return self._feeds if self._feeds is not None else get_effective_feed_urls()

    def is_available(self) -> bool:
        """Tries the first feed — returns True if it responds within 5s."""
        feeds = self._effective_feeds()
        if not feeds:
            return False
        try:
            with urllib.request.urlopen(feeds[0], timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def fetch_feed(self, url: str) -> list[dict]:
        """Downloads an RSS/Atom feed and parses it with feedparser; returns the list of articles.

        Fetches raw bytes via urllib (bounded by a 10s timeout) rather than
        handing the URL directly to feedparser.parse(), since feedparser has no
        built-in per-request timeout and could otherwise hang indefinitely on an
        unresponsive feed.
        """
        with urllib.request.urlopen(url, timeout=10) as resp:
            content = resp.read()
        parsed = feedparser.parse(content)
        if parsed.bozo:
            logger.debug(f"RSS feed parsed with warnings ({url}): {parsed.get('bozo_exception')}")
        items = []
        for entry in parsed.entries:
            title = entry.get("title", "")
            description = entry.get("summary", "") or entry.get("description", "")
            pub_date = entry.get("published", "") or entry.get("updated", "")
            link = entry.get("link", "")
            items.append({
                "title": title,
                "description": description,
                "pub_date": pub_date,
                "link": link,
                "text": f"{title} {description}",
            })
        return items

    def _get_feed_cached(self, url: str) -> list[dict]:
        """Returns cached articles if still valid (< 30 min), otherwise fetches fresh."""
        now = time.monotonic()
        if url in self._cache and now - self._cache_ts.get(url, 0) < _CACHE_TTL_SECONDS:
            return self._cache[url]
        try:
            items = self.fetch_feed(url)
            self._cache[url] = items
            self._cache_ts[url] = now
            return items
        except Exception as e:
            logger.warning(f"RSS feed unreachable ({url}): {e}")
            return []

    def search_fact(
        self,
        subject: str,
        relation: str,
        obj: str,
        date_hint: str = None,
    ) -> list[dict]:
        """Searches all feeds for relevant articles; score >= 3 required to be returned."""
        relation_enum: Optional[RelationType] = None
        try:
            relation_enum = RelationType(relation)
        except ValueError:
            pass

        keywords = RELATION_KEYWORDS.get(relation_enum, []) if relation_enum else []
        subj_lower = subject.lower()
        obj_lower = obj.lower()

        scored: list[tuple[int, dict]] = []

        for url in self._effective_feeds():
            items = self._get_feed_cached(url)
            for item in items:
                text_lower = item['text'].lower()
                score = 0
                if subj_lower in text_lower:
                    score += 2
                if obj_lower in text_lower:
                    score += 2
                for kw in keywords:
                    if kw in text_lower:
                        score += 1
                        break
                if score >= 3:
                    scored.append((score, {**item, 'feed_url': url}))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

    def verify_fact(self, fact: TemporalFact) -> Optional[dict]:
        """Verifies a fact against RSS feeds; returns a dict or None."""
        if not fact.subject or not fact.object:
            return None

        results = self.search_fact(
            subject=fact.subject.text,
            relation=fact.predicate.value,
            obj=fact.object.text,
        )

        if not results:
            return None

        best = results[0]
        feed_url = best.get('feed_url', '')
        headline = best['title'][:200] if best['title'] else best['description'][:200]
        return {
            "found": True,
            "feed_name": feed_name(feed_url),
            "feed_url": feed_url,
            "matched_entity": fact.subject.text,
            "headline": headline,
            "verified": True,
            "timestamp": best.get('pub_date', ''),
        }

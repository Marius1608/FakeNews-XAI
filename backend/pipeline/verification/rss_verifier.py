"""C3b Level 5 — RSS Stream verifier: searches for facts in recent news feeds."""

from __future__ import annotations

import logging
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional

from backend.pipeline.graph.models import RelationType, TemporalFact

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
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


def _feed_name(url: str) -> str:
    return FEED_NAMES.get(url, url.split("/")[2] if "/" in url else url)

RELATION_KEYWORDS: dict[RelationType, list[str]] = {
    RelationType.HOLDS_POSITION: ["president", "senator", "governor", "minister", "appointed", "elected"],
    RelationType.MEMBER_OF: ["member", "joined", "party", "coalition"],
    RelationType.OCCURRED_ON: ["signed", "passed", "announced", "held"],
}

_CACHE_TTL_SECONDS = 30 * 60


class RSSVerifier:
    """Searches for facts in recent RSS news feeds (C3b Level 5)."""

    def __init__(self, feeds: list[str] = None):
        self._feeds: list[str] = feeds if feeds is not None else DEFAULT_FEEDS
        self._cache: dict[str, list[dict]] = {}
        self._cache_ts: dict[str, float] = {}

    def is_available(self) -> bool:
        """Tries the first feed — returns True if it responds within 5s."""
        if not self._feeds:
            return False
        try:
            with urllib.request.urlopen(self._feeds[0], timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def fetch_feed(self, url: str) -> list[dict]:
        """Downloads and parses an RSS feed; returns the list of articles."""
        with urllib.request.urlopen(url, timeout=10) as resp:
            content = resp.read()
        tree = ET.fromstring(content)
        items = []
        for item in tree.findall('.//item'):
            title = item.findtext('title', '')
            description = item.findtext('description', '')
            pub_date = item.findtext('pubDate', '')
            link = item.findtext('link', '')
            items.append({
                'title': title,
                'description': description,
                'pub_date': pub_date,
                'link': link,
                'text': f"{title} {description}",
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
        except ET.ParseError as e:
            logger.warning(f"RSS malformed XML ({url}): {e}")
            return []
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

        for url in self._feeds:
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
            "feed_name": _feed_name(feed_url),
            "feed_url": feed_url,
            "matched_entity": fact.subject.text,
            "headline": headline,
            "verified": True,
            "timestamp": best.get('pub_date', ''),
        }

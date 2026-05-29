"""C3b Nivel 5 — RSS Stream verifier: caută fapte în feed-uri de știri recente."""

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
    "https://feeds.reuters.com/Reuters/PoliticsNews",
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "https://feeds.npr.org/1014/rss.xml",
]

RELATION_KEYWORDS: dict[RelationType, list[str]] = {
    RelationType.HOLDS_POSITION: ["president", "senator", "governor", "minister", "appointed", "elected"],
    RelationType.MEMBER_OF: ["member", "joined", "party", "coalition"],
    RelationType.OCCURRED_ON: ["signed", "passed", "announced", "held"],
}

_CACHE_TTL_SECONDS = 30 * 60


class RSSVerifier:
    """Caută fapte în feed-uri RSS de știri recente (C3b Nivel 5)."""

    def __init__(self, feeds: list[str] = None):
        self._feeds: list[str] = feeds if feeds is not None else DEFAULT_FEEDS
        self._cache: dict[str, list[dict]] = {}
        self._cache_ts: dict[str, float] = {}

    def is_available(self) -> bool:
        """Încearcă primul feed — returnează True dacă răspunde în 5s."""
        if not self._feeds:
            return False
        try:
            with urllib.request.urlopen(self._feeds[0], timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def fetch_feed(self, url: str) -> list[dict]:
        """Descarcă și parsează un feed RSS; returnează lista de articole."""
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
        """Returnează cache dacă e valid (< 30 min), altfel fetch nou."""
        now = time.monotonic()
        if url in self._cache and now - self._cache_ts.get(url, 0) < _CACHE_TTL_SECONDS:
            return self._cache[url]
        try:
            items = self.fetch_feed(url)
            self._cache[url] = items
            self._cache_ts[url] = now
            return items
        except ET.ParseError as e:
            logger.warning(f"RSS XML malformat ({url}): {e}")
            return []
        except Exception as e:
            logger.warning(f"RSS feed inaccesibil ({url}): {e}")
            return []

    def search_fact(
        self,
        subject: str,
        relation: str,
        obj: str,
        date_hint: str = None,
    ) -> list[dict]:
        """Caută în toate feed-urile articole relevante; scor ≥ 3 pentru a fi returnat."""
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
        """Verifică un fapt în feed-urile RSS; returnează dict sau None."""
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
        snippet = best['title'][:120] if best['title'] else best['description'][:120]
        return {
            "found": True,
            "source": best.get('feed_url', ''),
            "snippet": snippet,
            "link": best.get('link', ''),
        }

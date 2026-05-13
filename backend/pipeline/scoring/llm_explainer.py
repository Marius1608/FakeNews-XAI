"""XAI — Explicatii in limbaj natural generate de LLM (llama3 via Ollama)."""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from backend.config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS
from backend.pipeline.graph.models import TCSResult, TemporalFact

logger = logging.getLogger(__name__)

# // section prompt

EXPLANATION_SYSTEM_PROMPT = """You are an expert fact-checker explaining the results of a temporal consistency analysis on a news article.

Given:
- A TCS (Temporal Coherence Score) between 0.0 and 1.0, where 1.0 = fully consistent and 0.0 = highly inconsistent
- A list of temporal facts extracted from the article
- A list of detected inconsistencies (if any)
- The article's metadata

Your task: write a clear, concise explanation (3-5 sentences) in English that:
1. States the overall assessment (consistent, suspicious, or unreliable)
2. Highlights the MOST IMPORTANT inconsistencies found (if any), with specific dates/entities
3. Mentions what was verified and how (internal logic, Wikidata, cross-article)
4. Gives actionable insight: should the reader trust this article's timeline?

Do NOT use bullet points. Write flowing prose. Be specific — mention actual entities and dates from the analysis.
If no inconsistencies were found, explain WHY the article appears consistent.

Respond with ONLY the explanation text. No preamble, no markdown."""


class LLMExplainer:
    """Genereaza explicatii XAI folosind llama3 via Ollama."""

    def __init__(self, model: str = None, host: str = None, timeout: int = None):
        self._model = model or OLLAMA_MODEL
        self._host = host or OLLAMA_HOST
        self._timeout = timeout or OLLAMA_TIMEOUT_SECONDS

    def is_available(self) -> bool:
        """Verifica daca Ollama e accesibil."""
        try:
            r = requests.get(f"{self._host}/api/tags", timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def explain(self, result: TCSResult, article_text: str = "", article_title: str = "") -> Optional[str]:
        """Genereaza explicatie XAI pe baza rezultatului TCS.

        Returneaza string cu explicatia sau None daca Ollama nu e disponibil.
        """
        context = self._build_context(result, article_text, article_title)

        try:
            response = requests.post(
                f"{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
                        {"role": "user", "content": context},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 300},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            explanation = data.get("message", {}).get("content", "").strip()

            if not explanation:
                logger.warning("LLMExplainer: raspuns gol de la Ollama")
                return None

            logger.info(f"LLMExplainer: explicatie generata ({len(explanation)} chars)")
            logger.debug(f"LLMExplainer response: {explanation[:200]}...")
            return explanation

        except requests.RequestException as e:
            logger.error(f"LLMExplainer: eroare Ollama — {e}")
            return None
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"LLMExplainer: eroare parsare raspuns — {e}")
            return None

    # // section context

    def _build_context(self, result: TCSResult, article_text: str, article_title: str) -> str:
        """Construieste contextul pentru prompt-ul de explicatie."""
        parts = []

        parts.append(f"Article title: {article_title or 'Unknown'}")
        parts.append(f"TCS Score: {result.score:.3f} (label: {result.label})")
        parts.append(f"Temporal claims extracted: {result.n_temporal_claims}")
        parts.append(f"Inconsistencies detected: {result.n_inconsistencies}")
        parts.append(f"Pipeline: {result.pipeline_variant}")
        parts.append(f"Coherence factor: {result.coherence_factor:.3f}")

        if result.facts:
            parts.append("\nExtracted temporal facts:")
            for i, fact in enumerate(result.facts[:10]):
                time_str = _format_fact_time(fact)
                parts.append(f"  {i+1}. {fact.subject.text} — {fact.predicate.value} → {fact.object.text} {time_str}")

        if result.inconsistencies:
            parts.append("\nDetected inconsistencies:")
            for i, inc in enumerate(result.inconsistencies):
                parts.append(f"  {i+1}. [{inc.severity.value}] {inc.inconsistency_type.value}: {inc.description}")
                if inc.evidence:
                    parts.append(f"     Evidence: {inc.evidence}")
        else:
            parts.append("\nNo inconsistencies detected.")

        if article_text:
            parts.append(f"\nArticle excerpt: {article_text[:500]}...")

        return "\n".join(parts)


def _format_fact_time(fact: TemporalFact) -> str:
    """Formateaza timpul unui fapt pentru context."""
    if fact.time_point and fact.time_point.date_string:
        return f"@{fact.time_point.date_string}"
    parts = []
    if fact.time_start and fact.time_start.date_string:
        parts.append(fact.time_start.date_string)
    if fact.time_end and fact.time_end.date_string:
        parts.append(fact.time_end.date_string)
    return f"[{' → '.join(parts)}]" if parts else ""

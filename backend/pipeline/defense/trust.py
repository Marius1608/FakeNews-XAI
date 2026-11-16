"""5.2 Trust-tiered knowledge graph.

Problem (V-04, V-05, V-06): every persisted fact is trusted as a reference for later
articles, the human verdict is stored but never read, and entities are matched by
substring in both directions, so a poisoned fact can reach many targets.

Defence: every stored fact carries a trust tier derived from PROVENANCE, and the
cross-article check uses the tier:

    TIER_REJECTED    -1  fact of an article judged FAKE (by the system at write time or by a human)
    TIER_UNVERIFIED   0  not confirmed by any independent source (default for user submissions)
    TIER_HUMAN        1  confirmed by a human reviewer (HITL verdict "true")
    TIER_EXTERNAL     2  matched an independent source at write time (Reference KG / Wikidata)

    * rejected facts are never used as reference;
    * a conflict against an UNVERIFIED stored fact can raise at most a LOW signal
      (weight 0 in TCS): unconfirmed user content cannot move a verdict;
    * conflicts against HUMAN/EXTERNAL facts keep their original severity;
    * when >= BURST_THRESHOLD distinct unverified articles contradict the same fact,
      the signal is annotated as a possible poisoning burst (anomaly detection);
    * entity retrieval uses word-boundary matching with a minimum length instead of
      raw substring matching (`names_match_strict`, mirrored in Cypher).

Tiers are always WRITTEN (cheap provenance data); they are only READ when
DEFENSE_TRUST_TIERS is on, so the "before" measurement is unchanged.
"""

from __future__ import annotations

from typing import Iterable, Optional

from backend.pipeline.graph.models import Inconsistency, Severity, TemporalFact

TIER_REJECTED = -1
TIER_UNVERIFIED = 0
TIER_HUMAN = 1
TIER_EXTERNAL = 2

BURST_THRESHOLD = 2
MIN_NAME_LEN = 4


def fact_key(f: TemporalFact) -> tuple:
    """Identity of a fact independent of object identity (survives copies)."""
    return (
        (f.subject.text or "").lower().strip(),
        f.predicate.value,
        (f.object.text or "").lower().strip(),
        f.source_sentence_idx,
    )


def assign_tiers(
    facts: Iterable[TemporalFact],
    externally_verified: Iterable[TemporalFact],
    article_flagged_fake: bool,
) -> None:
    """Set `trust_tier` on each fact before it is persisted (provenance at write time)."""
    verified = {fact_key(f) for f in externally_verified}
    for f in facts:
        if article_flagged_fake:
            tier = TIER_REJECTED
        elif fact_key(f) in verified:
            tier = TIER_EXTERNAL
        else:
            tier = TIER_UNVERIFIED
        f.trust_tier = tier  # type: ignore[attr-defined]


def effective_tier(stored: TemporalFact) -> int:
    """Tier of a stored fact after applying the human verdict of its article."""
    tier = getattr(stored, "trust_tier", TIER_UNVERIFIED)
    verdict = getattr(stored, "human_verdict", None)
    if verdict == "fake":
        return TIER_REJECTED
    if verdict == "true":
        return max(tier, TIER_HUMAN)
    return tier


def is_usable_reference(stored: TemporalFact) -> bool:
    return effective_tier(stored) >= TIER_UNVERIFIED


def apply_tier(inc: Inconsistency, stored: TemporalFact) -> Inconsistency:
    """Cap the severity of a conflict whose stored side is unverified."""
    if effective_tier(stored) >= TIER_HUMAN:
        return inc
    inc.severity = Severity.LOW
    inc.description = "[unverified stored fact] " + inc.description
    return inc


def burst_note(unverified_article_ids: set) -> Optional[str]:
    ids = {a for a in unverified_article_ids if a}
    if len(ids) >= BURST_THRESHOLD:
        return (f"possible poisoning burst: {len(ids)} distinct unverified articles "
                f"contradict this fact")
    return None


def names_match_strict(a: str, b: str, min_len: int = MIN_NAME_LEN) -> bool:
    """Word-boundary entity match; mirrors the Cypher in Neo4jTKGStore.

    exact equality, or one name occurs in the other as whole words, and the shorter
    name has at least `min_len` characters ("jackson" matches "ketanji brown jackson";
    "us" or "mr" match nothing, "obam" does not match "obama").
    """
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return False
    if a == b:
        return True
    pa, pb = f" {a} ", f" {b} "
    if len(a) >= min_len and pa in pb:
        return True
    if len(b) >= min_len and pb in pa:
        return True
    return False

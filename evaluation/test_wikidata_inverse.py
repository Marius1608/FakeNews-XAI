"""Test script pentru Wikidata invers.

Ideea: in loc sa verificam "faptul din articol exista in Wikidata?",
descarcam TOATE faptele temporale ale entitatii din Wikidata
si comparam cu ce zice articolul.

Rulare:
  python evaluation/test_wikidata_inverse.py

Output: afiseaza faptele Wikidata pentru entitatile testate
si compara cu faptele din articol.
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from datetime import datetime

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from backend.pipeline.verification.wikidata import WikidataClient


# ─────────────────────────────────────────────────────────────────────────────
# Entitati de test (QID-uri cunoscute)
# ─────────────────────────────────────────────────────────────────────────────
TEST_ENTITIES = [
    ("Barack Obama",   "Q76"),
    ("Donald Trump",   "Q22686"),
    ("Joe Biden",      "Q6279"),
    ("Bill Clinton",   "Q1124"),
    ("George W. Bush", "Q207"),
]

# Fapte din articolele FAKE pe care vrem sa le detectam
# Format: (entitate, pozitie_falsa_sau_data_falsa, an_fals)
KNOWN_FAKE_FACTS = [
    ("Barack Obama",   "Illinois Governor", None),       # a fost Senator, nu Governor
    ("Joe Biden",      "U.S. Senator",      2013),       # era VP din 2009
    ("Bill Clinton",   "President",         2004),       # presedintie terminata in 2001
    ("Donald Trump",   "President",         2017),       # inaugurat 2017, nu 2021
]


def fetch_all_temporal_facts(client: WikidataClient, entity_name: str, qid: str) -> list:
    """Descarca toate faptele temporale pentru o entitate."""
    print(f"\n{'='*60}")
    print(f"  {entity_name} ({qid})")
    print(f"{'='*60}")

    # P39 = position held (pozitii detinute)
    facts_p39 = client.get_temporal_facts(qid, relation_properties=["P39"])
    # P463 = member of (membru in)
    facts_p463 = client.get_temporal_facts(qid, relation_properties=["P463"])

    all_facts = facts_p39 + facts_p463

    if not all_facts:
        print("  [!] Niciun fapt temporal gasit.")
        return []

    print(f"  {len(all_facts)} fapte temporale:\n")
    for f in all_facts:
        time_str = ""
        if f.time_start and f.time_end:
            time_str = f"[{f.time_start.year} → {f.time_end.year}]"
        elif f.time_start:
            time_str = f"[{f.time_start.year} → ?]"
        elif f.time_point:
            time_str = f"@{f.time_point.year}"
        print(f"    {f.property_id}: {f.value_label:<40} {time_str}")

    return all_facts


def check_fake_fact(all_facts: dict, entity_name: str, position: str, year: int | None):
    """
    Verifica daca o afirmatie falsa poate fi detectata comparand cu faptele Wikidata.
    Strategia inversa: daca Wikidata nu confirma pozitia/perioada, e suspect.
    """
    print(f"\n  [CHECK] '{entity_name}' — '{position}'" + (f" in {year}" if year else ""))

    facts = all_facts.get(entity_name, [])
    if not facts:
        print("    -> Niciun fapt disponibil pentru comparatie.")
        return

    # Cauta confirmarea in Wikidata
    position_lower = position.lower()
    confirmed = False
    conflict = False

    for f in facts:
        label_lower = f.value_label.lower()

        # Match fuzzy pe pozitie
        if any(word in label_lower for word in position_lower.split()):
            # Verifica perioada daca e specificat un an
            if year:
                start_y = f.time_start.year if f.time_start else None
                end_y = f.time_end.year if f.time_end else (datetime.now().year)
                if start_y and end_y:
                    if start_y <= year <= end_y:
                        confirmed = True
                        print(f"    -> CONFIRMAT de Wikidata: {f.value_label} [{start_y}-{end_y}]")
                    else:
                        conflict = True
                        print(f"    -> CONFLICT cu Wikidata: {f.value_label} [{start_y}-{end_y}], articol zice {year}")
            else:
                confirmed = True
                print(f"    -> CONFIRMAT de Wikidata: {f.value_label}")

    if not confirmed and not conflict:
        print(f"    -> NEGASIT in Wikidata: '{position}' — posibil fapt fabricat")
    elif conflict:
        print(f"    -> DETECTAT: data inconsistenta fata de Wikidata!")


def main():
    client = WikidataClient()

    print("\n" + "="*60)
    print("  WIKIDATA INVERS — Test Script")
    print("  Descarca TOATE faptele entitatii si compara cu articolul")
    print("="*60)

    # Pasul 1: Descarca toate faptele pentru entitatile de test
    all_facts: dict[str, list] = {}
    for entity_name, qid in TEST_ENTITIES:
        facts = fetch_all_temporal_facts(client, entity_name, qid)
        all_facts[entity_name] = facts

    # Pasul 2: Verifica faptele false din articole
    print("\n\n" + "="*60)
    print("  VERIFICARE FAPTE FALSE DIN ARTICOLE")
    print("="*60)

    for entity_name, position, year in KNOWN_FAKE_FACTS:
        check_fake_fact(all_facts, entity_name, position, year)

    # Pasul 3: Rezumat
    print("\n\n" + "="*60)
    print("  CONCLUZIE")
    print("="*60)
    print("""
  Wikidata invers functioneaza daca:
  1. Entitatea e gasita in Wikidata (QID rezolvat)
  2. Proprietatea relevanta (P39, P463) are date temporale
  3. Comparatia an/pozitie detecteaza discrepanta

  Pasul urmator pentru integrare:
  - In ExternalVerifier: dupa cautarea QID-ului, descarca TOATE
    faptele P39 ale entitatii, nu doar cele care match cu relatia
    din articol
  - Compara fiecare fapt din articol cu intervalele Wikidata
  - Daca nu exista confirmare → inconsistenta potential
    """)


if __name__ == "__main__":
    main()

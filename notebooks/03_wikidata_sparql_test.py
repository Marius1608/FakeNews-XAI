"""
03 — Test SPARQL: verificare query-uri Wikidata pe entitati cunoscute.

Testeaza WikidataClient pe cazuri cu raspuns cunoscut:
  - Obama: President 2009-2017 (P39)
  - Trump: President 2017-2021 (P39)
  - Merkel: Chancellor 2005-2021 (P39)

Ruleaza: python notebooks/03_wikidata_sparql_test.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.pipeline.verification.wikidata import WikidataClient, WikidataFact

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cazuri de test cu raspuns cunoscut
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "entity": "Barack Obama",
        "description": "President of the United States, 2009-2017",
        "properties": ["P39"],
        "expected_years": (2009, 2017),
    },
    {
        "entity": "Donald Trump",
        "description": "President of the United States, 2017-2021",
        "properties": ["P39"],
        "expected_years": (2017, 2021),
    },
    {
        "entity": "Angela Merkel",
        "description": "Chancellor of Germany, 2005-2021",
        "properties": ["P39"],
        "expected_years": (2005, 2021),
    },
]


def run_test(client: WikidataClient, tc: dict) -> bool:
    """Ruleaza un singur test case. Returneaza True daca trece."""
    entity = tc["entity"]
    props = tc["properties"]
    start_year, end_year = tc["expected_years"]

    print(f"\n{'─'*60}")
    print(f"Test: {entity} — {tc['description']}")

    # Cautare QID
    qid = client.search_entity(entity)
    if not qid:
        print(f"  ✗ Nu s-a gasit pe Wikidata")
        return False
    print(f"  QID: {qid}")

    # Query filtrat pe proprietati specifice
    facts = client.get_temporal_facts(qid, relation_properties=props)
    print(f"  Fapte gasite: {len(facts)}")

    if not facts:
        print(f"  ✗ Niciun fapt {props} cu date temporale")
        return False

    # Afiseaza rezultate
    for f in facts:
        start_str = f.time_start.strftime('%Y-%m-%d') if f.time_start else "—"
        end_str = f.time_end.strftime('%Y-%m-%d') if f.time_end else "—"
        point_str = f.time_point.strftime('%Y-%m-%d') if f.time_point else "—"
        print(f"    • {f.value_label}  [{start_str} → {end_str}]  point: {point_str}")

    # Verifica anii asteptati
    found_start = False
    found_end = False

    for f in facts:
        f_start = f.time_start.year if f.time_start else None
        f_end = f.time_end.year if f.time_end else None
        f_point = f.time_point.year if f.time_point else None

        if start_year and (f_start == start_year or f_point == start_year):
            found_start = True
        if end_year and (f_end == end_year or f_point == end_year):
            found_end = True

    if found_start:
        print(f"  ✓ Start year {start_year} confirmat")
    else:
        print(f"  ⚠ Start year {start_year} negasit")

    if end_year:
        if found_end:
            print(f"  ✓ End year {end_year} confirmat")
        else:
            print(f"  ⚠ End year {end_year} negasit")

    return found_start or found_end


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Test SPARQL — Wikidata Temporal Properties")
    print("=" * 60)

    client = WikidataClient()

    # Verificare conectivitate
    print("\nVerificare conectivitate Wikidata...")
    try:
        test_qid = client.search_entity("Barack Obama")
        if test_qid:
            print(f"  ✓ Conexiune OK (Obama = {test_qid})")
        else:
            print("  ✗ Cautarea nu returneaza rezultate")
            return
    except Exception as e:
        print(f"  ✗ Eroare conexiune: {e}")
        return

    # Test rapid — afiseaza query-ul generat
    print("\nQuery SPARQL generat (Obama P39):")
    test_query = client._build_temporal_query(test_qid, ["P39"])
    print(test_query)

    # Ruleaza teste
    passed = 0
    total = len(TEST_CASES)

    for tc in TEST_CASES:
        ok = run_test(client, tc)
        if ok:
            passed += 1

    # Test suplimentar: query general (fara filtru proprietati)
    print(f"\n{'─'*60}")
    print("Test suplimentar: Obama — toate proprietatile temporale")
    all_facts = client.get_temporal_facts(test_qid)
    print(f"  Total fapte cu date: {len(all_facts)}")
    props_found = set(f.property_id for f in all_facts)
    print(f"  Proprietati distincte: {sorted(props_found)}")

    # Sumar
    print(f"\n{'='*60}")
    print(f"Rezultat: {passed}/{total} teste trecute")
    if passed == total:
        print("✓ Toate query-urile SPARQL functioneaza corect!")
    elif passed > 0:
        print("⚠ Unele teste au trecut.")
    else:
        print("✗ Niciun test trecut.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
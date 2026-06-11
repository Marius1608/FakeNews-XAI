"""Adaugă entități noi în verified_events.json fără să șteargă cele existente.

Rulare:
    python scripts/update_reference_kg.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update_reference_kg")

OUTPUT_FILE = _PROJECT_ROOT / "data" / "reference_kg" / "verified_events.json"
QUERY_DELAY = 1.5

NEW_ENTITIES = [
    # UK Politicians
    {"name": "Keir Starmer",          "qid": "Q23497151", "category": "uk_politician"},
    {"name": "Tony Blair",            "qid": "Q9682",     "category": "uk_politician"},
    {"name": "Rishi Sunak",           "qid": "Q63455796", "category": "uk_politician"},
    {"name": "Boris Johnson",         "qid": "Q327407",   "category": "uk_politician"},
    {"name": "Theresa May",           "qid": "Q264766",   "category": "uk_politician"},
    {"name": "Gordon Brown",          "qid": "Q3936",     "category": "uk_politician"},
    {"name": "Wes Streeting",         "qid": "Q7983907",  "category": "uk_politician"},
    {"name": "Andy Burnham",          "qid": "Q4759326",  "category": "uk_politician"},
    {"name": "Nicola Sturgeon",       "qid": "Q329938",   "category": "uk_politician"},
    {"name": "Margaret Thatcher",     "qid": "Q7837",     "category": "uk_politician"},
    # EU Politicians
    {"name": "Donald Tusk",           "qid": "Q946",      "category": "eu_politician"},
    {"name": "Emmanuel Macron",       "qid": "Q3052772",  "category": "eu_politician"},
    {"name": "Olaf Scholz",           "qid": "Q61053",    "category": "eu_politician"},
    {"name": "Ursula von der Leyen",  "qid": "Q21023677", "category": "eu_politician"},
    # US Politicians
    {"name": "Ken Paxton",            "qid": "Q7383626",  "category": "us_politician"},
    # US Presidents — historical
    {"name": "Richard Nixon",         "qid": "Q9588",     "category": "us_president"},
    {"name": "Gerald Ford",           "qid": "Q9582",     "category": "us_president"},
    {"name": "Lyndon B. Johnson",     "qid": "Q9597",     "category": "us_president"},
    {"name": "Dwight Eisenhower",     "qid": "Q9586",     "category": "us_president"},
    {"name": "John F. Kennedy",       "qid": "Q9574",     "category": "us_president"},
    {"name": "Harry Truman",          "qid": "Q9583",     "category": "us_president"},
]


def _wikidata_facts_to_entries(name: str, qid: str, wikidata_facts: list) -> list[dict]:
    """Convertește WikidataFact-uri în formatul reference KG, filtrând datele eronate."""
    result = []
    for wf in wikidata_facts:
        start_year = wf.time_start.year if wf.time_start else None

        # Fix P569: filtrează faptele cu date eronate din Wikidata
        if start_year is not None and start_year < 1900:
            logger.debug(f"  skip '{wf.value_label}' — start_year={start_year} < 1900")
            continue

        entry: dict = {
            "entity":    name,
            "entity_id": qid,
            "position":  wf.value_label,
            "property":  wf.property_id,
        }
        if wf.time_start:
            entry["start_year"] = wf.time_start.year
            entry["start_date"] = wf.time_start.strftime("%Y-%m-%d")
        if wf.time_end:
            entry["end_year"] = wf.time_end.year
            entry["end_date"] = wf.time_end.strftime("%Y-%m-%d")
        if wf.time_point:
            entry["point_year"] = wf.time_point.year
            entry["point_date"] = wf.time_point.strftime("%Y-%m-%d")
        result.append(entry)
    return result


def fetch_facts(name: str, qid: str) -> tuple[list[dict], str]:
    """Fetch P39 + P463 din Wikidata. Returnează (fapte, qid_folosit).

    Dacă QID-ul dat returnează 0 fapte, încearcă automat search_entity_full(name)
    și folosește primul rezultat cu QID diferit.
    """
    from backend.pipeline.verification.wikidata import WikidataClient

    client = WikidataClient()
    raw_facts = client.get_temporal_facts(qid, relation_properties=["P39", "P463"])

    if not raw_facts:
        logger.warning(f"  0 fapte pentru {name} ({qid}) — încearcă search_entity_full")
        time.sleep(QUERY_DELAY)

        search_results = client.search_entity_full(name)
        if search_results:
            candidate = search_results[0]
            candidate_qid = candidate["id"]
            candidate_label = candidate.get("label", "")
            candidate_desc = candidate.get("description", "")

            if candidate_qid != qid:
                logger.info(
                    f"  QID corectat: {qid} -> {candidate_qid} "
                    f"({candidate_label} — {candidate_desc})"
                )
                time.sleep(QUERY_DELAY)
                raw_facts = client.get_temporal_facts(
                    candidate_qid, relation_properties=["P39", "P463"]
                )
                if raw_facts:
                    qid = candidate_qid
                    logger.info(f"  -> {len(raw_facts)} fapte cu QID corectat")
                else:
                    logger.warning(f"  QID corectat {candidate_qid} returnează tot 0 fapte")
            else:
                logger.warning(f"  search_entity_full a returnat același QID {qid} — 0 fapte finale")
        else:
            logger.warning(f"  search_entity_full nu a găsit rezultate pentru '{name}'")

    facts = _wikidata_facts_to_entries(name, qid, raw_facts)
    return facts, qid


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--refetch-empty",
        action="store_true",
        help="Re-fetch fapte pentru entitati cu 0 fapte in KG",
    )
    args = parser.parse_args()

    # 1. Încarcă KG-ul existent
    if not OUTPUT_FILE.exists():
        logger.error(f"Fisierul {OUTPUT_FILE} nu exista. Ruleaza build_reference_kg.py intai.")
        sys.exit(1)

    with open(OUTPUT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    entities: list[dict] = data.get("entities", [])

    # 2. Index după nume (case-insensitive)
    existing_names = {e["name"].lower() for e in entities}

    print(f"\nKG existent: {len(entities)} entitati, {data.get('total_facts', '?')} fapte")

    # Modul --refetch-empty: re-fetch entitati cu 0 fapte
    if args.refetch_empty:
        empty = [e for e in entities if len(e.get("facts", [])) == 0]
        print(f"Entitati cu 0 fapte: {len(empty)}\n")

        updated_count = 0
        updated_facts = 0

        for entity in empty:
            name = entity["name"]
            qid = entity["qid"]
            logger.info(f"  Refetch: {name} ({qid})")
            try:
                facts, used_qid = fetch_facts(name, qid)
            except Exception as e:
                logger.warning(f"  EROARE la {name}: {e}")
                time.sleep(QUERY_DELAY)
                continue

            if facts:
                entity["facts"] = facts
                entity["qid"] = used_qid
                entity["fetched_at"] = datetime.now().isoformat()
                updated_count += 1
                updated_facts += len(facts)
                logger.info(f"  UPDATED: {name} -> {len(facts)} fapte noi")
            else:
                logger.info(f"  NO DATA: {name} — 0 fapte si dupa retry")

            time.sleep(QUERY_DELAY)

        total_facts = sum(len(e.get("facts", [])) for e in entities)
        data["entities"] = entities
        data["total_entities"] = len(entities)
        data["total_facts"] = total_facts
        data["generated_at"] = datetime.now().isoformat()

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\nRezultat --refetch-empty:")
        print(f"  Entitati actualizate  : {updated_count} / {len(empty)}")
        print(f"  Fapte noi total       : {updated_facts}")
        print(f"  Total fapte in KG     : {total_facts}")
        print(f"  Salvat in             : {OUTPUT_FILE}\n")
        return

    print(f"Entitati noi de procesat: {len(NEW_ENTITIES)}\n")

    added_entities = 0
    added_facts = 0
    skipped = 0

    # 3. Adaugă entitățile noi
    for entity in NEW_ENTITIES:
        name = entity["name"]
        qid = entity["qid"]
        category = entity["category"]

        if name.lower() in existing_names:
            logger.info(f"  SKIP (exista deja): {name}")
            skipped += 1
            continue

        logger.info(f"  Fetch: {name} ({qid}) [{category}]")
        try:
            facts, used_qid = fetch_facts(name, qid)
        except Exception as e:
            logger.warning(f"  EROARE la {name}: {e}")
            continue

        if used_qid != qid:
            logger.info(f"  QID salvat in KG: {used_qid} (corectat de la {qid})")

        entities.append({
            "name":       name,
            "qid":        used_qid,
            "category":   category,
            "facts":      facts,
            "fetched_at": datetime.now().isoformat(),
        })
        existing_names.add(name.lower())
        added_entities += 1
        added_facts += len(facts)
        logger.info(f"  -> {len(facts)} fapte adaugate pentru {name}")

        time.sleep(QUERY_DELAY)

    # 4. Actualizează metadatele
    total_facts = sum(len(e.get("facts", [])) for e in entities)
    data["entities"] = entities
    data["total_entities"] = len(entities)
    data["total_facts"] = total_facts
    data["generated_at"] = datetime.now().isoformat()

    # 5. Salvează
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nRezultat:")
    print(f"  Entitati noi adaugate : {added_entities}")
    print(f"  Fapte noi adaugate    : {added_facts}")
    print(f"  Sarite (deja exista)  : {skipped}")
    print(f"  Total entitati in KG  : {len(entities)}")
    print(f"  Total fapte in KG     : {total_facts}")
    print(f"  Salvat in             : {OUTPUT_FILE}\n")


if __name__ == "__main__":
    main()

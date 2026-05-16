"""Build Extended Reference KG from Wikidata.

Downloads temporal facts (positions held, P39) for the top ~200 most notable
politicians and saves them to data/reference_kg/verified_events.json,
replacing or extending the existing 16-entity Reference KG.

The script queries Wikidata for:
- US Presidents and Vice Presidents
- US Senators and Representatives (most notable)
- Secretaries of State and Defense
- UK Prime Ministers
- EU/European leaders (Merkel, Macron, etc.)
- Other major world leaders

Usage:
    python scripts/build_reference_kg.py
    python scripts/build_reference_kg.py --dry-run    # show entities, don't save
    python scripts/build_reference_kg.py --merge       # merge with existing KG

Output:
    data/reference_kg/verified_events.json
    data/reference_kg/build_log_YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-30s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_reference_kg")

OUTPUT_DIR  = _PROJECT_ROOT / "data" / "reference_kg"
OUTPUT_FILE = OUTPUT_DIR / "verified_events.json"
LOG_FILE    = OUTPUT_DIR / f"build_log_{datetime.now().strftime('%Y-%m-%d')}.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# delay between Wikidata queries to avoid rate limiting
QUERY_DELAY = 1.5

# section: entity list
# Format: (name, wikidata_QID, category)
# QIDs verified manually from Wikidata
ENTITIES = [
    # US Presidents
    ("Barack Obama",          "Q76",    "us_president"),
    ("Donald Trump",          "Q22686", "us_president"),
    ("Joe Biden",             "Q6279",  "us_president"),
    ("Bill Clinton",          "Q1124",  "us_president"),
    ("George W. Bush",        "Q207",   "us_president"),
    ("George H.W. Bush",      "Q23505", "us_president"),
    ("Ronald Reagan",         "Q9960",  "us_president"),
    ("Jimmy Carter",          "Q23685", "us_president"),
    ("Gerald Ford",           "Q9916",  "us_president"),
    ("Richard Nixon",         "Q9588",  "us_president"),
    ("Lyndon B. Johnson",     "Q9640",  "us_president"),
    ("John F. Kennedy",       "Q9696",  "us_president"),
    ("Dwight Eisenhower",     "Q9916",  "us_president"),
    ("Harry S. Truman",       "Q9682",  "us_president"),

    # US Vice Presidents
    ("Mike Pence",            "Q373472",  "us_vp"),
    ("Dick Cheney",           "Q48259",   "us_vp"),
    ("Al Gore",               "Q19673",   "us_vp"),
    ("Dan Quayle",            "Q48305",   "us_vp"),
    ("Walter Mondale",        "Q223779",  "us_vp"),
    ("Kamala Harris",         "Q185530",  "us_vp"),

    # US Senators (notable)
    ("Hillary Clinton",       "Q6294",   "us_senator"),
    ("John McCain",           "Q10390",  "us_senator"),
    ("Bernie Sanders",        "Q359442", "us_senator"),
    ("Elizabeth Warren",      "Q1173433","us_senator"),
    ("Mitch McConnell",       "Q355522", "us_senator"),
    ("Chuck Schumer",         "Q380900", "us_senator"),
    ("Marco Rubio",           "Q349455", "us_senator"),
    ("Ted Cruz",              "Q905014", "us_senator"),
    ("Rand Paul",             "Q671426", "us_senator"),
    ("Lindsey Graham",        "Q378702", "us_senator"),
    ("Amy Klobuchar",         "Q23714",  "us_senator"),
    ("Cory Booker",           "Q922820", "us_senator"),
    ("Bob Menendez",          "Q539566", "us_senator"),
    ("Dianne Feinstein",      "Q231033", "us_senator"),
    ("Susan Collins",         "Q276932", "us_senator"),
    ("Lisa Murkowski",        "Q230539", "us_senator"),

    # US House Representatives (notable)
    ("Nancy Pelosi",          "Q170581", "us_representative"),
    ("Kevin McCarthy",        "Q977592", "us_representative"),
    ("Paul Ryan",             "Q381812", "us_representative"),
    ("John Boehner",          "Q310461", "us_representative"),
    ("Newt Gingrich",         "Q313756", "us_representative"),
    ("Alexandria Ocasio-Cortez","Q55223754","us_representative"),
    ("Ilhan Omar",            "Q55405334","us_representative"),
    ("Matt Gaetz",            "Q24834954","us_representative"),
    ("Jim Jordan",            "Q1689040", "us_representative"),
    ("Adam Schiff",           "Q350843",  "us_representative"),
    ("Jerry Nadler",          "Q555961",  "us_representative"),
    ("Maxine Waters",         "Q234302",  "us_representative"),
    ("Steny Hoyer",           "Q558566",  "us_representative"),
    ("Eric Cantor",           "Q726155",  "us_representative"),

    # US Secretaries of State / Defense
    ("John Kerry",            "Q33866",  "us_cabinet"),
    ("Rex Tillerson",         "Q7313083","us_cabinet"),
    ("Mike Pompeo",           "Q974374", "us_cabinet"),
    ("Antony Blinken",        "Q720301", "us_cabinet"),
    ("Condoleezza Rice",      "Q62398",  "us_cabinet"),
    ("Colin Powell",          "Q34296",  "us_cabinet"),
    ("Madeleine Albright",    "Q41225",  "us_cabinet"),
    ("Robert Gates",          "Q312930", "us_cabinet"),
    ("Donald Rumsfeld",       "Q48259",  "us_cabinet"),
    ("Lloyd Austin",          "Q6664165","us_cabinet"),

    # US Governors (notable)
    ("Mitt Romney",           "Q1036",   "us_governor"),
    ("Arnold Schwarzenegger", "Q2685",   "us_governor"),
    ("Andrew Cuomo",          "Q312528", "us_governor"),
    ("Gavin Newsom",          "Q979879", "us_governor"),
    ("Ron DeSantis",          "Q20767779","us_governor"),
    ("Chris Christie",        "Q1063986","us_governor"),
    ("Scott Walker",          "Q2608",   "us_governor"),
    ("Greg Abbott",           "Q1543000","us_governor"),
    ("Brian Kemp",            "Q16216063","us_governor"),

    # UK Prime Ministers
    ("Boris Johnson",         "Q180589", "uk_pm"),
    ("Theresa May",           "Q264766", "uk_pm"),
    ("David Cameron",         "Q192",    "uk_pm"),
    ("Gordon Brown",          "Q3336",   "uk_pm"),
    ("Tony Blair",            "Q9545",   "uk_pm"),
    ("John Major",            "Q9624",   "uk_pm"),
    ("Margaret Thatcher",     "Q7174",   "uk_pm"),
    ("Rishi Sunak",           "Q109404461","uk_pm"),
    ("Liz Truss",             "Q220359", "uk_pm"),
    ("Keir Starmer",          "Q7671853","uk_pm"),

    # UK Politicians
    ("Jeremy Corbyn",         "Q186630", "uk_politician"),
    ("Nigel Farage",          "Q192893", "uk_politician"),
    ("Sadiq Khan",            "Q3444954","uk_politician"),

    # European Leaders
    ("Angela Merkel",         "Q567",    "eu_leader"),
    ("Emmanuel Macron",       "Q3052772","eu_leader"),
    ("Nicolas Sarkozy",       "Q1631",   "eu_leader"),
    ("François Hollande",     "Q191360", "eu_leader"),
    ("Olaf Scholz",           "Q61221",  "eu_leader"),
    ("Gerhard Schroeder",     "Q2530",   "eu_leader"),
    ("Silvio Berlusconi",     "Q11860",  "eu_leader"),
    ("Mario Draghi",          "Q172572", "eu_leader"),
    ("Pedro Sánchez",         "Q58808",  "eu_leader"),
    ("Mariano Rajoy",         "Q156560", "eu_leader"),
    ("Justin Trudeau",        "Q3099714","eu_leader"),
    ("Stephen Harper",        "Q154454", "eu_leader"),
    ("Jean Chrétien",         "Q179943", "eu_leader"),
    ("Vladimir Putin",        "Q7747",   "world_leader"),
    ("Volodymyr Zelenskyy",   "Q4328088","world_leader"),
    ("Xi Jinping",            "Q15180",  "world_leader"),
    ("Narendra Modi",         "Q1058583","world_leader"),
    ("Benjamin Netanyahu",    "Q39455",  "world_leader"),
    ("Recep Tayyip Erdoğan",  "Q1058589","world_leader"),

    # US Judiciary
    ("John Roberts",          "Q190126", "us_judiciary"),
    ("Ruth Bader Ginsburg",   "Q17652",  "us_judiciary"),
    ("Antonin Scalia",        "Q186171", "us_judiciary"),
    ("Clarence Thomas",       "Q186120", "us_judiciary"),
    ("Samuel Alito",          "Q329134", "us_judiciary"),
    ("Sonia Sotomayor",       "Q220813", "us_judiciary"),
    ("Elena Kagan",           "Q220812", "us_judiciary"),
    ("Neil Gorsuch",          "Q22248662","us_judiciary"),
    ("Brett Kavanaugh",       "Q2713403","us_judiciary"),
    ("Amy Coney Barrett",     "Q88491423","us_judiciary"),
    ("Ketanji Brown Jackson", "Q78783",  "us_judiciary"),
    ("Stephen Breyer",        "Q329185", "us_judiciary"),
    ("Anthony Kennedy",       "Q329136", "us_judiciary"),
    ("David Souter",          "Q329188", "us_judiciary"),
    ("Sandra Day O'Connor",   "Q185743", "us_judiciary"),

    # Other notable US politicians
    ("Al Sharpton",           "Q348522", "us_politician"),
    ("Jesse Jackson",         "Q254987", "us_politician"),
    ("John Lewis",            "Q957110", "us_politician"),
    ("Elijah Cummings",       "Q1329428","us_politician"),
    ("Trey Gowdy",            "Q1345735","us_politician"),
    ("Bennie Thompson",       "Q1023040","us_politician"),
    ("Liz Cheney",            "Q1631912","us_politician"),
    ("Adam Kinzinger",        "Q3608736","us_politician"),
    ("Pete Buttigieg",        "Q939894", "us_politician"),
    ("Eric Adams",            "Q1328525","us_politician"),
    ("Andrew Yang",           "Q17491546","us_politician"),
    ("Tulsi Gabbard",         "Q16145726","us_politician"),
    ("Beto O'Rourke",         "Q21994992","us_politician"),
    ("Stacey Abrams",         "Q7597777","us_politician"),
    ("Raphael Warnock",       "Q7293064","us_politician"),
    ("Jon Ossoff",            "Q23039098","us_politician"),
    ("Doug Jones",            "Q17496143","us_politician"),
    ("Roy Moore",             "Q7374376","us_politician"),
    ("Luther Strange",        "Q6706827","us_politician"),
    ("Jeff Sessions",         "Q310847", "us_politician"),
    ("Eric Holder",           "Q866030", "us_politician"),
    ("Loretta Lynch",         "Q16960752","us_politician"),
    ("William Barr",          "Q215082", "us_politician"),
    ("Merrick Garland",       "Q360413", "us_politician"),
    ("Robert Mueller",        "Q367626", "us_politician"),
    ("James Comey",           "Q5028025","us_politician"),
    ("Andrew McCabe",         "Q4760695","us_politician"),
]


# section: wikidata fetch

def fetch_entity_facts(name: str, qid: str) -> list[dict]:
    """Fetch all P39 (position held) facts for an entity from Wikidata."""
    from backend.pipeline.verification.wikidata import WikidataClient

    client = WikidataClient()
    facts = client.get_temporal_facts(qid, relation_properties=["P39", "P463"])

    result = []
    for f in facts:
        entry = {
            "entity":     name,
            "entity_id":  qid,
            "position":   f.value_label,
            "property":   f.property_id,
        }
        if f.time_start:
            entry["start_year"] = f.time_start.year
            entry["start_date"] = f.time_start.strftime("%Y-%m-%d")
        if f.time_end:
            entry["end_year"]   = f.time_end.year
            entry["end_date"]   = f.time_end.strftime("%Y-%m-%d")
        if f.time_point:
            entry["point_year"] = f.time_point.year
            entry["point_date"] = f.time_point.strftime("%Y-%m-%d")
        result.append(entry)

    return result


# section: main

def main(args: argparse.Namespace) -> None:
    dry_run = args.dry_run
    merge   = args.merge
    limit   = args.limit

    entities = ENTITIES[:limit] if limit else ENTITIES

    print("\n" + "=" * 65)
    print("  BUILD EXTENDED REFERENCE KG")
    print(f"  Entities   : {len(entities)}")
    print(f"  Dry run    : {dry_run}")
    print(f"  Merge      : {merge}")
    print(f"  Output     : {OUTPUT_FILE}")
    print("=" * 65 + "\n")

    # load existing KG if merging
    existing: dict[str, list[dict]] = {}
    if merge and OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # index by entity name
        for entry in data.get("entities", []):
            existing[entry["name"]] = entry
        logger.info(f"Loaded {len(existing)} existing entities for merge.")

    # fetch facts for each entity
    all_entities = []
    failed = []
    log_entries = []

    for i, (name, qid, category) in enumerate(entities, 1):
        logger.info(f"[{i:3}/{len(entities)}] {name} ({qid}) [{category}]")

        if dry_run:
            print(f"  DRY RUN: would fetch {name} ({qid})")
            continue

        try:
            facts = fetch_entity_facts(name, qid)

            entity_entry = {
                "name":     name,
                "qid":      qid,
                "category": category,
                "facts":    facts,
                "fetched_at": datetime.now().isoformat(),
            }

            all_entities.append(entity_entry)

            log_entries.append({
                "name": name, "qid": qid,
                "facts_count": len(facts), "status": "ok",
            })

            logger.info(f"  -> {len(facts)} facts fetched")

            if not facts:
                logger.warning(f"  -> no facts found for {name}")

        except Exception as e:
            logger.error(f"  -> FAILED: {e}")
            failed.append({"name": name, "qid": qid, "error": str(e)})
            log_entries.append({
                "name": name, "qid": qid,
                "facts_count": 0, "status": "failed", "error": str(e),
            })

        time.sleep(QUERY_DELAY)

    if dry_run:
        print(f"\nDry run complete. Would have fetched {len(entities)} entities.")
        return

    # merge with existing if requested
    if merge and existing:
        existing_names = {e["name"] for e in all_entities}
        for name, entry in existing.items():
            if name not in existing_names:
                all_entities.append(entry)
                logger.info(f"Kept existing: {name}")

    # build output structure
    output = {
        "generated_at":   datetime.now().isoformat(),
        "total_entities": len(all_entities),
        "total_facts":    sum(len(e["facts"]) for e in all_entities),
        "failed_count":   len(failed),
        "entities":       all_entities,
        "failed":         failed,
    }

    # save output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # save build log
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "entries": log_entries,
            "failed": failed,
        }, f, ensure_ascii=False, indent=2)

    # summary
    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    print(f"  Entities fetched : {len(all_entities)}")
    print(f"  Total facts      : {output['total_facts']}")
    print(f"  Failed           : {len(failed)}")
    print(f"  Output           : {OUTPUT_FILE}")
    print(f"  Log              : {LOG_FILE}")

    if failed:
        print(f"\n  Failed entities:")
        for f in failed:
            print(f"    - {f['name']} ({f['qid']}): {f['error']}")

    print("\n  Top entities by fact count:")
    sorted_entities = sorted(all_entities, key=lambda e: len(e["facts"]), reverse=True)
    for e in sorted_entities[:10]:
        print(f"    {e['name']:<35} {len(e['facts']):>3} facts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Extended Reference KG from Wikidata")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show entities without fetching data")
    parser.add_argument("--merge", action="store_true",
                        help="Merge with existing Reference KG (keep existing entities)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of entities (e.g. --limit 20 for quick test)")
    args = parser.parse_args()
    main(args)

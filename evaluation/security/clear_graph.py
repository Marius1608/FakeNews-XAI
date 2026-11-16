"""Delete ALL articles and their facts from the configured Neo4j instance.

Use before a 4.2 run so the cross-article baseline starts from an empty graph
(e.g. to remove articles saved manually from the UI). Destructive and guarded:
requires --yes. Only ever points at the instance in your .env.

Usage:
  python evaluation/security/clear_graph.py            # lists articles, does nothing
  python evaluation/security/clear_graph.py --yes      # deletes them
"""

from __future__ import annotations

import argparse

from common import setup_logging, logger  # noqa: F401
from backend.config import NEO4J_ENABLED
from backend.pipeline.graph.factory import create_persistent_store


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="actually delete")
    args = ap.parse_args()
    setup_logging(True)

    if not NEO4J_ENABLED:
        raise SystemExit("NEO4J_ENABLED is false — nothing to clear")
    store = create_persistent_store()
    if store is None:
        raise SystemExit("Neo4j store unavailable — check .env")

    try:
        articles = store.get_articles()
        print(f"{len(articles)} article(s) currently in the graph:")
        for a in articles:
            print(f"  {a.get('article_id')}  {str(a.get('title',''))[:60]}")
        if not args.yes:
            print("\nDry run. Re-run with --yes to delete all of the above.")
            return 0
        removed = sum(int(store.delete_article(a["article_id"])) for a in articles)
        print(f"\nDeleted {removed}/{len(articles)} article(s).")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())

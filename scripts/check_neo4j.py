"""Checks connectivity to the Neo4j instance configured in the environment.

Works for both local Neo4j (bolt://localhost:7687) and Neo4j Aura (neo4j+s://...).
Uses NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE.

Exit codes: 0 = reachable and authenticated, 1 = not usable.
Used by start.sh (local) and scripts/docker-entrypoint.sh (Docker / HF Spaces).

Usage: python scripts/check_neo4j.py [--timeout SECONDS]
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    uri = os.getenv("NEO4J_URI", "").strip()
    user = (os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME") or "neo4j").strip()
    password = os.getenv("NEO4J_PASSWORD", "")
    database = os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j"

    if not uri:
        print("NEO4J_URI is not set")
        return 1
    if not password:
        print("NEO4J_PASSWORD is not set")
        return 1

    host = urlparse(uri).hostname or uri  # never print credentials

    try:
        from neo4j import GraphDatabase
        from neo4j.exceptions import AuthError, ClientError, ServiceUnavailable
    except ImportError:
        print("Python package 'neo4j' is not installed (pip install neo4j)")
        return 1

    try:
        with GraphDatabase.driver(
            uri,
            auth=(user, password),
            connection_timeout=args.timeout,
            connection_acquisition_timeout=args.timeout,
        ) as driver:
            driver.verify_connectivity()
            with driver.session(database=database) as session:
                session.run("RETURN 1").consume()
    except AuthError:
        print(f"Authentication failed for user '{user}' at {host} — check NEO4J_USER / NEO4J_PASSWORD")
        return 1
    except ServiceUnavailable:
        print(f"{host} unreachable — if this is Aura, the instance may be paused (resume it in console.neo4j.io)")
        return 1
    except ClientError as e:
        if "database" in str(e).lower():
            print(f"Database '{database}' not found at {host} — check NEO4J_DATABASE")
        else:
            print(f"Neo4j client error at {host}: {e.code}")
        return 1
    except Exception as e:  # DNS errors, TLS errors, malformed URI, ...
        print(f"Cannot connect to {host}: {type(e).__name__}: {e}")
        return 1

    print(f"{host} (database '{database}')")
    return 0


if __name__ == "__main__":
    sys.exit(main())

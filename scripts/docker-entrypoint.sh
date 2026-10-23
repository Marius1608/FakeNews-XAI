#!/usr/bin/env sh
# Docker / HuggingFace Spaces entrypoint.
# If NEO4J_ENABLED=true (set via Spaces Secrets), verify that the configured
# Neo4j instance (e.g. Aura) is reachable before starting the API.
# On failure the app still starts, with Neo4j disabled (graceful degradation).

if [ "${NEO4J_ENABLED:-false}" = "true" ]; then
    echo "[*] Checking Neo4j..."
    if MSG=$(python scripts/check_neo4j.py --timeout 20); then
        echo "[OK] Neo4j connected: $MSG"
    else
        echo "[!] Neo4j check failed: $MSG"
        echo "[!] Starting with NEO4J_ENABLED=false (no persistence, cross-article, HITL)"
        export NEO4J_ENABLED=false
    fi
else
    echo "[*] NEO4J_ENABLED=false — Neo4j features disabled"
fi

exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-7860}"

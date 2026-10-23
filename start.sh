#!/usr/bin/env bash
# Usage: bash start.sh
# Checks spaCy models, then launches backend (FastAPI :8000) and frontend (React :3000).

set -euo pipefail

GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
RESET="\033[0m"

BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"
NEO4J_STATUS="disabled"

BACKEND_PID=""
FRONTEND_PID=""

step() { echo -e "${CYAN}[*] $*${RESET}"; }
ok()   { echo -e "${GREEN}[OK] $*${RESET}"; }
warn() { echo -e "${YELLOW}[!] $*${RESET}"; }
err()  { echo -e "${RED}[ERR] $*${RESET}"; }

cleanup() {
    echo ""
    step "Shutting down..."
    [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null && ok "Backend stopped"
    [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null && ok "Frontend stopped"
}
trap cleanup EXIT INT TERM

# Load .env into the current shell environment
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$REPO_ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
    # strip Windows CRLF so values (e.g. NEO4J_PASSWORD) don't end in \r
    set -a
    # shellcheck disable=SC1090
    source <(tr -d '\r' < "$ENV_FILE")
    set +a
fi

IFS=',' read -ra SPACY_MODELS <<< "${SPACY_MODELS:-en_core_web_trf}"
for i in "${!SPACY_MODELS[@]}"; do SPACY_MODELS[$i]="${SPACY_MODELS[$i]// /}"; done

# Check if a URL responds with HTTP 200
check_http() {
    curl -sf -o /dev/null --max-time 5 "$1"
}

# [0/3] Python venv (needed by the Neo4j check and the backend)
step "[0/3] Activating Python venv..."
if [[ -f "$REPO_ROOT/venv/Scripts/activate" ]]; then
    source "$REPO_ROOT/venv/Scripts/activate"
elif [[ -f "$REPO_ROOT/venv/bin/activate" ]]; then
    source "$REPO_ROOT/venv/bin/activate"
else
    err "venv not found. Run: python -m venv venv && pip install -r requirements.txt"
    exit 1
fi
ok "venv activated"

# [0/3] Neo4j (optional) — checks the instance in NEO4J_URI (local or Aura)
step "[0/3] Checking Neo4j..."
if [[ "${NEO4J_ENABLED:-false}" == "true" ]]; then
    if NEO4J_MSG=$(python "$REPO_ROOT/scripts/check_neo4j.py" --timeout 20); then
        ok "Neo4j connected: $NEO4J_MSG"
        NEO4J_STATUS="$NEO4J_MSG"
    else
        warn "Neo4j check failed: $NEO4J_MSG"
        warn "Continuing with NEO4J_ENABLED=false — persistence, cross-article and HITL disabled"
        export NEO4J_ENABLED=false
    fi
else
    warn "NEO4J_ENABLED is not true in .env — persistence, cross-article and HITL disabled"
fi

# [1/3] spaCy models
step "[1/3] Checking spaCy models..."
for model in "${SPACY_MODELS[@]}"; do
    if python -c "import spacy; spacy.load('$model')" 2>/dev/null; then
        ok "spaCy model present: $model"
    else
        warn "spaCy model not found: $model — downloading..."
        if ! python -m spacy download "$model"; then
            err "Failed to download spaCy model: $model"
            exit 1
        fi
        ok "Downloaded spaCy model: $model"
    fi
done

# [2/3] Backend
step "[2/3] Starting backend (uvicorn on :8000)..."
cd "$REPO_ROOT"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 2>&1 | sed 's/^/[backend]  /' &
BACKEND_PID=$!

sleep 5
if check_http "$BACKEND_URL/health"; then
    ok "Backend healthy at $BACKEND_URL"
else
    warn "Backend did not respond in time — check output above"
fi

# [3/3] Frontend
step "[3/3] Starting frontend (npm start on :3000)..."
cd "$REPO_ROOT/frontend"
npm start 2>&1 | sed 's/^/[frontend] /' &
FRONTEND_PID=$!

cd "$REPO_ROOT"

# Summary
echo ""
echo -e "${CYAN}================================================${RESET}"
echo -e "${GREEN}  Backend    $BACKEND_URL${RESET}"
echo -e "${GREEN}  Frontend   $FRONTEND_URL${RESET}"
echo -e "${GREEN}  Neo4j      $NEO4J_STATUS${RESET}"
echo -e "${CYAN}------------------------------------------------${RESET}"
echo -e "${YELLOW}  Pipelines: A (spaCy en_core_web_trf) | B (Qwen3-1.7B local LLM)${RESET}"
echo -e "${YELLOW}  C3b:       RefKG → Neo4j → Wikidata → RSS${RESET}"
echo -e "${YELLOW}  HITL:      persist=true → Mark TRUE/FAKE${RESET}"
echo -e "${CYAN}------------------------------------------------${RESET}"
echo -e "${YELLOW}  Press Ctrl+C to stop all services${RESET}"
echo -e "${CYAN}================================================${RESET}"
echo ""

wait

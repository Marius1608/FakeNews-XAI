#!/usr/bin/env bash
# Usage: bash start.sh
# Starts Neo4j check, Ollama, pulls required models, verifies spaCy + REBEL models,
# then launches the backend (FastAPI :8000) and frontend (React :3000).

set -euo pipefail

GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
RED="\033[0;31m"
RESET="\033[0m"

BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"
NEO4J_URL="http://localhost:7474"

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
    # shellcheck disable=SC2046
    export $(grep -v '^\s*#' "$ENV_FILE" | grep '=' | xargs)
fi

# Resolve values from env with fallbacks
OLLAMA_URL="${OLLAMA_HOST:-http://localhost:11434}"

IFS=',' read -ra LLM_MODELS   <<< "${LLM_MODELS:-llama3}"
IFS=',' read -ra SPACY_MODELS <<< "${SPACY_MODELS:-en_core_web_trf}"

# Trim whitespace from each element
for i in "${!LLM_MODELS[@]}";   do LLM_MODELS[$i]="${LLM_MODELS[$i]// /}";   done
for i in "${!SPACY_MODELS[@]}"; do SPACY_MODELS[$i]="${SPACY_MODELS[$i]// /}"; done

# Check if a URL responds with HTTP 200
check_http() {
    curl -sf -o /dev/null --max-time 5 "$1"
}

# [1/6] Neo4j
step "[1/6] Checking Neo4j..."
if check_http "$NEO4J_URL"; then
    ok "Neo4j is running at $NEO4J_URL"
else
    warn "Neo4j not running — cross-article verification and HITL will be disabled"
    warn "Start Neo4j manually before running start.sh for full functionality"
fi

# [2/6] Ollama daemon
step "[2/6] Checking Ollama..."
if ! check_http "$OLLAMA_URL/api/tags"; then
    warn "Ollama not running — starting ollama serve"
    ollama serve &>/dev/null &
    sleep 3
    if ! check_http "$OLLAMA_URL/api/tags"; then
        err "Ollama failed to start. Is it installed?"
        exit 1
    fi
fi
ok "Ollama is running"

# [3/6] Ollama LLM models
step "[3/6] Checking Ollama LLM models..."
PULLED_MODELS=$(curl -sf "$OLLAMA_URL/api/tags" \
    | grep -o '"name":"[^"]*"' \
    | sed 's/"name":"//;s/"//' \
    | sed 's/:latest//' \
    || true)

for model in "${LLM_MODELS[@]}"; do
    short="${model%%:*}"
    if echo "$PULLED_MODELS" | grep -qxF "$short"; then
        ok "LLM model present: $model"
    else
        warn "Pulling LLM model: $model"
        if ! ollama pull "$model"; then
            err "Failed to pull $model"
            exit 1
        fi
        ok "Pulled: $model"
    fi
done

# [4/6] spaCy NLP models
step "[4/6] Checking spaCy models..."
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

# [5/6] REBEL model (Pipeline C)
step "[5/6] Checking REBEL-large model (Pipeline C)..."
REBEL_CACHE="$HOME/.cache/huggingface/hub/models--Babelscape--rebel-large"
if [[ -d "$REBEL_CACHE" ]]; then
    ok "REBEL-large model present in HuggingFace cache"
else
    warn "REBEL-large not in cache — Pipeline C will download on first use (~1.6GB)"
    warn "To pre-download: python -c \"from transformers import pipeline; pipeline('text2text-generation', model='Babelscape/rebel-large')\""
fi

# [6/6] Backend + Frontend
step "[6/6] Activating Python venv..."
if [[ -f "$REPO_ROOT/venv/Scripts/activate" ]]; then
    source "$REPO_ROOT/venv/Scripts/activate"
elif [[ -f "$REPO_ROOT/venv/bin/activate" ]]; then
    source "$REPO_ROOT/venv/bin/activate"
else
    err "venv not found. Run: python -m venv venv && pip install -r requirements.txt"
    exit 1
fi
ok "venv activated"

step "[6/6] Starting backend (uvicorn on :8000)..."
cd "$REPO_ROOT"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 2>&1 | sed 's/^/[backend]  /' &
BACKEND_PID=$!

sleep 5
if check_http "$BACKEND_URL/health"; then
    ok "Backend healthy at $BACKEND_URL"
else
    warn "Backend did not respond in time — check output above"
fi

step "[6/6] Starting frontend (npm start on :3000)..."
cd "$REPO_ROOT/frontend"
npm start 2>&1 | sed 's/^/[frontend] /' &
FRONTEND_PID=$!

cd "$REPO_ROOT"

# Summary
echo ""
echo -e "${CYAN}================================================${RESET}"
echo -e "${GREEN}  Backend    $BACKEND_URL${RESET}"
echo -e "${GREEN}  Frontend   $FRONTEND_URL${RESET}"
echo -e "${GREEN}  Ollama     $OLLAMA_URL${RESET}"
echo -e "${GREEN}  Neo4j      $NEO4J_URL${RESET}"
echo -e "${CYAN}------------------------------------------------${RESET}"
echo -e "${YELLOW}  Pipelines: A (spaCy) | B (llama3) | C (REBEL)${RESET}"
echo -e "${YELLOW}  C3b:       RefKG → Neo4j → Wikidata → RSS${RESET}"
echo -e "${YELLOW}  HITL:      persist=true → Mark TRUE/FAKE${RESET}"
echo -e "${CYAN}------------------------------------------------${RESET}"
echo -e "${YELLOW}  Press Ctrl+C to stop all services${RESET}"
echo -e "${CYAN}================================================${RESET}"
echo ""

wait
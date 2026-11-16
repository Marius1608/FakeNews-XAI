#!/usr/bin/env bash
# Final injection runs (Pipeline B), same articles for each configuration.
#   off  = original;  on = guard + trust tiers (recommended);  full = on + prompt hardening
# Usage (Git Bash, repo root, venv active):   bash evaluation/security/run_final.sh
#   N=12 by default (articles); ~35 min per configuration on the RTX 4060.
# Output: evaluation/security/results/final_<timestamp>/SUMMARIES.txt  <- send me this

N="${N:-12}"
TS="$(date +%Y-%m-%d_%H%M%S)"
OUT="evaluation/security/results/final_${TS}"
mkdir -p "$OUT"; SUM="$OUT/SUMMARIES.txt"; STATUS="$OUT/STATUS.txt"; : > "$SUM"; : > "$STATUS"
if [ -f .env ]; then set -a; source <(tr -d '\r' < .env); set +a; fi

step () {
  local mode="$1"; local log="$OUT/injection_${mode}.log"
  echo "[$(date +%H:%M:%S)] START $mode" | tee -a "$STATUS"
  python -u evaluation/security/run_injection.py --pipeline llm --defenses "$mode" --limit "$N" > "$log" 2>&1
  local c=$?
  [ $c -eq 0 ] && echo "[$(date +%H:%M:%S)] OK    $mode" | tee -a "$STATUS" || echo "[$(date +%H:%M:%S)] FAIL($c) $mode" | tee -a "$STATUS"
  { echo; echo "##### injection $mode"; grep -A14 -E "^=== " "$log"; } >> "$SUM"
}

step off
step on
step full
echo "[$(date +%H:%M:%S)] ALL DONE. Send me: $SUM" | tee -a "$STATUS"

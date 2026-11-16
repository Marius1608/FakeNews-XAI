#!/usr/bin/env bash
# Ablation on normal data: which defence component changes the benchmark verdicts?
#   guard     = only the cross-pipeline guard (prompts unchanged)
#   hardening = only the prompt hardening (no guard)
# Usage (Git Bash, repo root, venv active):   bash evaluation/security/run_ablation.sh
# Output: evaluation/security/results/ablation_<timestamp>/  (SUMMARIES.txt = send me this)

TS="$(date +%Y-%m-%d_%H%M%S)"
OUT="evaluation/security/results/ablation_${TS}"
mkdir -p "$OUT"; SUM="$OUT/SUMMARIES.txt"; STATUS="$OUT/STATUS.txt"; : > "$SUM"; : > "$STATUS"
if [ -f .env ]; then set -a; source <(tr -d '\r' < .env); set +a; fi

step () {
  local mode="$1"; local log="$OUT/benchmark_llm_${mode}.log"
  echo "[$(date +%H:%M:%S)] START $mode" | tee -a "$STATUS"
  python -u evaluation/security/run_defense_benchmark.py --pipeline llm --defenses "$mode" > "$log" 2>&1
  local c=$?
  [ $c -eq 0 ] && echo "[$(date +%H:%M:%S)] OK    $mode" | tee -a "$STATUS" || echo "[$(date +%H:%M:%S)] FAIL($c) $mode" | tee -a "$STATUS"
  { echo; echo "##### $mode"; grep -A12 -E "^=== " "$log"; } >> "$SUM"
}

step guard
step hardening
echo "[$(date +%H:%M:%S)] ALL DONE. Send me: $SUM" | tee -a "$STATUS"

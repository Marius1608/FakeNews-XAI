#!/usr/bin/env bash
# Quick check of title isolation (channel "title" + control), Pipeline B, same 12 articles.
#   strict = guard + trust tiers + title isolation.   ~10 min.
# Usage (Git Bash, repo root, venv active):   bash evaluation/security/run_strict.sh
TS="$(date +%Y-%m-%d_%H%M%S)"; OUT="evaluation/security/results/strict_${TS}"; mkdir -p "$OUT"
if [ -f .env ]; then set -a; source <(tr -d '\r' < .env); set +a; fi
python -u evaluation/security/run_injection.py --pipeline llm --defenses strict --limit 12 \
  --cases baseline-none,override-title,override-inline > "$OUT/injection_strict.log" 2>&1
grep -A8 -E "^=== " "$OUT/injection_strict.log" | tee "$OUT/SUMMARIES.txt"
echo "DONE -> $OUT/SUMMARIES.txt"

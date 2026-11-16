# Security experiments — FakeNews-XAI (RC report, chapters 4–6)

Measurements for the two in-depth vulnerabilities, run against **your own** local/Aura
instance, each in two modes: `--defenses off` (original system, the "before") and
`--defenses on` (all defences of chapter 5, the "after").

> Run only against your own instance. Keep the HuggingFace Space **private** while poison
> data is in the graph — the API has no authentication (V-01).

## The defences (what `--defenses on` switches on)

| Flag (`.env`) | Defence | Targets |
|---|---|---|
| `DEFENSE_CROSS_PIPELINE` | 5.1 cross-pipeline consistency guard (Pipeline B vs deterministic Pipeline A) + check of the LLM explanation against the structured evidence | V-02, V-03 |
| `DEFENSE_PROMPT_HARDENING` | 5.1 first layer: article marked as data in the LLM prompts | V-02, V-03 |
| `DEFENSE_TRUST_TIERS` | 5.2 trust-tiered KG: provenance tiers, human verdict read, strict entity match, burst annotation | V-04, V-05, V-06 |

`DEFENSES=all` in `.env` turns on every flag not set explicitly. The experiment scripts set
the flags themselves from `--defenses` and ignore `.env` for them.

## Files

| File | Purpose |
|---|---|
| `common.py` | Helpers: benchmark, orchestrator, FAKE rule (≥1 fact and TCS < 0.75), JSONL output. |
| `payloads.example.json` | Template for the 4.1 cases. **Copy to `payloads.json`** and add your own. |
| `run_injection.py` | 4.1 — prompt-injection success rate against Pipeline B. |
| `poison.example.json` | Template for 4.2 (fictional entity + utility check). Copy to `poison.json`. |
| `run_poisoning.py` | 4.2 — poisoning, HITL test, and utility check. |
| `run_defense_benchmark.py` | Cost of the defences on the 100 normal articles (P/R/F1, guard false alarms). |
| `clear_graph.py` | Empties the graph before a 4.2 run. Needs `--yes`. |
| `results/` | JSONL outputs (git-ignored). |

## Order of work (each step in Git Bash, repo root, venv active)

```bash
source venv/Scripts/activate

# 0. unit tests (no models, no network)
python -m pytest backend/tests/test_defenses.py -q

# 1. empty graph
python evaluation/security/clear_graph.py --yes

# 2. 4.1 prompt injection, before and after   (Pipeline B is slow: use --limit first)
python evaluation/security/run_injection.py --pipeline llm --defenses off --limit 3 -v
python evaluation/security/run_injection.py --pipeline llm --defenses on  --limit 3 -v
#    then the full runs without --limit

# 3. 4.2 poisoning, before and after
cp evaluation/security/poison.example.json evaluation/security/poison.json
python evaluation/security/run_poisoning.py --scenarios evaluation/security/poison.json --defenses off -v
python evaluation/security/run_poisoning.py --scenarios evaluation/security/poison.json --defenses on  -v
python evaluation/security/run_poisoning.py --target "Obama" --defenses off     # auto scenario (entity known to the KG)
python evaluation/security/run_poisoning.py --target "Obama" --defenses on

# 4. cost of the defences on normal data
python evaluation/security/run_defense_benchmark.py --pipeline llm --defenses off
python evaluation/security/run_defense_benchmark.py --pipeline llm --defenses on
python evaluation/security/run_defense_benchmark.py --pipeline spacy --defenses on --limit 30   # Pipeline A must be unchanged
```

## How to read the results

**4.1** (`run_injection.py`): per payload case, `flipped FAKE->TRUE / baseline-detected`.
`baseline-none` must give 0. Compare the same cases `off` vs `on`.

**4.2** (`run_poisoning.py`):
- `attack_succeeded` — the legitimate article flips TRUE → FAKE after poisoning;
- `hitl_recovered` — it recovers once a human marks the poison FAKE (expected `False` with
  defences off: V-05; `True`/not needed with defences on);
- `poison_flagged_fake_at_write` — whether the system itself caught the poison when it was
  stored (false for the fictional entity: external sources know nothing about it, so the
  trust tiers are what protects the graph);
- utility `conflict_detected` — a human-confirmed article must still expose a genuinely
  contradicting one with MEDIUM+ severity, with the defences on **and** off. If it turns
  `False` with defences on, the defence costs real detection and must be reported.

**Cost** (`run_defense_benchmark.py`): P/R/F1 at θ = 0.75 off vs on (thesis reference for
Pipeline A: P 0.909, R 0.227, F1 0.364), `false_alarm_rate_on_true_articles` of the guard,
and with `--with-explainer` how many LLM narratives the explanation check rejects.

## Known limits to state in the report

- The guard keeps LLM facts in sentences the deterministic extractor does not cover
  (otherwise Pipeline B loses its reason to exist): an injection that fabricates a
  *coherent* fact in such a sentence is not caught.
- Trust tiers trade some cross-article sensitivity on entities that no external source can
  confirm: until a human confirms an article, its facts only raise LOW signals.
- Dates are compared at year/month precision; a day-level change inside the same month is
  not detected by the guard.
- Pipeline B samples at temperature 0.1: runs are seeded but can still differ slightly.

## Demo (presentation, ~4 minutes)

Set `DEMO_MODE=true` in `.env`, start the backend, and flip the defences without a restart:

```bash
curl -s localhost:8000/defenses
curl -s -X PUT localhost:8000/defenses -H "content-type: application/json" \
     -d '{"cross_pipeline": true, "prompt_hardening": true, "trust_tiers": true}'
curl -s -X PUT localhost:8000/defenses -H "content-type: application/json" \
     -d '{"cross_pipeline": false, "prompt_hardening": false, "trust_tiers": false}'
```

`GET /health` also shows the current state under `components.defenses`. Never set
`DEMO_MODE=true` on a public deployment.

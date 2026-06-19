# Thesis Evaluation — FakeNews-XAI

**Thesis:** "Explainable Agentic AI for Fake News Detection"
**Student:** Marius Pantea — UTCN, Faculty of Automation and Computer Science
**Supervisor:** Prof. Adrian Groza · **Co-supervisor:** Conf. Ioana Chereș
**Submission:** July 1, 2026
**Reviewer role:** external AI/NLP examiner
**Basis:** source read of `tcs.py`, `external.py`, `internal.py`, `spacy_extractor.py`,
`orchestrator.py`, `README.md`, the reference KG, and the reported benchmark results.

---

## SECTION 1 — THESIS QUALITY ASSESSMENT

### 1.1 Originality and definition of the contribution

**The contribution is original at the engineering/synthesis level, modest at the research level.**

- **TCS as a metric.** The Temporal Coherence Score — `TCS = (1 − penalty_ratio) × score_coherence`,
  with a severity-weighted penalty over extracted temporal claims and an internal-coherence term
  derived from a temporal knowledge graph — is, as far as I can tell, a *novel packaging* of known
  ideas rather than a fundamentally new algorithm. Temporal consistency checking over knowledge
  graphs (temporal cycles, causal ordering, interval overlap) exists in the TKG literature; framing a
  single normalized [0,1] *article-level* score for misinformation triage, with an explainable
  breakdown, is the genuine novelty. That is a legitimate bachelor-level contribution: a new
  *application and operationalization*, not a new theory.

- **Problem motivation is sound but narrow.** "Temporal inconsistency in political news" is a real,
  underexplored signal. The honest framing should be that TCS detects *one specific failure mode*
  (impossible chronology), not fake news in general — and the evaluation confirms exactly this.

- **Comparison to existing approaches is thin.** I did not see a quantitative baseline (e.g. a
  TF-IDF/transformer text classifier on the same 100 articles). Without it, the committee cannot tell
  whether TCS beats a trivial baseline on this benchmark. This is the most important missing
  experiment for the *research* claim.

### 1.2 Methodology

**Mixed: rigorous in places, with one structural weakness.**

- **Strength — honest negative results.** ISOT (F1=0.000), RAGuard (F1=0.039), LIAR2, PolitiFact are
  all reported as failures *and explained* (emotional-language fakes, short claims, no
  HOLDS_POSITION facts). Documenting where your method does **not** work, and *why*, is exactly the
  scientific maturity examiners reward. The "evaluated and rejected" log (REBEL, DeepKE, Ollama,
  flan-t5, Wikipedia REST, Stanza, QLoRA) is similarly excellent engineering hygiene.

- **Weakness — the primary benchmark is self-constructed and synthetic.** F1=0.393 is measured on
  100 articles the author wrote. There is an inherent risk that the test set is implicitly shaped by
  what the system can detect. The external datasets (where the method scores ~0) are the *honest*
  generalization signal. The thesis must frame the 100-article benchmark as a **controlled probe of
  the mechanism**, not as evidence of real-world performance — otherwise a sharp examiner will press
  on circularity.

- **Evaluation appropriateness.** P/R/F1/Accuracy plus TCS-separation (TRUE 0.888 vs FAKE 0.737,
  +0.151) is appropriate. What is missing: a **threshold/ROC analysis**. With a separation of only
  0.151 and threshold fixed at 0.70 *below* the FAKE mean (0.737), the operating point is
  recall-hostile by construction. A simple threshold sweep would materially strengthen the rigor.

### 1.3 Implementation completeness and code quality

**Strong — clearly above typical bachelor level in breadth and engineering discipline.**

- The system genuinely does what it claims for the C1→C4 pipeline: extraction (spaCy + Qwen3-1.7B),
  TKG (NetworkX + Neo4j), 5-level hierarchical verification, severity-weighted scoring, and a
  local-LLM XAI explanation, behind a FastAPI backend and a React/TS frontend with a
  human-in-the-loop verdict path. The on-premise constraint is respected.

- Code quality is good: typed dataclasses, abstract interfaces (`AbstractExtractor`,
  `AbstractTKGStore`), lazy model loading, a true Qwen singleton, and reasonable separation of
  concerns. (A separate code audit identified some shared-singleton/state-bleed issues in the
  request layer — real, but not visible to a thesis reader.)

- **Two credibility problems a committee WILL notice:**

  1. **Documentation drift (most urgent).** The `README.md` describes a *different system* than the
     code: it still says Pipeline B = **Ollama `llama3:8b`** (the code uses **Qwen3-1.7B**), gives a
     TCS formula with a `coverage_factor` term that **does not exist** in `tcs.py`, lists severity
     weights (LOW=0.2/MED=0.5) that **disagree** with the code (LOW=0.0/MED=0.3), reports an **old
     benchmark** (84 articles, F1=0.227) instead of the current one (100, F1=0.393), and says the
     reference KG has **16 entities** while it actually ships 150 (+manual). If the *thesis PDF*
     contains the same drift, this is a serious defense liability — the written method must match the
     running code exactly.

  2. **The "150 entities / 1169 facts" reference KG is largely inert.** In `verified_events.json`
     the 150-entity bulk dump lives under an `"entities"` key that the verifier **never looks up**;
     only ~18 hand-curated entries actually drive verification, and the bulk data contains corrupted
     records (e.g. Trump "president 1971–2017"). Claiming "1169 facts, 150 entities" as the
     verification backbone overstates the real coverage. Either wire the bulk data in (after
     cleaning) or report the *effective* coverage honestly.

### 1.4 Likely grade and committee questions

**Likely outcome: strong — roughly 9/10 (Romanian scale), defensible up to 9.5 with a polished
defense and fixed documentation; at risk of dropping to ~8 if the drift/overstatement issues are
exposed and unaddressed.**

- **Strongest points:** engineering breadth and completeness; intellectual honesty about failure
  modes and rejected alternatives; a clean, explainable, fully on-premise architecture; an original
  operationalization (TCS) with a working XAI layer.

- **Weakest points:** recall (0.273 — misses ~73% of fakes); validation essentially limited to
  self-authored synthetic data; the "agentic" claim in the title is not realized in the code (the
  orchestrator is a *fixed deterministic cascade*, not an agent that plans or selects tools); no
  baseline comparison; documentation/claims drift.

- **Questions the committee will likely ask:**
  1. "Your title says *Agentic AI* — where is the agent? What decisions does it make autonomously?"
  2. "Recall is 0.27. For a detector, isn't missing 3 of 4 fakes disqualifying? What is the intended
     deployment role?"
  3. "Your benchmark is synthetic and self-written. How do you rule out that it just tests what your
     rules already encode?"
  4. "What is the baseline? Does a vanilla BERT classifier beat TCS on these 100 articles?"
  5. "Why TCS=0.5 for 'insufficient data' — doesn't that put a third of real datasets in a dead
     zone (LIAR2/RAGuard)?"
  6. "Walk me through the exact scoring formula." (The PDF must match `tcs.py`.)

---

## SECTION 2 — TECHNICAL IMPROVEMENTS (implementable before July 1)

**Reality check first:** of the 32 false negatives, the large cluster at **TCS = 1.000** cannot be
recovered by tuning. TCS=1.000 means *zero inconsistencies detected* and coherence = 1.0 — the
verifiers found nothing. Threshold changes are useless for these; they need **new detection signal**.
The soft FNs (0.73–0.85: idx 18, 51, 52, 53, 74, …) are the ones reachable by calibration.

> Note: a prior pass already implemented precision fixes (object-matching + year-granularity in
> reference comparison, corrupted-interval guard, chronological interval ordering, LOW-severity
> exclusion from coherence, V5 party-object guard, V7 President×Governor) expected to cut FP from 5
> to ~1–2. The remaining lever — and the bigger prize — is **recall**.

### Why the 32 TCS=1.000 FNs are invisible

Three compounding gaps:
1. **Extraction never produces ordering/causal relations.** Fakes like "PATRIOT Act before 9/11",
   "acquittal before House vote", "ruling before passage" are encoded as independent `OCCURRED_ON`
   point events. The cycle check (V1) and causal check (V2) only fire on `PRECEDED/FOLLOWED/CAUSED`
   edges, which `spacy_extractor` almost never emits → V1/V2 are **dormant**.
2. **No event-level external reference.** The reference KG holds *positions* (P39) and a handful of
   bill-signing dates. It has no Nobel Prizes, treaties, rulings, votes, attacks → wrong-date fakes
   about events (Nobel year, NAFTA year, ACA SCOTUS date) have nothing to check against.
3. **No notion of event prerequisites** (an official act cannot precede taking office; an effect
   cannot precede its cause).

### Prioritized improvements

| # | Improvement | What to change | Est. FN/FP impact | Time | Complexity |
|---|---|---|---|---|---|
| **I1** | **Threshold / ROC calibration** | Sweep threshold 0.5→0.9 on the benchmark; report ROC + F1-optimal point. Given FAKE mean 0.737 < current 0.70, moving toward ~0.78–0.80 catches the soft-FN cluster. | +6–10 FN recovered (the 0.73–0.85 cluster); costs a few FP — net F1 likely up. | 1 day | **LOW** |
| **I2** | **Event-date reference check** | Extend `verified_events.json` with ~50–100 canonical political *events* (9/11=2001-09-11, ACA passage=2010-03-23, Paris Agreement=2015-12, NAFTA=1994-01, Bin Laden=2011-05, etc.) and add an `OCCURRED_ON` comparison branch in `external.py` (reuse the new year-granularity + value-matching logic). | +8–12 FN (wrong-date event fakes: Nobel, NAFTA, ACA ruling, signings). Low FP risk if curated. | ~1 week | **MEDIUM** |
| **I3** | **"Action before office" internal check (V8)** | For each `HOLDS_POSITION` (office start S) of an entity, flag any `OCCURRED_ON/STARTED` action by the same entity dated meaningfully before S ("Trump signed bill before inauguration", idx=25). | +3–5 FN. FP risk low (requires same-entity + clear gap). | ~3 days | **LOW–MED** |
| **I4** | **Activate temporal connectives in C1** | In `spacy_extractor._classify_relation`, map "before/after/prior to/following/led to/because of" to `PRECEDED/FOLLOWED/CAUSED` so the dormant V1/V2 cycle & causal checks finally fire on reordered-event fakes. | +4–8 FN (activates existing checks). Moderate FP risk → needs guards. | ~1 week | **MEDIUM** |
| **I5** | **Clean + wire the bulk reference KG** | Drop corrupted records (end<start, "president 1971"), normalize, and expose the 150 entities for per-entity lookup (currently dead under `"entities"`). Reuse object-matching + year-granularity to contain FP. | +2–4 FN (wrong tenure dates for more entities). FP risk real → gate carefully. | ~3–4 days | **MEDIUM** |

**Recommended 2–3 week plan:** I1 (day 1, free recall + rigor) → I2 (biggest single FN bucket) →
I3 (cheap, high-precision) → if time remains, I4. Skip I5 unless data cleaning is fast.

**Combined realistic estimate:** FN 32 → ~18–22, FP 5 → ~2–3, **F1 ~0.45–0.52** with I1+I2+I3.
The TCS=1.000 fakes that are pure *narrative reordering with no external anchor* will remain the
hardest residual — be explicit about that in the thesis rather than chasing them.

**Do NOT do before July 1:** retrain/fine-tune (QLoRA), swap models, or rewrite the scoring formula
globally — high risk, unmeasurable in the time left, and they jeopardize a working system 19 days
out.

---

## SECTION 3 — FUTURE RESEARCH DIRECTIONS (for Cap. 8)

### 3.1 Short-term (master's level, 1–2 years)

- **Make it genuinely agentic.** The most natural extension that also closes the title gap: replace
  the fixed C3 cascade with an LLM **planner-agent** that chooses which verifier to call per claim
  (skip Wikidata for non-entity claims, escalate to RSS only for recent events, decide when evidence
  is sufficient). This converts "hierarchical fallback" into real tool-selecting agency.
- **Learned TCS calibration.** Replace the hand-weighted penalty with a small supervised model
  (logistic regression / gradient boosting) over per-check features → principled weights and a
  calibrated probability instead of a hand-tuned threshold.
- **Event-centric temporal KB + temporal RAG.** Generalize I2 into a retrieved temporal evidence
  layer (TimeQA/TempLAMA-style) so the system is not limited to ~18 entities.
- **Multilingual / Romanian.** The VER-1 dataset (Conf. Chereș) is the obvious next corpus;
  temporal misinformation in Romanian political news is a defensible, locally-valuable niche.
- **Highest-impact model improvement:** fine-tune the C1 extractor (the QLoRA infra already exists)
  to lift recall of `PRECEDED/FOLLOWED/CAUSED` and event triples — extraction recall (0.50) is the
  true ceiling on the whole pipeline.

### 3.2 Long-term (PhD level)

- **Generalize "coherence scoring" beyond time.** TCS is one instance of *intra-document consistency
  verification*. The research question: can a unified, explainable **Consistency Score** combine
  temporal, numerical, geographic, and causal coherence into one neuro-symbolic verifier?
- **Neuro-symbolic temporal reasoning.** Combine LLM extraction with formal temporal logic (Allen's
  interval algebra, constraint solving) for *provable* inconsistency detection with guarantees —
  the explainability angle has real depth here.
- **Claim decomposition + verification at scale.** Break complex articles into atomic checkable
  claims (FEVEROUS/HoVer-style) and route each to the right reasoning module.
- **Production form.** A deployable version would be an **ensemble feature**, not a standalone
  classifier: TCS as one explainable signal feeding a broader detector, with streaming KB updates,
  caching, calibrated confidence, and human-in-the-loop active learning (the verdict endpoint is the
  seed of this).

### 3.3 Related-work positioning and venues

- **Complements:** temporal KG reasoning (Cai et al., already cited), temporal IE (TempEval, TORQUE,
  MATRES), temporal QA (TimeQA, TempLAMA, MenatQA), and fact verification (FEVER/FEVEROUS, HoVer).
  The thesis sits in the *gap* between temporal reasoning and misinformation detection — a sparsely
  populated, genuinely interesting intersection.
- **State of the field:** temporal reasoning remains a known LLM weakness; *temporal* misinformation
  specifically is understudied relative to stylistic/stance-based fake-news work. That is the
  strongest "why this matters" argument for Cap. 8.
- **Realistic submission targets:** a workshop paper is achievable — FEVER workshop, NLP4IF,
  or the fact-checking / misinformation tracks; regionally, RANLP or LREC-COLING (resource/eval
  angle). Framed honestly as "a temporal-consistency signal + explainable operationalization," with
  the threshold/ROC analysis and a baseline, it is workshop-credible. It is **not** top-tier-main
  material as-is.

---

## SECTION 4 — HONEST OVERALL ASSESSMENT

**1. Is this a strong bachelor thesis?**
Yes — clearly above average. It demonstrates end-to-end systems competence (NLP, graphs, local LLMs,
full-stack, evaluation), a coherent original idea, and — rarest of all at this level — scientific
honesty about what fails. The shortfalls are *research-depth and validation* shortfalls, not
*effort or competence* shortfalls.

**2. Single most impressive aspect.**
The **intellectual honesty and engineering rigor of the negative results**: explicitly measuring and
explaining failure on ISOT/RAGuard/LIAR2, and maintaining a documented log of rejected approaches
(REBEL, DeepKE, Ollama, flan-t5, Wikipedia, Stanza). Most bachelor theses hide this; here it is a
genuine strength and signals real research maturity. (The original TCS+XAI operationalization is a
close second.)

**3. Single biggest weakness.**
**Recall, compounded by validation scope.** TCS=0.273 means the system misses ~73% of fakes, and the
only data where it works is the author's own synthetic benchmark (≈0 F1 on every external dataset).
As a *fake-news detector* it is not yet useful; the honest claim is "a high-precision detector of one
narrow inconsistency type, on a controlled corpus." The mismatch between that reality and the
ambitious title ("Agentic AI for Fake News Detection") is the central vulnerability.

**4. If I were the supervisor — what to do in the remaining 19 days.**
*Stop optimizing F1; start protecting credibility. Writing now outranks coding.*
   1. **Fix documentation drift (day 1–2, non-negotiable).** Make the README **and the thesis PDF**
      match the code exactly: Qwen3-1.7B (not Ollama/llama3), the real formula and severity weights
      from `tcs.py`, the current 100-article results, and the *effective* reference-KG coverage.
   2. **Run the threshold/ROC analysis (I1).** One day, free recall + a rigor box the committee
      expects.
   3. **Add one baseline** (a BERT/TF-IDF classifier on the 100 articles) so TCS has something to be
      compared against. Without it the research claim is unanchored.
   4. **Reframe the contribution honestly** in the abstract/intro/conclusions: a *precision-oriented,
      explainable temporal-consistency signal* for a specific domain, with documented limits — and
      address the "agentic" wording (either justify the hierarchical-verifier-as-agent framing or
      soften the title in the text).
   5. **Only if 1–4 are done:** implement I2 (event-date reference) for a real recall bump.

**5. Genuinely useful, or academic exercise?**
**Primarily a strong academic proof-of-concept** — not a deployable fake-news detector (recall too
low, domain too narrow, ~0 on real data). But the underlying *signal is real*: impossible chronology
is a legitimate, explainable misinformation cue, and TCS is a sensible way to surface it. Its honest
future is as **one explainable feature in an ensemble**, plus a strong didactic/portfolio artifact.
Judged as a bachelor thesis (learning, breadth, honesty, working system) it succeeds; judged as a
production tool it does not — and the thesis will be stronger if it says exactly that.

---

### Bottom line
A well-engineered, honest, original-in-application bachelor thesis with a real (if narrow) signal,
let down by weak recall, synthetic-only validation, an over-reaching title, and documentation that
describes an earlier version of the system. Nineteen days are best spent on **alignment and
framing** (docs ↔ code ↔ claims, baseline, ROC) rather than on chasing the largely
unreachable TCS=1.000 false negatives.

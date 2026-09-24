# Briefing for PPT generation — Certified Numeric Verification

Paste this whole document into a Claude.ai conversation with a request like:
"Turn this into a 12-15 slide academic presentation deck for an MCA project
review, IEEE-style, with a title slide, problem/motivation, related work,
method/architecture, dataset, RPA deployment, current status, and next
steps." Everything below is real, either measured from our own pipeline or
verified via citation search — nothing is invented.

---

## 1. Project identity

**Title:** Certified Numeric Verification: Guaranteed-Error Fact-Checking of
Numeric Claims over Tables with Automated Human Escalation

**Authors:** Mohd. Aatir, Prafful Gupta, Prashant Kumar Singh, [Member 4] —
Department of Computer Applications (MCA), KIET Group of Institutions.

**SDG alignment:** SDG 16 (public access to reliable information, primary);
SDG 4 (educational information, secondary — institutional deployment over
academic records).

**Status as of this presentation:** working end-to-end system (data
pipeline, LLM verifier, conformal calibration code, FastAPI service, RPA
integration design, demo) is built and demonstrably functioning on live
data. The large-scale experimental evaluation (the "Results" section of the
paper) is in progress, rate-limited by free-tier LLM API access, and is
explicitly presented as in-progress future work, not fabricated.

---

## 2. The problem (motivation slide)

LLMs verify numeric claims about tables unreliably: they miscount rows,
mis-sum columns, and get comparisons wrong. Two specific reasons this is
hard, worth a slide each or combined:

1. **Citations don't help.** A citation points to a passage that supports a
   claim. But an aggregated number — a count, a total, an average — is not
   written anywhere in the source table; it has to be *computed*. There is
   nothing to cite for "the total fee is 95,000" when 95,000 is the sum of
   two other cells.
2. **Near-miss claims are semantically invisible.** "The total fee is
   95,000" and "the total fee is 99,000" differ by one digit but have
   opposite truth values. Any system that checks a claim by how *similar* it
   is to the source (retrieval/embedding-based fact-checking) cannot tell
   these apart — we measured this directly (see Section 5 below).

**Concrete example for a slide (real, from our own demo tables):**
- Table: MCA program fees, semester 1 → tuition 60,000 + hostel 35,000 = total 95,000.
- Claim A (TRUE): "the total fee for MCA semester 1 is 95000"
- Claim B (FALSE, near-miss): "the total fee for MCA semester 1 is 99000"
- These two claims are nearly identical text; only a computation, not a citation or a similarity check, can tell them apart.

---

## 3. Our three contributions (good as a 3-box slide)

**C1 — NumNear-TabFact.** A large benchmark of numeric near-miss claims,
built entirely programmatically (no LLM calls) from the TabFact dataset, by
taking true claims and changing exactly one number just enough to flip the
claim's truth value, then verifying the flip against the table.

**C2 — Execution-agreement confidence.** Instead of asking an LLM to state a
verdict directly, we ask it to translate the claim into a small JSON
"program" (a filter + an operation like count/sum/average/compare), execute
that program deterministically with pandas, sample this 5 times, and use
*agreement among the 5 independently executed results* as a confidence
score.

**C3 — Conformal risk control.** We statistically calibrate that confidence
score so that, among the claims the system chooses to answer, the error rate
is mathematically guaranteed (with high probability) not to exceed a chosen
threshold — 2%, 5%, or 10%. Every claim below that confidence threshold is
automatically routed to a human reviewer instead of being answered
incorrectly.

---

## 4. Why this differs from prior work (for a "related work" slide)

We searched and verified these exist; we differ from all of them:
- **TabFact (Chen et al., ICLR 2020)** — introduced the table-verification task itself; used a trained semantic parser, no numeric-near-miss testing, no confidence/abstention mechanism.
- **Binder / Dater / Chain-of-Table / PAL / Program-of-Thoughts** — LLM-driven program synthesis for table/math reasoning; target general accuracy, not the near-miss failure mode, and none couples execution to a statistical abstention guarantee.
- **NumPert (2025) / QuanTemp (2024)** — numeric-claim robustness/benchmarks, but over free-text evidence, not tables, and without an execution-based defense or conformal calibration.
- **Conformal factuality (Mohri & Hashimoto, ICML 2024) / Conformal abstention (Abbasi Yadkori et al., 2024)** — conformal calibration for LLM factuality, but for open-ended generation with LLM-judged confidence, not table-grounded execution-based confidence.
- **No prior work combines all three: a numeric near-miss table benchmark + execution-agreement confidence + conformal risk control with a human-review deployment.**

---

## 5. Real data we already have (use these numbers verbatim — do not round further or embellish)

**Dataset scale (TabFact, exact counts, no sampling):**
- 118,275 total claims, 16,573 tables (train/val/test: 92,585 / 12,851 / 12,839)
- 103,966 claims (88%) contain a number, number word, or count/comparison/superlative/aggregation cue → our "numeric subset"
- 11,400 numeric claims in the test split (used for evaluation)
- Claim-type breakdown (numeric claims): lookup 50,433; comparison 17,709; superlative 21,846; aggregation 7,526; count 6,452

**NumNear-TabFact (our new benchmark, built and validated):**
- 53,472 label-flip-verified near-miss claim variants
- 5,474 of these derived from test-split tables (used for evaluation)
- Perturbation types: off-by-one (13,528), digit-swap (9,697), magnitude-change (15,123), round-number-change (15,124)

**The headline result — cosine similarity between true claims and their near-misses (all-MiniLM-L6-v2 sentence embeddings):**
- **Mean cosine similarity: 0.961**
- 91.2% of pairs have similarity above 0.9
- 74.5% of pairs have similarity above 0.95
- **This is the single most important number in the deck** — it's the quantitative proof that a wrong numeric claim looks, to a semantic model, almost identical to the correct one.

**Pilot run (n=50, real, completed):** running locally on Qwen2.5-7B-Instruct
via Ollama (cost: $0):
- B1 (LLM-only): 74.0% accuracy
- B2 (LLM-only + self-reported confidence): 78.0%
- B3 (single executed check): 40.0%
- Ours (5 executed checks, majority vote): 52.0%

**Honest interpretation for the slide (this is a *finding*, not a weak
result to hide):** at this small model size, generating a correct
*structured JSON check* is harder than just answering directly in free
text — so the execution-based methods score lower here than the free-text
baselines. This is a real, useful discovery: it shows the accuracy benefit
of execution-agreement is conditional on the base model's instruction-
following reliability. It does **not** undermine the core safety claim —
the conformal-calibrated abstention (C3) is designed so that low agreement
correctly routes uncertain claims to human review, regardless of the base
model's raw accuracy. We flag this for confirmation with a larger/hosted
model as immediate future work.

**Why the full run isn't finished:** the free-tier hosted API we first used
(Google Gemini) turned out to cap at exactly 500 requests/day — confirmed by
a live quota-exceeded error — nowhere near the ~135,000 calls the full
16,874-claim evaluation needs. We pivoted to running locally (Ollama, no
external limit), which works but is compute-bound: the full run is
estimated at roughly 3 days on this hardware and is running in the
background past this presentation.

---

## 6. System architecture (for an architecture diagram slide)

```
Claim + Table
     |
     v
LLM generates 5 independent JSON "checks"
(each: row filter + operation + expected value)
     |
     v
pandas executes each check deterministically
     |
     v
Agreement score = (majority count) / 5
     |
     v
Conformal-calibrated threshold gate
     |
     +-- above threshold --> Answer (verdict + the exact computed number as evidence)
     |
     +-- below threshold  --> Abstain --> RPA human-review queue
```

We built this as a real FastAPI service (`POST /verify`) with a live web
frontend calling it directly — tested end-to-end, e.g.:
- Claim: "the total fee for MCA semester 1 is 95000" → **TRUE**, agreement 1.0, computed value 95,000 (matches).
- Claim: "the total fee for MCA semester 1 is 99000" → **ABSTAIN**, agreement 0.6, computed value 95,000 across the valid checks (correctly contradicts the claim's stated 99,000 — but agreement fell below the calibration threshold, so it goes to human review instead of asserting FALSE outright). This is the abstention pathway working live, and it's actually a *better* demo moment than a clean answer: it shows the review-queue escalation, not just the happy path.
- Note: exact agreement scores vary run to run and by which model is behind the API at the time (the earlier number above was measured on a hosted model; tomorrow's live demo runs on the local Qwen2.5-7B model, so don't be surprised if numbers differ slightly from claim to claim — the important thing to narrate is *why* it abstains, not a specific score).

---

## 7. RPA deployment (a slide on the practical/institutional angle — this is graded heavily)

- Every abstained claim is written to a review queue (Excel) with the claim,
  computed evidence, and reason.
- A UiPath REFramework automation (Dispatcher + Performer pattern) validates
  incoming claims, calls our API, routes answered vs. abstained results,
  creates a review ticket + email notification for abstentions, and escalates
  overdue tickets to a supervisor after N days.
- Full design docs exist: a Process Definition Document (as-is vs. to-be
  workflows), a Solution Design Document (queue schema, exception rules,
  retry policy), a click-by-click UiPath Studio build guide, and a 23-case
  test matrix.
- Business exceptions (missing table, empty claim, duplicate ID) are caught
  before spending an LLM call; system exceptions (API down) are retried,
  business exceptions are not.
- Key framing for the slide: **the size of the human-review queue is not an
  arbitrary business rule — it is a direct, statistically quantified
  consequence of the chosen error-rate guarantee (2%/5%/10%).**

---

## 8. What's done vs. what's still in progress (an honest "status" slide — presentation is tomorrow, full run is not finished)

**Done and working:**
- Full data pipeline (TabFact loaded, numeric filter, claim typing)
- NumNear-TabFact benchmark built and validated (53,472 variants)
- Similarity analysis complete (the 0.961 result above)
- Core verification system (JSON check language, executor, LLM client with
  caching/retry), running on a local LLM (Qwen2.5-7B-Instruct via Ollama)
- Conformal risk-control calibration code, implemented per the published
  "conformal risk control" framework (Angelopoulos et al., ICLR 2024)
- 50-claim pilot run complete (real numbers in Section 5 above), validating
  the full pipeline end-to-end
- FastAPI service, tested end-to-end with real claims, including a full
  TRUE/FALSE/abstain demo cycle
- A custom live web frontend (not just Streamlit) that calls the API
  directly, showing the verdict, agreement score, and every executed check
- Full RPA design (PDD, SDD, UiPath build guide, test cases, sample bot inputs)
- Streamlit demo (reviewer dashboard + live tester)
- Paper compiled in IEEEtran format (currently ~6 pages), all written
  sections original text with verified citations, including the real pilot
  numbers and an honest discussion of what they show

**In progress (why): compute time, not scope.**
- The full-scale evaluation (~17,000 claims across 4 methods) requires
  roughly 135,000 LLM calls. We first tried a free hosted API (Google
  Gemini) but it turned out to cap at exactly 500 requests/day — confirmed
  by a live quota error — so we moved to running locally, which removes the
  rate limit but is compute-bound on a single machine; the full run is
  estimated at ~3 days and is running in the background.
- Once complete: final accuracy/F1 numbers, risk-coverage curves, ablations
  (K=1/3/5), per-claim-type breakdown, and error analysis will be added —
  the paper and all scripts are already built to generate these
  automatically from the run's output.

---

## 9. Suggested slide order

1. Title
2. Problem / motivation (the citation gap + the near-miss example)
3. Why existing approaches don't solve this (related work, condensed)
4. Our three contributions (C1/C2/C3)
5. Architecture diagram
6. NumNear-TabFact + the 0.961 similarity result (this is your strongest
   visual — consider a bar/histogram)
7. Live system demo screenshot/example (the TRUE/FALSE fee example above)
8. RPA deployment architecture + why the review queue is statistically
   principled, not ad hoc
9. Current status (what's done vs. running)
10. Conclusion + SDG alignment + future work

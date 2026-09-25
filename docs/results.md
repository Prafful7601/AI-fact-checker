# Results Summary — Certified Numeric Verification

Real, measured results only. No fabricated numbers. Generated from
`results/logs/comparison_gemini_raw.jsonl` (primary, complete) and
`results/logs/full_run_raw.jsonl` (secondary, ongoing at time of writing).
Reproduce via `scripts/analyze_gemini_results.py` and `scripts/make_figures.py`.

## 1. Dataset

| | Count |
|---|---|
| TabFact total claims | 118,275 |
| Numeric claims (our filter) | 103,966 |
| Numeric claims, test split | 11,400 |
| NumNear-TabFact near-miss variants (total) | 53,472 |
| — derived from test-split tables | 5,474 |
| **Full evaluation set (original + near-miss test claims)** | **16,874** |

Full evaluation set split in half by claim (seed 42): first half → local
model, second half → hosted model.

## 2. The core motivation, confirmed

Mean cosine similarity (all-MiniLM-L6-v2) between an original TabFact claim
and its NumNear-TabFact near-miss: **0.961** (σ=0.045). 91.2% of pairs score
above 0.9 similarity; 74.5% above 0.95. A wrong numeric claim and its correct
counterpart are, to a standard sentence embedding, almost the same sentence.

## 3. Main accuracy results (Gemini 3.5 Flash-Lite, n=8,205, 97.3% of assigned half)

Test-half only (n=4,107: 2,812 original + 1,295 near-miss):

| Method | Acc. (original) | F1 (original) | Acc. (near-miss) | F1 (near-miss) |
|---|---|---|---|---|
| B1 (LLM-only) | 0.761 | 0.756 | 0.781 | 0.439 |
| B2 (+ confidence) | 0.740 | 0.740 | 0.824 | 0.452 |
| B3 (K=1 check) | 0.671 | 0.671 | 0.435 | 0.303 |
| **Ours (K=5)** | **0.701** | **0.700** | **0.468** | **0.319** |

**McNemar's test** (original test claims, Ours vs. each baseline):
- vs. B1: χ²=28.5, p=9.5×10⁻⁸ (B1 significantly better)
- vs. B2: χ²=13.0, p=3.1×10⁻⁴ (B2 significantly better)
- vs. B3: χ²=22.3, p=2.3×10⁻⁶ (**Ours significantly better** — K=5 sampling beats K=1)

95% bootstrap CIs are all within ±1.8 points of the point estimates above
(`results/tables/gemini_bootstrap_ci.csv`).

## 4. Cross-model comparison (the honest capability check)

| Model | Method | n | Accuracy | Unverifiable rate |
|---|---|---|---|---|
| Gemini 3.5 Flash-Lite (hosted) | B1 | 8,205 | 0.761 | 0.000 |
| Gemini 3.5 Flash-Lite (hosted) | B2 | 8,205 | 0.764 | 0.000 |
| Gemini 3.5 Flash-Lite (hosted) | B3 | 8,205 | 0.585 | 0.118 |
| Gemini 3.5 Flash-Lite (hosted) | Ours | 8,205 | 0.620 | 0.057 |
| Qwen2.5-7B-Instruct (local, ongoing) | B1 | 3,752 | 0.743 | 0.000 |
| Qwen2.5-7B-Instruct (local, ongoing) | B2 | 3,752 | 0.732 | 0.000 |
| Qwen2.5-7B-Instruct (local, ongoing) | B3 | 3,752 | 0.314 | 0.503 |
| Qwen2.5-7B-Instruct (local, ongoing) | Ours | 3,752 | 0.426 | 0.320 |

**Reading:** B1/B2 (free-text) degrade gracefully across model tiers. B3/Ours
(execution-based) degrade sharply — the local model's checks fail to
parse/execute (UNVERIFIABLE) 32-50% of the time vs. 6-12% for the hosted
model. Execution-agreement's reliability is conditional on the base model's
instruction-following capability at the specific check-generation sub-task,
not general language understanding.

## 5. The central finding: risk-coverage (conformal calibration)

Three confidence signals, calibrated independently, tested at
α ∈ {0.02, 0.05, 0.10, 0.15, 0.20, 0.30} (widened beyond the original
{0.02, 0.05, 0.10} once those all failed — see below):

| Signal | Works at α ≥ | Coverage at that α | Realised risk |
|---|---|---|---|
| Ours (within-method agreement, K=5) | **never** (up to 0.30) | 0.000 | n/a |
| B2 (self-reported confidence) | 0.15 | 0.882 | 0.131 |
| **Cross-method (Ours ∧ B2 agree)** | **0.10** | **0.439** | **0.088** |

**Why within-method agreement fails:** K=5 sampling only produces 6 possible
agreement values (0, 0.2, 0.4, 0.6, 0.8, 1.0). Even the best bucket (full
5/5 agreement, 67% of test claims) has a real error rate of 29.5% — above
every target we tested, including the most lenient (30%). The conformal
procedure correctly detects this and abstains on everything rather than
falsely certify a guarantee the data can't support. This is the calibration
math working as designed, on a confidence signal that turned out to be too
coarse for this task.

**Why cross-method agreement works better:** when the execution-based
verdict (Ours) and an independently-elicited free-text verdict (B2) agree,
that's a stronger correctness signal than either method's internal
self-confidence — two different reasoning paths landing on the same answer.
This combined signal is the one addition to the original method design;
everything else follows the original spec.

**Ablation — does more sampling fix within-method agreement?** K∈{1,3,5},
reconstructed from the same 5 already-sampled checks (no extra API cost):

| K | Raw accuracy | Coverage at α=0.10 |
|---|---|---|
| 1 (greedy) | 0.597 | 0.000 |
| 3 | 0.619 | 0.000 |
| 5 | 0.627 | 0.000 |

Raw accuracy improves modestly with K but coverage stays at zero throughout
— confirms the ceiling isn't a K=5-specific artifact; a much larger K, or a
qualitatively different signal, would be needed to fix within-method
agreement alone.

## 6. Per-claim-type breakdown (Ours, Gemini)

| Claim type | Acc. (original) | Acc. (near-miss) |
|---|---|---|
| lookup | 0.780 | 0.457 |
| count | 0.728 | 0.413 |
| comparison | 0.622 | 0.483 |
| superlative | 0.621 | 0.417 |
| aggregation | 0.652 | 0.608 |

Aggregation claims are the most robust to the near-miss perturbation (small
drop, 0.652→0.608) — plausibly because an aggregation check re-derives its
value from the whole column rather than matching one perturbed cell.

## 7. Why B1/B2 score *higher* on near-miss claims (a real behavioral finding, not a bug)

Near-miss claims are FALSE by construction. B1's FALSE-prediction rate jumps
from 35.5% (on original claims) to 78.1% (on near-miss claims) — a real
behavioral shift, not flat bias (a fixed-prior model would show the same
FALSE rate regardless of input). Breaking this down by perturbation type
shows it tracks difficulty exactly as expected:

| Perturbation type | n | B1 accuracy (= FALSE-prediction rate) |
|---|---|---|
| off-by-one (hardest) | 329 | 0.705 |
| round-number-change | 372 | 0.766 |
| magnitude-change | 342 | 0.787 |
| digit-swap (easiest) | 252 | 0.897 |

## 8. Error analysis (30 sampled failures per method, Gemini test set)

| Category | B1 | B2 | B3 | Ours |
|---|---|---|---|---|
| (genuine_)reasoning_error | 28 | 14 | 18 | 21 |
| format_error | 2 | 16 | — | — |
| wrong_column | — | — | 5 | 3 |
| wrong_filter | — | — | 2 | 3 |
| number_parsing_error | — | — | 5 | 3 |

**Two findings:**
1. On a capable model, the dominant failure mode for check-based methods is
   *semantic* (the check runs fine but encodes the wrong logic), not
   *syntactic* — the opposite of the local-model pattern, where malformed
   JSON dominated.
2. B2's two-line confidence format itself causes over half its failures
   (format_error) — a fixable engineering cost of asking for structured
   self-reported confidence, distinct from actual reasoning failures.

## 9. Cost and completion

- Gemini half: 8,205/8,437 claims (97.3%) completed before the prepaid
  budget (~$28/₹3,000) was exhausted. Real measured cost: ~$27.46.
- Ollama half: 3,752/8,437 claims (44.5%) as of this writing — a background,
  zero-cost, ongoing run (~30s/claim on local hardware).

## 10. Bottom line

- **C1 (NumNear-TabFact) is unconditionally solid** — the 0.961 similarity
  result doesn't depend on model choice at all.
- **C2 (execution-agreement) has real but limited value on its own** — it
  significantly beats a single check (K=1), but its confidence signal is too
  coarse to support strict conformal guarantees.
- **C3 (conformal calibration) works correctly** — including by correctly
  *refusing* to certify a guarantee the data doesn't support, which is the
  procedure behaving as designed, not a failure.
- **The novel finding this run surfaced**: cross-method agreement (combining
  execution-based and free-text verdicts) is a meaningfully better
  confidence signal than either method alone, and is the one piece that
  makes C3 produce a genuinely usable operating point (α=0.10 at 43.9%
  coverage).

# Novelty Check — Certified Numeric Verification

Date: 2026-09-23. Time-boxed web search (~20 min) against the three areas requested.
Conclusion up front: **no prior work combines (a) a numeric near-miss benchmark for
tables, (b) execution-agreement confidence from sampled program checks, and
(c) split-conformal risk control with a human-review escalation queue.** No stop
condition triggered — proceeding to Step 1.

## (a) Program-based table verification

- **Chen et al., ICLR 2020 — "TabFact: A Large-scale Dataset for Table-based Fact
  Verification"** (arXiv:1909.02164; repo: github.com/wenhuchen/Table-Fact-Checking).
  117,854 statements over 16,573 Wikipedia tables, ENTAILED/REFUTED labels. Proposes
  Table-BERT (linearize + encode) and the Latent Program Algorithm (LPA), a semantic
  parser that generates a program and executes it against the table.
  **Difference:** LPA is a *learned semantic parser trained on TabFact*, evaluated once
  on the original label distribution. It does not (i) test robustness to
  minimally-perturbed numeric near-misses, (ii) use LLM-generated JSON checks with a
  fixed schema executed by pandas, (iii) sample multiple checks for an agreement score,
  or (iv) attach any statistical risk guarantee or abstention mechanism. Our JSON check
  language and multi-sample agreement score are a zero-shot-LLM analogue of LPA's
  program-execution idea, but built specifically to expose numeric near-misses and to
  feed a conformal gate — neither of which TabFact's own methods address.

- **Binder** (LLM + SQL/Python program synthesis for table QA/verification),
  **Dater** (decompose table+question, self-consistency over decomposed sub-tables),
  **Chain-of-Table** (ICLR 2024, arXiv:2401.04398 — table itself evolves as the
  reasoning-chain intermediate state; greedy operation search, no self-consistency
  sampling), and **PAL / Program-of-Thoughts** (arXiv:2211.10435 / 2211.12588 —
  offload arithmetic to a Python interpreter for math word problems, not tables).
  **Difference:** all four target *accuracy* on general table QA/verification or math
  word problems via better program construction or search strategy. None targets the
  numeric-near-miss failure mode specifically, none reports an embedding-similarity
  analysis of true vs. minimally-perturbed claims, and none couples program execution
  to a conformal risk-control abstention layer with a quantified human-review workload.
  Chain-of-Table explicitly avoids self-consistency sampling (uses greedy search) —
  the opposite of our K-sample agreement approach, which needs sampling variance as
  the confidence signal.

## (b) Numerical perturbation in fact-checking

- **NumPert** (Aarnes & Setty, IJCNLP-AACL 2025 Student Research Workshop;
  arXiv:2511.09971) — systematically perturbs *numbers in claim/evidence pairs* for
  open-domain veracity prediction and shows accuracy drops up to 62% under controlled
  numerical perturbations, plus a context-length interaction study.
  **Difference:** NumPert's evidence is free text (open-domain claim/evidence pairs),
  not tables, so there is no structured-check execution step and no table-derived
  aggregation labels (count/sum/avg). It measures the robustness *problem* only — no
  execution-based defense, no confidence/agreement mechanism, no conformal calibration,
  and no benchmark construction protocol tied to table semantics (our four perturbation
  types — off-by-one, digit swap, magnitude change, round-number change — are
  table/label-verified, i.e. we re-check the perturbed claim against the table to
  confirm the label actually flips, which NumPert-style text-evidence perturbation
  cannot do because aggregated numbers usually aren't written verbatim in a table cell).

- **QuanTemp** (arXiv:2403.17169, github.com/factiverse/QuanTemp) — first large-scale
  real-world benchmark (15k+ claims from 45 fact-checking orgs) dedicated to numerical/
  temporal claims, with a taxonomy of statistical/temporal/comparison/interval claims;
  evidence is retrieved open-domain text, best baseline macro-F1 ≈ 58.3.
  **Difference:** QuanTemp is naturally-occurring numeric claims verified against
  retrieved web text, not a controlled minimal-pair perturbation benchmark, and not
  tabular. It has no execution-based verification layer and no conformal component.
  Our NumNear-TabFact is complementary: a *programmatically constructed, label-flip-
  verified* near-miss benchmark specifically over TabFact's tables, letting us isolate
  the "semantically near-identical, numerically wrong" failure mode in a controlled way
  that QuanTemp's naturally-occurring claims cannot guarantee.

## (c) Conformal abstention / factuality for LLMs

- **Mohri & Hashimoto, ICML 2024 — "Language Models with Conformal Factuality
  Guarantees"** (proceedings.mlr.press/v235/mohri24a.html; arXiv:2402.10978) — frames
  factuality as an entailment-set uncertainty-quantification problem and uses a
  conformal back-off procedure (progressively less specific claims) to give high-
  probability correctness guarantees for long-form generation.
  **Difference:** targets open-ended long-form generation (retain/remove sub-claims
  via back-off), not a binary verify/abstain decision over a table-grounded numeric
  claim, and has no notion of executable checks or agreement-based confidence.

- **Abbasi-Yadkori et al., 2024 — "Mitigating LLM Hallucinations via Conformal
  Abstention"** (arXiv:2405.01563, NeurIPS 2024) — self-consistency + LLM self-
  similarity scoring, calibrated via conformal prediction to bound hallucination rate
  on open-domain QA (TriviaQA, Temporal Sequences), evaluated on Gemini Pro.
  **Difference:** confidence comes from *LLM self-judged* answer similarity, not from
  executing independently-generated structured checks against ground-truth data; no
  table setting; no cost/workload analysis for a downstream human-review queue.

- Other 2024-2025 conformal/selective-prediction work found (ConU, COIN, Conformal
  Linguistic Calibration, Conformal Abstention Framework generalizations, "Certified
  Against Which Oracle?" for text-to-SQL, Conformal Aggregation for CoT) generalizes
  or extends conformal abstention machinery (e.g., to SQL execution correctness, or to
  chain-of-thought aggregation) but none of it is applied to: table numeric fact
  verification + a purpose-built numeric near-miss benchmark + an operational RPA
  human-escalation workflow, which is the specific combination C1+C2+C3 targets.
  Note "Certified Against Which Oracle? ... Conformal Abstention for Text-to-SQL"
  (arXiv:2609.25938) is the closest adjacent idea (execution-based correctness label +
  conformal abstention) but is about SQL query generation correctness, not fact
  verification of natural-language numeric claims against tables, and does not include
  a near-miss robustness benchmark or human-review deployment layer.

## Verdict

No single prior work does C1 (numeric near-miss table benchmark, label-flip verified)
+ C2 (multi-sample execution-agreement confidence) + C3 (conformal risk control with
quantified RPA escalation workload) together on tables. Proceeding to Step 1 (data).

All papers above were confirmed to exist via web search (titles, venues, arXiv IDs
cross-checked against arXiv/ACL Anthology/ICML/NeurIPS listings). Exact page numbers
and BibTeX details will be verified again when refs.bib is built; anything not
independently confirmed will be marked TODO-VERIFY there.

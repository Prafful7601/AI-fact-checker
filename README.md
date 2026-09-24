# Certified Numeric Verification

Guaranteed-error fact-checking of numeric claims over tables, with a
conformal-risk-controlled abstention gate and a UiPath RPA escalation
workflow for the claims the system won't answer on its own.

Paper: "Certified Numeric Verification: Guaranteed-Error Fact-Checking of
Numeric Claims over Tables with Automated Human Escalation" (MCA, KIET Group
of Institutions). See `paper/main.tex` / `paper/main.pdf`.

LLMs verify numeric claims about tables unreliably — they miscount rows,
mis-sum columns, and get comparisons wrong — and citations don't fix this,
because an aggregated number (a count, a total, an average) is not written
anywhere in the source table to cite. This project replaces free-text LLM
verdicts with **executable, sampled checks** run deterministically with
pandas, calibrates the resulting agreement score with **split-conformal risk
control** so the error rate among answered claims is statistically bounded,
and routes everything else to an automated **UiPath RPA** review workflow.

## 0. Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas numpy scikit-learn scipy matplotlib pyyaml anthropic \
            google-genai ollama python-dotenv tenacity tqdm openpyxl \
            sentence-transformers streamlit fastapi "uvicorn[standard]" httpx pypdf
```

The LLM backend is provider-agnostic (`src/llm_client.py`): Anthropic,
Google Gemini, and local Ollama models are all supported from the same
`config.yaml`, with no code changes needed to add a new model to any of the
three. Set `models.default` in `config.yaml` to the model you want to use,
and provide credentials for whichever provider that model belongs to via a
local `.env` file (never commit this — it's gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...      # if using an anthropic model
GEMINI_API_KEY=...                # if using a gemini model
```

Ollama models need no API key, just a running local server:
```bash
# macOS: download Ollama.app from ollama.com, then
open -a Ollama --args hidden
ollama pull qwen2.5:7b-instruct
```

Seed is fixed at 42 everywhere. Every LLM call is cached to disk in `cache/`
(keyed by provider+model+prompt+temperature+a sampling nonce), so reruns of
any script are free and interrupted runs lose nothing.

**Note on model choice:** free tiers of hosted APIs are not designed for a
project at this scale. Anthropic requires a billing method to issue a key at
all; Google's Gemini free tier for `gemini-3.5-flash-lite` caps at a hard
**500 requests/day** (confirmed via a live `RESOURCE_EXHAUSTED` response),
against the ~135,000 calls a full evaluation run needs. This project
currently runs on a local model via Ollama, which removes the external
rate limit entirely at the cost of being slower per-call and less reliable
at the structured JSON-check task than a larger hosted model would be — see
the paper's Limitations section for the honest accuracy implications of that
tradeoff.

## 1. Data pipeline (no LLM/API needed)

```bash
# Clone TabFact if not already present under data/Table-Fact-Checking
git clone https://github.com/wenhuchen/Table-Fact-Checking data/Table-Fact-Checking

# Merge r1+r2 collected data, tag claim types, filter the numeric subset,
# write data/processed/tabfact_all.jsonl + dataset_summary.json
python3 scripts/build_dataset.py

# Build NumNear-TabFact (C1): programmatic, label-flip-verified numeric
# near-miss benchmark from TRUE claims in train+test.
python3 scripts/build_nearmiss.py

# Cosine-similarity analysis of original vs. near-miss claim pairs
# (all-MiniLM-L6-v2) -> results/tables/similarity_stats.csv,
# results/figures/similarity_histogram.pdf
python3 scripts/compute_similarity.py

# Stratified calibration/test split of the test-split numeric claims and the
# test-derived near-miss claims (by label x claim_type) -> eval_splits.json
python3 scripts/build_splits.py
```

Exact counts as of the last run (see `data/processed/dataset_summary.json`
and `numnear_summary.json` for the authoritative numbers): 118,275 total
TabFact claims; 103,966 numeric claims (11,400 in the test split); 53,472
NumNear-TabFact near-miss variants (5,474 derived from test-split tables).
Mean cosine similarity between an original claim and its near-miss:
**0.961** (91.2% of pairs above 0.9) — the quantitative core of the paper's
motivation.

## 2. Pilot run (hard gate before the full run)

```bash
python3 scripts/pilot.py
```

Runs B1/B2/B3/Ours(K=5) on 50 sampled claims (35 original + 15 near-miss),
prints accuracy per method plus an API-call/cost/time projection for the
full run, and writes `results/logs/pilot_results.json`. **Review this before
running the full evaluation.**

## 3. Full evaluation

```bash
python3 scripts/run_full_eval.py --batch-size 20
```

Evaluates every claim in `data/processed/eval_splits.json` (calibration +
test halves, both original and near-miss) with all four methods, writing
incrementally to `results/logs/full_run_raw.jsonl` after every batch so a
crash or interruption loses at most one batch (already-completed claims are
skipped on rerun). Use a small `--batch-size` on a slow/local model so
progress is visible and checkpoints are frequent — a large batch size can
mean hours between writes.

```bash
python3 scripts/evaluate.py         # metrics, conformal calibration, ablations -> results/tables/, paper/tables/
python3 scripts/error_analysis.py   # categorised failure sample -> results/tables/error_analysis.csv
```

## 4. Verifier API (the RPA integration point)

```bash
uvicorn api.server:app --host 127.0.0.1 --port 8008
```

- `GET /health` -> `{status, llm_available, model}`
- `POST /verify` -> `{verdict, agreement_score, executed_checks,
  computed_values, reason, latency_ms, sent_to_review}`; error codes: 400
  (bad input), 422 (unparsable table), 503 (LLM unavailable).

Every abstained claim is appended to `results/review_queue.xlsx`. See
`docs/PDD.md` and `docs/SDD.md` for the full process design, and
`docs/uipath_build_guide.md` for the click-by-click UiPath Studio build.

Sample bot inputs: `input/claims.xlsx` + `input/tables/*.csv` (includes 4
deliberately bad rows for exception-handling tests). Test matrix:
`docs/test_cases.xlsx` (23 cases).

## 5. Demo

**Frontend** (primary demo UI — calls the API directly, no build step):
```bash
cd frontend && python3 -m http.server 8800
# open http://localhost:8800/index.html
```

**Streamlit** (secondary reviewer dashboard):
```bash
streamlit run demo/app.py
```

See `docs/demo_day_checklist.md` for a full pre-flight/demo script.

## 6. Paper

```bash
cd paper && tectonic main.tex   # or any IEEEtran-capable LaTeX toolchain
```

`docs/novelty_check.md` documents how this differs from prior work
(TabFact, Binder, Dater, Chain-of-Table, PAL, NumPert, QuanTemp, conformal
factuality/abstention literature).

## Repository layout

```
config.yaml                  model/provider/seed/paths/experiment configuration
src/                         core library (data, checks, LLM client, verifier, conformal)
api/server.py                FastAPI wrapper (UiPath integration point)
frontend/index.html          standalone demo UI (calls the API directly)
scripts/                     data-build, pilot, full-run, and evaluation scripts
data/Table-Fact-Checking/    cloned TabFact repo (tables + claims + splits) -- gitignored, regenerate via clone
data/processed/              built datasets (tabfact_all.jsonl, numnear_tabfact.jsonl, ...) -- gitignored, regenerate via scripts/
cache/                       disk cache of every LLM call -- gitignored
results/                     tables, figures, logs, review_queue.xlsx
input/                       sample RPA bot inputs (claims.xlsx, tables/)
docs/                        novelty_check.md, PDD.md, SDD.md, uipath_build_guide.md, test_cases.xlsx,
                              presentation_briefing.md, demo_day_checklist.md
demo/app.py                  Streamlit reviewer dashboard + live verifier
paper/                       IEEEtran manuscript (main.tex, refs.bib, tables/, figures/) + compiled main.pdf
```

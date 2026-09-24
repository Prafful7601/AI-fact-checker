# Demo day checklist (for tomorrow's presentation)

## Why do this tonight, not live tomorrow
Every LLM call is cached to disk by `src/llm_client.py` (keyed by
model+prompt hash). If you run through your demo claims once tonight, the
exact same calls tomorrow hit the cache and return instantly — no waiting on
the local model to (re)generate. **Run every claim you plan to show at least
once before the presentation.** The system now runs on a local model
(Qwen2.5-7B-Instruct via Ollama) — no internet dependency at all for the
demo, which is actually safer for a live venue than a hosted API.

## Setup (do this once, or confirm it's still running)

Ollama itself runs as a background app (menu bar), started via:
```bash
open -a Ollama --args hidden
```
Confirm it's up:
```bash
curl -s http://localhost:11434/api/version
```

## Start the two services (separate terminal tabs/windows)

**Terminal 1 — the verifier API (start this first):**
```bash
cd "/Users/praffulg/RAA Research"
source .venv/bin/activate
uvicorn api.server:app --host 127.0.0.1 --port 8008
```
Leave this running. Confirm it's up: open http://127.0.0.1:8008/health in a
browser — should show `{"status":"ok","llm_available":true,"model":"qwen2.5:7b-instruct"}`.

**Terminal 2 — the frontend (the primary visual demo):**
```bash
cd "/Users/praffulg/RAA Research/frontend"
python3 -m http.server 8800
```
Open http://localhost:8800/index.html in a browser. It shows a table
picker (with 3 preloaded college tables), a claim box with example
true/false/near-miss buttons, and a live results panel with the verdict,
agreement score, and every executed check.

**Optional Terminal 3 — the Streamlit reviewer dashboard (secondary):**
```bash
cd "/Users/praffulg/RAA Research"
source .venv/bin/activate
streamlit run demo/app.py
```

## Pre-warm these exact demo claims tonight

Open the frontend, pick each table, and run these (already confirmed to
work against the real system):

| Table | Claim | What you should see |
|---|---|---|
| Fee structure | `the total fee for MCA semester 1 is 95000` | **TRUE**, high agreement, computed value 95000 |
| Fee structure | `the total fee for MCA semester 1 is 99000` | **ABSTAIN** (or FALSE), computed value 95000 across valid checks — contradicts the claim's 99000 |
| Semester results | `prafful gupta has a cgpa of 8.9 in semester 3` | **TRUE** |
| Semester results | `prafful gupta has a cgpa of 9.9 in semester 3` | **FALSE** or **ABSTAIN** |
| Scholarship eligibility | `rohit verma is eligible for the scholarship` | **TRUE** |
| Scholarship eligibility | `aatir khan is eligible for the scholarship` | **FALSE** or **ABSTAIN** |

Because this is a small local model, don't be surprised if some runs land on
**ABSTAIN** instead of a clean TRUE/FALSE — that's expected, and it's
actually a good thing to show live: point at the executed checks panel and
explain that low agreement correctly triggers human review instead of a
confident guess.

Also run a couple of the `input/claims.xlsx` "bad row" examples directly
against the API (for the RPA/exception-handling story):

```bash
# missing table -> 422
curl -s -X POST http://127.0.0.1:8008/verify -H "Content-Type: application/json" \
  -d '{"claim":"x","table_path":"does_not_exist.csv"}'

# empty claim -> 400
curl -s -X POST http://127.0.0.1:8008/verify -H "Content-Type: application/json" \
  -d '{"claim":"","table_path":"input/tables/fee_structure.csv"}'
```

## What to say about the false/near-miss examples
This is the actual thesis of the paper: the claim "...is 99000" is nearly
identical, word for word, to "...is 95000" — that's the "near-miss" problem.
Point at the checks panel: it shows the JSON program the model generated and
the *computed number* pandas actually calculated (95000), which directly
contradicts the claim's stated 99000 — that's the auditable evidence a
citation-only system could never produce, because 95000 isn't written
anywhere in the table; it's the sum of two cells.

## If something breaks live
- If a port is already in use: `pkill -f "uvicorn api.server:app"` or
  `pkill -f "http.server 8800"`, then restart.
- If Ollama seems unresponsive, restart it: `pkill -x Ollama; open -a Ollama --args hidden`.
- Pre-warmed claims hit the cache and return in well under a second either
  way — stick to those for anything time-sensitive in front of an audience.
- The paper PDF (`paper/main.pdf`) and this repo's README are your fallback
  if the live demo has any issue — the system's real, cited, measured
  results (dataset stats, the 0.961 similarity number, the 50-claim pilot
  numbers) stand on their own.

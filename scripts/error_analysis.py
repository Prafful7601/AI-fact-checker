#!/usr/bin/env python3
"""Step 3 error analysis: up to 30 failures per method (original test claims),
categorised into {invalid_json, wrong_column, wrong_filter,
number_parsing_error, genuine_reasoning_error} for check-based methods
(B3, Ours), or {format_error, reasoning_error} for free-text methods
(B1, B2). Writes results/tables/error_analysis.csv and
results/logs/error_examples.json with the actual failing examples."""
from __future__ import annotations
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "results" / "logs" / "full_run_raw.jsonl"
SEED = 42
N_PER_METHOD = 30


def gold_str(label: int) -> str:
    return "TRUE" if label == 1 else "FALSE"


def categorize_check_based(rec_method: dict) -> str:
    checks = rec_method.get("executed_checks", [])
    if not checks:
        return "invalid_json"
    # use the first executed check as representative (majority-vote methods
    # may have several; the categorisation targets the dominant failure mode)
    chk = checks[0]
    if chk.get("check") is None:
        return "invalid_json"
    result = chk.get("result", {})
    if not result.get("ok"):
        err = (result.get("error") or "").lower()
        if "unknown column" in err or "unknown target_column" in err:
            return "wrong_column"
        if "filter matched no rows" in err:
            return "wrong_filter"
        if "parse" in err or "numeric" in err:
            return "number_parsing_error"
        return "number_parsing_error"
    return "genuine_reasoning_error"


def categorize_freetext(rec_method: dict) -> str:
    if rec_method["verdict"] not in ("TRUE", "FALSE"):
        return "format_error"
    return "reasoning_error"


def main():
    if not RAW_PATH.exists():
        print(f"ERROR: {RAW_PATH} not found. Run scripts/run_full_eval.py first.")
        sys.exit(1)
    records = [json.loads(l) for l in open(RAW_PATH) if json.loads(l)["kind"] == "original"
               and json.loads(l)["half"] == "test"]
    rng = random.Random(SEED)

    all_examples = {}
    summary_rows = []
    for method in ("b1", "b2", "b3", "ours"):
        failures = [r for r in records if r[method]["verdict"] != gold_str(r["label"])]
        rng.shuffle(failures)
        sample = failures[:N_PER_METHOD]
        cats = Counter()
        examples = []
        for r in sample:
            cat = (categorize_freetext(r[method]) if method in ("b1", "b2")
                   else categorize_check_based(r[method]))
            cats[cat] += 1
            examples.append({
                "id": r["id"], "claim_type": r["claim_type"], "gold": gold_str(r["label"]),
                "predicted": r[method]["verdict"], "category": cat,
                "detail": r[method].get("raw_text") or r[method].get("executed_checks"),
            })
        all_examples[method] = examples
        for cat, n in cats.items():
            summary_rows.append([method, cat, n])
        print(f"{method}: {len(failures)} failures in test set, sampled {len(sample)}, categories: {dict(cats)}")

    import csv
    out_csv = ROOT / "results" / "tables" / "error_analysis.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["method", "category", "count"])
        w.writerows(summary_rows)

    with open(ROOT / "results" / "logs" / "error_examples.json", "w") as f:
        json.dump(all_examples, f, indent=2, default=str)
    print(f"Wrote {out_csv} and results/logs/error_examples.json")


if __name__ == "__main__":
    main()

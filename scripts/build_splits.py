#!/usr/bin/env python3
"""Splits the TabFact test-split numeric claims, and the test-derived
NumNear-TabFact near-miss claims, into calibration/test halves stratified by
(label, claim_type). Seed 42. Writes data/processed/eval_splits.json."""
from __future__ import annotations
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 42
CAL_FRACTION = 0.5


def stratified_split(items: list[dict], key_fn, frac: float, seed: int):
    groups = defaultdict(list)
    for it in items:
        groups[key_fn(it)].append(it["id"])
    rng = random.Random(seed)
    cal_ids, test_ids = [], []
    for key, ids in groups.items():
        ids = sorted(ids)  # deterministic order before shuffling
        rng.shuffle(ids)
        n_cal = round(len(ids) * frac)
        cal_ids.extend(ids[:n_cal])
        test_ids.extend(ids[n_cal:])
    return cal_ids, test_ids


def main():
    all_records = [json.loads(l) for l in open(ROOT / "data" / "processed" / "tabfact_all.jsonl")]
    eval_claims = [r for r in all_records if r["split"] == "test" and r["is_numeric"]]
    items = [{"id": r["claim_id"], "label": r["label"], "claim_type": r["claim_type"]} for r in eval_claims]
    cal_ids, test_ids = stratified_split(items, lambda x: (x["label"], x["claim_type"]), CAL_FRACTION, SEED)

    nearmiss = [json.loads(l) for l in open(ROOT / "data" / "processed" / "numnear_tabfact.jsonl")]
    nm_test = [r for r in nearmiss if r["split"] == "test"]
    nm_items = [{"id": r["nearmiss_id"], "label": r["label"], "claim_type": r["claim_type"]} for r in nm_test]
    nm_cal_ids, nm_test_ids = stratified_split(nm_items, lambda x: (x["label"], x["claim_type"]), CAL_FRACTION, SEED)

    out = {
        "seed": SEED, "calibration_fraction": CAL_FRACTION,
        "original": {"total": len(items), "calibration": cal_ids, "test": test_ids},
        "nearmiss": {"total": len(nm_items), "calibration": nm_cal_ids, "test": nm_test_ids},
    }
    out_path = ROOT / "data" / "processed" / "eval_splits.json"
    with open(out_path, "w") as f:
        json.dump(out, f)

    print(f"Original numeric test claims: {len(items)} -> calibration {len(cal_ids)} / test {len(test_ids)}")
    print(f"Near-miss (test-derived) claims: {len(nm_items)} -> calibration {len(nm_cal_ids)} / test {len(nm_test_ids)}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

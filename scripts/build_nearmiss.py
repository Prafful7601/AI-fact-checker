#!/usr/bin/env python3
"""Step 1 / C1: build NumNear-TabFact from TRUE claims in train+test splits.
Fully programmatic (no LLM calls). Writes data/processed/numnear_tabfact.jsonl
and a summary with exact counts, per perturbation type and split."""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.nearmiss import generate_nearmiss_variants

ROOT = Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT / "data" / "Table-Fact-Checking" / "data" / "all_csv"
IN_PATH = ROOT / "data" / "processed" / "tabfact_all.jsonl"
OUT_PATH = ROOT / "data" / "processed" / "numnear_tabfact.jsonl"
SEED = 42


def main():
    records = [json.loads(l) for l in open(IN_PATH)]
    true_claims = [r for r in records if r["label"] == 1 and r["split"] in ("train", "test")
                   and r["is_numeric"]]
    print(f"Candidate TRUE numeric claims (train+test): {len(true_claims)}")

    out = []
    counts_by_split = Counter()
    counts_by_type = Counter()
    skipped_no_anchor = 0
    for i, rec in enumerate(true_claims):
        table_csv = str(TABLES_DIR / rec["table_id"])
        try:
            variants = generate_nearmiss_variants(rec["claim"], table_csv, seed=SEED + i)
        except Exception as e:
            variants = []
        if not variants:
            skipped_no_anchor += 1
            continue
        for v in variants:
            out.append({
                "nearmiss_id": f"{rec['claim_id']}::{v['perturbation_type']}",
                "table_id": rec["table_id"],
                "split": rec["split"],
                "claim_type": rec["claim_type"],
                "original_claim": rec["claim"],
                "original_claim_id": rec["claim_id"],
                "perturbed_claim": v["perturbed_claim"],
                "perturbation_type": v["perturbation_type"],
                "anchor_value": v["anchor_value"],
                "perturbed_value": v["perturbed_value"],
                "label": 0,  # near-miss is FALSE by construction
            })
            counts_by_split[rec["split"]] += 1
            counts_by_type[v["perturbation_type"]] += 1
        if (i + 1) % 5000 == 0:
            print(f"  processed {i+1}/{len(true_claims)} candidates, {len(out)} variants so far")

    with open(OUT_PATH, "w") as f:
        for rec in out:
            f.write(json.dumps(rec) + "\n")

    n_source_claims_with_variant = len(set(r["original_claim_id"] for r in out))
    summary = {
        "candidate_true_numeric_claims": len(true_claims),
        "source_claims_with_at_least_one_variant": n_source_claims_with_variant,
        "source_claims_skipped_no_anchor": skipped_no_anchor,
        "total_nearmiss_variants": len(out),
        "variants_by_split": dict(counts_by_split),
        "variants_by_perturbation_type": dict(counts_by_type),
    }
    with open(ROOT / "data" / "processed" / "numnear_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    print(f"Wrote {len(out)} near-miss variants to {OUT_PATH}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Step 1: build the unified TabFact claim dataset (all splits), tag claim
types, and mark the numeric subset. Writes data/processed/tabfact_all.jsonl
and prints exact counts (no sampling, no LLM calls)."""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.claim_types import classify_claim_type, is_numeric_claim

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / "data" / "Table-Fact-Checking"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


def load_ids(name: str) -> set:
    return set(json.load(open(REPO / "data" / name)))


def main():
    r1 = json.load(open(REPO / "collected_data" / "r1_training_all.json"))
    r2 = json.load(open(REPO / "collected_data" / "r2_training_all.json"))

    merged = {}
    for d in (r1, r2):
        for table_id, (stmts, labels, caption) in d.items():
            entry = merged.setdefault(table_id, {"stmts": [], "labels": [], "caption": caption})
            entry["stmts"].extend(stmts)
            entry["labels"].extend(labels)

    train_ids = load_ids("train_id.json")
    val_ids = load_ids("val_id.json")
    test_ids = load_ids("test_id.json")

    def split_of(table_id: str) -> str:
        if table_id in train_ids:
            return "train"
        if table_id in val_ids:
            return "val"
        if table_id in test_ids:
            return "test"
        return "unknown"

    records = []
    counts = Counter()
    numeric_counts = Counter()
    claim_type_counts = Counter()
    for table_id, entry in merged.items():
        split = split_of(table_id)
        for i, (stmt, label) in enumerate(zip(entry["stmts"], entry["labels"])):
            claim_id = f"{table_id}::{i}"
            numeric = is_numeric_claim(stmt)
            ctype = classify_claim_type(stmt) if numeric else "other"
            rec = {
                "claim_id": claim_id,
                "table_id": table_id,
                "claim": stmt,
                "label": int(label),
                "split": split,
                "caption": entry["caption"],
                "is_numeric": numeric,
                "claim_type": ctype,
            }
            records.append(rec)
            counts[split] += 1
            if numeric:
                numeric_counts[split] += 1
                claim_type_counts[ctype] += 1

    out_path = OUT / "tabfact_all.jsonl"
    with open(out_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")

    print(f"Wrote {len(records)} total claims to {out_path}")
    print("Counts per split (all claims):", dict(counts))
    print("Counts per split (numeric claims):", dict(numeric_counts))
    print("Numeric claim total:", sum(numeric_counts.values()))
    print("Claim-type breakdown (numeric claims only):", dict(claim_type_counts))

    summary = {
        "total_claims": len(records),
        "counts_per_split": dict(counts),
        "numeric_counts_per_split": dict(numeric_counts),
        "numeric_total": sum(numeric_counts.values()),
        "claim_type_breakdown": dict(claim_type_counts),
    }
    with open(OUT / "dataset_summary.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()

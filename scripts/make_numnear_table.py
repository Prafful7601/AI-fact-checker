#!/usr/bin/env python3
"""Generates paper/tables/numnear_stats.tex from data/processed/numnear_summary.json
and results/tables/similarity_stats.csv (real, already-computed numbers)."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
summary = json.load(open(ROOT / "data" / "processed" / "numnear_summary.json"))
sim_rows = list(csv.DictReader(open(ROOT / "results" / "tables" / "similarity_stats.csv")))
sim_by_group = {r["group"]: r for r in sim_rows}

nearmiss_records = [json.loads(l) for l in open(ROOT / "data" / "processed" / "numnear_tabfact.jsonl")]
test_count_by_type = {}
for r in nearmiss_records:
    if r["split"] == "test":
        test_count_by_type[r["perturbation_type"]] = test_count_by_type.get(r["perturbation_type"], 0) + 1

perturb_order = ["off_by_one", "digit_swap", "magnitude_change", "round_number_change"]
lines = []
lines.append(r"\begin{table}[t]")
lines.append(r"\centering")
lines.append(r"\caption{NumNear-TabFact construction statistics and per-type cosine similarity (all-MiniLM-L6-v2) between original and near-miss claims.}")
lines.append(r"\label{tab:numnear-stats}")
lines.append(r"\begin{tabular}{lrrr}")
lines.append(r"\toprule")
lines.append(r"Perturbation type & \#Variants & \#Test & Mean sim.\\")
lines.append(r"\midrule")
by_type = summary["variants_by_perturbation_type"]
for ptype in perturb_order:
    n = by_type.get(ptype, 0)
    n_test = test_count_by_type.get(ptype, 0)
    sim = sim_by_group.get(ptype, {}).get("mean", "--")
    sim_str = f"{float(sim):.3f}" if sim != "--" else "--"
    label = ptype.replace("_", " ")
    lines.append(f"{label} & {n:,} & {n_test:,} & {sim_str} \\\\")
lines.append(r"\midrule")
overall = sim_by_group.get("overall", {})
lines.append(
    f"\\textbf{{Total}} & {summary['total_nearmiss_variants']:,} & "
    f"{summary['variants_by_split'].get('test', 0):,} & "
    f"{float(overall.get('mean', 0)):.3f} \\\\"
)
lines.append(r"\bottomrule")
lines.append(r"\end{tabular}")
lines.append(r"\end{table}")

out_path = ROOT / "paper" / "tables" / "numnear_stats.tex"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text("\n".join(lines) + "\n")
print(f"Wrote {out_path}")
print("\n".join(lines))

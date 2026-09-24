#!/usr/bin/env python3
"""C1(a): cosine similarity between original and perturbed claims using
all-MiniLM-L6-v2, to demonstrate the near-identical-meaning / different-value
problem. Writes results/tables/similarity_stats.csv and the raw per-pair
similarities to data/processed/nearmiss_similarity.jsonl, plus a histogram
figure (results/figures/similarity_histogram.pdf)."""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "processed" / "numnear_tabfact.jsonl"
OUT_JSONL = ROOT / "data" / "processed" / "nearmiss_similarity.jsonl"
OUT_CSV = ROOT / "results" / "tables" / "similarity_stats.csv"
OUT_FIG = ROOT / "results" / "figures" / "similarity_histogram.pdf"
SEED = 42


def main():
    records = [json.loads(l) for l in open(IN_PATH)]
    originals = [r["original_claim"] for r in records]
    perturbed = [r["perturbed_claim"] for r in records]

    model = SentenceTransformer("all-MiniLM-L6-v2")
    emb_orig = model.encode(originals, batch_size=256, show_progress_bar=True, normalize_embeddings=True)
    emb_pert = model.encode(perturbed, batch_size=256, show_progress_bar=True, normalize_embeddings=True)
    sims = np.sum(emb_orig * emb_pert, axis=1)  # cosine sim, since normalized

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSONL, "w") as f:
        for r, s in zip(records, sims):
            f.write(json.dumps({"nearmiss_id": r["nearmiss_id"], "perturbation_type": r["perturbation_type"],
                                 "cosine_similarity": float(s)}) + "\n")

    overall = {
        "n_pairs": len(sims),
        "mean": float(np.mean(sims)),
        "std": float(np.std(sims)),
        "median": float(np.median(sims)),
        "p5": float(np.percentile(sims, 5)),
        "p95": float(np.percentile(sims, 95)),
        "frac_above_0.9": float(np.mean(sims > 0.9)),
        "frac_above_0.95": float(np.mean(sims > 0.95)),
    }
    print(json.dumps(overall, indent=2))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    import csv
    by_type = {}
    for r, s in zip(records, sims):
        by_type.setdefault(r["perturbation_type"], []).append(s)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "n", "mean", "std", "median", "p5", "p95"])
        w.writerow(["overall", overall["n_pairs"], overall["mean"], overall["std"],
                    overall["median"], overall["p5"], overall["p95"]])
        for ptype, vals in sorted(by_type.items()):
            vals = np.array(vals)
            w.writerow([ptype, len(vals), float(np.mean(vals)), float(np.std(vals)),
                        float(np.median(vals)), float(np.percentile(vals, 5)), float(np.percentile(vals, 95))])
    print(f"Wrote {OUT_CSV}")

    # figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.size": 9})
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    ax.hist(sims, bins=40, color="#4c72b0", edgecolor="black", linewidth=0.3)
    ax.set_xlabel("Cosine similarity (original vs. near-miss claim)")
    ax.set_ylabel("Count")
    ax.axvline(float(np.mean(sims)), color="black", linestyle="--", linewidth=1,
               label=f"mean={np.mean(sims):.3f}")
    ax.legend(fontsize=7)
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG)
    print(f"Wrote {OUT_FIG}")

    with open(ROOT / "data" / "processed" / "similarity_summary.json", "w") as f:
        json.dump(overall, f, indent=2)


if __name__ == "__main__":
    main()

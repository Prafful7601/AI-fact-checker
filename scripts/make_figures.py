#!/usr/bin/env python3
"""Generates all paper figures from the real computed results in
results/tables/. IEEE-style: serif font, single-column width (~3.5in),
readable in greyscale (distinct markers/hatching, not just color)."""
from __future__ import annotations
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "results" / "tables"
RESULTS_FIGS = ROOT / "results" / "figures"
PAPER_FIGS = ROOT / "paper" / "figures"
for d in (RESULTS_FIGS, PAPER_FIGS):
    d.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "serif", "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
})

MARKERS = {"ours_agreement": "o", "b2_confidence": "s", "cross_method": "^"}
LABELS = {"ours_agreement": "Ours (agreement)", "b2_confidence": "B2 (self-conf.)", "cross_method": "Cross-method"}
LINESTYLES = {"ours_agreement": "--", "b2_confidence": ":", "cross_method": "-"}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(RESULTS_FIGS / name)
    fig.savefig(PAPER_FIGS / name)
    print(f"Wrote {name}")


def read_csv(name):
    with open(TABLES / name) as f:
        return list(csv.DictReader(f))


def fig_risk_coverage():
    rows = read_csv("gemini_risk_coverage.csv")
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    for sig in ("ours_agreement", "b2_confidence", "cross_method"):
        sig_rows = sorted([r for r in rows if r["signal"] == sig], key=lambda r: float(r["alpha"]))
        alphas = [float(r["alpha"]) for r in sig_rows]
        risks = [float(r["realised_risk"]) for r in sig_rows]
        ax.plot(alphas, risks, marker=MARKERS[sig], linestyle=LINESTYLES[sig],
                label=LABELS[sig], color="black", markerfacecolor="white", markersize=5)
    lims = [0, 0.32]
    ax.plot(lims, lims, color="gray", linewidth=0.7, linestyle="-", alpha=0.6, label="target = realised")
    ax.set_xlabel(r"Target risk $\alpha$")
    ax.set_ylabel("Realised risk (test half)")
    ax.set_xlim(0, 0.32)
    ax.set_ylim(0, 0.32)
    ax.legend(fontsize=6.5, loc="upper left")
    save(fig, "risk_coverage_curve.pdf")


def fig_coverage_vs_alpha():
    rows = read_csv("gemini_risk_coverage.csv")
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    for sig in ("ours_agreement", "b2_confidence", "cross_method"):
        sig_rows = sorted([r for r in rows if r["signal"] == sig], key=lambda r: float(r["alpha"]))
        alphas = [float(r["alpha"]) for r in sig_rows]
        cov = [float(r["coverage"]) for r in sig_rows]
        ax.plot(alphas, cov, marker=MARKERS[sig], linestyle=LINESTYLES[sig],
                label=LABELS[sig], color="black", markerfacecolor="white", markersize=5)
    ax.set_xlabel(r"Target risk $\alpha$")
    ax.set_ylabel("Coverage (fraction answered)")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(fontsize=6.5, loc="upper left")
    save(fig, "coverage_vs_alpha.pdf")


def fig_accuracy_by_confidence():
    rows = read_csv("gemini_accuracy_by_confidence.csv")
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.4), sharey=True)
    sig_order = ["ours_agreement", "b2_confidence", "cross_method"]
    for ax, sig in zip(axes, sig_order):
        sig_rows = sorted([r for r in rows if r["signal"] == sig], key=lambda r: float(r["score_bucket"]))
        x = [float(r["score_bucket"]) for r in sig_rows]
        y = [float(r["accuracy"]) for r in sig_rows]
        n = [int(r["n"]) for r in sig_rows]
        bars = ax.bar([f"{v:.1f}" for v in x], y, color="#4c72b0", edgecolor="black", linewidth=0.4, width=0.6)
        for b, ni in zip(bars, n):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02, f"n={ni}",
                    ha="center", fontsize=5.5, rotation=90 if b.get_height() < 0.3 else 0)
        ax.axhline(0.5, color="gray", linewidth=0.6, linestyle="--")
        ax.set_title(LABELS[sig], fontsize=8)
        ax.set_xlabel("Score bucket")
        ax.set_ylim(0, 1.0)
    axes[0].set_ylabel("Accuracy")
    save(fig, "accuracy_by_confidence.pdf")


def fig_cross_model():
    rows = read_csv("cross_model_comparison.csv")
    models = sorted(set(r["model"] for r in rows), key=lambda m: 0 if "Gemini" in m else 1)
    methods = ["B1", "B2", "B3", "OURS"]
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    width = 0.35
    x = np.arange(len(methods))
    hatches = ["", "//"]
    for i, model in enumerate(models):
        accs = []
        for m in methods:
            match = [r for r in rows if r["model"] == model and r["method"] == m]
            accs.append(float(match[0]["accuracy"]) if match else 0.0)
        short_name = "Gemini (hosted)" if "Gemini" in model else "Qwen2.5-7B (local)"
        ax.bar(x + (i - 0.5) * width, accs, width, label=short_name, color="white" if i else "#4c72b0",
               edgecolor="black", hatch=hatches[i], linewidth=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(methods)
    ax.set_ylabel("Accuracy")
    ax.axhline(0.5, color="gray", linewidth=0.6, linestyle="--")
    ax.legend(fontsize=7)
    save(fig, "cross_model_comparison.pdf")


def fig_perturbation_difficulty():
    import json
    records = [json.loads(l) for l in open(ROOT / "results" / "logs" / "comparison_gemini_raw.jsonl")]
    test_nm = [r for r in records if r["half"] == "test" and r["kind"] == "nearmiss"]
    from collections import defaultdict
    by_type = defaultdict(lambda: [0, 0])
    for r in test_nm:
        ptype = r["id"].split("::")[-1]
        by_type[ptype][0] += 1
        by_type[ptype][1] += int(r["b1"]["verdict"] == "FALSE")
    order = ["off_by_one", "round_number_change", "magnitude_change", "digit_swap"]
    labels = ["off-by-\none", "round-\nnumber", "magnitude\nchange", "digit\nswap"]
    accs = [by_type[k][1] / by_type[k][0] for k in order]
    ns = [by_type[k][0] for k in order]
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    bars = ax.bar(labels, accs, color="#4c72b0", edgecolor="black", linewidth=0.5)
    for b, n in zip(bars, ns):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02, f"n={n}", ha="center", fontsize=6.5)
    ax.axhline(0.5, color="gray", linewidth=0.6, linestyle="--", label="chance")
    ax.set_ylabel("B1 accuracy on near-miss\n(= FALSE-prediction rate)")
    ax.set_ylim(0, 1.0)
    save(fig, "perturbation_difficulty.pdf")


if __name__ == "__main__":
    fig_risk_coverage()
    fig_coverage_vs_alpha()
    fig_accuracy_by_confidence()
    fig_cross_model()
    fig_perturbation_difficulty()

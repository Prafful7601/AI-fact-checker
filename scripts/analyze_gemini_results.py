#!/usr/bin/env python3
"""Final analysis for the paper, on the completed Gemini half (8,205 claims).
Computes: main accuracy/F1, conformal calibration for three confidence
signals (within-method execution-agreement, B2 self-confidence, and a new
cross-method combined signal), per-claim-type breakdown, bootstrap CIs,
McNemar tests, and cross-model (Gemini vs. Ollama-partial) comparison.
Writes CSV/LaTeX tables to results/tables/ and paper/tables/, and generates
all figures to results/figures/ and paper/figures/."""
from __future__ import annotations
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.conformal import calibrate_threshold, realised_risk_coverage

ROOT = Path(__file__).resolve().parents[1]
GEMINI_PATH = ROOT / "results" / "logs" / "comparison_gemini_raw.jsonl"
OLLAMA_PATH = ROOT / "results" / "logs" / "full_run_raw.jsonl"
RESULTS_TABLES = ROOT / "results" / "tables"
PAPER_TABLES = ROOT / "paper" / "tables"
RESULTS_FIGS = ROOT / "results" / "figures"
PAPER_FIGS = ROOT / "paper" / "figures"
SEED = 42
ALPHAS = [0.02, 0.05, 0.10, 0.15, 0.20, 0.30]
METHODS = ["b1", "b2", "b3", "ours"]

for d in (RESULTS_TABLES, PAPER_TABLES, RESULTS_FIGS, PAPER_FIGS):
    d.mkdir(parents=True, exist_ok=True)


def gold_str(label: int) -> str:
    return "TRUE" if label == 1 else "FALSE"


def is_correct(r, method) -> bool:
    return r[method]["verdict"] == gold_str(r["label"])


def score_ours(r) -> float:
    return r["ours"].get("agreement_score", 0.0) if r["ours"]["verdict"] != "UNVERIFIABLE" else 0.0


def score_b2(r) -> float:
    c = r["b2"].get("confidence")
    return (c / 100.0) if c is not None else 0.0


def score_cross(r) -> float:
    """New combined signal: average of execution-agreement and self-reported
    confidence, but only when the two independently-derived verdicts (Ours,
    B2) actually agree with each other; 0 otherwise. Two methods reaching the
    same answer via different routes (code execution vs. free-text reasoning)
    is a stronger correctness signal than either method's internal
    self-confidence alone."""
    ov, bv = r["ours"]["verdict"], r["b2"]["verdict"]
    if ov not in ("TRUE", "FALSE") or bv not in ("TRUE", "FALSE") or ov != bv:
        return 0.0
    return (score_ours(r) + score_b2(r)) / 2.0


def cross_verdict(r):
    ov, bv = r["ours"]["verdict"], r["b2"]["verdict"]
    return ov if (ov in ("TRUE", "FALSE") and ov == bv) else "UNVERIFIABLE"


def f1_binary(y_true, y_pred, positive="TRUE"):
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == positive and p == positive)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != positive and p == positive)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == positive and p != positive)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    return 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0


def macro_f1(y_true, y_pred):
    return (f1_binary(y_true, y_pred, "TRUE") + f1_binary(y_true, y_pred, "FALSE")) / 2


def bootstrap_ci(values, n_boot=2000, seed=SEED):
    rng = np.random.default_rng(seed)
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return (0.0, 0.0)
    boots = [rng.choice(values, size=len(values), replace=True).mean() for _ in range(n_boot)]
    return (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)))


def mcnemar(correct_a, correct_b):
    b = sum(1 for a, bb in zip(correct_a, correct_b) if a and not bb)
    c = sum(1 for a, bb in zip(correct_a, correct_b) if not a and bb)
    if b + c == 0:
        return {"b": b, "c": c, "statistic": 0.0, "p_value": 1.0}
    stat = (abs(b - c) - 1) ** 2 / (b + c)
    from scipy.stats import chi2
    p = 1 - chi2.cdf(stat, df=1)
    return {"b": b, "c": c, "statistic": float(stat), "p_value": float(p)}


def write_csv(path, rows, header):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    records = [json.loads(l) for l in open(GEMINI_PATH)]
    print(f"Loaded {len(records)} Gemini-evaluated claims.")
    test = [r for r in records if r["half"] == "test"]
    cal = [r for r in records if r["half"] == "calibration"]
    test_orig = [r for r in test if r["kind"] == "original"]
    test_nm = [r for r in test if r["kind"] == "nearmiss"]
    print(f"Calibration: {len(cal)} | Test: {len(test)} (orig={len(test_orig)}, nearmiss={len(test_nm)})")

    # ---- 1. Main accuracy/F1 (test half) ----
    main_rows = []
    correctness = {}
    for method in METHODS:
        for group_name, group in [("orig", test_orig), ("nm", test_nm)]:
            y_true = [gold_str(r["label"]) for r in group]
            y_pred = [r[method]["verdict"] if r[method]["verdict"] in ("TRUE", "FALSE") else
                      ("FALSE" if gold_str(r["label"]) == "TRUE" else "TRUE") for r in group]
            acc = np.mean([t == p for t, p in zip(y_true, y_pred)]) if group else 0.0
            f1 = macro_f1(y_true, y_pred) if group else 0.0
            main_rows.append([method.upper(), group_name, len(group), acc, f1])
        correctness[method] = {r["id"]: is_correct(r, method) for r in test_orig}
    write_csv(RESULTS_TABLES / "gemini_main_results.csv", main_rows, ["method", "claim_set", "n", "accuracy", "macro_f1"])

    def get(method, group):
        row = [r for r in main_rows if r[0] == method.upper() and r[1] == group][0]
        return row[3], row[4]
    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{Accuracy / macro-F1 on original vs.\ near-miss test claims (Gemini 3.5 Flash-Lite, $n=8{,}205$).}",
             r"\label{tab:main-results}", r"\begin{tabular}{lcccc}", r"\toprule",
             r"Method & Acc.\ (orig.) & F1 (orig.) & Acc.\ (near-miss) & F1 (near-miss) \\", r"\midrule"]
    labels = {"b1": "B1 (LLM-only)", "b2": "B2 (+ confidence)", "b3": "B3 ($K$=1 check)", "ours": "Ours ($K$=5)"}
    for method in METHODS:
        ao, fo = get(method, "orig")
        an, fn = get(method, "nm")
        lines.append(f"{labels[method]} & {ao:.3f} & {fo:.3f} & {an:.3f} & {fn:.3f} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER_TABLES / "main_results.tex").write_text("\n".join(lines) + "\n")

    # ---- 2. McNemar (Ours vs each baseline, original test claims) ----
    mcnemar_rows = []
    for method in ("b1", "b2", "b3"):
        res = mcnemar([correctness["ours"][r["id"]] for r in test_orig],
                       [correctness[method][r["id"]] for r in test_orig])
        mcnemar_rows.append(["ours_vs_" + method, res["b"], res["c"], res["statistic"], res["p_value"]])
    write_csv(RESULTS_TABLES / "gemini_mcnemar.csv", mcnemar_rows, ["comparison", "b", "c", "statistic", "p_value"])

    # ---- 3. Bootstrap CIs ----
    ci_rows = []
    for method in METHODS:
        for group_name, group in [("orig", test_orig), ("nm", test_nm)]:
            correct = [is_correct(r, method) if r[method]["verdict"] in ("TRUE", "FALSE") else False for r in group]
            lo, hi = bootstrap_ci(correct)
            ci_rows.append([method, group_name, np.mean(correct) if correct else 0.0, lo, hi])
    write_csv(RESULTS_TABLES / "gemini_bootstrap_ci.csv", ci_rows, ["method", "claim_set", "accuracy", "ci_lo", "ci_hi"])

    # ---- 4. Conformal calibration: three signals, expanded alpha grid ----
    signals = {
        "ours_agreement": (score_ours, lambda r: r["ours"]["verdict"]),
        "b2_confidence": (score_b2, lambda r: r["b2"]["verdict"]),
        "cross_method": (score_cross, cross_verdict),
    }
    risk_rows = []
    thresholds = {}
    for sig_name, (scorefn, verdictfn) in signals.items():
        thresholds[sig_name] = {}
        cal_scores = np.array([scorefn(r) for r in cal])
        cal_correct = np.array([verdictfn(r) == gold_str(r["label"]) for r in cal])
        test_scores = np.array([scorefn(r) for r in test])
        test_correct = np.array([verdictfn(r) == gold_str(r["label"]) for r in test])
        for alpha in ALPHAS:
            lam = calibrate_threshold(cal_scores, cal_correct, alpha)
            rc = realised_risk_coverage(test_scores, test_correct, lam)
            thresholds[sig_name][alpha] = lam
            risk_rows.append([sig_name, alpha, lam, rc["realised_risk"], rc["coverage"],
                               rc["n_answered"], rc["n_abstained"], rc["n_total"]])
    write_csv(RESULTS_TABLES / "gemini_risk_coverage.csv", risk_rows,
              ["signal", "alpha", "lambda", "realised_risk", "coverage", "n_answered", "n_abstained", "n_total"])
    with open(RESULTS_TABLES / "gemini_conformal_thresholds.json", "w") as f:
        json.dump(thresholds, f, indent=2)

    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{Realised risk and coverage after conformal calibration, three confidence signals (Gemini, test half, $n=4{,}107$).}",
             r"\label{tab:risk-coverage}", r"\begin{tabular}{llccc}", r"\toprule",
             r"Signal & $\alpha$ & Risk & Coverage & $\lambda_\alpha$ \\", r"\midrule"]
    sig_labels = {"ours_agreement": "Ours (agreement)", "b2_confidence": "B2 (self-conf.)", "cross_method": "Cross-method"}
    for sig_name in signals:
        for alpha in ALPHAS:
            row = [r for r in risk_rows if r[0] == sig_name and r[1] == alpha][0]
            lines.append(f"{sig_labels[sig_name]} & {alpha:.2f} & {row[3]:.3f} & {row[4]:.3f} & {row[2]:.2f} \\\\")
        lines.append(r"\midrule")
    lines = lines[:-1] + [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER_TABLES / "risk_coverage.tex").write_text("\n".join(lines) + "\n")

    # ---- 5. Accuracy-by-agreement-bucket (for the figure) ----
    bucket_rows = []
    for sig_name, (scorefn, verdictfn) in signals.items():
        buckets = {}
        for r in test:
            key = round(scorefn(r), 1)
            buckets.setdefault(key, [0, 0])
            buckets[key][0] += 1
            buckets[key][1] += int(verdictfn(r) == gold_str(r["label"]))
        for k in sorted(buckets):
            n, c = buckets[k]
            bucket_rows.append([sig_name, k, n, c / n])
    write_csv(RESULTS_TABLES / "gemini_accuracy_by_confidence.csv", bucket_rows,
              ["signal", "score_bucket", "n", "accuracy"])

    # ---- 6. Per-claim-type breakdown ----
    type_rows = []
    for ctype in ["lookup", "count", "comparison", "superlative", "aggregation"]:
        og = [r for r in test_orig if r["claim_type"] == ctype]
        ng = [r for r in test_nm if r["claim_type"] == ctype]
        acc_o = np.mean([is_correct(r, "ours") for r in og]) if og else float("nan")
        acc_n = np.mean([is_correct(r, "ours") for r in ng]) if ng else float("nan")
        type_rows.append([ctype, len(og), acc_o, len(ng), acc_n])
    write_csv(RESULTS_TABLES / "gemini_per_claim_type.csv", type_rows,
              ["claim_type", "n_orig", "acc_orig", "n_nearmiss", "acc_nearmiss"])
    lines = [r"\begin{table}[t]", r"\centering", r"\caption{Ours ($K$=5) accuracy by claim type (Gemini).}",
             r"\label{tab:per-claim-type}", r"\begin{tabular}{lcc}", r"\toprule",
             r"Claim type & Acc.\ (orig.) & Acc.\ (near-miss) \\", r"\midrule"]
    for row in type_rows:
        ao = f"{row[2]:.3f}" if row[2] == row[2] else "--"
        an = f"{row[4]:.3f}" if row[4] == row[4] else "--"
        lines.append(f"{row[0]} & {ao} & {an} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER_TABLES / "per_claim_type.tex").write_text("\n".join(lines) + "\n")

    # ---- 7. Cross-model comparison (Gemini full vs. Ollama partial) ----
    ollama_records = [json.loads(l) for l in open(OLLAMA_PATH)] if OLLAMA_PATH.exists() else []
    cross_rows = []
    for model_name, recs in [("Gemini 3.5 Flash-Lite (hosted)", records), ("Qwen2.5-7B-Instruct (local)", ollama_records)]:
        if not recs:
            continue
        for method in METHODS:
            acc = np.mean([is_correct(r, method) for r in recs])
            unverif = np.mean([r[method]["verdict"] == "UNVERIFIABLE" for r in recs])
            cross_rows.append([model_name, method.upper(), len(recs), acc, unverif])
    write_csv(RESULTS_TABLES / "cross_model_comparison.csv", cross_rows,
              ["model", "method", "n", "accuracy", "unverifiable_rate"])
    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{Cross-model comparison: hosted vs.\ local model (n as shown; Ollama run partial/ongoing).}",
             r"\label{tab:cross-model}", r"\begin{tabular}{llccc}", r"\toprule",
             r"Model & Method & $n$ & Acc. & Unverif.\ rate \\", r"\midrule"]
    for row in cross_rows:
        lines.append(f"{row[0]} & {row[1]} & {row[2]:,} & {row[3]:.3f} & {row[4]:.3f} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER_TABLES / "cross_model.tex").write_text("\n".join(lines) + "\n")

    print("Wrote all tables. Risk-coverage summary:")
    for row in risk_rows:
        print(" ", row)
    print("\nCross-model summary:")
    for row in cross_rows:
        print(" ", row)


if __name__ == "__main__":
    main()

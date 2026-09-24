#!/usr/bin/env python3
"""Step 3 evaluation: metrics, conformal calibration + validity check,
per-claim-type breakdown, ablations, McNemar tests, bootstrap CIs, cost, and
error analysis. Reads results/logs/full_run_raw.jsonl (written by
scripts/run_full_eval.py). Writes CSV+LaTeX tables to results/tables/ and
paper/tables/, figures to results/figures/ and paper/figures/."""
from __future__ import annotations
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.conformal import calibrate_threshold, realised_risk_coverage

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "results" / "logs" / "full_run_raw.jsonl"
RESULTS_TABLES = ROOT / "results" / "tables"
PAPER_TABLES = ROOT / "paper" / "tables"
RESULTS_FIGS = ROOT / "results" / "figures"
PAPER_FIGS = ROOT / "paper" / "figures"
SEED = 42
ALPHAS = [0.02, 0.05, 0.10]
METHODS = ["b1", "b2", "b3", "ours"]


def gold_str(label: int) -> str:
    return "TRUE" if label == 1 else "FALSE"


def load_records():
    return [json.loads(l) for l in open(RAW_PATH)]


def confidence_of(rec: dict, method: str) -> float:
    if method == "ours":
        return rec["ours"].get("agreement_score", 0.0) if rec["ours"]["verdict"] != "UNVERIFIABLE" else 0.0
    if method == "b3":
        return 1.0 if rec["b3"]["verdict"] in ("TRUE", "FALSE") else 0.0
    if method == "b2":
        c = rec["b2"].get("confidence")
        return (c / 100.0) if c is not None else 0.0
    return 1.0  # b1 has no confidence signal; treated as always-answer


def is_correct(rec: dict, method: str) -> bool:
    return rec[method]["verdict"] == gold_str(rec["label"])


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


def write_csv(path: Path, rows: list, header: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    if not RAW_PATH.exists():
        print(f"ERROR: {RAW_PATH} not found. Run scripts/run_full_eval.py first.")
        sys.exit(1)
    records = load_records()
    print(f"Loaded {len(records)} evaluated claims.")

    orig = [r for r in records if r["kind"] == "original"]
    nm = [r for r in records if r["kind"] == "nearmiss"]
    test_orig = [r for r in orig if r["half"] == "test"]
    test_nm = [r for r in nm if r["half"] == "test"]
    cal_orig = [r for r in orig if r["half"] == "calibration"]
    cal_nm = [r for r in nm if r["half"] == "calibration"]

    # ---- 1. Main accuracy/F1 table (test half) ----
    main_rows = []
    correctness = {}  # method -> {claim_id: bool}, for McNemar
    for method in METHODS:
        for group_name, group in [("orig", test_orig), ("nm", test_nm)]:
            y_true = [gold_str(r["label"]) for r in group]
            y_pred = [r[method]["verdict"] if r[method]["verdict"] in ("TRUE", "FALSE") else
                      ("FALSE" if gold_str(r["label"]) == "TRUE" else "TRUE") for r in group]
            acc = np.mean([t == p for t, p in zip(y_true, y_pred)]) if group else 0.0
            f1 = macro_f1(y_true, y_pred) if group else 0.0
            main_rows.append([method.upper(), group_name, len(group), acc, f1])
        correctness[method] = {r["id"]: is_correct(r, method) for r in test_orig}
    write_csv(RESULTS_TABLES / "main_results.csv", main_rows, ["method", "claim_set", "n", "accuracy", "macro_f1"])

    # LaTeX main results table
    def get(method, group):
        row = [r for r in main_rows if r[0] == method.upper() and r[1] == group][0]
        return row[3], row[4]
    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{Accuracy / macro-F1 on original vs.\ near-miss test claims, by method.}",
             r"\label{tab:main-results}", r"\begin{tabular}{lcccc}", r"\toprule",
             r"Method & Acc.\ (orig.) & F1 (orig.) & Acc.\ (near-miss) & F1 (near-miss) \\", r"\midrule"]
    labels = {"b1": "B1 (LLM-only)", "b2": "B2 (+ confidence)", "b3": "B3 ($K$=1 check)", "ours": "Ours ($K$=5)"}
    for method in METHODS:
        ao, fo = get(method, "orig")
        an, fn = get(method, "nm")
        lines.append(f"{labels[method]} & {ao:.3f} & {fo:.3f} & {an:.3f} & {fn:.3f} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER_TABLES / "main_results.tex").write_text("\n".join(lines) + "\n")

    # ---- 2. McNemar tests (original test claims, ours vs each baseline) ----
    mcnemar_rows = []
    for method in ("b1", "b2", "b3"):
        res = mcnemar([correctness["ours"][r["id"]] for r in test_orig],
                       [correctness[method][r["id"]] for r in test_orig])
        mcnemar_rows.append(["ours_vs_" + method, res["b"], res["c"], res["statistic"], res["p_value"]])
    write_csv(RESULTS_TABLES / "mcnemar.csv", mcnemar_rows, ["comparison", "b", "c", "statistic", "p_value"])

    # ---- 3. Bootstrap CIs on accuracy (test half, per method, per claim set) ----
    ci_rows = []
    for method in METHODS:
        for group_name, group in [("orig", test_orig), ("nm", test_nm)]:
            correct = [is_correct(r, method) if r[method]["verdict"] in ("TRUE", "FALSE")
                       else False for r in group]
            lo, hi = bootstrap_ci(correct)
            ci_rows.append([method, group_name, np.mean(correct) if correct else 0.0, lo, hi])
    write_csv(RESULTS_TABLES / "bootstrap_ci.csv", ci_rows, ["method", "claim_set", "accuracy", "ci_lo", "ci_hi"])

    # ---- 4. Conformal calibration (Ours and B2) ----
    risk_rows = []
    thresholds = {}
    for method in ("b2", "ours"):
        thresholds[method] = {}
        cal_pool = cal_orig + cal_nm
        test_pool = test_orig + test_nm
        cal_scores = np.array([confidence_of(r, method) for r in cal_pool])
        cal_correct = np.array([is_correct(r, method) for r in cal_pool])
        test_scores = np.array([confidence_of(r, method) for r in test_pool])
        test_correct = np.array([is_correct(r, method) for r in test_pool])
        for alpha in ALPHAS:
            lam = calibrate_threshold(cal_scores, cal_correct, alpha)
            rc = realised_risk_coverage(test_scores, test_correct, lam)
            thresholds[method][alpha] = lam
            risk_rows.append([method, alpha, lam, rc["realised_risk"], rc["coverage"],
                               rc["n_answered"], rc["n_abstained"], rc["n_total"]])
    write_csv(RESULTS_TABLES / "risk_coverage.csv", risk_rows,
              ["method", "alpha", "lambda", "realised_risk", "coverage", "n_answered", "n_abstained", "n_total"])

    with open(RESULTS_TABLES / "conformal_thresholds.json", "w") as f:
        json.dump(thresholds.get("ours", {}), f, indent=2)
    import shutil
    shutil.copy(RESULTS_TABLES / "conformal_thresholds.json", ROOT / "results" / "conformal_thresholds.json")

    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{Realised risk and coverage after conformal calibration (Ours, $K$=5).}",
             r"\label{tab:risk-coverage}", r"\begin{tabular}{lcccc}", r"\toprule",
             r"$\alpha$ & Realised risk & Coverage & Review workload & $\lambda_\alpha$ \\", r"\midrule"]
    for alpha in ALPHAS:
        row = [r for r in risk_rows if r[0] == "ours" and r[1] == alpha][0]
        lines.append(f"{alpha:.2f} & {row[3]:.4f} & {row[4]:.3f} & {row[6]} & {row[2]:.3f} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER_TABLES / "risk_coverage.tex").write_text("\n".join(lines) + "\n")

    # ---- 5. Conformal validity: 100 random re-splits ----
    validity_rows = []
    all_pool = orig + nm
    for alpha in ALPHAS:
        risks, covs = [], []
        rng = random.Random(SEED)
        for trial in range(100):
            ids = list(range(len(all_pool)))
            rng.shuffle(ids)
            half = len(ids) // 2
            cal_idx, test_idx = ids[:half], ids[half:]
            cal_scores = np.array([confidence_of(all_pool[i], "ours") for i in cal_idx])
            cal_correct = np.array([is_correct(all_pool[i], "ours") for i in cal_idx])
            test_scores = np.array([confidence_of(all_pool[i], "ours") for i in test_idx])
            test_correct = np.array([is_correct(all_pool[i], "ours") for i in test_idx])
            lam = calibrate_threshold(cal_scores, cal_correct, alpha)
            rc = realised_risk_coverage(test_scores, test_correct, lam)
            risks.append(rc["realised_risk"])
            covs.append(rc["coverage"])
        validity_rows.append([alpha, np.mean(risks), np.std(risks), np.mean(covs), np.std(covs)])
    write_csv(RESULTS_TABLES / "conformal_validity.csv", validity_rows,
              ["alpha", "risk_mean", "risk_std", "coverage_mean", "coverage_std"])

    # ---- 6. Per-claim-type breakdown (Ours, test half) ----
    type_rows = []
    for ctype in ["lookup", "count", "comparison", "superlative", "aggregation"]:
        orig_group = [r for r in test_orig if r["claim_type"] == ctype]
        nm_group = [r for r in test_nm if r["claim_type"] == ctype]
        acc_o = np.mean([is_correct(r, "ours") for r in orig_group]) if orig_group else float("nan")
        acc_n = np.mean([is_correct(r, "ours") for r in nm_group]) if nm_group else float("nan")
        type_rows.append([ctype, len(orig_group), acc_o, len(nm_group), acc_n])
    write_csv(RESULTS_TABLES / "per_claim_type.csv", type_rows,
              ["claim_type", "n_orig", "acc_orig", "n_nearmiss", "acc_nearmiss"])
    lines = [r"\begin{table}[t]", r"\centering", r"\caption{Ours ($K$=5) accuracy by claim type.}",
             r"\label{tab:per-claim-type}", r"\begin{tabular}{lcc}", r"\toprule",
             r"Claim type & Acc.\ (orig.) & Acc.\ (near-miss) \\", r"\midrule"]
    for row in type_rows:
        ao = f"{row[2]:.3f}" if row[2] == row[2] else "--"
        an = f"{row[4]:.3f}" if row[4] == row[4] else "--"
        lines.append(f"{row[0]} & {ao} & {an} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER_TABLES / "per_claim_type.tex").write_text("\n".join(lines) + "\n")

    # ---- 7. Ablations: K in {1,3,5}; with/without calibration; greedy vs sampled ----
    def majority_from_k(executed_checks, k):
        subset = executed_checks[:k]
        votes = [c["result"]["verdict"] for c in subset if c.get("result", {}).get("ok")]
        if not votes:
            return "UNVERIFIABLE", 0.0
        n_t, n_f = votes.count("TRUE"), votes.count("FALSE")
        verdict = "TRUE" if n_t >= n_f else "FALSE"
        return verdict, max(n_t, n_f) / k

    ablation_rows = []
    for k in (1, 3, 5):
        accs_o, accs_n = [], []
        for group, accs in [(test_orig, accs_o), (test_nm, accs_n)]:
            correct = []
            for r in group:
                v, _ = majority_from_k(r["ours"]["executed_checks"], k)
                correct.append(v == gold_str(r["label"]))
            accs.append(np.mean(correct) if correct else 0.0)
        # coverage @ alpha=0.05 for this K, recalibrated on the calibration half
        cal_pool = cal_orig + cal_nm
        test_pool = test_orig + test_nm
        cal_scores, cal_correct = [], []
        for r in cal_pool:
            v, s = majority_from_k(r["ours"]["executed_checks"], k)
            cal_scores.append(s); cal_correct.append(v == gold_str(r["label"]))
        test_scores, test_correct = [], []
        for r in test_pool:
            v, s = majority_from_k(r["ours"]["executed_checks"], k)
            test_scores.append(s); test_correct.append(v == gold_str(r["label"]))
        lam = calibrate_threshold(np.array(cal_scores), np.array(cal_correct), 0.05)
        rc = realised_risk_coverage(np.array(test_scores), np.array(test_correct), lam)
        ablation_rows.append([f"K={k}", accs_o[0], accs_n[0], rc["coverage"]])
    # no-calibration ablation: coverage = 1.0 always-answer accuracy at K=5
    acc_o_nc = np.mean([is_correct(r, "ours") if r["ours"]["verdict"] != "UNVERIFIABLE" else False for r in test_orig])
    acc_n_nc = np.mean([is_correct(r, "ours") if r["ours"]["verdict"] != "UNVERIFIABLE" else False for r in test_nm])
    ablation_rows.append(["K=5, no calibration", acc_o_nc, acc_n_nc, 1.0])
    write_csv(RESULTS_TABLES / "ablations.csv", ablation_rows,
              ["config", "acc_orig", "acc_nearmiss", "coverage_at_alpha_0.05"])
    lines = [r"\begin{table}[t]", r"\centering",
             r"\caption{Ablations: $K\in\{1,3,5\}$, with/without conformal calibration.}",
             r"\label{tab:ablations}", r"\begin{tabular}{lccc}", r"\toprule",
             r"Configuration & Acc.\ (orig.) & Acc.\ (near-miss) & Coverage @ $\alpha$=0.05 \\", r"\midrule"]
    for row in ablation_rows:
        lines.append(f"{row[0]} & {row[1]:.3f} & {row[2]:.3f} & {row[3]:.3f} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (PAPER_TABLES / "ablations.tex").write_text("\n".join(lines) + "\n")

    # ---- 8. Cost and latency ----
    def total_usage(r):
        tot_in = tot_out = 0
        for m in METHODS:
            u = r[m].get("usage", {})
            tot_in += u.get("input_tokens", 0)
            tot_out += u.get("output_tokens", 0)
        return tot_in, tot_out
    usages = [total_usage(r) for r in records]
    write_csv(RESULTS_TABLES / "cost_summary.csv",
              [[len(records), sum(u[0] for u in usages), sum(u[1] for u in usages)]],
              ["n_claims", "total_input_tokens", "total_output_tokens"])

    print("Wrote all evaluation tables to results/tables/ and paper/tables/.")
    print(f"Risk-coverage: {risk_rows}")
    print(f"Conformal validity (100 re-splits): {validity_rows}")


if __name__ == "__main__":
    main()

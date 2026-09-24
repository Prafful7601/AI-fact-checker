#!/usr/bin/env python3
"""Pilot run (hard rule): all methods (B1, B2, B3, Ours K=5) on 50 claims.
Reports accuracy, API call counts, tokens, and (given pricing) a cost/time
projection for the full run. Requires ANTHROPIC_API_KEY. Every LLM call is
cached to disk, so this pilot's calls are reused for free during the full run."""
from __future__ import annotations
import asyncio
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.llm_client import LLMClient, load_config
from src.table_utils import load_table_cached
from src.verifier import verify_claim

ROOT = Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT / "data" / "Table-Fact-Checking" / "data" / "all_csv"
SEED = 42
N_PILOT = 50
N_ORIGINAL = 35
N_NEARMISS = 15


def sample_pilot_claims():
    splits = json.load(open(ROOT / "data" / "processed" / "eval_splits.json"))
    all_records = {r["claim_id"]: r for r in
                   (json.loads(l) for l in open(ROOT / "data" / "processed" / "tabfact_all.jsonl"))}
    nearmiss_records = {r["nearmiss_id"]: r for r in
                         (json.loads(l) for l in open(ROOT / "data" / "processed" / "numnear_tabfact.jsonl"))}

    rng = random.Random(SEED)
    orig_ids = rng.sample(splits["original"]["test"], N_ORIGINAL)
    nm_ids = rng.sample(splits["nearmiss"]["test"], N_NEARMISS)

    claims = []
    for cid in orig_ids:
        r = all_records[cid]
        claims.append({"id": cid, "claim": r["claim"], "table_id": r["table_id"],
                        "label": r["label"], "kind": "original", "claim_type": r["claim_type"]})
    for nid in nm_ids:
        r = nearmiss_records[nid]
        claims.append({"id": nid, "claim": r["perturbed_claim"], "table_id": r["table_id"],
                        "label": r["label"], "kind": "nearmiss", "claim_type": r["claim_type"]})
    return claims


async def run_one(client, model, claim_rec, config):
    table_path = str(TABLES_DIR / claim_rec["table_id"])
    out = {"id": claim_rec["id"], "label": claim_rec["label"], "kind": claim_rec["kind"]}
    for method in ("b1", "b2", "b3", "ours"):
        res = await verify_claim(client, model, claim_rec["claim"], table_path,
                                  k=config["experiment"]["k_checks"],
                                  temperature=config["models"]["available"][0]["temperature_checks"],
                                  method=method)
        out[method] = res
    return out


async def main():
    config = load_config()
    model = config["models"]["default"]
    client = LLMClient(config)
    if not client.available():
        model_conf = next(m for m in config["models"]["available"] if m["name"] == model)
        provider = model_conf["provider"]
        api_key_env = config["providers"][provider]["api_key_env"]
        print(f"ERROR: {api_key_env} is not set (or invalid) for provider '{provider}'. Cannot run the pilot.")
        sys.exit(1)

    claims = sample_pilot_claims()
    print(f"Sampled {len(claims)} pilot claims ({N_ORIGINAL} original + {N_NEARMISS} near-miss)")

    start = time.time()
    raw = await asyncio.gather(*[run_one(client, model, c, config) for c in claims], return_exceptions=True)
    elapsed = time.time() - start

    results, failed = [], []
    for c, r in zip(claims, raw):
        if isinstance(r, Exception):
            failed.append({"id": c["id"], "error": str(r)})
        else:
            results.append(r)
    if failed:
        print(f"\nWARNING: {len(failed)}/{len(claims)} claims failed even after retries: {failed}")
    if not results:
        print("ERROR: every claim failed; nothing to report.")
        sys.exit(1)

    def gold_str(label):
        return "TRUE" if label == 1 else "FALSE"

    accuracy = {}
    for method in ("b1", "b2", "b3", "ours"):
        correct = 0
        for r in results:
            v = r[method]["verdict"]
            correct += int(v == gold_str(r["label"]))
        accuracy[method] = correct / len(results)

    print(f"\n=== PILOT RESULTS (n={len(results)}/{len(claims)} completed) ===")
    print(f"Wall-clock time: {elapsed:.1f}s")
    for method in ("b1", "b2", "b3", "ours"):
        print(f"  {method.upper():5s} accuracy: {accuracy[method]:.3f}")
    print(f"\nLLM stats: {client.stats}")

    pricing = config["models"]["available"][0]
    cost = client.cost_estimate(pricing)
    n_calls = client.stats["calls"]
    calls_per_claim = n_calls / len(results) if results else 0
    cost_per_claim = cost["total_cost"] / len(results) if results else 0
    time_per_claim = elapsed / len(results) if results else 0

    n_full_original = 11400  # exact count from scripts/build_dataset.py
    n_full_nearmiss = 5474   # exact count of test-derived near-miss variants
    n_full_claims = n_full_original + n_full_nearmiss
    projected_cost = cost_per_claim * n_full_claims
    projected_time_seq = time_per_claim * n_full_claims

    print("\n=== FULL-RUN PROJECTION (based on this pilot's per-claim averages) ===")
    print(f"Pilot: {n_calls} API calls over {len(claims)} claims ({calls_per_claim:.2f} calls/claim)")
    print(f"Pilot cost: ${cost['total_cost']:.4f} (${cost_per_claim:.5f}/claim)")
    print(f"Full-run claim count (test-split originals + test-derived near-misses): {n_full_claims}")
    print(f"Projected full-run cost: ${projected_cost:.2f}")
    print(f"Projected full-run wall-clock at pilot concurrency (config.llm.max_concurrency="
          f"{config['llm']['max_concurrency']}): ~{projected_time_seq/60:.1f} minutes "
          f"(actual will vary with rate limits / cache hits)")

    out_dir = ROOT / "results" / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "pilot_results.json", "w") as f:
        json.dump({"accuracy": accuracy, "elapsed_seconds": elapsed, "llm_stats": client.stats,
                   "n_claims_completed": len(results), "n_claims_sampled": len(claims), "failed": failed,
                   "cost_estimate": cost,
                   "projected_full_run": {"n_claims": n_full_claims, "cost_usd": projected_cost,
                                           "time_minutes": projected_time_seq / 60}},
                  f, indent=2, default=str)
    with open(out_dir / "pilot_raw.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nWrote {out_dir / 'pilot_results.json'} and pilot_raw.json")


if __name__ == "__main__":
    asyncio.run(main())

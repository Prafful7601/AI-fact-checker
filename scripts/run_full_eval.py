#!/usr/bin/env python3
"""Full run: B1/B2/B3/Ours(K=5) over every original test-split numeric claim
and every test-derived NumNear-TabFact near-miss claim. Resumable in batches:
every LLM call is cached to disk (src/llm_client.py), so re-running this
script after an interruption only pays for uncached calls. Writes
results/logs/full_run_raw.jsonl incrementally (one line per claim) so a
crash loses at most the in-flight batch.

Usage: python3 scripts/run_full_eval.py [--batch-size 200] [--limit N]
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.llm_client import LLMClient, load_config
from src.verifier import verify_claim

ROOT = Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT / "data" / "Table-Fact-Checking" / "data" / "all_csv"
DEFAULT_OUT_PATH = ROOT / "results" / "logs" / "full_run_raw.jsonl"


def load_all_claims():
    splits = json.load(open(ROOT / "data" / "processed" / "eval_splits.json"))
    all_records = {r["claim_id"]: r for r in
                   (json.loads(l) for l in open(ROOT / "data" / "processed" / "tabfact_all.jsonl"))}
    nearmiss_records = {r["nearmiss_id"]: r for r in
                         (json.loads(l) for l in open(ROOT / "data" / "processed" / "numnear_tabfact.jsonl"))}

    claims = []
    for cid in splits["original"]["calibration"] + splits["original"]["test"]:
        r = all_records[cid]
        half = "calibration" if cid in splits["original"]["calibration"] else "test"
        claims.append({"id": cid, "claim": r["claim"], "table_id": r["table_id"], "label": r["label"],
                        "kind": "original", "claim_type": r["claim_type"], "half": half})
    for nid in splits["nearmiss"]["calibration"] + splits["nearmiss"]["test"]:
        r = nearmiss_records[nid]
        half = "calibration" if nid in splits["nearmiss"]["calibration"] else "test"
        claims.append({"id": nid, "claim": r["perturbed_claim"], "table_id": r["table_id"], "label": r["label"],
                        "kind": "nearmiss", "claim_type": r["claim_type"], "half": half})

    # Shuffle deterministically so that ANY prefix of this list (i.e. "however
    # far the run has gotten when someone looks") is a representative sample
    # across kind x half x label x claim_type, not four solid blocks in the
    # original/calibration -> original/test -> nearmiss/calibration ->
    # nearmiss/test order above. This is what makes an interim analysis of a
    # partially-completed run meaningful rather than accidentally lopsided.
    import random
    random.Random(42).shuffle(claims)
    return claims


def already_done(out_path: Path) -> set:
    if not out_path.exists():
        return set()
    done = set()
    for line in open(out_path):
        line = line.strip()
        if not line:
            continue
        try:
            done.add(json.loads(line)["id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return done


async def run_one(client, model, temperature, config, claim_rec):
    table_path = str(TABLES_DIR / claim_rec["table_id"])
    out = {"id": claim_rec["id"], "label": claim_rec["label"], "kind": claim_rec["kind"],
           "claim_type": claim_rec["claim_type"], "half": claim_rec["half"]}
    for method in ("b1", "b2", "b3", "ours"):
        res = await verify_claim(client, model, claim_rec["claim"], table_path,
                                  k=config["experiment"]["k_checks"], temperature=temperature, method=method)
        out[method] = res
    return out


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--offset", type=int, default=0,
                         help="Skip the first N claims of the (deterministically shuffled) list -- "
                              "combined with --limit, lets two providers split the same claim list into "
                              "disjoint halves (e.g. --limit 8437 vs. --offset 8437) instead of overlapping.")
    parser.add_argument("--limit", type=int, default=None,
                         help="Take at most N claims starting at --offset -- for a smaller comparison run "
                              "or a disjoint slice of the full evaluation set.")
    parser.add_argument("--model", type=str, default=None,
                         help="Override config.yaml's models.default, e.g. to run a comparison against "
                              "a different provider without touching the config the main run reads.")
    parser.add_argument("--output", type=str, default=None,
                         help="Override the output path, so a comparison run doesn't collide with the main one.")
    args = parser.parse_args()

    config = load_config()
    model = args.model or config["models"]["default"]
    model_conf = next((m for m in config["models"]["available"] if m["name"] == model), None)
    if model_conf is None:
        print(f"ERROR: model '{model}' is not listed in config.yaml models.available.")
        sys.exit(1)
    temperature = model_conf["temperature_checks"]
    out_path = Path(args.output) if args.output else DEFAULT_OUT_PATH

    client = LLMClient(config)
    if not client.available(model):
        print(f"ERROR: model '{model}' not available (API key/server not set up for its provider).")
        sys.exit(1)

    claims = load_all_claims()
    if args.limit:
        claims = claims[args.offset: args.offset + args.limit]
    elif args.offset:
        claims = claims[args.offset:]
    done = already_done(out_path)
    remaining = [c for c in claims if c["id"] not in done]
    print(f"Model: {model} | Total claims: {len(claims)} | already done: {len(done)} | remaining: {len(remaining)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a") as f:
        for i in range(0, len(remaining), args.batch_size):
            batch = remaining[i: i + args.batch_size]
            results = await asyncio.gather(*[run_one(client, model, temperature, config, c) for c in batch],
                                            return_exceptions=True)
            for rec, res in zip(batch, results):
                if isinstance(res, Exception):
                    print(f"  ERROR on {rec['id']}: {res}")
                    continue
                f.write(json.dumps(res, default=str) + "\n")
            f.flush()
            print(f"  batch {i//args.batch_size + 1}: {i+len(batch)}/{len(remaining)} done "
                  f"(cache hits so far: {client.stats['cache_hits']}, calls: {client.stats['calls']})")

    print(f"\nDone. LLM stats: {client.stats}")
    print(f"Wrote/updated {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

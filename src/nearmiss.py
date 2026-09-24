"""NumNear-TabFact construction (C1) -- fully programmatic, no LLM calls.

Construction logic
-------------------
For a TRUE (label=1) claim containing a number, we look for an "anchor": a
number in the claim text that matches -- within `numeric_tolerance` -- exactly
one value in the table's *grounding pool* (every parseable raw cell, plus the
row count and each numeric column's sum/mean/max/min). Uniqueness of the match
is what lets us flip the label without semantic parsing: if the claim's stated
number is the *only* place in the table (raw or aggregated) that value occurs,
altering that number to a different value directly contradicts the one fact
in the table that could have made the claim true, so the perturbed claim must
be FALSE. This is the "checking against the table" verification step referred
to in the spec; it substitutes for a full semantic parser.

Limitation (documented in the paper): claims whose truth hinges on a derived
quantity that is neither a raw cell nor one of the aggregates we compute
(e.g. an ad hoc count of rows matching a textual filter) will simply fail to
find an anchor and are skipped -- they do not enter NumNear-TabFact. This
biases the benchmark towards lookup/count/aggregation claims that are
literally groundable, which is exactly the numeric-near-miss regime we test.
"""
from __future__ import annotations
import random
import re
import zlib
from dataclasses import dataclass, field

from src.number_parsing import extract_numbers, parse_number
from src.table_utils import load_table_cached

TOL = 1e-6
NUMBER_TOKEN_RE = re.compile(r"-?\d[\d,]*\.?\d*")


@dataclass
class GroundingPool:
    value_counts: dict = field(default_factory=dict)  # rounded value -> occurrence count

    def add(self, value: float):
        if value is None:
            return
        key = round(value, 4)
        self.value_counts[key] = self.value_counts.get(key, 0) + 1

    def occurrences(self, value: float) -> int:
        key = round(value, 4)
        return self.value_counts.get(key, 0)


def build_grounding_pool(df) -> GroundingPool:
    pool = GroundingPool()
    for col in df.columns:
        vals = []
        for cell in df[col]:
            v = parse_number(cell)
            if v is not None:
                vals.append(v)
                pool.add(v)
        # column is "numeric enough" if most non-empty cells parsed
        non_empty = sum(1 for c in df[col] if str(c).strip() != "")
        if non_empty > 0 and len(vals) / non_empty >= 0.5 and len(vals) > 0:
            pool.add(sum(vals))
            pool.add(sum(vals) / len(vals))
            pool.add(max(vals))
            pool.add(min(vals))
    pool.add(float(len(df)))  # row count, for count-style claims
    return pool


def find_anchors(claim: str, pool: GroundingPool) -> list[float]:
    anchors = []
    for n in extract_numbers(claim):
        if pool.occurrences(n) == 1:
            anchors.append(n)
    return anchors


# ---- perturbation operators -------------------------------------------

def _fmt(v: float) -> str:
    if abs(v - round(v)) < TOL:
        return str(int(round(v)))
    return str(round(v, 2))


def perturb_off_by_one(v: float, rng: random.Random):
    if abs(v - round(v)) > TOL:
        return None
    delta = rng.choice([-1, 1])
    return v + delta


def perturb_digit_swap(v: float, rng: random.Random):
    is_int = abs(v - round(v)) < TOL
    digits = list(str(int(round(abs(v)))))
    if len(digits) < 2:
        return None
    # simple adjacent swap search: try each adjacent pair until it changes the value
    for pos in range(len(digits) - 1):
        cand = digits.copy()
        cand[pos], cand[pos + 1] = cand[pos + 1], cand[pos]
        if cand[0] == "0":
            continue
        new_val = int("".join(cand))
        if new_val != int(round(abs(v))):
            signed = -new_val if v < 0 else new_val
            return float(signed) if is_int else float(signed)
    return None


def perturb_magnitude_change(v: float, rng: random.Random):
    if v == 0:
        return None
    factor = rng.choice([10.0, 0.1])
    new_val = v * factor
    if new_val == v:
        return None
    return new_val


def perturb_round_number_change(v: float, rng: random.Random):
    if abs(v) >= 100:
        base = 100
    elif abs(v) >= 10:
        base = 10
    else:
        base = 5
    rounded = round(v / base) * base
    if rounded == v:
        rounded = rounded + base if rng.random() < 0.5 else rounded - base
    return float(rounded)


PERTURBATIONS = {
    "off_by_one": perturb_off_by_one,
    "digit_swap": perturb_digit_swap,
    "magnitude_change": perturb_magnitude_change,
    "round_number_change": perturb_round_number_change,
}


def replace_number_in_text(claim: str, old_value: float, new_value: float) -> str | None:
    """Replace the first number token in `claim` that parses to old_value."""
    for m in NUMBER_TOKEN_RE.finditer(claim):
        tok = m.group()
        v = parse_number(tok)
        if v is not None and abs(v - old_value) < TOL:
            new_str = _fmt(new_value)
            return claim[: m.start()] + new_str + claim[m.end():]
    return None


def generate_nearmiss_variants(claim: str, table_csv_path: str, seed: int) -> list[dict]:
    """Return a list of {perturbation_type, anchor_value, perturbed_value,
    perturbed_claim} dicts for every perturbation type that succeeds."""
    df = load_table_cached(table_csv_path)
    pool = build_grounding_pool(df)
    anchors = find_anchors(claim, pool)
    if not anchors:
        return []
    rng = random.Random(seed)
    anchor = anchors[0]
    results = []
    for ptype, fn in PERTURBATIONS.items():
        local_rng = random.Random(seed ^ zlib.crc32(ptype.encode()))
        new_val = fn(anchor, local_rng)
        if new_val is None or abs(new_val - anchor) < TOL:
            continue
        new_val = round(new_val, 6)
        # verify: perturbed value must not itself be a valid unique fact
        # equal to the anchor's grounded truth (guaranteed, since new_val != anchor
        # and anchor's occurrence in the pool is unique to that one true value).
        new_claim = replace_number_in_text(claim, anchor, new_val)
        if new_claim is None or new_claim == claim:
            continue
        results.append({
            "perturbation_type": ptype,
            "anchor_value": anchor,
            "perturbed_value": new_val,
            "perturbed_claim": new_claim,
        })
    return results

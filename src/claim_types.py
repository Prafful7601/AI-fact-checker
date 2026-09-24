"""Keyword-heuristic tagging of TabFact claims into lookup / count / comparison /
superlative / aggregation / other, and the numeric-subset filter.

Heuristics are intentionally simple and documented here (used verbatim in the
paper's Dataset section and Limitations, since heuristic typing is imperfect).
A claim can match multiple cue sets; priority order below picks one primary type.
"""
from __future__ import annotations
import re
from src.number_parsing import contains_digit, contains_number_word

COUNT_CUES = [
    "how many", "the number of", "number of", "there are", "there is",
    "a total of", "in total", "times", "occurrences", "occurs",
]
COMPARISON_CUES = [
    "more than", "less than", "fewer than", "greater than", "as many as",
    "compared to", "compare", "than", "higher than", "lower than",
    "before", "after", "earlier than", "later than",
]
SUPERLATIVE_CUES = [
    "most", "least", "highest", "lowest", "largest", "smallest", "biggest",
    "best", "worst", "first", "last", "top", "bottom", "maximum", "minimum",
    "only", "sole",
]
AGGREGATION_CUES = [
    "total", "sum", "average", "avg", "all of", "combined", "altogether",
    "mean",
]

# Priority when several cue sets match: aggregation is the most specific
# (overrides generic superlative words like "most"/"only" if a sum/avg cue
# is also present), then comparison, then count, then superlative.
_PRIORITY = ["aggregation", "comparison", "count", "superlative"]


def _match_any(text: str, cues: list[str]) -> bool:
    return any(c in text for c in cues)


def classify_claim_type(claim: str) -> str:
    text = f" {claim.lower()} "
    matches = {
        "aggregation": _match_any(text, AGGREGATION_CUES),
        "comparison": _match_any(text, COMPARISON_CUES),
        "count": _match_any(text, COUNT_CUES),
        "superlative": _match_any(text, SUPERLATIVE_CUES),
    }
    for t in _PRIORITY:
        if matches[t]:
            return t
    if contains_digit(claim) or contains_number_word(claim):
        return "lookup"
    return "other"


NUMERIC_CUES = (
    COUNT_CUES + COMPARISON_CUES + SUPERLATIVE_CUES + AGGREGATION_CUES
)


def is_numeric_claim(claim: str) -> bool:
    """A claim is 'numeric' if it contains digits/number words, or a
    count/comparison/superlative/aggregation cue phrase (spec definition)."""
    if contains_digit(claim):
        return True
    if contains_number_word(claim):
        return True
    text = f" {claim.lower()} "
    return _match_any(text, NUMERIC_CUES)

"""Tier 1 golden-pair suite: runs every case in evals/cases/tier1.json
through Tier 0 (must pass) and the Tier 1 scorer (ADR-002 fast lane).
"""

import json
from pathlib import Path

import pytest

from domains.housing.config import (
    SCORING_SPEC,
    SIMILARITY_ATTRIBUTES,
    TIER0_FILTERS,
    profile_to_entity,
)
from engine.filters import run_filters
from engine.scoring import score_pair

CASES_PATH = Path(__file__).resolve().parent.parent / "evals" / "cases" / "tier1.json"
SUITE = json.loads(CASES_PATH.read_text())


def run_case(case):
    a = profile_to_entity("a", case["profile_a"])
    b = profile_to_entity("b", case["profile_b"])
    decision = run_filters(a, b, TIER0_FILTERS)
    assert decision.passed, f"tier1 case failed tier0: {decision.failures}"
    return score_pair(a, b, SCORING_SPEC)


@pytest.mark.parametrize("case", SUITE["cases"], ids=lambda c: c["id"])
def test_tier1_case(case):
    result = run_case(case)
    expected = case["expected"]

    if "base_score" in expected:  # hard-constraint short-circuit case
        assert result.base_score == expected["base_score"]
        # Exactly the named constraint fires (one-variable isolation rule).
        assert {v.rule for v in result.violations} == {expected["failed_constraint"]}
        assert result.components == {}
    else:
        assert result.violations == ()
        lo, hi = expected["score_range"]
        assert lo <= result.base_score <= hi, (
            f"{case['id']}: base_score {result.base_score:.2f}"
            f" outside expected range [{lo}, {hi}]"
        )


def test_case_weights_match_housing_config():
    config_weights = {a.name: a.weight for a in SIMILARITY_ATTRIBUTES}
    assert SUITE["weights"] == config_weights

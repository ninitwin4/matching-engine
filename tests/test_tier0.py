"""Tier 0 golden-pair suite: runs every case in evals/cases/tier0.json
through the housing config and the engine filter stage (ADR-002 fast lane).
"""

import json
from pathlib import Path

import pytest

from domains.housing.config import (
    LOCATION_VOCABULARY,
    SCORING_SPEC,
    TIER0_FILTERS,
    profile_to_entity,
)
from engine.filters import run_filters
from engine.scoring import score_pair

CASES_PATH = Path(__file__).resolve().parent.parent / "evals" / "cases" / "tier0.json"
SUITE = json.loads(CASES_PATH.read_text())


def decide(case):
    a = profile_to_entity("a", case["profile_a"])
    b = profile_to_entity("b", case["profile_b"])
    return run_filters(a, b, TIER0_FILTERS)


@pytest.mark.parametrize("case", SUITE["cases"], ids=lambda c: c["id"])
def test_tier0_case(case):
    decision = decide(case)
    expected = case["expected"]

    if expected["tier0"] == "reject":
        assert expected["scored"] is False, "tier0 rejections must never be scored"
        assert not decision.passed
        # Golden-pair authoring rule (ADR-004 amendment 5): a rejection case
        # isolates exactly one variable, so exactly one filter may fire.
        assert {f.rule for f in decision.failures} == {expected["failed_filter"]}
        if "failing_direction" in expected:
            assert {f.direction.value for f in decision.failures} == {
                expected["failing_direction"]
            }
    else:
        assert expected["scored"] is True
        assert decision.passed, f"must-PASS case over-blocked: {decision.failures}"
        assert decision.failures == ()
        if "score_range" in expected:  # verifiable now that Tier 1 exists
            a = profile_to_entity("a", case["profile_a"])
            b = profile_to_entity("b", case["profile_b"])
            result = score_pair(a, b, SCORING_SPEC)
            assert result.violations == ()
            lo, hi = expected["score_range"]
            assert lo <= result.base_score <= hi, (
                f"{case['id']}: base_score {result.base_score:.2f}"
                f" outside expected range [{lo}, {hi}]"
            )


def test_case_vocabulary_matches_housing_config():
    assert set(SUITE["location_vocabulary"]) == set(LOCATION_VOCABULARY)

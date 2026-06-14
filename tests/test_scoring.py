"""Unit tests for intervals, hard constraints, and similarity scoring.

Synthetic attributes only — the engine must work with zero domain
vocabulary (ADR-003).
"""

import pytest

from engine.constraints import run_hard_constraints
from engine.intervals import intervals_overlap
from engine.scoring import score_pair, similarity_fraction
from engine.types import (
    Direction,
    Entity,
    IntervalOverlapRule,
    ScoringSpec,
    SimilarityAttribute,
    ToleranceOverride,
    ToleranceRule,
    Violation,
)

# ---- intervals ----


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ([1, 5], [4, 8], True),
        ([1, 5], [5, 8], True),  # touching endpoints overlap
        ([1, 5], [6, 8], False),
        ([None, 5], [4, None], True),  # None = unbounded
        ([None, 5], [6, None], False),
        ([None, None], [3, 4], True),
        (["2026-07-01", "2026-07-07"], ["2026-07-07", "2026-07-31"], True),
        (["2026-07-01", "2026-07-07"], ["2026-08-01", "2026-08-31"], False),
    ],
)
def test_intervals_overlap(a, b, expected):
    assert intervals_overlap(a, b) is expected
    assert intervals_overlap(b, a) is expected  # symmetric


# ---- hard constraints ----

LOUD = ToleranceRule(name="loud", actor="is_loud", tolerance="loud_ok")
LOUD_STRICT = ToleranceRule(
    name="loud",
    actor="is_loud",
    tolerance="loud_ok",
    override=ToleranceOverride(attribute="needs_silence", report_name="loud_strict"),
)
SPAN = IntervalOverlapRule(name="span", attribute="span")


def entity(eid, identity=None, preferences=None):
    return Entity(id=eid, identity=identity or {}, preferences=preferences or {})


def test_tolerance_violation_carries_direction():
    a = entity("a", {"is_loud": False}, {"loud_ok": False})
    b = entity("b", {"is_loud": True}, {"loud_ok": True})
    assert run_hard_constraints(a, b, [LOUD]) == (
        Violation(rule="loud", direction=Direction.A_TO_B),
    )


def test_tolerance_accepted_when_tolerant():
    a = entity("a", {"is_loud": True}, {"loud_ok": True})
    b = entity("b", {"is_loud": False}, {"loud_ok": True})
    assert run_hard_constraints(a, b, [LOUD]) == ()


def test_tolerance_skipped_when_fields_missing():
    assert run_hard_constraints(entity("a"), entity("b"), [LOUD]) == ()


def test_override_fires_with_its_own_name_and_subsumes_plain():
    a = entity("a", {"is_loud": False}, {"loud_ok": False, "needs_silence": True})
    b = entity("b", {"is_loud": True}, {"loud_ok": True})
    violations = run_hard_constraints(a, b, [LOUD_STRICT])
    assert violations == (Violation(rule="loud_strict", direction=Direction.A_TO_B),)


def test_override_ignores_stated_tolerance():
    # Tolerance says yes, override says strict: strict wins.
    a = entity("a", {"is_loud": False}, {"loud_ok": True, "needs_silence": True})
    b = entity("b", {"is_loud": True}, {"loud_ok": True})
    assert run_hard_constraints(a, b, [LOUD_STRICT]) == (
        Violation(rule="loud_strict", direction=Direction.A_TO_B),
    )


def test_interval_rule_symmetric_violation():
    a = entity("a", {"span": [1, 3]})
    b = entity("b", {"span": [5, 9]})
    assert run_hard_constraints(a, b, [SPAN]) == (Violation(rule="span"),)


# ---- similarity ----

ATTRS = (
    SimilarityAttribute(name="x", scale=(1, 5), weight=0.6),
    SimilarityAttribute(name="y", scale=(1, 5), weight=0.4),
)


def test_similarity_weighted():
    a = entity("a", {"x": 5, "y": 1})
    b = entity("b", {"x": 5, "y": 5})
    fraction, components = similarity_fraction(a, b, ATTRS)
    assert fraction == pytest.approx(0.6)  # x: 1.0 * 0.6, y: 0.0 * 0.4
    assert components == {"x": 1.0, "y": 0.0}


def test_similarity_renormalizes_over_present_attributes():
    a = entity("a", {"x": 3})
    b = entity("b", {"x": 5, "y": 2})  # y missing on a -> excluded
    fraction, components = similarity_fraction(a, b, ATTRS)
    assert fraction == pytest.approx(0.5)
    assert components == {"x": 0.5}


def test_similarity_coerces_booleans_to_scale_endpoints():
    a = entity("a", {"x": True})
    b = entity("b", {"x": 5})
    fraction, _ = similarity_fraction(a, b, ATTRS)
    assert fraction == pytest.approx(1.0)


def test_similarity_raises_when_nothing_shared():
    with pytest.raises(ValueError):
        similarity_fraction(entity("a"), entity("b"), ATTRS)


# ---- score_pair ----

SPEC = ScoringSpec(hard_constraints=(LOUD, SPAN), similarity=ATTRS, base_range=(0, 90))


def test_violation_short_circuits_to_floor_without_similarity():
    a = entity("a", {"span": [1, 3], "x": 5, "y": 5})
    b = entity("b", {"span": [5, 9], "x": 5, "y": 5})
    result = score_pair(a, b, SPEC)
    assert result.base_score == 0
    assert result.violations == (Violation(rule="span"),)
    assert result.components == {}  # similarity never ran


def test_clean_pair_scales_to_base_range():
    a = entity("a", {"x": 5, "y": 1}, {"loud_ok": True})
    b = entity("b", {"x": 5, "y": 5}, {"loud_ok": True})
    result = score_pair(a, b, SPEC)
    assert result.base_score == pytest.approx(54.0)  # 0.6 * 90
    assert result.violations == ()

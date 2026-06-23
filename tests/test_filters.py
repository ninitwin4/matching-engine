"""Unit tests for the generic filter primitives.

Uses synthetic attributes only — the engine must work with zero domain
vocabulary (ADR-003).
"""

import pytest

from engine.filters import run_filters
from engine.types import (
    ACCEPT_ANY,
    AcceptsRule,
    Direction,
    Entity,
    FilterFailure,
    SameValueRule,
)

SAME_COLOR = SameValueRule(name="color", attribute="color")
SHAPE_ACCEPTS = AcceptsRule(
    name="shape",
    preference="shape_pref",
    attribute="shape",
    accepted={
        "round_only": frozenset({"circle"}),
        "anything": ACCEPT_ANY,
    },
)


def entity(eid, color="red", shape="circle", shape_pref="anything"):
    return Entity(
        id=eid,
        identity={"color": color, "shape": shape},
        preferences={"shape_pref": shape_pref},
    )


def test_all_rules_pass():
    decision = run_filters(entity("a"), entity("b"), [SAME_COLOR, SHAPE_ACCEPTS])
    assert decision.passed
    assert decision.failures == ()


def test_same_value_rejects_differing_identity():
    decision = run_filters(
        entity("a", color="red"), entity("b", color="blue"), [SAME_COLOR]
    )
    assert not decision.passed
    assert decision.failures == (FilterFailure(rule="color"),)


def test_accepts_reports_the_failing_direction():
    a = entity("a", shape_pref="round_only")
    b = entity("b", shape="square", shape_pref="anything")
    decision = run_filters(a, b, [SHAPE_ACCEPTS])
    assert decision.failures == (
        FilterFailure(rule="shape", direction=Direction.A_TO_B),
    )


def test_accepts_can_fail_both_directions():
    a = entity("a", shape="square", shape_pref="round_only")
    b = entity("b", shape="square", shape_pref="round_only")
    decision = run_filters(a, b, [SHAPE_ACCEPTS])
    assert {f.direction for f in decision.failures} == {
        Direction.A_TO_B,
        Direction.B_TO_A,
    }


def test_accept_any_passes_every_identity_value():
    a = entity("a", shape_pref="anything")
    b = entity("b", shape="hexagon", shape_pref="anything")
    assert run_filters(a, b, [SHAPE_ACCEPTS]).passed


def test_all_failing_rules_are_reported():
    a = entity("a", color="red", shape="square", shape_pref="round_only")
    b = entity("b", color="blue", shape="square", shape_pref="round_only")
    decision = run_filters(a, b, [SAME_COLOR, SHAPE_ACCEPTS])
    assert {f.rule for f in decision.failures} == {"color", "shape"}


def test_unknown_preference_value_raises():
    a = entity("a", shape_pref="triangles_only")
    with pytest.raises(KeyError):
        run_filters(a, entity("b"), [SHAPE_ACCEPTS])

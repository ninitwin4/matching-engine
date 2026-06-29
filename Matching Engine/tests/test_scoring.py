"""Unit tests for intervals, hard constraints, and similarity scoring.

Synthetic attributes only — the engine must work with zero domain
vocabulary (ADR-003).
"""

import pytest

from engine.constraints import run_hard_constraints
from engine.intervals import intervals_overlap
from engine.scoring import score_pair, similarity_fraction
from engine.types import (
    ACCEPT_ANY,
    ComplementaryAttribute,
    Direction,
    Entity,
    IntervalOverlapRule,
    ScoringSpec,
    SimilarityAttribute,
    SoftPreferenceRule,
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


# ---- complementary + soft preference (ADR-006) ----

LEVELS = {"effective": 1.0, "neutral": 0.5, "ineffective": 0.0}
COMP = ComplementaryAttribute(
    name="fit", need="need", strengths="strengths", levels=LEVELS, weight=1.0
)


def test_complementary_scores_provider_strength_in_need():
    patient = Entity("p", {"need": "trauma"})
    strong = Entity("t1", {"strengths": {"trauma": "effective", "depression": "neutral"}})
    weak = Entity("t2", {"strengths": {"trauma": "ineffective"}})
    spec = ScoringSpec(hard_constraints=(), similarity=(), base_range=(0, 90),
                       complementary=(COMP,))
    assert score_pair(patient, strong, spec).base_score == pytest.approx(90.0)
    assert score_pair(patient, weak, spec).base_score == pytest.approx(0.0)


def test_complementary_missing_dimension_uses_missing_level():
    patient = Entity("p", {"need": "substance_use"})
    therapist = Entity("t", {"strengths": {"trauma": "effective"}})  # no substance_use
    spec = ScoringSpec(hard_constraints=(), similarity=(), base_range=(0, 90),
                       complementary=(COMP,))
    assert score_pair(patient, therapist, spec).base_score == pytest.approx(0.0)


def test_complementary_is_orientation_robust():
    # Directional need must score the same whichever entity is passed first,
    # so the pipeline's min-of-both-directions rule yields the forward score.
    patient = Entity("p", {"need": "trauma"})
    therapist = Entity("t", {"strengths": {"trauma": "effective"}})
    spec = ScoringSpec(hard_constraints=(), similarity=(), base_range=(0, 90),
                       complementary=(COMP,))
    assert (score_pair(patient, therapist, spec).base_score
            == score_pair(therapist, patient, spec).base_score
            == pytest.approx(90.0))


GENDER_PREF = SoftPreferenceRule(
    name="gender_pref", preference="wants", attribute="gender",
    accepted={"female": frozenset({"female"}), "any": ACCEPT_ANY},
    weight=1.0, unmet_score=0.25,
)


def test_soft_preference_met_unmet_and_absent():
    spec = ScoringSpec(hard_constraints=(), similarity=(), base_range=(0, 100),
                       soft_preferences=(GENDER_PREF,))
    a_wants_f = Entity("a", {}, {"wants": "female"})
    fem = Entity("f", {"gender": "female"})
    masc = Entity("m", {"gender": "male"})
    assert score_pair(a_wants_f, fem, spec).base_score == pytest.approx(100.0)  # met
    assert score_pair(a_wants_f, masc, spec).base_score == pytest.approx(25.0)  # unmet penalty
    # No preference stated -> factor skipped -> no scored factors -> raises.
    with pytest.raises(ValueError):
        score_pair(Entity("a", {}, {}), masc, spec)


def test_complementary_dominates_when_weighted_higher():
    # complementary weight 0.8 vs similarity 0.2 -> complementary drives ranking.
    sim = SimilarityAttribute(name="lang", scale=(1, 5), weight=0.2)
    comp = ComplementaryAttribute(name="fit", need="need", strengths="strengths",
                                  levels=LEVELS, weight=0.8)
    spec = ScoringSpec(hard_constraints=(), similarity=(sim,), base_range=(0, 90),
                       complementary=(comp,))
    patient = Entity("p", {"need": "trauma", "lang": 3})
    # Strong on trauma but dissimilar language vs weak on trauma but identical language.
    strong = Entity("t1", {"strengths": {"trauma": "effective"}, "lang": 1})
    weak = Entity("t2", {"strengths": {"trauma": "ineffective"}, "lang": 3})
    assert score_pair(patient, strong, spec).base_score > score_pair(patient, weak, spec).base_score

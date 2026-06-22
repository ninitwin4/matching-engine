"""Tier 1 deterministic base score: hard constraints, then weighted
similarity, scaled to the spec's base range (ADR-001: 0–90 for housing).

Missing-data policy (v1): similarity attributes absent on either side are
excluded and the remaining weights renormalized, so partial profiles are
scored on what they share rather than penalized for gaps. Booleans coerce
to the scale endpoints (True = high, False = low).
"""

from engine.constraints import run_hard_constraints
from engine.types import (
    Entity,
    FinalScore,
    ScoreResult,
    ScoringSpec,
    SimilarityAttribute,
)


def _coerce(value, scale: tuple[float, float]) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return scale[1] if value else scale[0]
    return float(value)


def similarity_fraction(
    a: Entity, b: Entity, attributes: tuple[SimilarityAttribute, ...]
) -> tuple[float, dict[str, float]]:
    """Weighted similarity in [0, 1] plus the per-attribute breakdown
    (stored for auditability — ADR-001's explainable-arithmetic requirement)."""
    components: dict[str, float] = {}
    weighted_sum = 0.0
    total_weight = 0.0
    for attr in attributes:
        value_a = _coerce(a.identity.get(attr.name), attr.scale)
        value_b = _coerce(b.identity.get(attr.name), attr.scale)
        if value_a is None or value_b is None:
            continue
        similarity = 1.0 - abs(value_a - value_b) / (attr.scale[1] - attr.scale[0])
        components[attr.name] = similarity
        weighted_sum += attr.weight * similarity
        total_weight += attr.weight
    if total_weight == 0.0:
        raise ValueError(
            f"no similarity attributes present on both entities ({a.id!r}, {b.id!r})"
        )
    return weighted_sum / total_weight, components


def score_pair(a: Entity, b: Entity, spec: ScoringSpec) -> ScoreResult:
    violations = run_hard_constraints(a, b, spec.hard_constraints)
    lo, hi = spec.base_range
    if violations:
        return ScoreResult(base_score=lo, violations=violations)
    fraction, components = similarity_fraction(a, b, spec.similarity)
    return ScoreResult(base_score=lo + fraction * (hi - lo), components=components)


def final_score(base_a_to_b: float, base_b_to_a: float, bonus: float) -> FinalScore:
    """Assemble the displayed score at read time (ADR-001, ADR-004 §3).

    The base scores are directional; the Tier 2 bonus is pair-level, so the
    same adjustment applies to both directions. The headline displays the
    minimum of the two — cohabitation is a weakest-link system (ADR-004).
    Inputs stay stored separately; this is the only place they combine.
    """
    a_to_b = base_a_to_b + bonus
    b_to_a = base_b_to_a + bonus
    return FinalScore(a_to_b=a_to_b, b_to_a=b_to_a, display=min(a_to_b, b_to_a))

"""Tier 1 deterministic base score: hard constraints, then a weighted blend of
scored factors (similarity, complementary, soft preference), scaled to the
spec's base range (ADR-001 roles; ADR-006 blend).

Missing-data policy (v1): factors absent on the pair are excluded and the
remaining weights renormalized, so partial profiles are scored on what they
share rather than penalized for gaps. Booleans coerce to the scale endpoints
(True = high, False = low). The relative weight of each role is the only thing
that makes a domain similarity-dominant (housing) or complementary-dominant
(healthcare) — the engine itself is role-agnostic.
"""

from engine.constraints import run_hard_constraints
from engine.types import (
    ACCEPT_ANY,
    ComplementaryAttribute,
    Entity,
    FinalScore,
    ScoreResult,
    ScoringSpec,
    SimilarityAttribute,
    SoftPreferenceRule,
)


def _coerce(value, scale: tuple[float, float]) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return scale[1] if value else scale[0]
    return float(value)


def _pair_similarity(a: Entity, b: Entity, attr: SimilarityAttribute) -> float | None:
    """Closeness in [0, 1] for one attribute, or None if absent on either side."""
    value_a = _coerce(a.identity.get(attr.name), attr.scale)
    value_b = _coerce(b.identity.get(attr.name), attr.scale)
    if value_a is None or value_b is None:
        return None
    return 1.0 - abs(value_a - value_b) / (attr.scale[1] - attr.scale[0])


def similarity_fraction(
    a: Entity, b: Entity, attributes: tuple[SimilarityAttribute, ...]
) -> tuple[float, dict[str, float]]:
    """Weighted similarity in [0, 1] plus the per-attribute breakdown
    (stored for auditability — ADR-001's explainable-arithmetic requirement)."""
    components: dict[str, float] = {}
    weighted_sum = 0.0
    total_weight = 0.0
    for attr in attributes:
        s = _pair_similarity(a, b, attr)
        if s is None:
            continue
        components[attr.name] = s
        weighted_sum += attr.weight * s
        total_weight += attr.weight
    if total_weight == 0.0:
        raise ValueError(
            f"no similarity attributes present on both entities ({a.id!r}, {b.id!r})"
        )
    return weighted_sum / total_weight, components


def _complementary_lookup(
    needer: Entity, provider: Entity, attr: ComplementaryAttribute
) -> float | None:
    """Score for one orientation, or None if this orientation has no need or no
    strengths map (so the other orientation can be tried)."""
    need = needer.identity.get(attr.need)
    strengths = provider.identity.get(attr.strengths)
    if need is None or not hasattr(strengths, "get"):
        return None
    level = strengths.get(need)
    if level is None:  # provider has no measured strength for this need
        return attr.missing_level
    return attr.levels.get(level, attr.missing_level)


def _complementary_value(a: Entity, b: Entity, attr: ComplementaryAttribute) -> float | None:
    """Orientation-robust: locate the (needer, provider) relationship wherever
    it sits in the pair, so the score is independent of argument order."""
    v = _complementary_lookup(a, b, attr)
    if v is not None:
        return v
    return _complementary_lookup(b, a, attr)


def _soft_preference_value(a: Entity, b: Entity, rule: SoftPreferenceRule) -> float | None:
    """Seeker `a`'s stated preference against candidate `b`; None when no
    preference is stated (factor skipped), 1.0 when met, `unmet_score` when not."""
    pref = a.preferences.get(rule.preference)
    if pref is None:
        return None
    accepted = rule.accepted.get(pref)
    if accepted is ACCEPT_ANY:
        return 1.0
    if accepted is None:
        return rule.unmet_score
    return 1.0 if b.identity.get(rule.attribute) in accepted else rule.unmet_score


def _blend(a: Entity, b: Entity, spec: ScoringSpec) -> tuple[float, dict[str, float]]:
    """Weighted blend over every present scored factor, jointly renormalized
    (ADR-006). Role weights alone decide what dominates."""
    components: dict[str, float] = {}
    weighted_sum = 0.0
    total_weight = 0.0

    def add(name, weight, value):
        nonlocal weighted_sum, total_weight
        if value is None:
            return
        components[name] = value
        weighted_sum += weight * value
        total_weight += weight

    for attr in spec.similarity:
        add(attr.name, attr.weight, _pair_similarity(a, b, attr))
    for attr in spec.complementary:
        add(attr.name, attr.weight, _complementary_value(a, b, attr))
    for rule in spec.soft_preferences:
        add(rule.name, rule.weight, _soft_preference_value(a, b, rule))

    if total_weight == 0.0:
        raise ValueError(
            f"no scored factors present on both entities ({a.id!r}, {b.id!r})"
        )
    return weighted_sum / total_weight, components


def score_pair(a: Entity, b: Entity, spec: ScoringSpec) -> ScoreResult:
    violations = run_hard_constraints(a, b, spec.hard_constraints)
    lo, hi = spec.base_range
    if violations:
        return ScoreResult(base_score=lo, violations=violations)
    fraction, components = _blend(a, b, spec)
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

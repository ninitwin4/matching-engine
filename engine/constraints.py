"""Tier 1 hard constraints: any violation zeroes the base score before
similarity runs (ADR-001). All violations are reported, not just the first.

Missing-data policy (v1): a constraint whose fields are absent on the
relevant side is skipped, not violated — golden pairs authored before the
schema was pinned omit fields, and the questionnaire enforces required
fields at intake.
"""

from typing import Iterable

from engine.intervals import intervals_overlap
from engine.types import (
    Direction,
    Entity,
    HardConstraintRule,
    IntervalOverlapRule,
    ToleranceRule,
    Violation,
)


def _check_tolerance(
    rule: ToleranceRule, evaluator: Entity, candidate: Entity, direction: Direction
) -> Violation | None:
    actor = candidate.identity.get(rule.actor)
    if actor is None:
        return None
    if rule.override is not None and evaluator.preferences.get(rule.override.attribute):
        # Strict mode: the candidate's behavior alone decides, and the
        # stricter check subsumes the plain tolerance check.
        if actor:
            return Violation(rule=rule.override.report_name, direction=direction)
        return None
    tolerance = evaluator.preferences.get(rule.tolerance)
    if tolerance is None:
        return None
    if actor and not tolerance:
        return Violation(rule=rule.name, direction=direction)
    return None


def run_hard_constraints(
    a: Entity, b: Entity, rules: Iterable[HardConstraintRule]
) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    for rule in rules:
        if isinstance(rule, ToleranceRule):
            for direction, evaluator, candidate in (
                (Direction.A_TO_B, a, b),
                (Direction.B_TO_A, b, a),
            ):
                violation = _check_tolerance(rule, evaluator, candidate, direction)
                if violation is not None:
                    violations.append(violation)
        elif isinstance(rule, IntervalOverlapRule):
            interval_a = a.identity.get(rule.attribute)
            interval_b = b.identity.get(rule.attribute)
            if interval_a is None or interval_b is None:
                continue
            if not intervals_overlap(interval_a, interval_b):
                violations.append(Violation(rule=rule.name))
        else:  # pragma: no cover
            raise TypeError(f"unknown hard-constraint rule type: {type(rule).__name__}")
    return tuple(violations)

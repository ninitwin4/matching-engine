"""Tier 0 filter stage: viability gates that run before any scoring.

Failed pairs are never scored (ADR-004). All failing rules are reported,
not just the first, so rejections stay auditable.
"""

from typing import Iterable

from engine.types import (
    AcceptsRule,
    Direction,
    Entity,
    FilterDecision,
    FilterFailure,
    FilterRule,
    SameValueRule,
    ACCEPT_ANY,
)


def run_filters(a: Entity, b: Entity, rules: Iterable[FilterRule]) -> FilterDecision:
    failures: list[FilterFailure] = []
    for rule in rules:
        if isinstance(rule, SameValueRule):
            if a.identity[rule.attribute] != b.identity[rule.attribute]:
                failures.append(FilterFailure(rule=rule.name))
        elif isinstance(rule, AcceptsRule):
            for direction, evaluator, candidate in (
                (Direction.A_TO_B, a, b),
                (Direction.B_TO_A, b, a),
            ):
                accepted = rule.accepted[evaluator.preferences[rule.preference]]
                if accepted is ACCEPT_ANY:
                    continue
                if candidate.identity[rule.attribute] not in accepted:
                    failures.append(FilterFailure(rule=rule.name, direction=direction))
        else:  # pragma: no cover
            raise TypeError(f"unknown filter rule type: {type(rule).__name__}")
    return FilterDecision(passed=not failures, failures=tuple(failures))

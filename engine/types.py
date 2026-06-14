"""Generic data types for the matching engine core.

The engine speaks only in entities, attributes, rules, and decisions
(ADR-003). Domain vocabulary (what the attributes mean) lives in domain
configs under domains/, which import this package — never the reverse.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class Direction(str, Enum):
    """Which side's preferences were being evaluated (ADR-004 §3).

    A_TO_B means B was evaluated against A's preferences.
    """

    A_TO_B = "a_to_b"
    B_TO_A = "b_to_a"


class _AcceptAny:
    def __repr__(self) -> str:  # pragma: no cover
        return "ACCEPT_ANY"


# Sentinel for an AcceptsRule preference value that accepts every identity
# value (e.g. an "open to all" option in a domain config).
ACCEPT_ANY = _AcceptAny()


@dataclass(frozen=True)
class Entity:
    """A matchable entity.

    Identity attributes (what the entity is) and preferences-about-others
    (what it wants in a counterpart) are first-class and separate
    (ADR-003 amendment 2).
    """

    id: str
    identity: Mapping[str, Any] = field(default_factory=dict)
    preferences: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SameValueRule:
    """Tier 0 gate: both entities must hold the same identity value."""

    name: str
    attribute: str


@dataclass(frozen=True)
class AcceptsRule:
    """Tier 0 gate: each side's preference must accept the other's identity.

    `accepted` maps each preference value to the set of identity values it
    accepts, or to ACCEPT_ANY. Evaluated in both directions; one failing
    direction rejects the pair.
    """

    name: str
    preference: str
    attribute: str
    accepted: Mapping[Any, Any]


FilterRule = SameValueRule | AcceptsRule


@dataclass(frozen=True)
class FilterFailure:
    rule: str
    direction: Direction | None = None


@dataclass(frozen=True)
class FilterDecision:
    """The Tier 0 verdict for a pair.

    A rejection is "not a match" — it carries no score, and scoring must
    never run on a rejected pair (ADR-004).
    """

    passed: bool
    failures: tuple[FilterFailure, ...] = ()


@dataclass(frozen=True)
class ToleranceOverride:
    """Escalates a ToleranceRule to strict for entities that set `attribute`.

    When the evaluating side's override attribute is truthy, the candidate's
    actor attribute alone decides — the evaluator's stated tolerance is
    ignored. Violations report under `report_name` so domains can label the
    stricter failure distinctly.
    """

    attribute: str
    report_name: str


@dataclass(frozen=True)
class ToleranceRule:
    """Tier 1 hard constraint: behavior vs the other side's tolerance.

    Checked in both directions: the candidate's identity `actor` attribute
    against the evaluator's preference `tolerance` attribute. Truthy actor
    with falsy tolerance is a violation. Directions follow ADR-004 §3
    (A_TO_B = A's preferences evaluating B).
    """

    name: str
    actor: str
    tolerance: str
    override: ToleranceOverride | None = None


@dataclass(frozen=True)
class IntervalOverlapRule:
    """Tier 1 hard constraint: both entities' closed intervals must overlap.

    Symmetric, so violations carry no direction. None bounds are unbounded.
    """

    name: str
    attribute: str


HardConstraintRule = ToleranceRule | IntervalOverlapRule


@dataclass(frozen=True)
class Violation:
    rule: str
    direction: Direction | None = None


@dataclass(frozen=True)
class SimilarityAttribute:
    """A scored identity attribute: closeness on `scale`, weighted."""

    name: str
    scale: tuple[float, float]
    weight: float


@dataclass(frozen=True)
class ScoringSpec:
    """Everything the engine needs to score a pair; built by a domain config."""

    hard_constraints: tuple[HardConstraintRule, ...]
    similarity: tuple[SimilarityAttribute, ...]
    base_range: tuple[float, float]


@dataclass(frozen=True)
class ScoreResult:
    """Tier 1 outcome. Violations short-circuit: base_score is the range
    floor and `components` stays empty (similarity never ran, ADR-001)."""

    base_score: float
    violations: tuple[Violation, ...] = ()
    components: Mapping[str, float] = field(default_factory=dict)

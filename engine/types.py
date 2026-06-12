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

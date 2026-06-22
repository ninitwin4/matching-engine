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
    """A scored identity attribute: closeness on `scale`, weighted.
    Rewards alikeness — two near values score high (ADR-001 role)."""

    name: str
    scale: tuple[float, float]
    weight: float


@dataclass(frozen=True)
class ComplementaryAttribute:
    """Strength-fills-need scoring (ADR-001 role; ADR-006). One side of the pair
    has a `need` (a dimension label); the other holds a `strengths` map of
    dimension -> level label. The score is the provider's level in the needed
    dimension, mapped through `levels` to a fraction.

    Orientation-robust: the (needer, provider) relationship is located within
    the pair regardless of argument order, so a directional need scores the same
    whichever entity is passed first — which lets the directional pipeline's
    min rule handle asymmetric matching unchanged (ADR-006)."""

    name: str
    need: str
    strengths: str
    levels: Mapping[Any, float]
    weight: float
    missing_level: float = 0.0


@dataclass(frozen=True)
class SoftPreferenceRule:
    """A weighted, non-exclusionary preference (ADR-001 role). The seeker's
    `preference` (in preferences) is tested against the candidate's `attribute`
    via `accepted` (value -> accepted set | ACCEPT_ANY). Met -> 1.0; a stated
    but unmet preference -> `unmet_score` (a penalty, never a disqualification);
    no preference stated -> the factor is skipped."""

    name: str
    preference: str
    attribute: str
    accepted: Mapping[Any, Any]
    weight: float
    unmet_score: float = 0.0


@dataclass(frozen=True)
class ScoringSpec:
    """Everything the engine needs to score a pair; built by a domain config.
    `complementary` and `soft_preferences` default empty so similarity-only
    domains (housing) are unaffected (ADR-006)."""

    hard_constraints: tuple[HardConstraintRule, ...]
    similarity: tuple[SimilarityAttribute, ...]
    base_range: tuple[float, float]
    complementary: tuple[ComplementaryAttribute, ...] = ()
    soft_preferences: tuple[SoftPreferenceRule, ...] = ()


@dataclass(frozen=True)
class ScoreResult:
    """Tier 1 outcome. Violations short-circuit: base_score is the range
    floor and `components` stays empty (similarity never ran, ADR-001)."""

    base_score: float
    violations: tuple[Violation, ...] = ()
    components: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class AIBonusSpec:
    """Everything the engine needs to compute a Tier 2 nuance bonus; built by
    a domain config. The engine knows the mechanism (call, parse, clamp,
    degrade); the domain owns the prompt and model choice (ADR-003)."""

    model: str
    system_prompt: str
    cap: float = 10.0  # hard cap, ADR-001 — enforced in code, not by prompt
    max_tokens: int = 1024
    # Tiered escalation (ADR-005): sample the primary model `samples` times;
    # if the samples disagree by more than `agreement_threshold`, escalate to
    # `escalation_model`. escalation_model=None disables escalation.
    escalation_model: str | None = None
    samples: int = 2
    agreement_threshold: float = 1.0


@dataclass(frozen=True)
class AIBonusResult:
    """Tier 2 outcome. `adjustment` is always within [-cap, cap] — clamped in
    code, never trusted to the model. `raw_adjustment` preserves what the model
    actually returned (None when degraded). On any failure the engine degrades
    to a zero adjustment so a match never depends on LLM availability
    (ADR-001)."""

    adjustment: float
    rationale: str
    raw_adjustment: float | None = None
    degraded: bool = False
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class EscalatedBonusResult:
    """Outcome of the tiered escalation policy (ADR-005). Carries the final
    adjustment plus enough provenance to audit escalation rate and per-model
    cost: the primary-model `samples` and the secondary-model `escalation`
    call (None when the samples agreed and no escalation happened)."""

    adjustment: float
    rationale: str
    raw_adjustment: float | None
    degraded: bool
    model: str  # the model that produced the final adjustment
    escalated: bool
    samples: tuple["AIBonusResult", ...]
    escalation: "AIBonusResult | None"
    latency_ms: float


@dataclass(frozen=True)
class FinalScore:
    """Read-time assembly of base + bonus. Stored fields stay separate and
    are never blended (ADR-001); `display` is the minimum of the two
    directions (ADR-004 §3)."""

    a_to_b: float
    b_to_a: float
    display: float


@dataclass(frozen=True)
class Match:
    """One ranked match in an end-to-end run. `display_score` is what the card
    shows (min of the two directions, ADR-004); the base scores, AI adjustment,
    and rationale are kept separate, never blended (ADR-001). `components` is
    the similarity breakdown for the detail view."""

    candidate_id: str
    display_score: float
    base_a_to_b: float
    base_b_to_a: float
    ai_adjustment: float
    ai_rationale: str
    ai_applied: bool  # was the bonus run (i.e. in top-N)?
    degraded: bool  # did the LLM call fall back to base?
    components: Mapping[str, float] = field(default_factory=dict)

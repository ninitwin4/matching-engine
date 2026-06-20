"""Housing domain config: loads housing-config-v1.yaml (the single source
of truth, ADR-003's public config contract) and binds it to the generic
engine primitives. Engine code never imports from this package.
"""

from pathlib import Path
from typing import Any, Mapping

import yaml

from engine.types import (
    ACCEPT_ANY,
    AcceptsRule,
    Entity,
    FilterRule,
    HardConstraintRule,
    IntervalOverlapRule,
    SameValueRule,
    ScoringSpec,
    SimilarityAttribute,
    ToleranceOverride,
    ToleranceRule,
)

CONFIG_PATH = Path(__file__).resolve().parent / "housing-config-v1.yaml"
_raw = yaml.safe_load(CONFIG_PATH.read_text())

# Fields that describe what the entity wants in (or can tolerate from) a
# counterpart, routed to Entity.preferences (ADR-003 amendment 2).
PREFERENCE_FIELDS = ("gender_preference", "smoking_ok", "pets_ok", "pet_allergy")

# The YAML names constraints; the questionnaire attribute names they bind to
# are housing glue. Interval constraints use their own name as the attribute.
_TOLERANCE_BINDINGS = {
    "smoking": ("smoking", "smoking_ok"),
    "pets": ("has_pet", "pets_ok"),
}
_OVERRIDE_BINDINGS = {
    # Allergy is stricter than preference: checked against actual household
    # pets, never soft (ADR-001 amendment 2026-06-12).
    "pets": ToleranceOverride(attribute="pet_allergy", report_name="pets_allergy"),
}


# ---- Tier 0 filters ----

LOCATION_VOCABULARY = frozenset(_raw["filters"]["location"]["vocabulary"])
GENDER_IDENTITIES = frozenset(_raw["filters"]["gender"]["identity_options"])


def _gender_accepts() -> Mapping[str, Any]:
    # "<identity>_only" accepts exactly that identity; open_to_all accepts
    # anything. self_describe appears in no *_only set, so those users pass
    # only open_to_all — the documented trade-off of ADR-004 §2.
    accepts: dict[str, Any] = {}
    for option in _raw["filters"]["gender"]["preference_options"]:
        if option == "open_to_all":
            accepts[option] = ACCEPT_ANY
        else:
            identity = option.removesuffix("_only")
            assert identity in GENDER_IDENTITIES, f"unmapped preference {option!r}"
            accepts[option] = frozenset({identity})
    return accepts


GENDER_ACCEPTS = _gender_accepts()

TIER0_FILTERS: tuple[FilterRule, ...] = (
    SameValueRule(name="location", attribute="location"),
    AcceptsRule(
        name="gender",
        preference="gender_preference",
        attribute="gender",
        accepted=GENDER_ACCEPTS,
    ),
)


# ---- Tier 1 scoring ----

def _hard_constraints() -> tuple[HardConstraintRule, ...]:
    rules: list[HardConstraintRule] = []
    for name, cfg in _raw["hard_constraints"].items():
        if cfg["type"] == "bidirectional_tolerance":
            actor, tolerance = _TOLERANCE_BINDINGS[name]
            override = (
                _OVERRIDE_BINDINGS[name] if cfg.get("allergy_override") else None
            )
            rules.append(
                ToleranceRule(
                    name=name, actor=actor, tolerance=tolerance, override=override
                )
            )
        elif cfg["type"] == "interval_overlap":
            # NOTE: budget's graded_above_floor (score scaled by overlap
            # size above the hard floor, ADR-001 amendment 1) is not yet
            # implemented; v1 scores the floor only.
            rules.append(IntervalOverlapRule(name=name, attribute=name))
        else:
            raise ValueError(f"unknown hard-constraint type {cfg['type']!r}")
    return tuple(rules)


HARD_CONSTRAINTS = _hard_constraints()

SIMILARITY_ATTRIBUTES = tuple(
    SimilarityAttribute(name=name, scale=tuple(cfg["scale"]), weight=cfg["weight"])
    for name, cfg in _raw["similarity"].items()
)
assert round(sum(a.weight for a in SIMILARITY_ATTRIBUTES), 10) == 1.0

SCORING_SPEC = ScoringSpec(
    hard_constraints=HARD_CONSTRAINTS,
    similarity=SIMILARITY_ATTRIBUTES,
    base_range=tuple(_raw["base_score_range"]),
)

# Tier 2 applies the AI bonus only to each seeker's top-N candidates by base
# score (ADR-001 amendment 2). N is domain config, not engine.
TOP_N = _raw["ai_bonus"]["top_n"]


# ---- Profile glue ----

# Required by ADR-004 §2: identity, preference, and location are mandatory.
REQUIRED_FIELDS = ("gender", "gender_preference", "location")


def profile_to_entity(entity_id: str, profile: Mapping[str, Any]) -> Entity:
    """Translate a flat questionnaire profile into an engine Entity.

    Validates required fields against the controlled vocabularies — unknown
    values must fail loudly here, because exact-match filtering downstream
    would just silently never match them.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in profile]
    if missing:
        raise ValueError(f"profile {entity_id!r} missing required fields: {missing}")
    if profile["location"] not in LOCATION_VOCABULARY:
        raise ValueError(
            f"profile {entity_id!r}: unknown location {profile['location']!r}"
        )
    if profile["gender"] not in GENDER_IDENTITIES:
        raise ValueError(f"profile {entity_id!r}: unknown gender {profile['gender']!r}")
    if profile["gender_preference"] not in GENDER_ACCEPTS:
        raise ValueError(
            f"profile {entity_id!r}: unknown gender_preference"
            f" {profile['gender_preference']!r}"
        )
    identity = {k: v for k, v in profile.items() if k not in PREFERENCE_FIELDS}
    preferences = {k: v for k, v in profile.items() if k in PREFERENCE_FIELDS}
    return Entity(id=entity_id, identity=identity, preferences=preferences)

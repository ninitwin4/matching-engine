"""Healthcare domain config loader: builds engine specs from
healthcare-config-v1.yaml. Domain glue only — the engine imports nothing from
here (ADR-003). Demonstrates the complementary + soft_preference roles (ADR-006)
that the housing reference never exercised.

SYNTHETIC DEMO ONLY — not a clinical product, no PHI (see the YAML header).
"""

from pathlib import Path
from typing import Any, Mapping

import yaml

from engine.types import (
    ACCEPT_ANY,
    ComplementaryAttribute,
    Entity,
    FilterRule,
    HardConstraintRule,
    SameValueRule,
    ScoringSpec,
    SimilarityAttribute,
    SoftPreferenceRule,
    ToleranceRule,
)

CONFIG_PATH = Path(__file__).resolve().parent / "healthcare-config-v1.yaml"
_raw = yaml.safe_load(CONFIG_PATH.read_text())

# Fields describing what the patient wants/tolerates in a therapist -> preferences.
# Everything else (incl. the therapist effectiveness map and identity flags) is
# identity. The patient/therapist schemas are asymmetric; routing is shared.
PREFERENCE_FIELDS = (
    "accepts_telehealth",       # tolerance for the modality hard constraint
    "therapist_gender_pref",
    "wants_sliding_scale",
    "schedule_pref",
)

# Unary therapist eligibility — gated in the domain pre-filter (match.py), not
# by an engine rule (relational gates only live in Tier 0).
AVAILABILITY_FIELDS = ("accepts_new_patients", "has_capacity")


def _accepts(raw: Mapping[str, Any]) -> dict[Any, Any]:
    out: dict[Any, Any] = {}
    for key, val in raw.items():
        out[key] = ACCEPT_ANY if val == "ANY" else frozenset(val)
    return out


# ---- Tier 0 filters ----
TIER0_FILTERS: tuple[FilterRule, ...] = tuple(
    SameValueRule(name=name, attribute=name)
    for name, cfg in _raw["filters"].items()
    if cfg["type"] == "exact_match"
)


# ---- Tier 1 hard constraints ----
def _hard_constraints() -> tuple[HardConstraintRule, ...]:
    rules: list[HardConstraintRule] = []
    for name, cfg in _raw.get("hard_constraints", {}).items():
        if cfg["type"] == "bidirectional_tolerance":
            rules.append(
                ToleranceRule(
                    name=name, actor=cfg["actor"], tolerance=cfg["tolerance"]
                )
            )
        else:
            raise ValueError(f"unknown hard-constraint type {cfg['type']!r}")
    return tuple(rules)


HARD_CONSTRAINTS = _hard_constraints()

# ---- Tier 1 scored roles ----
SIMILARITY_ATTRIBUTES = tuple(
    SimilarityAttribute(name=name, scale=tuple(cfg["scale"]), weight=cfg["weight"])
    for name, cfg in _raw.get("similarity", {}).items()
)

COMPLEMENTARY_ATTRIBUTES = tuple(
    ComplementaryAttribute(
        name=name,
        need=cfg["need"],
        strengths=cfg["strengths"],
        levels=dict(cfg["levels"]),
        weight=cfg["weight"],
        missing_level=cfg.get("missing_level", 0.0),
    )
    for name, cfg in _raw.get("complementary", {}).items()
)

SOFT_PREFERENCES = tuple(
    SoftPreferenceRule(
        name=name,
        preference=cfg["preference"],
        attribute=cfg["attribute"],
        accepted=_accepts(cfg["accepted"]),
        weight=cfg["weight"],
        unmet_score=cfg.get("unmet_score", 0.0),
    )
    for name, cfg in _raw.get("soft_preferences", {}).items()
)

SCORING_SPEC = ScoringSpec(
    hard_constraints=HARD_CONSTRAINTS,
    similarity=SIMILARITY_ATTRIBUTES,
    base_range=tuple(_raw["base_score_range"]),
    complementary=COMPLEMENTARY_ATTRIBUTES,
    soft_preferences=SOFT_PREFERENCES,
)


def profile_to_entity(entity_id: str, profile: Mapping[str, Any]) -> Entity:
    """Route a flat patient/therapist profile into an engine Entity. Preference
    fields go to preferences; everything else (incl. the effectiveness map and
    identity concordance flags) to identity. Availability fields are dropped —
    they gate the pool in match.py, they are not scored."""
    identity = {
        k: v
        for k, v in profile.items()
        if k not in PREFERENCE_FIELDS and k not in AVAILABILITY_FIELDS and k != "id"
    }
    preferences = {k: v for k, v in profile.items() if k in PREFERENCE_FIELDS}
    return Entity(id=entity_id, identity=identity, preferences=preferences)

"""End-to-end healthcare match: patient seeker over a therapist pool, using the
SAME engine pipeline as housing (engine.run_match) — only the config and data
differ (ADR-003 proof). No Tier 2 AI bonus in this domain; ranking is the
deterministic complementary-dominant base score.

SYNTHETIC DEMO ONLY — not a clinical product, no PHI.
"""

from typing import Any, Mapping, Sequence

from domains.healthcare.config import (
    AVAILABILITY_FIELDS,
    SCORING_SPEC,
    TIER0_FILTERS,
    profile_to_entity,
)
from engine.pipeline import run_match
from engine.types import Match


def _available(therapist: Mapping[str, Any]) -> bool:
    """Unary eligibility pre-filter: a therapist must be taking patients and
    have capacity. Relational gates (state/insurance/population/modality) are
    the engine's job; this unary one is domain glue."""
    return all(therapist.get(f) for f in AVAILABILITY_FIELDS)


def match_patient(
    patient_profile: Mapping[str, Any],
    therapist_profiles: Sequence[Mapping[str, Any]],
) -> list[Match]:
    """Rank therapists for one patient. Therapist eligibility is pre-filtered;
    the engine then applies Tier 0 relational filters, the modality hard
    constraint, and complementary-dominant Tier 1 scoring."""
    patient = profile_to_entity(str(patient_profile["id"]), patient_profile)
    eligible = [t for t in therapist_profiles if _available(t)]
    therapists = [profile_to_entity(str(t["id"]), t) for t in eligible]
    return run_match(
        patient,
        therapists,
        filters=TIER0_FILTERS,
        scoring_spec=SCORING_SPEC,
    )

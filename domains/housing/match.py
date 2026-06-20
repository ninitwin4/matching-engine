"""End-to-end housing match: wires Tier 0 -> Tier 1 -> Tier 2 over the generic
engine pipeline (ADR-004). Domain glue only — it supplies the housing config to
`run_match` and nothing more.

Live-path policy (ADR-005 amendment): the bonus uses the Haiku spec with no
escalation. `run_match` calls `compute_bonus` (a single primary-model call),
never the two-sample escalation ladder, so Sonnet is never invoked in the live
matching path. This module is the enforcement point for that policy.
"""

from typing import Any, Mapping, Sequence

from domains.housing.ai_bonus import housing_bonus_spec
from domains.housing.config import (
    SCORING_SPEC,
    TIER0_FILTERS,
    TOP_N,
    profile_to_entity,
)
from engine.pipeline import run_match
from engine.types import Entity, Match


def _bio(entity: Entity) -> str:
    """Free-text extractor for the bonus. The bonus reads a 'bio' identity
    attribute; absent or empty bios yield an empty string (the bonus then
    degrades to a 0 adjustment)."""
    return entity.identity.get("bio", "") or ""


def match_seeker(
    seeker_profile: Mapping[str, Any],
    candidate_profiles: Sequence[Mapping[str, Any]],
    *,
    client=None,
) -> list[Match]:
    """Rank candidates for one seeker.

    Each profile is a flat questionnaire dict; candidate profiles must carry an
    `id`. Pass a live Anthropic `client` to enable the Tier 2 bonus; omit it
    (or pass None) for a pure deterministic Tier 0+1 run.
    """
    seeker = profile_to_entity(str(seeker_profile.get("id", "seeker")), seeker_profile)
    candidates = [profile_to_entity(str(p["id"]), p) for p in candidate_profiles]
    return run_match(
        seeker,
        candidates,
        filters=TIER0_FILTERS,
        scoring_spec=SCORING_SPEC,
        top_n=TOP_N,
        bonus_spec=housing_bonus_spec(),
        client=client,
        text_of=_bio,
    )

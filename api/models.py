"""Pydantic request/response models for the match API.

Mirrors the housing v1 schema. Vocabularies are validated against the domain
config (not re-listed here) so the API can't drift from the source of truth.
Invalid input raises ValueError -> FastAPI returns 422.
"""

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from domains.housing.config import (
    GENDER_ACCEPTS,
    GENDER_IDENTITIES,
    LOCATION_VOCABULARY,
)

Slider = Annotated[int, Field(ge=1, le=5)]


class SeekerProfile(BaseModel):
    """One questionnaire profile on the housing v1 schema. `id` is optional for
    a posted seeker but present on seed-pool candidates."""

    id: Optional[str] = None
    gender: str
    gender_preference: str
    location: str
    budget: tuple[Optional[int], Optional[int]]
    move_in_window: tuple[str, str]
    lease_term_months: tuple[int, int]
    smoking: bool
    smoking_ok: bool
    has_pet: bool
    pets_ok: bool
    pet_allergy: bool = False
    cleanliness: Slider
    noise: Slider
    guests: Slider
    homebody: Slider
    sleep_time: Slider
    bio: str = ""

    @field_validator("gender")
    @classmethod
    def _gender(cls, v):
        if v not in GENDER_IDENTITIES:
            raise ValueError(f"gender must be one of {sorted(GENDER_IDENTITIES)}")
        return v

    @field_validator("gender_preference")
    @classmethod
    def _gender_pref(cls, v):
        if v not in GENDER_ACCEPTS:
            raise ValueError(
                f"gender_preference must be one of {sorted(GENDER_ACCEPTS)}"
            )
        return v

    @field_validator("location")
    @classmethod
    def _location(cls, v):
        if v not in LOCATION_VOCABULARY:
            raise ValueError(
                f"location must be one of the {len(LOCATION_VOCABULARY)} "
                "v1 markets"
            )
        return v


class MatchRequest(BaseModel):
    seeker: SeekerProfile
    # Optional inline candidate pool; omit to use the seed pool. A file-path
    # reference is intentionally not accepted (path-traversal safety).
    pool: Optional[list[SeekerProfile]] = None


class MatchOut(BaseModel):
    candidate_id: str
    display_score: float  # the card headline: min of the two directions
    base_score: float  # base of the limiting direction (pre-bonus)
    ai_adjustment: float
    ai_rationale: str
    ai_applied: bool
    degraded: bool
    # Failing-direction info (ADR-004 §3): both directional bases and which
    # one is the weaker/limiting side that the displayed minimum reflects.
    base_a_to_b: float
    base_b_to_a: float
    limiting_direction: Literal["a_to_b", "b_to_a"]
    components: dict[str, float] = Field(default_factory=dict)


class MatchResponse(BaseModel):
    seeker_id: str
    pool_size: int
    matches: list[MatchOut]

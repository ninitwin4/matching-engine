"""Pydantic request/response models for the match API.

The demo selects a seeker by id from a domain's seed pool, so /match takes a
domain + seeker_id rather than a full posted profile.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

Domain = Literal["housing", "healthcare"]


class MatchRequest(BaseModel):
    domain: Domain
    seeker_id: str


class MatchOut(BaseModel):
    candidate_id: str
    candidate: dict[str, Any] = Field(default_factory=dict)  # display attributes
    display_score: float
    base_score: float
    ai_adjustment: float
    ai_rationale: str
    ai_applied: bool
    degraded: bool
    # Failing-direction info (ADR-004 §3): both directional bases and which one
    # is the weaker/limiting side that the displayed minimum reflects.
    base_a_to_b: float
    base_b_to_a: float
    limiting_direction: Literal["a_to_b", "b_to_a"]
    components: dict[str, float] = Field(default_factory=dict)


class MatchResponse(BaseModel):
    domain: str
    seeker_id: str
    pool_size: int
    matches: list[MatchOut]

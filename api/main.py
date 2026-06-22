"""FastAPI wrapper over the end-to-end housing match run.

This is an API layer only — all matching logic lives in engine/ and
domains/housing/ and is already tested. The app imports them; they never
import the app (ADR-003).

Live scoring uses the Haiku bonus with no escalation (ADR-005 amendment),
enforced by domains.housing.match. The Anthropic key is read from the
environment / .env, never hardcoded.
"""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException

from api.models import MatchOut, MatchRequest, MatchResponse, SeekerProfile
from domains.housing.match import match_seeker
from engine.types import Match

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "domains" / "housing" / "seed" / "profiles.json"

app = FastAPI(title="Matching Engine — housing reference API", version="1.0")


@lru_cache
def _seed_pool() -> list[dict]:
    return json.loads(SEED_PATH.read_text())


def get_client():
    """Anthropic client for live Tier 2 scoring, or None if no key is
    available (then matching runs deterministically — graceful degradation,
    ADR-001). Overridden to None in tests to keep them LLM-free."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        import anthropic

        return anthropic.Anthropic()
    except Exception:
        return None


def _to_out(m: Match) -> MatchOut:
    final_ab = m.base_a_to_b + m.ai_adjustment
    final_ba = m.base_b_to_a + m.ai_adjustment
    limiting = "a_to_b" if final_ab <= final_ba else "b_to_a"
    base_score = m.base_a_to_b if limiting == "a_to_b" else m.base_b_to_a
    return MatchOut(
        candidate_id=m.candidate_id,
        display_score=m.display_score,
        base_score=base_score,
        ai_adjustment=m.ai_adjustment,
        ai_rationale=m.ai_rationale,
        ai_applied=m.ai_applied,
        degraded=m.degraded,
        base_a_to_b=m.base_a_to_b,
        base_b_to_a=m.base_b_to_a,
        limiting_direction=limiting,
        components=dict(m.components),
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/profiles", response_model=list[SeekerProfile])
def profiles():
    """The seed pool, so a frontend can list and pick demo seekers."""
    return _seed_pool()


@app.post("/match", response_model=MatchResponse)
def match(req: MatchRequest, client=Depends(get_client)):
    seeker = req.seeker.model_dump()
    pool = (
        [c.model_dump() for c in req.pool] if req.pool is not None else _seed_pool()
    )
    # Don't match the seeker against itself if it's part of the pool.
    seeker_id = seeker.get("id")
    if seeker_id is not None:
        pool = [c for c in pool if c.get("id") != seeker_id]
    try:
        results = match_seeker(seeker, pool, client=client)
    except ValueError as exc:
        # Domain-level schema/vocabulary error that slipped past Pydantic.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MatchResponse(
        seeker_id=str(seeker_id) if seeker_id is not None else "seeker",
        pool_size=len(pool),
        matches=[_to_out(m) for m in results],
    )

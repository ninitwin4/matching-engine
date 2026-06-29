"""FastAPI wrapper over the end-to-end match runs for both domains.

API layer only — all matching logic lives in engine/ and domains/ and is
already tested. The app imports them; they never import the app (ADR-003).
This layer adds domain routing and candidate enrichment; the engine and the
domain packages are unchanged.

Housing scoring uses the live Haiku bonus (ADR-005 amendment); healthcare is
deterministic (no Tier 2). The Anthropic key is read from env/.env.
"""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.models import MatchOut, MatchRequest, MatchResponse
from domains.healthcare.match import match_patient
from domains.housing.match import match_seeker
from engine.types import Match

ROOT = Path(__file__).resolve().parent.parent
SEED = {
    "housing": ROOT / "domains" / "housing" / "seed" / "profiles.json",
    "healthcare_seekers": ROOT / "domains" / "healthcare" / "seed" / "patients.json",
    "healthcare_pool": ROOT / "domains" / "healthcare" / "seed" / "therapists.json",
}

app = FastAPI(title="MatchingEngine API", version="2.0")

# Demo CORS: the Vite dev server runs on a different origin. Permissive is fine
# here — the API is read-only, holds no secrets in responses, and is local.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache
def _load(key: str) -> list[dict]:
    return json.loads(SEED[key].read_text())


def _seekers(domain: str) -> list[dict]:
    if domain == "housing":
        return _load("housing")
    if domain == "healthcare":
        return _load("healthcare_seekers")
    raise HTTPException(status_code=404, detail=f"unknown domain {domain!r}")


def get_client():
    """Anthropic client for live Tier 2 scoring (housing), or None if no key is
    available — matching then degrades gracefully (ADR-001). Overridden to None
    in tests to keep them LLM-free."""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        import anthropic

        return anthropic.Anthropic()
    except Exception:
        return None


def _to_out(m: Match, candidate: dict) -> MatchOut:
    final_ab = m.base_a_to_b + m.ai_adjustment
    final_ba = m.base_b_to_a + m.ai_adjustment
    limiting = "a_to_b" if final_ab <= final_ba else "b_to_a"
    base_score = m.base_a_to_b if limiting == "a_to_b" else m.base_b_to_a
    return MatchOut(
        candidate_id=m.candidate_id,
        candidate=candidate,
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


@app.get("/profiles")
def profiles(domain: str = Query("housing")):
    """Seekers for the active domain — housing roommates or healthcare patients."""
    return _seekers(domain)


@app.post("/match", response_model=MatchResponse)
def match(req: MatchRequest, client=Depends(get_client)):
    seekers = _seekers(req.domain)
    seeker = next((s for s in seekers if str(s.get("id")) == req.seeker_id), None)
    if seeker is None:
        raise HTTPException(
            status_code=404,
            detail=f"seeker {req.seeker_id!r} not found in domain {req.domain!r}",
        )

    if req.domain == "housing":
        pool = [c for c in seekers if c.get("id") != req.seeker_id]
        results = match_seeker(seeker, pool, client=client)
        candidates = {c["id"]: c for c in seekers}
        pool_size = len(pool)
    else:  # healthcare
        therapists = _load("healthcare_pool")
        results = match_patient(seeker, therapists)
        candidates = {t["id"]: t for t in therapists}
        pool_size = len(therapists)

    return MatchResponse(
        domain=req.domain,
        seeker_id=req.seeker_id,
        pool_size=pool_size,
        matches=[_to_out(m, candidates.get(m.candidate_id, {})) for m in results],
    )

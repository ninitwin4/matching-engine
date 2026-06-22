"""API tests via FastAPI's TestClient. The Anthropic client is overridden to
None so /match runs deterministically (Tier 0+1, no bonus) — offline and free.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_client

app.dependency_overrides[get_client] = lambda: None  # deterministic, no LLM
client = TestClient(app)


VALID_SEEKER = {
    "id": "test-seeker",
    "gender": "female",
    "gender_preference": "open_to_all",
    "location": "San Francisco",
    "budget": [1300, 1900],
    "move_in_window": ["2026-08-01", "2026-08-20"],
    "lease_term_months": [12, 12],
    "smoking": False,
    "smoking_ok": False,
    "has_pet": False,
    "pets_ok": True,
    "cleanliness": 5,
    "noise": 2,
    "guests": 2,
    "homebody": 4,
    "sleep_time": 3,
    "bio": "Quiet, tidy, happy to share a cleaning rota.",
}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_profiles_returns_seed_pool():
    r = client.get("/profiles")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 25
    assert {"sf-maya", "ok-noah", "bk-sam"} <= {p["id"] for p in body}


def test_match_ranked_results_for_valid_seeker():
    r = client.post("/match", json={"seeker": VALID_SEEKER})
    assert r.status_code == 200
    body = r.json()
    assert body["seeker_id"] == "test-seeker"
    ids = [m["candidate_id"] for m in body["matches"]]

    # Ranked by display score descending.
    scores = [m["display_score"] for m in body["matches"]]
    assert scores == sorted(scores, reverse=True)

    # SF females present; the identical-lifestyle profile tops it.
    assert ids and ids[0] == "sf-maya"
    # Tier 0 filters other cities and (none here) wrong gender; Tier 1
    # disqualifies the smoker. None of those appear.
    assert "ok-noah" not in ids  # different city
    assert "sf-dmitri" not in ids  # smoker vs strict non-smoker (hard constraint)

    # Deterministic run: no bonus applied.
    assert all(m["ai_adjustment"] == 0.0 for m in body["matches"])
    # Failing-direction info present.
    assert body["matches"][0]["limiting_direction"] in ("a_to_b", "b_to_a")


def test_match_excludes_seeker_itself_from_pool():
    seeker = dict(VALID_SEEKER, id="sf-maya")  # an id that exists in the pool
    r = client.post("/match", json={"seeker": seeker})
    assert r.status_code == 200
    ids = [m["candidate_id"] for m in r.json()["matches"]]
    assert "sf-maya" not in ids


@pytest.mark.parametrize(
    "bad",
    [
        {"location": "Atlantis"},  # not in vocabulary
        {"gender": "robot"},  # not a valid identity
        {"cleanliness": 9},  # slider out of 1–5
        {"gender_preference": "anyone"},  # not a valid preference
    ],
)
def test_match_invalid_profile_returns_422(bad):
    r = client.post("/match", json={"seeker": {**VALID_SEEKER, **bad}})
    assert r.status_code == 422

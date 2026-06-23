"""API tests via FastAPI's TestClient. The Anthropic client is overridden to
None so /match runs deterministically (no LLM) — offline and free.
"""

from fastapi.testclient import TestClient

from api.main import app, get_client

app.dependency_overrides[get_client] = lambda: None  # deterministic, no LLM
client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_profiles_housing():
    r = client.get("/profiles", params={"domain": "housing"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 25
    assert "sf-maya" in {p["id"] for p in body}


def test_profiles_healthcare():
    r = client.get("/profiles", params={"domain": "healthcare"})
    assert r.status_code == 200
    assert {p["id"] for p in r.json()} == {"p-rivera", "p-okoro", "p-nguyen"}


def test_profiles_unknown_domain_404():
    r = client.get("/profiles", params={"domain": "mentorship"})
    assert r.status_code == 404


def test_match_housing_ranked_with_candidate_attrs():
    r = client.post("/match", json={"domain": "housing", "seeker_id": "sf-priya"})
    assert r.status_code == 200
    body = r.json()
    assert body["domain"] == "housing"
    matches = body["matches"]
    scores = [m["display_score"] for m in matches]
    assert scores == sorted(scores, reverse=True)
    assert matches[0]["candidate_id"] == "sf-maya"
    # Candidate display attributes are enriched onto each match.
    assert matches[0]["candidate"]["location"] == "San Francisco"
    # Deterministic run: no bonus.
    assert all(m["ai_adjustment"] == 0.0 for m in matches)


def test_match_healthcare_complementary_ranked():
    r = client.post("/match", json={"domain": "healthcare", "seeker_id": "p-rivera"})
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert [m["candidate_id"] for m in matches] == [
        "t-river-stone",
        "t-ember-frost",
        "t-sky-meadows",
    ]
    # Complementary effectiveness is exposed in components.
    assert matches[0]["components"]["effectiveness"] == 1.0
    assert matches[0]["candidate"]["name"] == "Dr. River Stone"


def test_match_unknown_seeker_404():
    r = client.post("/match", json={"domain": "housing", "seeker_id": "nobody"})
    assert r.status_code == 404


def test_match_unknown_domain_422():
    r = client.post("/match", json={"domain": "mentorship", "seeker_id": "x"})
    assert r.status_code == 422  # Literal domain validation

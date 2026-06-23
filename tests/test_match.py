"""End-to-end match tests. The core asserts run with client=None (pure
deterministic, no network). Two tests use a fake client to exercise top-N
bonus gating and graceful degradation — still offline (ADR-002 fast lane).
"""

import pytest

from domains.housing.ai_bonus import housing_bonus_spec
from domains.housing.config import SCORING_SPEC, TIER0_FILTERS, profile_to_entity
from domains.housing.match import _bio, match_seeker
from engine.pipeline import run_match

# Seeker: SF female, female-only. Lifestyle baseline for similarity.
SEEKER = {
    "id": "seeker",
    "gender": "female",
    "gender_preference": "female_only",
    "location": "San Francisco",
    "budget": [1000, 2000],
    "smoking": False,
    "smoking_ok": False,
    "has_pet": False,
    "pets_ok": True,
    "cleanliness": 4,
    "noise": 2,
    "guests": 2,
    "homebody": 3,
    "sleep_time": 3,
    "bio": "Quiet weeknights, tidy kitchen, happy to share a cleaning rota.",
}


def _cand(cid, **overrides):
    base = {
        "id": cid,
        "gender": "female",
        "gender_preference": "open_to_all",
        "location": "San Francisco",
        "budget": [1100, 1800],
        "smoking": False,
        "smoking_ok": False,
        "has_pet": False,
        "pets_ok": True,
        "cleanliness": 4,
        "noise": 2,
        "guests": 2,
        "homebody": 3,
        "sleep_time": 3,
        "bio": "Easygoing, clean, looking for a calm place.",
    }
    base.update(overrides)
    return base


# Identical lifestyle -> high similarity (~90).
C_GOOD = _cand("good")
# Dissimilar lifestyle -> lower base.
C_MID = _cand("mid", cleanliness=2, noise=4, guests=4, homebody=1, sleep_time=5)
# Tier 0: different city -> filtered.
C_CITY = _cand("city", location="Oakland")
# Tier 0: male vs seeker's female_only -> filtered.
C_GENDER = _cand("gender", gender="male")
# Tier 1: budget does not overlap [1000,2000] -> hard-constraint disqualified.
C_HARD = _cand("hard", budget=[2500, 3000])

POOL = [C_GOOD, C_MID, C_CITY, C_GENDER, C_HARD]


def test_filtered_candidates_absent():
    ids = {m.candidate_id for m in match_seeker(SEEKER, POOL)}
    assert "city" not in ids  # Tier 0 location
    assert "gender" not in ids  # Tier 0 gender


def test_hard_constraint_pair_never_appears():
    ids = {m.candidate_id for m in match_seeker(SEEKER, POOL)}
    assert "hard" not in ids  # Tier 1 budget violation -> disqualified


def test_only_viable_candidates_returned():
    ids = {m.candidate_id for m in match_seeker(SEEKER, POOL)}
    assert ids == {"good", "mid"}


def test_ranked_by_display_descending():
    results = match_seeker(SEEKER, POOL)
    scores = [m.display_score for m in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0].candidate_id == "good"  # identical lifestyle ranks top


def test_deterministic_run_has_separate_breakdown_no_bonus():
    results = match_seeker(SEEKER, POOL)
    for m in results:
        assert m.ai_adjustment == 0.0  # no client -> no bonus
        assert m.ai_rationale == ""
        assert not m.ai_applied
        assert m.base_a_to_b == m.base_b_to_a  # Tier 1 symmetric today
        assert m.display_score == m.base_a_to_b  # display = base when bonus 0
        assert m.components  # similarity breakdown present for the detail view


# ---- fake client: top-N gating + graceful degradation ----


class _FakeParsed:
    def __init__(self, adjustment, rationale):
        self.adjustment = adjustment
        self.rationale = rationale


class _FakeUsage:
    input_tokens = 50
    output_tokens = 10


class _FakeResponse:
    def __init__(self, parsed):
        self.parsed_output = parsed
        self.usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, raises=False):
        self._raises = raises

    def parse(self, **kwargs):
        if self._raises:
            raise RuntimeError("simulated LLM failure")
        return _FakeResponse(_FakeParsed(5, "bio adds a concrete cleaning rota"))


class _FakeClient:
    def __init__(self, raises=False):
        self.messages = _FakeMessages(raises=raises)


def _entities():
    seeker = profile_to_entity("seeker", SEEKER)
    cands = [profile_to_entity(c["id"], c) for c in (C_GOOD, C_MID)]
    return seeker, cands


def test_bonus_applies_only_to_top_n():
    seeker, cands = _entities()
    # top_n=1 -> only the highest base ("good") gets the bonus.
    results = run_match(
        seeker,
        cands,
        filters=TIER0_FILTERS,
        scoring_spec=SCORING_SPEC,
        top_n=1,
        bonus_spec=housing_bonus_spec(),
        client=_FakeClient(),
        text_of=_bio,
    )
    by_id = {m.candidate_id: m for m in results}
    assert by_id["good"].ai_applied and by_id["good"].ai_adjustment == 5
    assert not by_id["mid"].ai_applied and by_id["mid"].ai_adjustment == 0.0


def test_llm_failure_degrades_to_base():
    seeker, cands = _entities()
    results = run_match(
        seeker,
        cands,
        filters=TIER0_FILTERS,
        scoring_spec=SCORING_SPEC,
        top_n=20,
        bonus_spec=housing_bonus_spec(),
        client=_FakeClient(raises=True),
        text_of=_bio,
    )
    for m in results:
        assert m.ai_applied  # bonus was attempted (top-N)
        assert m.degraded  # but the call failed
        assert m.ai_adjustment == 0.0  # -> fell back to base (ADR-001)
        assert m.display_score == m.base_a_to_b

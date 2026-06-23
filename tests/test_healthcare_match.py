"""End-to-end healthcare match tests over the synthetic seed pool. Proves the
SAME engine pipeline runs a non-housing config (ADR-003 / ADR-006) — offline,
no LLM (healthcare has no Tier 2 bonus).
"""

import json
from pathlib import Path

from domains.healthcare.match import match_patient

SEED = Path(__file__).resolve().parent.parent / "domains" / "healthcare" / "seed"
THERAPISTS = json.loads((SEED / "therapists.json").read_text())
PATIENTS = {p["id"]: p for p in json.loads((SEED / "patients.json").read_text())}


def _ranked(patient_id):
    results = match_patient(PATIENTS[patient_id], THERAPISTS)
    return results, [m.candidate_id for m in results]


def test_complementary_dominates_ranking():
    # Trauma patient: ranking is driven by therapist effectiveness in trauma,
    # not by anything else (effective > neutral > ineffective).
    results, ids = _ranked("p-rivera")
    assert ids == ["t-river-stone", "t-ember-frost", "t-sky-meadows"]
    comp = [m.components["effectiveness"] for m in results]
    assert comp == [1.0, 0.5, 0.0]  # effective, neutral, ineffective
    scores = [m.display_score for m in results]
    assert scores == sorted(scores, reverse=True)


def test_tier0_filters_exclude_on_state_insurance_population():
    _, ids = _ranked("p-rivera")  # CA / BlueCross / adults
    assert "t-wren-castle" not in ids  # NY (state)
    assert "t-quill-marsh" not in ids  # Aetna (insurance)
    assert "t-sage-brooks" not in ids  # self_pay (insurance) + adolescents


def test_modality_hard_constraint_disqualifies_telehealth_only():
    # Okoro needs in-person; nova-pine is depression-effective and passes all
    # filters, but is telehealth-only -> disqualified, never appears.
    _, ids = _ranked("p-okoro")
    assert "t-nova-pine" not in ids
    assert ids == ["t-wren-castle"]


def test_availability_pre_filter_drops_unavailable_therapist():
    # fern-hollow is trauma-effective and CA/BlueCross/adults — a strong match
    # on paper — but is not taking new patients, so it is pre-filtered out.
    _, ids = _ranked("p-rivera")
    assert "t-fern-hollow" not in ids


def test_substance_use_patient_matches_specialist():
    results, ids = _ranked("p-nguyen")
    assert ids == ["t-sage-brooks"]
    assert results[0].components["effectiveness"] == 1.0

"""Engine unit tests for the Tier 2 bonus mechanism and final-score assembly.

No network: a fake client stands in for the Anthropic SDK, so these run in
the free pytest fast lane (ADR-002). The live N=3 eval is the slow lane
(evals/run_ai_bonus.py).
"""

import pytest

from engine.ai_bonus import compute_bonus, compute_bonus_escalated
from engine.scoring import final_score
from engine.types import AIBonusSpec

SPEC = AIBonusSpec(model="fake-model", system_prompt="score it", cap=10.0)


class _FakeUsage:
    input_tokens = 100
    output_tokens = 20


class _FakeParsed:
    def __init__(self, adjustment, rationale):
        self.adjustment = adjustment
        self.rationale = rationale


class _FakeResponse:
    def __init__(self, parsed):
        self.parsed_output = parsed
        self.usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, parsed=None, raises=None):
        self._parsed = parsed
        self._raises = raises

    def parse(self, **kwargs):
        if self._raises is not None:
            raise self._raises
        return _FakeResponse(self._parsed)


class _FakeClient:
    def __init__(self, parsed=None, raises=None):
        self.messages = _FakeMessages(parsed=parsed, raises=raises)


def test_in_range_adjustment_passes_through():
    client = _FakeClient(_FakeParsed(7, "shared cleaning rota cited"))
    result = compute_bonus("a", "b", spec=SPEC, client=client)
    assert result.adjustment == 7
    assert result.raw_adjustment == 7
    assert not result.degraded
    assert result.input_tokens == 100


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(99, 10), (-50, -10), (10.0, 10.0), (-10.0, -10.0), (10.4, 10)],
)
def test_adjustment_is_hard_capped_in_code(raw, expected):
    client = _FakeClient(_FakeParsed(raw, "model tried to exceed the cap"))
    result = compute_bonus("a", "b", spec=SPEC, client=client)
    assert result.adjustment == expected
    assert result.raw_adjustment == raw  # raw preserved for auditing


def test_exception_degrades_to_zero():
    client = _FakeClient(raises=RuntimeError("connection reset"))
    result = compute_bonus("a", "b", spec=SPEC, client=client)
    assert result.adjustment == 0.0
    assert result.degraded
    assert result.rationale == ""
    assert result.raw_adjustment is None


def test_unparseable_output_degrades_to_zero():
    client = _FakeClient(parsed=None)  # refusal / schema miss
    result = compute_bonus("a", "b", spec=SPEC, client=client)
    assert result.adjustment == 0.0
    assert result.degraded


# ---- final-score assembly ----


def test_final_score_displays_minimum_direction():
    fs = final_score(base_a_to_b=85, base_b_to_a=60, bonus=5)
    assert fs.a_to_b == 90
    assert fs.b_to_a == 65
    assert fs.display == 65  # min, ADR-004 §3


def test_final_score_negative_bonus_lowers_both():
    fs = final_score(base_a_to_b=80, base_b_to_a=78, bonus=-6)
    assert fs.a_to_b == 74
    assert fs.b_to_a == 72
    assert fs.display == 72


# ---- escalation ladder (ADR-005) ----

ESC_SPEC = AIBonusSpec(
    model="primary",
    system_prompt="score it",
    cap=10.0,
    escalation_model="secondary",
    samples=2,
    agreement_threshold=1.0,
)


class _ScriptedMessages:
    """Returns queued results per model; an Exception in the queue is raised
    (to simulate a degraded call). Records the models called, in order."""

    def __init__(self, by_model):
        self._by_model = {m: list(v) for m, v in by_model.items()}
        self.calls = []

    def parse(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        item = self._by_model[model].pop(0)
        if isinstance(item, Exception):
            raise item
        adjustment, rationale = item
        return _FakeResponse(_FakeParsed(adjustment, rationale))


class _ScriptedClient:
    def __init__(self, by_model):
        self.messages = _ScriptedMessages(by_model)


def test_escalation_agreeing_samples_accept_primary_mean():
    client = _ScriptedClient({"primary": [(3, "r1"), (3, "r2")]})
    e = compute_bonus_escalated("a", "b", spec=ESC_SPEC, client=client)
    assert not e.escalated
    assert e.model == "primary"
    assert e.adjustment == 3
    assert e.escalation is None
    assert client.messages.calls == ["primary", "primary"]


def test_escalation_within_threshold_accepts_mean():
    client = _ScriptedClient({"primary": [(0, "r1"), (1, "r2")]})  # spread 1 <= 1.0
    e = compute_bonus_escalated("a", "b", spec=ESC_SPEC, client=client)
    assert not e.escalated
    assert e.adjustment == pytest.approx(0.5)


def test_escalation_on_disagreement_uses_secondary():
    client = _ScriptedClient(
        {"primary": [(-8, "p1"), (0, "p2")], "secondary": [(-8, "sonnet says")]}
    )
    e = compute_bonus_escalated("a", "b", spec=ESC_SPEC, client=client)
    assert e.escalated
    assert e.model == "secondary"
    assert e.adjustment == -8
    assert e.rationale == "sonnet says"
    assert e.escalation is not None
    assert client.messages.calls == ["primary", "primary", "secondary"]


def test_escalation_on_degraded_sample_even_if_numbers_agree():
    # First primary call degrades (raises -> adjustment 0); second returns 0.
    # Numbers agree (0, 0) but a degraded sample forces escalation.
    client = _ScriptedClient(
        {"primary": [RuntimeError("boom"), (0, "p2")], "secondary": [(5, "sonnet")]}
    )
    e = compute_bonus_escalated("a", "b", spec=ESC_SPEC, client=client)
    assert e.escalated
    assert e.adjustment == 5
    assert any(s.degraded for s in e.samples)


def test_no_escalation_model_is_single_call():
    spec = AIBonusSpec(
        model="primary", system_prompt="x", escalation_model=None, samples=1
    )
    client = _ScriptedClient({"primary": [(4, "solo")]})
    e = compute_bonus_escalated("a", "b", spec=spec, client=client)
    assert not e.escalated
    assert e.model == "primary"
    assert e.adjustment == 4
    assert client.messages.calls == ["primary"]

"""Tier 2 AI nuance bonus: a small, bounded LLM judgment over two free-text
inputs (ADR-001). The engine owns the *mechanism* only — call, parse, clamp,
degrade — and stays free of domain vocabulary (ADR-003). The prompt, model,
and cap come from a domain-supplied AIBonusSpec.

Two guarantees this module enforces in code, never by trusting the model:

1. **Hard cap.** The returned adjustment is always within [-cap, cap]
   (ADR-001). Whatever the model emits is clamped here.
2. **Graceful degradation.** Any failure — network, timeout, refusal,
   unparseable output — yields a zero adjustment with `degraded=True`. A
   match result never depends on LLM availability (ADR-001).
"""

import time
from dataclasses import replace

from pydantic import BaseModel

from engine.bonus_cache import cache_key
from engine.types import AIBonusResult, AIBonusSpec, EscalatedBonusResult


class _BonusOutput(BaseModel):
    """Structured shape we ask the model to return. The numeric bound lives in
    code (clamping below), not in this schema — we never trust the model to
    stay in range."""

    adjustment: float
    rationale: str


def compute_bonus(
    text_a: str, text_b: str, *, spec: AIBonusSpec, client, cache=None
) -> AIBonusResult:
    """Compute the bounded nuance bonus for a pair of free-text inputs.

    `client` is an Anthropic client (injected, not constructed here — keeps the
    engine testable with a fake and free of credential handling). The bonus is
    pair-level and symmetric: it reads both texts and returns one adjustment.

    `cache` is an optional pair-level cache (ADR-001 amendment 3). On a hit the
    stored adjustment and rationale are returned and no LLM call is made; on a
    miss the result is stored. Degraded results are never cached, so an outage
    is retried rather than remembered.
    """
    key = None
    if cache is not None:
        key = cache_key(text_a, text_b, spec)
        hit = cache.get(key)
        if hit is not None:
            return hit

    user_content = (
        "Profile A free text:\n"
        f"{text_a}\n\n"
        "Profile B free text:\n"
        f"{text_b}"
    )
    started = time.monotonic()
    try:
        response = client.messages.parse(
            model=spec.model,
            max_tokens=spec.max_tokens,
            system=spec.system_prompt,
            messages=[{"role": "user", "content": user_content}],
            output_format=_BonusOutput,
        )
        latency_ms = (time.monotonic() - started) * 1000.0
        parsed = response.parsed_output
        if parsed is None:  # refusal or unparseable — degrade
            return AIBonusResult(
                adjustment=0.0,
                rationale="",
                degraded=True,
                latency_ms=latency_ms,
                input_tokens=_get(response.usage, "input_tokens"),
                output_tokens=_get(response.usage, "output_tokens"),
            )
        raw = float(parsed.adjustment)
        clamped = max(-spec.cap, min(spec.cap, raw))
        result = AIBonusResult(
            adjustment=clamped,
            rationale=parsed.rationale,
            raw_adjustment=raw,
            degraded=False,
            latency_ms=latency_ms,
            input_tokens=_get(response.usage, "input_tokens"),
            output_tokens=_get(response.usage, "output_tokens"),
        )
        if cache is not None and key is not None:
            cache.set(key, result)
        return result
    except Exception:
        # Degrade on anything: connection error, timeout, bad JSON, schema
        # mismatch. The base score alone stands.
        latency_ms = (time.monotonic() - started) * 1000.0
        return AIBonusResult(
            adjustment=0.0, rationale="", degraded=True, latency_ms=latency_ms
        )


def _get(usage, field: str) -> int | None:
    return getattr(usage, field, None) if usage is not None else None


def compute_bonus_escalated(
    text_a: str, text_b: str, *, spec: AIBonusSpec, client
) -> EscalatedBonusResult:
    """Tiered two-sample agreement gate (ADR-005).

    Sample the primary model `spec.samples` times. If the samples agree (spread
    <= `spec.agreement_threshold`) and none degraded, accept their mean — the
    cheap model was self-consistent, so trust it. Otherwise escalate to
    `spec.escalation_model` and use that single call. With no escalation model
    configured this degenerates to a single primary call.

    Escalating on a degraded sample is deliberate: a failed second opinion
    means we could not confirm self-consistency, so defer to the stronger
    model. If the escalation call itself degrades, its zero adjustment stands —
    graceful degradation is preserved end to end (ADR-001).

    Deliberately **not cached**: this path exists to sample the model
    repeatedly and measure run-to-run spread. A cache would return one stored
    answer N times, making the agreement gate and the eval suite's consistency
    check meaningless. The live serving path (compute_bonus) is the cached one.
    """
    n = max(1, spec.samples)
    samples = tuple(
        compute_bonus(text_a, text_b, spec=spec, client=client) for _ in range(n)
    )
    total_latency = sum(s.latency_ms or 0.0 for s in samples)
    adjustments = [s.adjustment for s in samples]

    no_escalation = spec.escalation_model is None
    samples_disagree = (max(adjustments) - min(adjustments)) > spec.agreement_threshold
    degraded_sample = any(s.degraded for s in samples)

    if no_escalation or (not samples_disagree and not degraded_sample):
        # Accept the primary model. Mean of agreeing samples is the
        # representative adjustment; the first sample's rationale stands in.
        accepted = sum(adjustments) / len(adjustments)
        return EscalatedBonusResult(
            adjustment=accepted,
            rationale=samples[0].rationale,
            raw_adjustment=samples[0].raw_adjustment,
            degraded=samples[0].degraded if no_escalation else False,
            model=spec.model,
            escalated=False,
            samples=samples,
            escalation=None,
            latency_ms=total_latency,
        )

    escalation = compute_bonus(
        text_a, text_b, spec=replace(spec, model=spec.escalation_model), client=client
    )
    return EscalatedBonusResult(
        adjustment=escalation.adjustment,
        rationale=escalation.rationale,
        raw_adjustment=escalation.raw_adjustment,
        degraded=escalation.degraded,
        model=spec.escalation_model,
        escalated=True,
        samples=samples,
        escalation=escalation,
        latency_ms=total_latency + (escalation.latency_ms or 0.0),
    )

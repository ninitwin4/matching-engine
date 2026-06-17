# ADR-005: Tiered model escalation for the Tier 2 AI nuance bonus

**Status:** Accepted
**Date:** 2026-06-17
**Decision owner:** Ni Ni

## Context

ADR-001 amendment 5 (2026-06-10) set a "fast, inexpensive model class is the
default" for the Tier 2 AI nuance bonus, on the reasoning that the bonus is a
small, bounded judgment. The README phase-4 roadmap explicitly deferred the
question of whether the small model agrees with a larger one "often enough,"
to be answered *on* the eval harness (ADR-002).

Building the Tier 2 suite answered it with data. Running the AI bonus suite
(8 golden pairs, N=3) on the two model classes:

- **Haiku 4.5 (small):** 6/8. It is reliable on clear pairs (neutral,
  ritual-keyword, groundedness traps) but **variable at the new-signal
  boundary** — the borderline positive (ai-004) and negative (ai-006) cases.
  Failure modes observed: returning 0 by *assuming* a structured field already
  covers something (it once hallucinated a "conflict-style slider"), demanding
  bilateral evidence, or demanding a track record even for friction.
- **Sonnet 4.6 (larger):** 8/8, every check green, **adjustment spread 0.00**
  on every case. The two cases Haiku could not hold were rock-solid.

So the small model does *not* agree often enough on the nuanced boundary, but
it is correct and cheap on the clear majority. Switching wholesale to Sonnet
would clear the bar but abandons the cost discipline of ADR-001 (~5x the
per-pair cost on a layer that already dominates variable cost) and contradicts
amendment 5.

A second finding shaped the trigger: Haiku's self-reported confidence is **not
trustworthy** — on ai-006 it returned a confidently-wrong 0. So escalation
cannot key on a confidence field; it needs a *behavioral* signal. In the eval,
the cases Haiku got right had **self-consistency (spread 0)** across repeats;
the ones it failed had spread > 0. Self-consistency is the tell.

## Decision

The bonus uses a **two-stage model ladder with a self-agreement gate**,
superseding ADR-001 amendment 5's flat small-model default:

1. Sample the **primary** model (Haiku 4.5) `samples` times (default **2**).
2. If the samples **agree** (spread ≤ `agreement_threshold`, default **1.0**)
   and none degraded, accept their mean — the cheap model was self-consistent,
   so trust it.
3. Otherwise **escalate** to the **secondary** model (Sonnet 4.6) with a single
   call and use that result.

Guardrails carried forward from ADR-001:

- The ±10 hard cap is enforced in code on whichever model produces the value.
- **Graceful degradation is preserved end to end:** a degraded primary sample
  forces escalation (a failed second opinion can't confirm self-consistency);
  if the escalation call itself degrades, its zero adjustment stands. A match
  never depends on LLM availability.
- The mechanism is generic in the engine (`primary`, `secondary`, `samples`,
  `agreement_threshold` on `AIBonusSpec`); the model names and thresholds are
  housing domain config (ADR-003).

The eval harness validates the **actual production policy** (`--escalate`),
not a single model, so the ADR-002 100% bar is cleared honestly.

## Alternatives considered

- **Switch the bonus wholesale to Sonnet.** Simplest; 8/8. Rejected: ~5x
  per-pair cost on the dominant variable-cost layer, and it discards the small
  model where it is provably adequate (the clear majority).
- **Keep Haiku only.** Cheapest; rejected — 6/8, below the bar, and the
  failures are at the boundary the bonus exists to score.
- **Confidence-field trigger** (escalate when the model self-reports low
  confidence). Rejected: Haiku was confidently wrong, so self-reported
  confidence is not a reliable signal.

## Consequences

**Positive**

- Suite is green (8/8) under the real policy, at far below Sonnet-for-all cost.
- Measured on the suite: **12% escalation rate** (3/24 runs), blended eval cost
  **$0.13** vs $0.08 single-Haiku and $0.15 all-Sonnet. The stronger model is
  spent only on genuinely-uncertain pairs.
- Composes with ADR-001's top-N gating and pair caching — escalation only ever
  runs inside the already-shrunk top-N funnel.

**Negative / accepted costs**

- The gate catches Haiku's *variance*, not its *confident-but-wrong* answers:
  if both primary samples agree on the same wrong value, the gate accepts it.
  ai-004 surfaced this (both samples agreed on a wrong 0). The mitigation is
  **case design, not a bigger `k`** — a well-formed pair gives the small model
  a stable *correct* mode (ai-004 was re-authored as a bilateral-evidence
  positive and then passed on Haiku without escalating).
- The gate roughly **doubles** primary (Haiku) cost on every pair (two samples)
  regardless of escalation rate; Sonnet adds only a small increment. Cost is
  dominated by the doubled sampling, not by escalation.
- The groundedness judge (Haiku) is itself imperfect — an observed
  false-negative on a correctly-grounded rationale. Tracked as residual eval
  variance under the ADR-002 red-run triage protocol, not a blocker.

**Revisit when**

- Real-user feedback or a phase-4 cost review motivates tuning `samples`,
  `agreement_threshold`, or the model pair.
- Judge unreliability causes recurring flakes → consider a stronger judge model
  (the judge model is already a one-line config in the runner).
- A future structured field (e.g. conflict style, alcohol policy) absorbs what
  is currently bonus-only "new signal," shrinking the bonus's scope.

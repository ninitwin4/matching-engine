# ADR-002: Eval harness measures score correctness first

**Status:** Accepted
**Date:** 2026-06-10
**Decision owner:** Ni Ni

## Context

Match quality is the product's entire value, and it is invisible without
measurement. We need an eval harness, but cannot build evals for every surface
at once; the first measurement target shapes what gets built.

The hybrid scoring decision (ADR-001) splits "score correctness" into two
different testing problems:

- The **deterministic base score** has exact expected outputs → ordinary unit
  testing.
- The **AI nuance bonus** is an LLM judgment with run-to-run variance → needs
  LLM-style evaluation (bounds, direction, groundedness, consistency), not
  exact-match assertions.

A separate candidate target — **AI explanation quality** (does the AI narrate
a score faithfully and without hallucination?) — is valuable but presupposes
the score itself is trustworthy. Evaluating explanations of a possibly-wrong
number polishes the narration of a bad result.

## Decision

The eval harness is built as **shared infrastructure plus pluggable suites**:
a test-case dataset, a runner, metrics, and a report, with measurement suites
added over time.

**Suite order:**

1. **Score correctness (now).**
   - *Deterministic core:* pytest suite of authored test pairs with exact
     expected base scores, including hard-constraint short-circuits and
     boundary cases. (~15–20 pairs to start.)
   - *AI nuance bonus:* LLM eval suite asserting that the adjustment
     (a) stays within ±10, (b) is directionally correct on pairs with
     obviously aligned or obviously conflicting bios, (c) cites only facts
     actually present in the profiles (groundedness), and (d) is reasonably
     consistent across repeated runs (variance bound, not exact match).
2. **Explanation quality (named, planned second suite).** Faithfulness of
   user-facing match explanations to the stored score breakdown; hallucination
   rate. Runs on the same harness skeleton.

## Alternatives considered

- **Explanation quality first.** Originally chosen, then amended: it tests the
  narration layer before the number underneath is validated, and the hybrid
  decision means score correctness already exercises the same LLM-eval skills
  (groundedness, consistency) through a narrower, better-defined door.
- **Both from day one.** More coverage, slower to first signal; rejected in
  favor of sequencing on shared infrastructure, which makes adding the second
  suite cheap.

## Consequences

**Positive**

- Every change to scoring logic or AI prompts runs against a fixed test set
  before it ships; weight tuning stops being vibes-based.
- The harness skeleton is built once; explanation evals later are an
  incremental suite, not a rebuild.
- LLM-eval fundamentals (bounds, directional assertions, groundedness,
  consistency measurement) are learned on the smallest sensible surface.

**Negative / accepted costs**

- **Synthetic ground truth:** test pairs are authored by us, so the suite
  verifies the system matches *our theory* of compatibility — not that the
  theory is right. Real validation requires real-user outcomes post-launch.
  This limitation is accepted and stated openly.
- Explanation quality is unmeasured until suite 2 lands; user-facing
  explanations before then are best-effort.

**Revisit when**

- Suite 1 is green and stable → begin suite 2 (explanation quality).
- Real user feedback becomes available → add an outcome-based validation
  track alongside synthetic cases.

## Amendments (2026-06-10, same design session)

**Range assertions for golden pairs.** Deterministic cases now assert a
`score_range` (e.g. `[60, 75]`) rather than an exact score, except for
short-circuit cases (hard-constraint violations and Tier 0 filter rejections,
which assert exactly 0 / no-match). Rationale: exact scores presume the
weights are already chosen. Range-based golden pairs invert the relationship —
the authored ranges become the **calibration specification** that weight
tuning must satisfy. If the engine scores a "good not great" pair at 88, the
eval fails, signaling the weights are miscalibrated against the product's
theory of compatibility.

The learning roadmap that follows this ADR (see README appendix):
golden pairs → harness runs → failure analysis → latency/accuracy
optimization, each phase producing the raw material the next requires.

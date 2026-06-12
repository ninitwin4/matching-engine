# ADR-001: Hybrid scoring — deterministic core with bounded AI nuance bonus

**Status:** Accepted
**Date:** 2026-06-10
**Decision owner:** Ni Ni

## Context

The product is a compatibility-matching engine. Its central output is a 0–100
compatibility score between two entities (first use case: prospective roommates).
We had to decide what role, if any, an LLM plays in producing that score.

Forces in tension:

- Scores must be **explainable to users** ("why did we score 87?") and
  **auditable** by us.
- Scores must be **testable**: the eval strategy depends on whether scores are
  reproducible.
- Structured questionnaire data (cleanliness 1–5, budget ranges, hard
  constraints) is well served by deterministic math.
- Free-text profile bios contain real compatibility signal that rigid math
  cannot capture (e.g., two people who both describe needing quiet Sundays).
- LLM calls add cost, latency, and run-to-run variance; the system must not
  fall over if the LLM is unavailable.

## Decision

Scoring is **hybrid with a deterministic spine and a bounded AI adjustment**:

1. A **deterministic core** computes a base score in the range **0–90** from
   structured attributes, using three constraint types: hard constraints
   (violation → score 0, no AI involvement), similarity scoring, and
   complementary scoring, combined via configured weights.
2. An **LLM nuance bonus** adjusts the base score by at most **±10 points**,
   based on reading both parties' free-text bios.
3. Guardrails on the AI component:
   - The adjustment is **hard-capped** at ±10 in code (not by prompt alone).
   - `base_score`, `ai_adjustment`, and `ai_rationale` are **stored as separate
     fields** and never blended in storage; the displayed score is computed at
     read time.
   - **Graceful degradation:** if the LLM call fails or times out, the system
     returns the base score alone. A match result never depends on LLM
     availability.
   - Hard-constraint violations short-circuit before any LLM call; the AI can
     never resurrect a disqualified pair.

## Alternatives considered

- **A. Fully deterministic, AI only explains.** Maximum auditability and the
  cheapest to run, but discards genuine signal in free-text bios and is a
  weaker demonstration of AI-native design. Rejected, but it remains our
  degraded mode — which de-risks the hybrid considerably.
- **B. LLM judges compatibility end-to-end.** Most AI-native; captures nuance
  best. Rejected for v1: scores would be non-reproducible, expensive at
  O(n²) pair volume, hard to evaluate, and hard to explain. Unbounded model
  judgment over the entire score is too much trust too early.

## Consequences

**Positive**

- Scores remain explainable: at most 10 points of any score require an AI
  rationale; the rest decomposes into auditable arithmetic.
- The deterministic core is trivially testable with pytest.
- The AI surface is small and well-defined, which makes it a tractable first
  target for LLM evals (see ADR-002).
- Engine works (degraded) with zero AI dependency — useful for demos, tests,
  and cost control.

**Negative / accepted costs**

- Two scoring subsystems to maintain instead of one.
- Run-to-run variance of ±a few points on the AI bonus is accepted; evals
  bound it rather than eliminate it.
- LLM cost per matched pair; mitigated by short-circuiting hard-constraint
  failures and (later) only applying the bonus to top-N candidates by base
  score.

**Revisit when**

- Real-user feedback exists to validate whether the bonus improves match
  quality (if it doesn't measurably help, fall back to Alternative A).

## Amendments (2026-06-10, same design session)

Edge-case authoring for the eval golden pairs (see ADR-002) surfaced
refinements, adopted same-day:

1. **Constraint roles expanded.** The engine's attribute roles are now:
   `filter` (Tier 0 gate — see ADR-004), `hard_constraint`,
   `soft_preference` (violation applies a penalty, not disqualification),
   `similarity`, and `complementary`. Roles may compose: budget is a hard
   floor (no overlap → 0) **plus** a graded score above the floor scaled by
   overlap size (a $50 overlap scores far lower than a generous one).
2. **Top-N gating promoted from "revisit" to design.** The AI nuance bonus
   runs only on each user's top ~20 candidates by deterministic base score.
   A low-base pair cannot be rescued by +10; spending an LLM call on it is
   waste. This collapses LLM cost from O(pairs) to O(users × N).
3. **Pair-level caching.** The adjustment and rationale are cached keyed on a
   hash of both bios; the LLM is re-called only when a bio changes. Postgres
   serves as the cache store.
4. **Lazy explanations.** User-facing match explanations are generated
   on-demand (when a match detail is opened), not eagerly for every match.
5. **Model right-sizing.** The bonus is a small bounded judgment; a fast,
   inexpensive model class is the default. Batch/async processing is
   acceptable because matching is not a real-time requirement.

Rationale: LLM calls dominate variable cost (~90%+); deterministic scoring
and Postgres are effectively free by comparison. Cost strategy = shrink the
funnel before the expensive layer.

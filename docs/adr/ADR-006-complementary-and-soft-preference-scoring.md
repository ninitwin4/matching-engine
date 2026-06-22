# ADR-006: Engine gains complementary and soft-preference scoring

**Status:** Accepted
**Date:** 2026-06-17
**Decision owner:** Ni Ni

## Context

ADR-001's amendment defined five attribute roles — `filter`, `hard_constraint`,
`soft_preference`, `similarity`, `complementary` — and ADR-003 amendment 3
asserted "the engine stays more expressive than any one domain." But the housing
v1 build only ever needed three roles (`filter`, `hard_constraint`,
`similarity`), so `complementary` and `soft_preference` were declared in the
records but **never implemented** in `engine/scoring.py`. `score_pair` blended
similarity only.

Building a minimal second domain — healthcare (patient-to-therapist) — to
stress-test the engine/domain split (ADR-003) surfaced the gap immediately. Its
centerpiece is **complementary** scoring (a therapist's measured effectiveness
in the patient's primary need — strength fills need), the inverse of housing's
similarity-led model. Complementary cannot be expressed as similarity:
similarity rewards alikeness; complementary rewards a provider being *strong*
regardless of the seeker's level. Faking it in the domain layer would mean
healthcare bypassing the engine for its core scoring, defeating the whole
"same engine, different config" proof.

This was a leak check, and the answer was clear: the engine was not leaking
domain vocabulary — it was simply **under-built relative to its own role
design**. The honest fix is to complete the engine generically.

## Decision

Implement `complementary` and `soft_preference` as **generic** scored factors,
and generalize Tier 1 base scoring from "similarity only" to a **weighted blend
over all present scored factors**, jointly renormalized.

- `ComplementaryAttribute`: one side has a `need` (a dimension label), the other
  a `strengths` map (dimension → level); the score is the provider's level in
  the needed dimension, mapped through a config `levels` table to a fraction.
  **Orientation-robust** — it locates the (needer, provider) relationship
  wherever it sits in the pair, so a directional need scores identically
  regardless of argument order.
- `SoftPreferenceRule`: the seeker's stated preference tested against the
  candidate's attribute; met → 1.0, stated-but-unmet → a configured penalty
  fraction (never a disqualification), unstated → factor skipped.
- `score_pair` blends similarity + complementary + soft_preference by weight.
  **What dominates is purely the config weights** — housing stays
  similarity-dominant, healthcare is complementary-dominant; the engine is
  role-agnostic.

The new `ScoringSpec` fields default to empty, so existing domains are
unaffected.

## Consequences

**Positive**

- The engine now matches the five-role design it always claimed (ADR-001).
- **The directional pipeline is untouched.** ADR-004's min-of-both-directions
  rule assumes symmetric (cohabitation) matching; healthcare is one-directional
  (patient→therapist). Rather than make the display rule configurable (a
  pipeline change), the orientation-robust complementary scorer makes both
  directions yield the *same* forward score, so `min` naturally returns it.
  Asymmetric matching works with **no change to `run_match` or `final_score`**.
- Backward-compatible: housing scores are byte-identical; all prior tests stay
  green.
- The roles are domain-agnostic — housing could adopt complementary later
  (e.g. budget complementarity) as a pure config change.

**Negative / accepted costs**

- Two more scored-factor types to maintain.
- Soft preferences are seeker-side only, so on the reverse (eligibility-only)
  direction a *satisfied* preference is dropped by the min and only an *unmet*
  one surfaces as a penalty. This "penalty-only" behavior is acceptable and, for
  the asymmetric case, arguably correct; revisit if a domain needs symmetric
  soft preferences.

**Revisit when**

- A domain needs membership-style filters (seeker value ∈ candidate's list,
  e.g. multi-state licensure). Healthcare v1 sidesteps this with single-value
  modeling; a generic membership filter rule would be the next small, generic
  Tier 0 addition — surfaced here so it is not a silent gap.
- A domain needs a non-minimum display rule for asymmetric matching that the
  orientation-robust trick cannot express.

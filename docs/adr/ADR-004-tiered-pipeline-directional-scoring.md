# ADR-004: Tiered matching pipeline, directional scoring, and minimum-score display

**Status:** Accepted
**Date:** 2026-06-10
**Decision owner:** Ni Ni

## Context

Authoring eval golden pairs (ADR-002) surfaced cases the flat scoring model
could not express correctly:

- A pair compatible on everything except **location** (NYC vs. LA) is not a
  "low match" — it is *not a match*. A score, even 0, is the wrong shape for
  "not applicable."
- **Gender preferences** require both an identity field and a preference
  field, and the strictness of the preference determines whether it gates or
  scores.
- Asymmetric attributes (preferences evaluated against the *other* person's
  identity or tolerance) mean **A→B and B→A scores can differ**, forcing a
  decision about what users see.
- Pairwise matching is O(n²), and the AI nuance bonus (ADR-001) attaches an
  LLM cost to scored pairs — unfiltered scoring is both wrong and expensive.

## Decision

### 1. Three-tier pipeline

```
All candidates
   → TIER 0 · FILTER   gates run BEFORE scoring; failed pairs are never scored
   → TIER 1 · SCORE    deterministic base: hard constraints, soft preferences,
                        similarity, complementary (0–90)
   → TIER 2 · ENRICH   mutual interests (low-weight similarity) +
                        AI nuance bonus (±10, top-N candidates only)
   → Ranked matches
```

Tier 0 expresses *viability*; Tiers 1–2 express *quality*. The filter stage
is simultaneously the system's largest cost optimization: scoring never runs
across cities, collapsing the candidate set by orders of magnitude before any
compute is spent.

### 2. Tier 0 filters for housing v1

- **Location: city-level.** Both parties must seek the same city.
  Neighborhood proximity is deferred to a Tier 1 similarity factor.
- **Gender requirements.** Identity field (required): female, male, or
  self-describe. Preference field (required): `female_only`, `male_only`,
  `open_to_all`. The `*_only` options are Tier 0 gates matching declared
  identity exactly.

**Documented semantics for self-describe:** under exact-match filtering,
self-describe users pass only `open_to_all` preferences. This consequence is
(a) made transparent in the UI at selection time, and (b) explicitly flagged
for revisit with real-user feedback — it is a documented trade-off, not an
accident in the code.

A fourth "prefer but flexible" option (soft preference) was considered and
deferred: it would preserve a genuine middle ground at the cost of
questionnaire complexity. The engine retains the `soft_preference` role
(ADR-003 amendment 3), so re-introducing it is a config change.

### 3. Directional scoring, minimum displayed

- The engine computes and stores **both directions**: A→B (B's fit against
  A's preferences) and B→A. The `matches` table holds two directional rows
  per pair.
- **The match-card headline displays the minimum** of the two directions.
- The detail view shows the directional breakdown ("their fit for your
  preferences / your fit for theirs"), narrated by the explanation layer.

## Alternatives considered (display rule)

- **Maximum.** Rejected: it hides detected friction from both parties,
  over-promises, and erodes trust in the score — the product's core asset.
  Engagement-optimal short-term, credibility-destroying long-term.
- **Average.** Rejected: launders asymmetry — an 85/60 pair and a 73/72 pair
  display identically despite being very different propositions.
- **Both scores as the headline.** Rejected for the headline (cognitive
  load), adopted for the detail view.

**Chosen: minimum.** Cohabitation success is a weakest-link system; the
lower direction is the better predictor of outcome. Under-promising and
over-delivering compounds trust. The display rule is one line of read-time
logic over directional data, so it is cheap to revisit.

## Consequences

**Positive**

- "Not applicable" and "low quality" are finally distinct concepts.
- Tier 0 cuts both incorrect matches and the dominant cost driver (LLM calls
  on pairs that should never meet).
- Directional storage makes the display rule a presentation decision, not a
  data migration.
- The asymmetry breakdown becomes a user-facing feature ("the gap is my two
  cats") and a natural subject for the explanation-quality eval suite.

**Negative / accepted costs**

- Two rows per pair doubles `matches` storage (cheap) and requires
  consistency discipline (both rows written transactionally).
- Self-describe users have a structurally smaller candidate pool under
  exact-match semantics; accepted for v1, transparently disclosed, flagged
  for revisit.
- City-level filtering may split metro areas users consider one market
  (e.g., SF vs. Oakland); revisit granularity with usage data.

**Revisit when**

- Real-user feedback on the self-describe filter semantics or demand for a
  "prefer but flexible" gender option.
- Usage shows metro-area splits harming match supply → consider
  city-cluster or commute-radius filters.
- Display-rule feedback (does min feel too harsh?) → it's a read-time change.

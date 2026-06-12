# Matching Engine

A **domain-agnostic compatibility-matching engine**. The engine is the
product; the roommate/housing app is its first reference implementation —
the demo that proves the platform (see ADR-003).

## How it works

Matching runs as a tiered pipeline (ADR-004): Tier 0 **filters** gate
viability before any scoring; Tier 1 computes a **deterministic base score**
(0–90) from structured attributes; Tier 2 **enriches** top candidates with a
bounded AI nuance bonus (±10, hard-capped in code) read from free-text bios
(ADR-001). Scores are directional — A→B and B→A are computed and stored
separately, and the headline displays the minimum. Every change to scoring
logic or prompts must pass the eval harness before it ships (ADR-002).

The engine speaks only in generic vocabulary — entities, attributes,
constraint roles (filter, hard constraint, soft preference, similarity,
complementary), weights, scores. A new domain is a validated config file
plus thin glue code, not an engine change.

## Repository layout

```
engine/        # the product: generic core, zero domain imports
domains/
  housing/     # reference implementation: config + questionnaire + glue
evals/
  cases/       # golden-pair datasets (the theory of compatibility, testable)
  reports/     # timestamped eval reports, committed and diffable
docs/adr/      # architecture decision records — binding decisions
```

The dependency direction is strict: `engine/` imports nothing from
`domains/`; housing imports the engine.

## Decisions

All architecturally significant decisions are recorded in
[docs/adr/](docs/adr/README.md). Read them before changing anything
structural — they are binding until superseded.

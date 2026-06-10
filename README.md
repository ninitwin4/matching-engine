# Architecture Decision Records (ADRs)

This folder captures the significant architecture decisions for the matching engine
platform and its first reference implementation (the roommate/housing app).

## What is an ADR?

An ADR is a short document recording one architecturally significant decision:
what we decided, the context that forced the decision, the alternatives we
considered, and the consequences we accept. ADRs are written *when the decision
is made* and are never edited to pretend we always knew better — if a decision
is reversed, a new ADR supersedes the old one.

Format follows Michael Nygard's classic template (Context → Decision → Consequences),
extended with an "Alternatives considered" section.

## Index

| ID | Title | Status |
|----|-------|--------|
| [ADR-001](ADR-001-hybrid-scoring.md) | Hybrid scoring: deterministic core with bounded AI nuance bonus | Accepted |
| [ADR-002](ADR-002-eval-harness-score-correctness-first.md) | Eval harness measures score correctness first | Accepted |
| [ADR-003](ADR-003-engine-as-product.md) | The matching engine is the product; housing is the reference implementation | Accepted |

## Statuses

- **Proposed** — under discussion
- **Accepted** — in effect
- **Superseded by ADR-XXX** — replaced by a later decision

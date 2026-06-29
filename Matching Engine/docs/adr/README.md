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
| [ADR-001](ADR-001-hybrid-scoring.md) | Hybrid scoring: deterministic core with bounded AI nuance bonus | Accepted, amended 2026-06-10/12; bonus-model default superseded by ADR-005 |
| [ADR-002](ADR-002-eval-harness-score-correctness-first.md) | Eval harness measures score correctness first | Accepted, amended 2026-06-10 |
| [ADR-003](ADR-003-engine-as-product.md) | The matching engine is the product; housing is the reference implementation | Accepted, amended 2026-06-10 |
| [ADR-004](ADR-004-tiered-pipeline-directional-scoring.md) | Tiered matching pipeline, directional scoring, and minimum-score display | Accepted |
| [ADR-005](ADR-005-tiered-model-escalation-for-the-ai-bonus.md) | Tiered model escalation for the Tier 2 AI nuance bonus | Accepted |
| [ADR-006](ADR-006-complementary-and-soft-preference-scoring.md) | Engine gains complementary and soft-preference scoring | Accepted |

## Statuses

- **Proposed** — under discussion
- **Accepted** — in effect
- **Superseded by ADR-XXX** — replaced by a later decision

## Appendix: learning & build roadmap

The project doubles as a learning vehicle. The phases are sequenced so each
produces the raw material the next requires:

1. **Golden pairs** — author the eval dataset (the product's theory of
   compatibility, in testable form). *In progress.*
2. **Eval harness runs** — dataset + runner + report (ADR-002 skeleton).
3. **Failure analysis** — only learnable once real failures exist: build a
   failure taxonomy (direction errors, groundedness errors, variance
   blowups), find patterns, decide whether each fix belongs in the prompt,
   the weights, or the test case itself.
4. **Latency / accuracy / cost optimization** — needs a baseline to optimize
   against. Measure the trades already designed in (top-N gating, model
   right-sizing, caching — ADR-001 amendments): e.g., does the small model's
   bonus agree with a larger model's often enough? That experiment runs *on*
   the eval harness from phase 2.

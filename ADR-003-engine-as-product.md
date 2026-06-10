# ADR-003: The matching engine is the product; housing is the reference implementation

**Status:** Accepted
**Date:** 2026-06-10
**Decision owner:** Ni Ni

## Context

The long-term ambition is a **domain-agnostic compatibility engine** reusable
across industries (roommates, mentorship, co-founders, shift matching, …).
The roommate/housing app is the first use case. We had to decide how seriously
to invest in that generality now, before a second consumer exists — knowing
the classic trap that abstractions designed against a single example are
always slightly wrong.

## Decision

**The engine is the product. The housing app is its first reference
implementation — the demo that proves the platform.**

Concretely:

1. **Strict dependency direction.** The engine package imports nothing from
   the housing package. Housing imports the engine. Enforced by repo layout
   and (later) lint/CI checks.
2. **Generic vocabulary in the core.** The engine knows *entities, attributes,
   constraint types (hard / similarity / complementary), weights, and scores*.
   Words like "roommate", "rent", or "pets" never appear in engine code.
3. **The domain config contract is a public API.** A domain is defined by a
   validated, versioned configuration (attribute definitions, constraint
   types, scales, weights) plus thin glue code. It gets schema validation,
   versioning, and documentation written as if a stranger will use it.
4. **Repo structure makes the split visible at a glance:**

   ```
   matching-engine/
     engine/        # the product: generic core, zero domain imports
     domains/
       housing/     # config + questionnaire + glue (reference impl)
     evals/         # harness + suites (ADR-002)
     docs/adr/      # these records
   ```

5. **Guarded generality.** Housing remains the only consumer for now. We do
   not build speculative features for hypothetical domains; we *do* sanity-check
   the config contract against a thought-experiment second domain
   (e.g., mentorship: expertise gap = complementary, timezone = hard
   constraint) whenever the contract changes.

## Alternatives considered

- **Housing-only app, clean core as a bonus.** Least work; generality stays an
  internal nicety. Rejected: the platform story is the explicit product goal,
  and retrofitting public-API discipline onto an internal contract later is
  costlier than starting with it.
- **Second domain within ~6 months.** Forces the abstraction to prove itself
  early, but splits limited solo-builder time across two products before the
  first is validated. Deferred rather than rejected: a second domain config is
  the natural milestone after the housing demo works end-to-end.

## Consequences

**Positive**

- The day someone asks "can this match co-founders?", the answer is "write a
  config file."
- Engine code stays portable and independently testable; the eval harness can
  exercise the core with synthetic domains.
- The repository tells a platform story (engine + reference implementation),
  not an app story.

**Negative / accepted costs**

- Config contract design, validation, versioning, and documentation are real
  ongoing overhead that a single-app design would skip.
- Until a second real consumer exists, the abstraction is unproven; some
  rework when domain #2 arrives is expected and accepted.
- Solo-builder time spent on platform discipline is time not spent on housing
  features.

**Revisit when**

- The housing reference implementation works end-to-end → consider building a
  second domain config (mentorship is the leading candidate) to stress-test
  the contract.
- The config contract changes shape significantly → version it explicitly and
  record the change in a new ADR.

## Amendments (2026-06-10, same design session)

1. **The config contract gains attribute roles.** Domain configs assign each
   attribute one of: `filter`, `hard_constraint`, `soft_preference`,
   `similarity`, `complementary` (see ADR-001 amendments). Which attribute
   plays which role is domain config; for housing, *location* is the filter —
   for a hypothetical mentorship domain, *timezone* might be.
2. **Profiles split into identity attributes and preferences-about-others.**
   Asymmetric matching (A's preference evaluated against B's identity, and
   vice versa) is a first-class engine concept, generalizing the
   `smoker` / `smoker_ok` pattern.
3. **Engine stays more expressive than any one domain.** The housing v1
   config deliberately does not use `soft_preference` for gender (see
   ADR-004), but the role remains supported in the engine — other attributes
   use it (budget overlap), and re-enabling it for gender later is a config
   change, not an engine change. Principle: *decide simply, build flexibly.*

# ADR-007: Repository layout — seven top-level folders

**Status:** Accepted
**Date:** 2026-08-27
**Decision owner:** Ni Ni

## Context

ADR-003 established that the engine is the product and a domain is a config
file, and it sketched a four-folder layout in passing (`engine/`, `domains/`,
`evals/`, `docs/adr/`). The repository has since grown to seven top-level
folders — `api/`, `domains/`, `docs/`, `engine/`, `evals/`, `frontend/`,
`tests/` — without that growth ever being recorded as a decision.

This is for me to test how well I understand what the AI coding agent builds from all my ADR decisions, 
and also to review which are the main components to keep and which are deadweight to remove.

## Decision

**Keep the seven-folder split. Each top-level folder owns exactly one
responsibility, and the dependency direction between them is one-way.**

- **`engine/`** — the generic scoring core. Knows entities, attributes,
  constraints and weights. Imports nothing from `domains/`, `api/` or
  `frontend/`. This is the product (ADR-003).
- **`domains/`** — one subfolder per industry (`housing/`, `healthcare/`),
  each a versioned YAML config plus thin glue. The engine reads these files
  at runtime: they are the source of truth for weights and constraint
  definitions. The only place domain vocabulary such as "rent" or "therapist"
  is permitted.
- **`api/`** — the HTTP boundary. Translates requests into engine calls and
  engine results into JSON. Holds no scoring logic of its own.
- **`frontend/`** — the browser client. Talks to `api/` over HTTP only, and
  therefore knows nothing about Python, the engine, or the domain configs.
- **`evals/`** — evaluates whether the scoring produces good matches, using AI API calls.
- **`tests/`** — checks that the engine and API behave as specified, deterministically 
  and without AI calls; contains no logic the product depends on at runtime.
- **`docs/`** — records each architecture decision as an ADR. Nothing here is
  ever read by running code; it exists purely for human readers. 

The dependency direction is strictly one-way:
`frontend/` → `api/` → `domains/` → `engine/`. Nothing points back up.

## Alternatives considered

- **A single flat package.** Put every module in one folder and rely on file
  names for separation. Simplest to navigate while the project is small, and
  no import ceremony. Rejected: nothing would then *prevent* the engine from
  importing a housing constant, and ADR-003's central guarantee — that the
  engine is domain-agnostic — would be a convention rather than something the
  layout makes visible and reviewable.

- **Split the repository into separate repos** (engine, domains, app).
  Enforces the boundary absolutely, since a separate repo cannot be imported
  by accident. Rejected for now: version coordination across three
  repositories is real overhead for a solo builder, and the boundary is not
  yet under enough pressure to justify it.

## Consequences

**Positive**

- The dependency rule is visible in the folder tree, so a violation is
  obvious in review rather than buried in an import line.
- A newcomer can be told which folder to open for a given question without a
  tour of the code.
- `engine/` can be tested against synthetic domains, because it has no
  knowledge of any real one.
- All the remaining folders each carry enough of their own usefulness that
  they don't need to be merged into one.

**Negative / accepted costs**

The cost to newcomers is that they'd need to read both the `tests/` and
  `evals/` folders to understand how thoroughly the engine is verified.
  `tests/` is deterministic because a check that gives different answers on
  different runs can't tell you whether you broke something.

**Revisit when**

- A second consumer of the API appears (a mobile client, a partner
  integration), which would test whether `api/` is a real boundary or merely
  a wrapper around `frontend/`'s needs.
- Any folder grows large enough to need internal structure of its own.

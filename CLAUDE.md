# CLAUDE.md

Read docs/adr/ before making any architectural choice; those decisions are
binding. Key constraints: the engine package imports nothing from domains/;
AI adjustments are hard-capped at ±10 in code; deterministic evals must pass
100% before changes are accepted.

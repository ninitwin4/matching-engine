---
name: run-evals
description: Use when editing evals/cases/ai_bonus.json, evals/run_ai_bonus.py, the Tier 2 prompt in domains/housing/ai_bonus.py, engine/ai_bonus.py, or bonus_cache.json; when asked to run, re-run, or interpret the AI-bonus eval, a report in evals/reports/, or a pass rate like "7/8"; or before bumping the anthropic pin. Not for frontend/, API routing, or the Tier 0/1 pytest suites.
---

# Running the AI-bonus eval

## Running

```bash
python evals/run_ai_bonus.py              # single model: Haiku, as the live API serves it
python evals/run_ai_bonus.py --escalate   # production policy: 2 Haiku samples, Sonnet on disagreement
python evals/run_ai_bonus.py ai-004       # named cases only
```

- Needs `ANTHROPIC_API_KEY`. The runner reads a gitignored `.env` at the repo
  root and exits with a message if the key is missing. On a fresh clone `.env`
  doesn't exist: `cp .env.example .env` and paste the key in.
- Cost is real but small: 8 cases × 3 runs, roughly $0.08 (Haiku), $0.13
  (`--escalate`), $0.15 (`--model claude-sonnet-4-6`); about a cent per case.
  Judge calls are included. Runs are sequential; expect 1–2 minutes.
- Every run writes `evals/reports/ai_bonus_<timestamp>.md`. A run with a bad key
  still writes one, full of `degraded` zeros — delete it, don't commit it.
- Green tests don't prove the AI layer works: every test uses a fake client, so
  the real `client.messages.parse` call is never exercised, and `pytest` never
  reads `ai_bonus.json`. Only this runner does.

## Interpreting a result

- **A single failure is not a verdict.** ADR-002: re-run once. Pass → log a
  flake (a recurring flake on one case is a consistency problem). Fail again →
  real; decide with evidence whether the fix is the prompt, the weights, or
  the case. Never delete a failing case to go green.
- **Read every run's rationale, not just the pass/fail line.** A case fails
  consistency when spread > `max_spread` even if one run was exactly right.
- **The four checks mean different things:**
  - *bounds* — a value escaped ±cap after parsing: engine bug, not prompt.
  - *direction* — sign/magnitude vs. `expected.direction`, and **every** run must
    pass. `neutral_or_zero` means |adj| ≤ 3, not exactly 0; `mild_positive` is
    0–6. One run at −4 on a neutral case fails the whole case.
  - *groundedness* — an LLM judge checks that the rationale expresses each
    `must_reference` concept and asserts no `must_not_reference` claim. It
    grades the rationale's content, not the adjustment: a well-argued wrong
    answer passes. Verify direction separately. Cases with empty concept lists
    skip the judge (auto-pass), and a failed or malformed judge call reports
    as *not grounded* — check the notes before blaming the prompt.
  - *consistency* — max − min adjustment across runs ≤ `max_spread`. Variance,
    not wrongness; often a case-design problem (ADR-005).
- **Negative-direction cases are the fragile ones.** Haiku's judgment about
  what the questionnaire "already captures" shifts between runs, so a friction
  case can score −8 on one run and 0 on the next. Expect flakes there first.
- **Which run reflects users?** The live API calls `compute_bonus` — one Haiku
  call, no escalation — so a plain run is what users get. `--escalate` clears
  the ADR-002 bar (ADR-005), but it is not what's served.
- A judge or SDK change can shift results with no prompt edit. If a case flips
  after a dependency bump, suspect the pin before the case.

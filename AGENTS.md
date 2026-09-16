# AGENTS.md

Only what the code won't tell you.

## Scoring

- **Housing and healthcare score differently; never conflate them.** Housing:
  base 0–90 plus AI adjustment on the top-N. Healthcare: 0–100, no AI step
  (`ai_applied` always False).
- **The AI adjustment is signed.** Every identifier says "bonus" (`ai_bonus.py`,
  `AIBonusSpec`, `AIBonusResult`, `compute_bonus`), but negative adjustments for
  genuine friction are required behavior (eval case `ai-006`), not a bug.
- **Housing scores must stay byte-identical.** They were unchanged across the
  ADR-006 commit (`0959515`); any change to `engine/scoring.py` must preserve
  them. The tests won't catch drift — Tier 1 golden pairs assert score ranges —
  so compare every housing pair's scores at full float precision before and
  after.

## Engine boundary

- **`engine/` imports nothing from `domains/`, `api/`, or `frontend/`.** Enforced
  by convention only: no test, lint rule, or CI check fails if it breaks.
- **No domain vocabulary (rent, therapist, roommate, …) in `engine/` code**
  (docstrings naming domains as examples excepted).

## Models

- **Haiku is the default; Sonnet is eval-harness only.** The API and
  `scripts/build_bonus_cache.py` call `compute_bonus` — one Haiku call, no
  escalation — even though the housing spec carries `escalation_model`. Sonnet
  is reachable only through `compute_bonus_escalated`, which only
  `evals/run_ai_bonus.py --escalate` calls.

## AI failures are silent

- **Before editing the housing prompt, model, cap, or a seed bio, plan a cache
  rebuild.** The cache key hashes both bios, the model, the prompt, and the
  cap: a prompt, model, or cap change misses every cached pair; a bio edit
  misses that profile's pairs. A miss raises nothing — the API serves base
  scores with `degraded: true`, and `pytest` and CI check only `sf-priya`'s
  pairs. Rebuild with `python scripts/build_bonus_cache.py --rebuild` (one
  Haiku call per pair — costs money, needs `ANTHROPIC_API_KEY`).
- **Green tests don't prove the AI layer works.** Refusals, parse errors, and
  SDK exceptions return adjustment `0` with `degraded=True` instead of raising
  (`engine/ai_bonus.py`), and every test uses a fake client — so passing tests
  don't show the real `client.messages.parse` call works. Only
  `python evals/run_ai_bonus.py` does,
  so run it before bumping the `anthropic` pin: a broken bump looks like silent
  zero adjustments (commit `68d9215`).

## Decisions

- **Architectural changes are recorded in `docs/adr/`, never only in a code
  comment.** Refine an existing decision with a dated
  `## Amendment (YYYY-MM-DD, …)` section in its ADR; a new or reversed decision
  gets a new ADR that supersedes the old one. Never rewrite existing ADR text.

## Frontend

- **No build step.** `frontend/index.html` loads React, Babel standalone, and
  Tailwind from CDNs and compiles JSX in the browser; the API base URL comes
  from `frontend/env.js`. There is no `package.json` and no Vite — don't run npm.

## Working preferences

- No co-author trailers on commits.
- The maintainer writes ADR prose. Draft ADR text for them to edit; never commit
  ADR text directly.
- Ask before adding any new top-level folder or file.
- Before any command that deletes or rewrites git history, or discards
  uncommitted or untracked work — `update-ref -d`, `reset --hard`,
  `push --force`, `clean -fd`, `branch -D`, `rebase`, `filter-branch`,
  `checkout .`/`restore .`, `stash drop`/`stash clear` — propose the exact
  command and wait. Don't run it.

## Commands

From the repo root:

```bash
pytest                                            # deterministic tests: no LLM, no key
python evals/run_ai_bonus.py --escalate           # LLM eval — costs money
uvicorn api.main:app --reload --port 8000         # API
python3 -m http.server 5173 --directory frontend  # frontend -> http://localhost:5173
```

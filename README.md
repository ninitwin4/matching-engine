# MatchingEngine

A domain-agnostic AI matching engine — one scoring core, any industry, from
housing to healthcare. Built with an eval harness that validates match quality
automatically.

[![Watch the MatchingEngine demo](https://img.youtube.com/vi/FQaMMsk5KHk/maxresdefault.jpg)](https://www.youtube.com/watch?v=FQaMMsk5KHk)

▶ **[Watch the 60-second demo](https://www.youtube.com/watch?v=FQaMMsk5KHk)** — one engine matching housing and healthcare.

> Synthetic demo data · one engine scoring two domains.

---

## The idea

Most matching products are built for a single vertical — a roommate app, a
dating app, a hiring tool — with the matching logic fused to that one use case.
MatchingEngine separates the two: a generic scoring engine that knows only
*entities, attributes, constraints, and weights*, and per-domain config files
that describe what those mean for a given industry.

Housing is the first reference implementation. Healthcare (patient-to-therapist)
is the second — added as a config file and seed data, with the engine running
unchanged. That's the whole thesis: **the engine is the product; each domain is
a consumer.**

## How it works

Matching runs as a three-tier pipeline:

- **Tier 0 — Filter.** Hard gates (location, licensure, gender requirements).
  Incompatible pairs are removed before scoring, never ranked low.
- **Tier 1 — Score.** Deterministic 0–90 base score from structured attributes,
  combining hard constraints, similarity ("alike is better"), and complementary
  ("strength fills need") scoring.
- **Tier 2 — Enrich.** A bounded LLM nuance bonus (±10, hard-capped in code)
  reads free-text bios for signal the structured fields can't capture — applied
  only to top candidates, with graceful fallback if the model call fails.

Scores are computed in both directions and the lower one is displayed — a match
is only as strong as its least-enthusiastic side.

## Architecture decisions

Every significant decision is recorded as an ADR in [`docs/adr/`](docs/adr/):

- ADR-001 — Hybrid scoring: deterministic core + bounded AI bonus
- ADR-002 — Eval harness: score correctness first
- ADR-003 — The engine is the product; domains are consumers
- ADR-004 — Tiered pipeline, directional scoring, minimum-score display
- ADR-005 — Model escalation (Haiku default, Sonnet for ambiguous cases)
- ADR-006 — Complementary + soft-preference scoring (added for healthcare)

The scoring logic is validated by an eval harness with authored golden pairs
and an LLM-judged groundedness check for the AI bonus.

## Tech stack

- **Engine & API:** Python, FastAPI
- **Scoring:** deterministic core + Anthropic API (Claude) for the AI bonus
- **Frontend:** React, Tailwind, Vite
- **Evals:** pytest (deterministic) + a custom LLM-eval runner

## Run it locally

Backend:

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

The AI bonus requires an `ANTHROPIC_API_KEY` in a local `.env` (see
`.env.example`). The engine degrades gracefully to deterministic-only scoring
if no key is present.

## Security & scope

Security was triaged by risk, not treated as all-or-nothing. What's handled,
what's planned, and what's deliberately out of scope:

**Handled**
- Secrets: the Anthropic API key lives in a gitignored `.env`, read from the
  environment, never committed.
- LLM containment: the AI bonus is hard-capped to ±10 in code (not by prompt
  alone) and can never override a hard constraint. If the model call fails or
  returns unparseable output, the system degrades gracefully to
  deterministic-only scoring.

**Planned before any public or real-user deployment**
- Rate limiting on the LLM-backed endpoint, so a public link can't be used to
  run up API cost (a per-IP cap and/or pre-computed demo results).
- Prompt-injection handling on free-text bios: bios are user-authored text fed
  to the model, so a crafted bio could attempt to steer scoring. The ±10 cap
  already limits the blast radius; deliberate input separation and
  instruction-pattern checks are the planned hardening.

**Out of scope by design**
- Authentication and user accounts — the demo runs on synthetic seed data.
- PII and data privacy — no real personal data is used. The healthcare domain
  demonstrates the engine's domain-agnosticism only; it is not a clinical
  product and is not HIPAA-scoped.

## Status

A portfolio demo, not a production service. All profiles are synthetic. The
healthcare domain demonstrates the engine's domain-agnosticism only — it is not
a clinical product, handles no real patient data, and makes no medical claims.

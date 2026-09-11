# MatchingEngine

A domain-agnostic compatibility matching engine — one deterministic scoring
core, from housing to healthcare, with a bounded AI adjustment on top. Built
with an eval harness that validates the scoring logic.

[![Watch the MatchingEngine demo](https://img.youtube.com/vi/FQaMMsk5KHk/maxresdefault.jpg)](https://www.youtube.com/watch?v=FQaMMsk5KHk)

▶ **[Watch the 60-second demo](https://www.youtube.com/watch?v=FQaMMsk5KHk)** — one engine matching housing and healthcare.

**[Try the live demo](https://ninitwin4.github.io/matching-engine/)** — runs in
the browser; the free-tier API can take several seconds to wake on the first
request.

> Synthetic demo data · one engine scoring two domains.

---

## The idea

Most matching products are built for a single vertical — a roommate app, a
dating app, a hiring tool — with the matching logic fused to that one use case.
MatchingEngine separates the two: a generic scoring engine that knows only
*entities, attributes, constraints, and weights*, and per-domain config files
that describe what those mean for a given industry.

Housing is the first reference implementation. Healthcare (patient-to-therapist)
is the second, added as a config file and seed data. It also required
implementing two scoring roles — complementary and soft-preference — that the
engine's design had already declared but never built; housing's scores stayed
byte-identical
([ADR-006](docs/adr/ADR-006-complementary-and-soft-preference-scoring.md)).
That's the whole thesis: **the engine is the product; each domain is a
consumer.**

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
- ADR-007 — Repository layout: seven top-level folders, one-way dependencies

The scoring logic is validated by an [eval harness](evals/) with authored
golden pairs and an LLM-judged groundedness check for the AI bonus.

## The patterns in a shipped product

**[roomfit](https://github.com/ninitwin4/roomfit)** — a room-matching web app for
renters, built as a separate product rather than another domain config.

It reuses this engine's architecture — Tier 0 hard filters, a deterministic
scored core, per-factor explanations surfaced to the user — applied to
seeker→room matching, which is asymmetric: a person is scored against a
listing, so there's no second direction to take the minimum of.

No shared code; the ADRs travelled, not the implementation.

## Tech stack

- **Engine & API:** Python, FastAPI
- **Scoring:** deterministic core + Anthropic API (Claude) for the AI bonus
- **Frontend:** React + Tailwind via CDN, no build step
- **Evals:** pytest (deterministic) + a custom LLM-eval runner

## Run it locally

Backend (Python 3.12+):

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

Frontend (no build step, no Node — separate terminal):

```bash
python3 -m http.server 5173 --directory frontend
# open http://localhost:5173
```

Served from localhost, the page calls the local API automatically (see
`frontend/env.js`).

### Or run the API in Docker

```bash
docker build -t matching-engine-api .
docker run --rm -p 8000:8000 matching-engine-api
```

The image holds the API only; serve the frontend with the command above. Add
`--env-file .env` to pass an API key — it is supplied at runtime and never
copied into the image.

### API key

None is needed to run the demo: every pair the API can serve is answered from a
shipped cache (`domains/housing/seed/bonus_cache.json`). An `ANTHROPIC_API_KEY`
in a local `.env` (see `.env.example`) is only needed to run the LLM eval
suite, rebuild the cache, or score pairs the cache doesn't cover, such as
edited seed profiles. Without one, uncached pairs fall back to
deterministic-only scoring.

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
- Cost exposure on the public demo: every pair the deployed API can serve is
  answered from a pre-computed cache, so visitor traffic triggers no LLM calls
  and the deployment needs no API key.

**Planned before any real-user deployment**
- Rate limiting. The public demo is unauthenticated and unthrottled; the cache
  removes its LLM cost, but a service taking real user input would need a
  per-IP cap.
- Prompt-injection handling on free-text bios: bios are user-authored text fed
  to the model, so a crafted bio could attempt to steer scoring. The ±10 cap
  already limits the blast radius; deliberate input separation and
  instruction-pattern checks are the planned hardening.

**Out of scope by design**
- Authentication and user accounts — the demo runs on synthetic seed data.
- PII and data privacy — no real personal data is used. The healthcare domain
  demonstrates the engine's domain-agnosticism only; it is not a clinical
  product and is not HIPAA-scoped.

## Citation

If you use this software, please cite it. Machine-readable metadata lives in
[`CITATION.cff`](CITATION.cff); GitHub renders it as **Cite this repository** in
the sidebar, and [`.zenodo.json`](.zenodo.json) supplies the same metadata to
Zenodo on release.

<!-- DOI badge goes here after the first Zenodo release:
     [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)
     Use the *concept* DOI (the one that always resolves to the latest version),
     not the version-specific DOI. Then add the same value as a `doi:` field to
     CITATION.cff and .zenodo.json — deferred to v1.1.0, since the DOI does not
     exist until the first release is published. -->

> Tin Win, Ni Ni (2026). *MatchingEngine: Domain-Agnostic Compatibility Scoring
> with Bounded LLM Adjustment* (version 1.0.0).
> https://github.com/ninitwin4/matching-engine

## Status

A portfolio demo, not a production service. All profiles are synthetic. The
healthcare domain demonstrates the engine's domain-agnosticism only — it is not
a clinical product, handles no real patient data, and makes no medical claims.

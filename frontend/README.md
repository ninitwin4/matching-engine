# MatchingEngine — demo frontend

A no-build React + Tailwind single page (CDN React/Tailwind, JSX compiled
in-browser). One UI, two domains: a toggle flips the accent (Housing = cobalt,
Healthcare = flame) and reloads the relevant seeker pool. The score dial and
the expandable **Score Composition** are the focus.

## Run it (no Node required)

From the project root, with `.env` holding `ANTHROPIC_API_KEY`:

```bash
# 1. API (housing scoring makes live Haiku calls)
python3 -m uvicorn api.main:app --port 8000

# 2. Frontend (separate terminal)
python3 -m http.server 5173 --directory frontend
# open http://localhost:5173
```

The API base URL is read from `env.js` (`window.API_BASE`, default
`http://localhost:8000`) — edit that file to point elsewhere. This mirrors the
`VITE_API_BASE_URL` convention for a future Vite migration.

## Notes

- Needs network for the CDN scripts (React 18.3.1, Babel standalone 7.x,
  Tailwind Play CDN) and Google Fonts.
- Housing is scored by the deterministic engine + a bounded AI nuance bonus
  (Haiku); Healthcare is fully deterministic (complementary-dominant, no AI).
- No localStorage; responsive; visible keyboard focus; `prefers-reduced-motion`
  disables the dial/bar animations.

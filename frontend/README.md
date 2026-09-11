# MatchingEngine — demo frontend

A no-build React + Tailwind single page (CDN React/Tailwind, JSX compiled
in-browser). One UI, two domains: a toggle flips the accent (Housing = cobalt,
Healthcare = flame) and reloads the relevant seeker pool. The score dial and
the expandable **Score Composition** are the focus.

## Run it (no Node required)

From the project root. No API key is needed: housing's AI adjustments are
served from the shipped cache.

```bash
# 1. API
python3 -m uvicorn api.main:app --port 8000

# 2. Frontend (separate terminal)
python3 -m http.server 5173 --directory frontend
# open http://localhost:5173
```

The API base URL comes from `env.js` (`window.API_BASE`): served from
localhost, the page calls `http://localhost:8000`; anywhere else, it calls the
deployed API.

## Notes

- Needs network for the CDN scripts (React 18.3.1, Babel standalone 7.x,
  Tailwind Play CDN) and Google Fonts.
- Housing is scored by the deterministic engine + a bounded AI nuance bonus
  (Haiku); Healthcare is fully deterministic (complementary-dominant, no AI).
- No localStorage; responsive; visible keyboard focus; `prefers-reduced-motion`
  disables the dial/bar animations.

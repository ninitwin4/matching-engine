# MatchingEngine API image. Runtime deps only (requirements.txt) — no dev/test
# tooling, no frontend, no secrets baked in.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first so code edits don't invalidate the pip-install layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code only. engine/ and domains/ include the seed JSON + YAML configs the
# API reads at request time; tests/, evals/, frontend/, docs/ are irrelevant
# to serving the API and are excluded via .dockerignore.
COPY engine/ engine/
COPY domains/ domains/
COPY api/ api/

# ANTHROPIC_API_KEY is passed at `docker run` / by the host platform, never
# copied into the image. It isn't needed to serve the demo: every seed pair's
# AI adjustment is answered from domains/housing/seed/bonus_cache.json (copied
# above with domains/). Only a pair missing from that cache needs a key;
# without one it degrades to the base score (ADR-001).

# Non-root user. It does not own /app: the API only reads its files (the bonus
# cache is opened read-only), so a compromised process can't rewrite the code.
RUN useradd --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import os,urllib.request as u; u.urlopen(f\"http://localhost:{os.environ.get('PORT','8000')}/health\", timeout=2)" || exit 1

# Shell form so $PORT expands: hosting platforms (Render, Railway, Fly, Cloud
# Run) assign the port at runtime rather than letting the image pick one.
# `exec` replaces the shell with uvicorn, so uvicorn is PID 1 and receives
# SIGTERM directly — it shuts down cleanly on redeploy instead of being killed.
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}

"""Precompute the Tier 2 pair-level bonus cache for the housing demo pool.

Run this offline, deliberately, when the bios, the prompt, or the model change.
It sweeps every seeker in the seed pool, runs the real bonus for each surviving
pair, and writes domains/housing/seed/bonus_cache.json — which then ships in
the image so the deployed API serves the demo with zero LLM calls
(ADR-001 amendment 3).

Costs real money: roughly 32 Haiku calls (~5 cents) for the current pool, and
only for pairs not already cached. Safe to re-run — existing entries are hits.

Usage:
    python scripts/build_bonus_cache.py            # fill gaps
    python scripts/build_bonus_cache.py --rebuild  # discard and recompute all

Requires ANTHROPIC_API_KEY (read from .env). Never prints the key.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import anthropic  # noqa: E402

from domains.housing.match import (  # noqa: E402
    BONUS_CACHE_PATH,
    housing_bonus_cache,
    match_seeker,
)

SEED_PATH = ROOT / "domains" / "housing" / "seed" / "profiles.json"


def main(argv):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set — cannot build the cache.")

    if "--rebuild" in argv and BONUS_CACHE_PATH.exists():
        BONUS_CACHE_PATH.unlink()
        print("removed existing cache (rebuild)")

    profiles = json.loads(SEED_PATH.read_text())
    cache = housing_bonus_cache(writable=True)
    before = len(cache)
    client = anthropic.Anthropic()

    print(f"sweeping {len(profiles)} seekers (cache starts with {before} entries)")
    calls = 0
    for p in profiles:
        pool = [c for c in profiles if c["id"] != p["id"]]
        results = match_seeker(p, pool, client=client, cache=cache)
        applied = [m for m in results if m.ai_applied]
        degraded = [m for m in applied if m.degraded]
        calls += len(applied)
        flag = f"  !! {len(degraded)} degraded" if degraded else ""
        print(f"  {p['id']:12} {len(results)} matches, {len(applied)} scored{flag}")

    after = len(cache)
    print(f"\ncache: {before} -> {after} entries (+{after - before})")
    print(f"pairs scored this run: {calls}")
    print(f"written to {BONUS_CACHE_PATH.relative_to(ROOT)}")
    if after == before and calls:
        print("note: no new entries — every pair was already cached")


if __name__ == "__main__":
    main(sys.argv[1:])

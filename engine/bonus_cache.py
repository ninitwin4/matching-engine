"""Pair-level cache for the Tier 2 nuance bonus (ADR-001 amendment 3).

The bonus is an expensive, bounded judgment over two free-text inputs. Its
inputs are stable — a pair's texts rarely change — so the adjustment and
rationale are cached and the LLM is re-called only when something that affects
the answer changes.

The key hashes everything that can change the result:

  * both texts, **sorted** — the bonus is pair-level and symmetric (the same
    adjustment applies to both directions, see engine.scoring.final_score), so
    A/B and B/A are one cache entry, not two.
  * the model and the system prompt — a prompt or model change must invalidate
    the cache, otherwise a tuned prompt would silently serve stale answers.
  * the cap, which bounds the stored adjustment.

Engine-generic per ADR-003: this module knows nothing about bios, roommates,
or therapists — only opaque text and a key/value store.

ADR deviation: ADR-001 amendment 3 names Postgres as the cache store. This
implementation is a JSON file, because the deployed demo has no database and
its candidate pool is a fixed seed file. The store is behind a small interface,
so swapping in Postgres later is a new class, not a rewrite.
"""

import hashlib
import json
from pathlib import Path

from engine.types import AIBonusResult, AIBonusSpec


def cache_key(text_a: str, text_b: str, spec: AIBonusSpec) -> str:
    """Stable key for a pair under a given prompt/model/cap.

    Texts are sorted so the pair is order-independent; every other component
    that could change the answer is folded in, so a prompt or model change
    yields a different key rather than a stale hit.
    """
    first, second = sorted([text_a or "", text_b or ""])
    payload = "\x00".join(
        [first, second, spec.model, spec.system_prompt, str(spec.cap)]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class JsonFileCache:
    """Dict-backed cache persisted as JSON.

    Loads once into memory; `set` optionally writes through to disk. In the
    deployed API the file ships read-only inside the image (writes disabled),
    so a cold start still gets every precomputed pair for free.
    """

    def __init__(self, path: Path | str | None = None, *, writable: bool = False):
        self.path = Path(path) if path else None
        self.writable = writable
        self._data: dict[str, dict] = {}
        if self.path and self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                # A corrupt or unreadable cache must never break matching —
                # start empty and re-earn the entries.
                self._data = {}

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str) -> AIBonusResult | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        return AIBonusResult(
            adjustment=entry["adjustment"],
            rationale=entry["rationale"],
            raw_adjustment=entry.get("raw_adjustment"),
            degraded=False,
            latency_ms=0.0,  # served from cache, no call made
            input_tokens=0,
            output_tokens=0,
        )

    def set(self, key: str, result: AIBonusResult) -> None:
        """Store a successful result. Degraded results are never cached — a
        transient outage must not be remembered as a real zero adjustment."""
        if result.degraded:
            return
        self._data[key] = {
            "adjustment": result.adjustment,
            "rationale": result.rationale,
            "raw_adjustment": result.raw_adjustment,
        }
        if self.writable and self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))

"""Pair-level bonus cache tests (ADR-001 amendment 3). Fully offline — a
counting fake client proves when the LLM is and isn't called.
"""

import json

import pytest

from engine.ai_bonus import compute_bonus
from engine.bonus_cache import JsonFileCache, cache_key
from engine.types import AIBonusSpec

SPEC = AIBonusSpec(model="fake-model", system_prompt="score it", cap=10.0)


class _Parsed:
    def __init__(self, adjustment, rationale):
        self.adjustment = adjustment
        self.rationale = rationale


class _Usage:
    input_tokens = 100
    output_tokens = 20


class _Response:
    def __init__(self, parsed):
        self.parsed_output = parsed
        self.usage = _Usage()


class _CountingMessages:
    """Counts real calls, so a cache hit is provable by calls staying flat."""

    def __init__(self, adjustment=5, raises=False):
        self.calls = 0
        self._adjustment = adjustment
        self._raises = raises

    def parse(self, **kwargs):
        self.calls += 1
        if self._raises:
            raise RuntimeError("simulated outage")
        return _Response(_Parsed(self._adjustment, "cited the cleaning rota"))


class _CountingClient:
    def __init__(self, adjustment=5, raises=False):
        self.messages = _CountingMessages(adjustment, raises)


# ---- key behaviour ----


def test_key_is_order_independent():
    """The bonus is pair-level and symmetric, so A/B and B/A are one entry."""
    assert cache_key("alice bio", "bob bio", SPEC) == cache_key(
        "bob bio", "alice bio", SPEC
    )


def test_key_changes_when_prompt_changes():
    """A tuned prompt must not serve answers from the old prompt."""
    other = AIBonusSpec(model="fake-model", system_prompt="DIFFERENT", cap=10.0)
    assert cache_key("a", "b", SPEC) != cache_key("a", "b", other)


def test_key_changes_when_model_changes():
    other = AIBonusSpec(model="other-model", system_prompt="score it", cap=10.0)
    assert cache_key("a", "b", SPEC) != cache_key("a", "b", other)


def test_key_changes_when_text_changes():
    assert cache_key("a", "b", SPEC) != cache_key("a", "b2", SPEC)


# ---- cache behaviour through compute_bonus ----


def test_miss_then_hit_avoids_second_llm_call():
    cache = JsonFileCache(None)
    client = _CountingClient(adjustment=5)

    first = compute_bonus("bio a", "bio b", spec=SPEC, client=client, cache=cache)
    assert first.adjustment == 5
    assert client.messages.calls == 1

    second = compute_bonus("bio a", "bio b", spec=SPEC, client=client, cache=cache)
    assert second.adjustment == 5
    assert second.rationale == first.rationale
    assert client.messages.calls == 1  # no second call — served from cache


def test_reversed_pair_also_hits():
    cache = JsonFileCache(None)
    client = _CountingClient()
    compute_bonus("bio a", "bio b", spec=SPEC, client=client, cache=cache)
    compute_bonus("bio b", "bio a", spec=SPEC, client=client, cache=cache)
    assert client.messages.calls == 1


def test_no_cache_argument_always_calls():
    client = _CountingClient()
    compute_bonus("a", "b", spec=SPEC, client=client)
    compute_bonus("a", "b", spec=SPEC, client=client)
    assert client.messages.calls == 2


def test_degraded_results_are_not_cached():
    """An outage must be retried, never remembered as a real zero."""
    cache = JsonFileCache(None)
    failing = _CountingClient(raises=True)
    r = compute_bonus("a", "b", spec=SPEC, client=failing, cache=cache)
    assert r.degraded and r.adjustment == 0.0
    assert len(cache) == 0

    # A later healthy call still does real work and caches properly.
    healthy = _CountingClient(adjustment=7)
    r2 = compute_bonus("a", "b", spec=SPEC, client=healthy, cache=cache)
    assert r2.adjustment == 7 and not r2.degraded
    assert len(cache) == 1


# ---- persistence ----


def test_writable_cache_round_trips_to_disk(tmp_path):
    path = tmp_path / "cache.json"
    cache = JsonFileCache(path, writable=True)
    client = _CountingClient(adjustment=3)
    compute_bonus("a", "b", spec=SPEC, client=client, cache=cache)
    assert path.exists()

    # A fresh read-only cache loads it and serves without calling.
    reloaded = JsonFileCache(path)
    fresh_client = _CountingClient(adjustment=99)
    r = compute_bonus("a", "b", spec=SPEC, client=fresh_client, cache=reloaded)
    assert r.adjustment == 3  # the stored value, not the new client's 99
    assert fresh_client.messages.calls == 0


def test_read_only_cache_does_not_write(tmp_path):
    path = tmp_path / "cache.json"
    cache = JsonFileCache(path, writable=False)
    compute_bonus("a", "b", spec=SPEC, client=_CountingClient(), cache=cache)
    assert not path.exists()  # served in memory, nothing persisted


def test_corrupt_cache_file_degrades_to_empty(tmp_path):
    """A bad cache file must never break matching."""
    path = tmp_path / "cache.json"
    path.write_text("{not valid json")
    cache = JsonFileCache(path)
    assert len(cache) == 0
    client = _CountingClient(adjustment=4)
    assert compute_bonus("a", "b", spec=SPEC, client=client, cache=cache).adjustment == 4


def test_missing_cache_file_is_fine(tmp_path):
    cache = JsonFileCache(tmp_path / "does-not-exist.json")
    assert len(cache) == 0

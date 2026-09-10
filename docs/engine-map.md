# Engine map

One page. What each file in `engine/` owns, what it hands out, and which
stage of the match it runs in. Written 2026-08-29.

The engine is generic (ADR-003): it never names a domain attribute and
imports nothing from `domains/`.

## The run, in order

`run_match()` in `pipeline.py` is the single entry point. Everything below
happens inside one call to it.

| Stage                        | File             | Function                     | What happens                                                                         |
| ---------------------------- | ---------------- | ---------------------------- | ------------------------------------------------------------------------------------ |
| Tier 0 — viability gate      | `filters.py`     | `run_filters`                | Hard yes/no. Candidates that fail are dropped and never scored.                      |
| Tier 1 — deterministic score | `scoring.py`     | `score_pair`                 | Scores the pair **both directions** (A→B and B→A).                                   |
| Tier 1 — disqualify          | `constraints.py` | `run_hard_constraints`       | Called *inside* `score_pair`. Violations disqualify the pair before any LLM call.    |
| Tier 1 — helper              | `intervals.py`   | `intervals_overlap`          | Do two ranges overlap? Used by constraints for things like date or budget windows.   |
| Top-N cut                    | `pipeline.py`    | —                            | Ranks survivors by base score; only the top N continue.                              |
| Tier 2 — AI bonus            | `ai_bonus.py`    | `compute_bonus`              | LLM adjustment, capped at ±10. Returns zero on any failure, so the run never breaks. |
| Tier 2 — cache               | `bonus_cache.py` | `cache_key`, `JsonFileCache` | Already-scored pairs are served from disk instead of re-calling the LLM.             |
| Final                        | `scoring.py`     | `final_score`                | Combines the two directional scores plus the bonus into the displayed score.         |

## The files

| File             | Lines | Exposes                                            | Owns                                                                                            |
| ---------------- | ----- | -------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `types.py`       | 289   | 20 classes, **0 functions**                        | The vocabulary. Defines what an `Entity`, a `Match`, a `ScoringSpec` *are*. Nothing in it acts. |
| `pipeline.py`    | 112   | `run_match`                                        | The conductor. Calls the others in order; adds no scoring logic of its own.                     |
| `scoring.py`     | 151   | `similarity_fraction`, `score_pair`, `final_score` | All deterministic maths. Six private helpers do the work inside.                                |
| `ai_bonus.py`    | 168   | `compute_bonus`, `compute_bonus_escalated`         | The only file that talks to an LLM.                                                             |
| `bonus_cache.py` | 96    | `cache_key`, `JsonFileCache`                       | Persistence for bonus results.                                                                  |
| `constraints.py` | 65    | `run_hard_constraints`                             | Deal-breaker checks with tolerances.                                                            |
| `filters.py`     | 39    | `run_filters`                                      | The viability gate. One job.                                                                    |
| `intervals.py`   | 19    | `intervals_overlap`                                | Range overlap. The smallest, most reusable piece.                                               |

Total public surface: **11 functions/classes** plus 20 type definitions,
out of 939 lines.

## Who imports whom

```
pipeline.py ──> filters.py
            ──> scoring.py ──> constraints.py ──> intervals.py
            ──> ai_bonus.py ──> bonus_cache.py

everything  ──> types.py        (types.py imports nothing from engine/)
```

Arrows only point one way. There are no cycles.

## Three things to answer in your own words

TODO(you) 1 – The AI bonus runs only on the top-N candidates, not on every
survivor. Why did you build it that way? (One sentence. Think about what an
LLM call costs.)
ANSWER:  Not all results need AI since it has the base deterministic score that way LLM 
cost save for unnecessary results and plus AI bonus is capped in code so it won't reach 
within that capped.

TODO(you) 2 — `score_pair` is called twice per candidate: once A→B and once
B→A. `final_score` then combines them, and the number shown to the user is
the *lower* of the two. Why the lower one and not the average?
ANSWER: Cohabitation is the weakest-link system. It's better to show the lower one
rather than showing the average one. Just because A has 90 doesn't mean, it would be 
an average match to B who score has 20, it would clear clash once they start living 
under the same roof. 

TODO(you) 3 — `types.py` imports nothing from any other engine file, and
every other file imports from it. What would go wrong if `types.py` started
importing from `scoring.py`?
ANSWER: It will first run from scoring file with half executed then similarity fraction
isn't defined so it will have an import error because `types.py` is the foundation stack 
and depends on nothing.

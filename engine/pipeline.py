"""End-to-end match run: the three tiers wired into one ranked flow
(ADR-004). This is glue over the already-tested tier functions — it adds no
scoring logic of its own.

Generic per ADR-003: the pipeline takes filter rules, a scoring spec, an
optional bonus spec, and a `text_of` callable as parameters. It never names a
domain attribute, and imports nothing from domains/.

Graceful degradation (ADR-001) is inherited: `compute_bonus` already returns a
zero adjustment on any LLM failure, so a failed call falls back to the base
score automatically.
"""

from typing import Callable, Iterable

from engine.ai_bonus import compute_bonus
from engine.filters import run_filters
from engine.scoring import final_score, score_pair
from engine.types import (
    AIBonusSpec,
    Entity,
    FilterRule,
    Match,
    ScoringSpec,
)


def run_match(
    seeker: Entity,
    candidates: Iterable[Entity],
    *,
    filters: tuple[FilterRule, ...],
    scoring_spec: ScoringSpec,
    top_n: int | None = None,
    bonus_spec: AIBonusSpec | None = None,
    client=None,
    text_of: Callable[[Entity], str] | None = None,
) -> list[Match]:
    """Rank `candidates` for `seeker`.

    Tier 0 filters the pool; Tier 1 scores both directions and disqualifies
    hard-constraint violations; Tier 2 applies the bonus to the top-N by base
    score only; results are ranked by the displayed (minimum) score.

    The bonus runs only when `bonus_spec`, `client`, and `text_of` are all
    provided — so passing `client=None` yields a pure deterministic run.
    """
    # Tier 0 — viability gate. Filtered pairs are never scored (ADR-004).
    survivors = [c for c in candidates if run_filters(seeker, c, filters).passed]

    # Tier 1 — deterministic base, both directions (ADR-004). Currently
    # symmetric, but computed per-direction so it stays correct once asymmetric
    # scored attributes exist. Hard-constraint violations disqualify the pair
    # here, before any LLM call (ADR-001) — so they never reach Tier 2 and
    # never appear in results.
    scored: list[tuple[Entity, float, float, dict]] = []
    for cand in survivors:
        s_ab = score_pair(seeker, cand, scoring_spec)
        s_ba = score_pair(cand, seeker, scoring_spec)
        if s_ab.violations or s_ba.violations:
            continue
        scored.append((cand, s_ab.base_score, s_ba.base_score, dict(s_ab.components)))

    # Top-N by base score (min direction) — only these get the bonus (ADR-001).
    limit = len(scored) if top_n is None else top_n
    by_base = sorted(scored, key=lambda x: (-min(x[1], x[2]), x[0].id))
    topn_ids = {x[0].id for x in by_base[:limit]}

    can_bonus = bonus_spec is not None and client is not None and text_of is not None

    matches: list[Match] = []
    for cand, base_ab, base_ba, components in scored:
        adjustment, rationale, ai_applied, degraded = 0.0, "", False, False
        if can_bonus and cand.id in topn_ids:
            ai_applied = True
            result = compute_bonus(
                text_of(seeker), text_of(cand), spec=bonus_spec, client=client
            )
            adjustment = result.adjustment
            rationale = result.rationale
            degraded = result.degraded
        fs = final_score(base_ab, base_ba, adjustment)
        matches.append(
            Match(
                candidate_id=cand.id,
                display_score=fs.display,
                base_a_to_b=base_ab,
                base_b_to_a=base_ba,
                ai_adjustment=adjustment,
                ai_rationale=rationale,
                ai_applied=ai_applied,
                degraded=degraded,
                components=components,
            )
        )

    matches.sort(key=lambda m: (-m.display_score, m.candidate_id))
    return matches

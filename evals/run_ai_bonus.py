"""Slow-lane eval runner for the Tier 2 AI nuance bonus (ADR-002).

Not pytest: each case makes N real LLM calls, so this is run on demand, never
on every change. Per-case checks (ADR-002 amendment, per-case checks):
bounds, direction, groundedness, consistency. Emits a timestamped markdown
report to evals/reports/ with raw runs, rationales, latency, and token cost —
the raw material for failure analysis (README phase 3).

Usage:
    python evals/run_ai_bonus.py            # all cases
    python evals/run_ai_bonus.py ai-001 ai-004   # named cases only

Requires ANTHROPIC_API_KEY in the environment. Never hardcoded or committed.
"""

import datetime as dt
import json
import os
import statistics
import sys
from dataclasses import replace
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load ANTHROPIC_API_KEY from a gitignored .env at the project root, so the
# key never has to live in the shell environment or on a command line.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from domains.housing.ai_bonus import housing_bonus_spec  # noqa: E402
from engine.ai_bonus import compute_bonus, compute_bonus_escalated  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "evals" / "cases" / "ai_bonus.json"
REPORTS_DIR = ROOT / "evals" / "reports"

# Pricing $/1M tokens (ADR-001 cost tracking). Keyed by model so a one-off
# --model experiment (e.g. the README phase-4 Haiku-vs-larger comparison)
# still reports honest cost. Bonus and judge models are priced separately.
PRICING = {
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
}
_FALLBACK_PRICE = {"input": 1.0, "output": 5.0}

# Model that grades groundedness (ADR-002). Concept-presence detection in a
# short rationale is an objective reading task, so the fast/inexpensive class
# is adequate; swap a stronger judge in here if grading proves unreliable.
JUDGE_MODEL = "claude-haiku-4-5"


def check_direction(adjustment: float, expected: str) -> bool:
    if expected == "positive":
        return adjustment > 0
    if expected == "negative":
        return adjustment < 0
    if expected == "neutral_or_zero":
        return abs(adjustment) <= 3
    if expected == "mild_positive":
        return adjustment >= 0 and adjustment <= 6
    raise ValueError(f"unknown direction {expected!r}")


class _GroundednessVerdict(BaseModel):
    """The judge's structured verdict. Booleans are returned in the same order
    as the concepts supplied, so they zip back positionally."""

    required_present: list[bool]
    forbidden_present: list[bool]
    reasoning: str


def _format_concepts(concept_sets) -> str:
    # Each concept is a synonym set; the judge treats it as ONE concept and
    # matches on meaning (paraphrase counts), not on these literal tokens.
    return (
        "\n".join(
            f"{i + 1}. {' / '.join(tokens)}" for i, tokens in enumerate(concept_sets)
        )
        or "(none)"
    )


def judge_groundedness(
    bio_a: str, bio_b: str, rationale: str, must: list, must_not: list, *, client, model
) -> tuple[bool, list, int, int]:
    """LLM-judged groundedness (ADR-002). A judge model reads the two bios and
    the rationale and decides, per concept, whether the rationale expresses it
    — matching meaning rather than literal tokens, which keyword matching could
    not do against a paraphrasing generator. Returns
    (passed, notes, judge_input_tokens, judge_output_tokens).

    Fails loud: a malformed or failed judge call returns not-grounded with a
    note, so it surfaces for triage rather than silently passing."""
    if not must and not must_not:
        return True, [], 0, 0

    system = (
        "You grade whether a roommate-compatibility RATIONALE is grounded in two "
        "bios. Each REQUIRED concept is given as a set of related terms describing "
        "ONE idea; mark it present (true) if the rationale expresses that idea in "
        "any wording — paraphrase and synonyms count — and it is supported by the "
        "bios. Each FORBIDDEN concept is a claim the rationale must NOT make; mark "
        "it present (true) ONLY if the rationale AFFIRMATIVELY ASSERTS that claim "
        "as a true fact about these roommates (e.g. fabricates a detail not in the "
        "bios). Merely mentioning the topic does NOT count, and explicitly saying "
        "it is ABSENT / not present / not applicable is NOT a violation — mark "
        "those false. Return one boolean per concept, in the order given "
        "(required_present matches the REQUIRED list, forbidden_present the "
        "FORBIDDEN list), plus brief reasoning."
    )
    user = (
        f"BIO A:\n{bio_a}\n\nBIO B:\n{bio_b}\n\n"
        f"RATIONALE TO GRADE:\n{rationale}\n\n"
        f"REQUIRED concepts:\n{_format_concepts(must)}\n\n"
        f"FORBIDDEN concepts:\n{_format_concepts(must_not)}"
    )
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=_GroundednessVerdict,
        )
        verdict = response.parsed_output
        usage = response.usage
        jin = getattr(usage, "input_tokens", 0) or 0
        jout = getattr(usage, "output_tokens", 0) or 0
        if (
            verdict is None
            or len(verdict.required_present) != len(must)
            or len(verdict.forbidden_present) != len(must_not)
        ):
            return False, ["judge returned a malformed verdict"], jin, jout
    except Exception as exc:
        return False, [f"judge call failed: {type(exc).__name__}"], 0, 0

    notes = []
    for tokens, present in zip(must, verdict.required_present):
        if not present:
            notes.append(f"missing required concept: {tokens}")
    for tokens, present in zip(must_not, verdict.forbidden_present):
        if present:
            notes.append(f"contains forbidden concept: {tokens}")
    return (not notes), notes, jin, jout


def _record_single(r, model) -> dict:
    """Normalize a single-model AIBonusResult into a uniform per-run record."""
    return {
        "adjustment": r.adjustment,
        "raw_adjustment": r.raw_adjustment,
        "rationale": r.rationale,
        "degraded": r.degraded,
        "latency_ms": r.latency_ms or 0.0,
        "model": model,
        "escalated": False,
        "primary_in": r.input_tokens or 0,
        "primary_out": r.output_tokens or 0,
        "secondary_in": 0,
        "secondary_out": 0,
    }


def _record_escalated(e) -> dict:
    """Normalize an EscalatedBonusResult: primary tokens summed across samples,
    secondary tokens from the escalation call (0 if it did not escalate)."""
    sec_in = (e.escalation.input_tokens or 0) if e.escalation else 0
    sec_out = (e.escalation.output_tokens or 0) if e.escalation else 0
    return {
        "adjustment": e.adjustment,
        "raw_adjustment": e.raw_adjustment,
        "rationale": e.rationale,
        "degraded": e.degraded,
        "latency_ms": e.latency_ms or 0.0,
        "model": e.model,
        "escalated": e.escalated,
        "primary_in": sum(s.input_tokens or 0 for s in e.samples),
        "primary_out": sum(s.output_tokens or 0 for s in e.samples),
        "secondary_in": sec_in,
        "secondary_out": sec_out,
    }


def run_case(case, spec, client, n, escalate) -> dict:
    runs = []
    for _ in range(n):
        if escalate:
            e = compute_bonus_escalated(
                case["bio_a"], case["bio_b"], spec=spec, client=client
            )
            runs.append(_record_escalated(e))
        else:
            r = compute_bonus(case["bio_a"], case["bio_b"], spec=spec, client=client)
            runs.append(_record_single(r, spec.model))

    expected = case["expected"]
    max_spread = expected.get("max_spread", 5)
    adjustments = [r["adjustment"] for r in runs]
    spread = max(adjustments) - min(adjustments)

    bounds_ok = all(-spec.cap <= a <= spec.cap for a in adjustments)
    direction_ok = all(check_direction(a, expected["direction"]) for a in adjustments)

    ground_notes = []
    judge_in = judge_out = 0
    ground_ok = True
    for r in runs:
        passed, notes, jin, jout = judge_groundedness(
            case["bio_a"],
            case["bio_b"],
            r["rationale"],
            expected["must_reference"],
            expected["must_not_reference"],
            client=client,
            model=JUDGE_MODEL,
        )
        ground_notes.append(notes)
        ground_ok = ground_ok and passed
        judge_in += jin
        judge_out += jout

    consistency_ok = spread <= max_spread
    degraded_any = any(r["degraded"] for r in runs)

    return {
        "id": case["id"],
        "flavor": case.get("flavor", ""),
        "expected": expected,
        "runs": runs,
        "ground_notes": ground_notes,
        "judge_in": judge_in,
        "judge_out": judge_out,
        "escalated_count": sum(1 for r in runs if r["escalated"]),
        "spread": spread,
        "bounds_ok": bounds_ok,
        "direction_ok": direction_ok,
        "ground_ok": ground_ok,
        "consistency_ok": consistency_ok,
        "degraded_any": degraded_any,
        "passed": bounds_ok
        and direction_ok
        and ground_ok
        and consistency_ok
        and not degraded_any,
    }


def render_report(results, suite, model, n, escalate, escalation_model) -> str:
    total = len(results)
    passed = sum(r["passed"] for r in results)
    primary_in = sum(run["primary_in"] for r in results for run in r["runs"])
    primary_out = sum(run["primary_out"] for r in results for run in r["runs"])
    secondary_in = sum(run["secondary_in"] for r in results for run in r["runs"])
    secondary_out = sum(run["secondary_out"] for r in results for run in r["runs"])
    judge_in = sum(r["judge_in"] for r in results)
    judge_out = sum(r["judge_out"] for r in results)
    pp = PRICING.get(model, _FALLBACK_PRICE)
    sp = PRICING.get(escalation_model, _FALLBACK_PRICE)
    jp = PRICING.get(JUDGE_MODEL, _FALLBACK_PRICE)
    cost = (
        primary_in * pp["input"]
        + primary_out * pp["output"]
        + secondary_in * sp["input"]
        + secondary_out * sp["output"]
        + judge_in * jp["input"]
        + judge_out * jp["output"]
    ) / 1e6
    lat = [run["latency_ms"] for r in results for run in r["runs"] if run["latency_ms"]]
    mean_spread = statistics.mean(r["spread"] for r in results) if results else 0
    escalations = sum(r["escalated_count"] for r in results)
    total_runs = n * total

    def rate(key):
        return sum(r[key] for r in results)

    if escalate:
        model_line = (
            f"- Policy: escalation · primary `{model}` -> `{escalation_model}` "
            f"(2-sample agreement gate, ADR-005)  |  Judge: `{JUDGE_MODEL}`  |  N={n}"
        )
        esc_line = (
            f"- Escalations: {escalations}/{total_runs} runs "
            f"({100 * escalations / total_runs:.0f}%)"
        )
    else:
        model_line = f"- Model: `{model}`  |  Judge: `{JUDGE_MODEL}`  |  N={n}"
        esc_line = None

    lines = [
        f"# Tier 2 AI bonus eval — {suite}",
        "",
        f"- Run: {dt.datetime.now().isoformat(timespec='seconds')}",
        model_line,
        f"- **Cases passed: {passed}/{total}**  (pass bar is 100% — ADR-002)",
        f"- Checks: bounds {rate('bounds_ok')}/{total} · "
        f"direction {rate('direction_ok')}/{total} · "
        f"groundedness (LLM-judged) {rate('ground_ok')}/{total} · "
        f"consistency {rate('consistency_ok')}/{total}",
        f"- Mean adjustment spread: {mean_spread:.2f}",
    ]
    if esc_line:
        lines.append(esc_line)
    lines += [
        f"- Tokens: primary {primary_in} in / {primary_out} out · "
        f"escalation {secondary_in} in / {secondary_out} out · "
        f"judge {judge_in} in / {judge_out} out  |  Est. cost: ${cost:.4f}",
        f"- Mean latency: {statistics.mean(lat):.0f} ms" if lat else "- Latency: n/a",
        "",
        "## Per-case results",
        "",
    ]
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        lines.append(f"### {r['id']} — {r['flavor']} — {status}")
        lines.append("")
        lines.append(
            f"Expected direction: `{r['expected']['direction']}` · "
            f"spread {r['spread']} (max {r['expected'].get('max_spread', 5)})"
        )
        checks = []
        for key, label in [
            ("bounds_ok", "bounds"),
            ("direction_ok", "direction"),
            ("ground_ok", "groundedness"),
            ("consistency_ok", "consistency"),
        ]:
            checks.append(f"{label} {'✓' if r[key] else '✗'}")
        if r["degraded_any"]:
            checks.append("DEGRADED ⚠")
        lines.append("Checks: " + " · ".join(checks))
        lines.append("")
        for i, (run, notes) in enumerate(zip(r["runs"], r["ground_notes"]), 1):
            tag = f" [escalated -> {run['model']}]" if run["escalated"] else ""
            tokens = (
                f"{run['primary_in']}+{run['secondary_in']}in"
                f"/{run['primary_out']}+{run['secondary_out']}out"
            )
            lines.append(
                f"- Run {i}: adj **{run['adjustment']}** "
                f"(raw {run['raw_adjustment']}) · "
                f"{run['latency_ms']:.0f}ms · {tokens}{tag}"
            )
            lines.append(f"  - rationale: {run['rationale']!r}")
            if notes:
                lines.append(f"  - groundedness notes: {notes}")
        lines.append("")
    return "\n".join(lines)


def main(argv):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set — cannot run the live AI suite.")

    # Flags:
    #   --escalate        run the production escalation policy (ADR-005)
    #   --model <name>    one-off primary-model override (phase-4 experiment);
    #                     committed default in domains/housing stays untouched.
    args = list(argv)
    escalate = "--escalate" in args
    if escalate:
        args.remove("--escalate")
    model_override = None
    if "--model" in args:
        i = args.index("--model")
        model_override = args[i + 1]
        del args[i : i + 2]

    suite = json.loads(CASES_PATH.read_text())
    n = suite.get("runs_per_case", 3)
    wanted = set(args) or None
    cases = [c for c in suite["cases"] if not wanted or c["id"] in wanted]

    spec = housing_bonus_spec()
    if model_override:
        spec = replace(spec, model=model_override)
    client = anthropic.Anthropic()

    results = [run_case(c, spec, client, n, escalate) for c in cases]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    report_path = REPORTS_DIR / f"ai_bonus_{stamp}.md"
    report = render_report(
        results, suite["suite"], spec.model, n, escalate, spec.escalation_model
    )
    report_path.write_text(report)

    passed = sum(r["passed"] for r in results)
    mode = "escalation policy" if escalate else f"single model {spec.model}"
    print(f"\n[{mode}] {passed}/{len(results)} cases passed. Report: {report_path}")
    for r in results:
        if not r["passed"]:
            adjs = [run["adjustment"] for run in r["runs"]]
            esc = sum(1 for run in r["runs"] if run["escalated"])
            print(
                f"  ✗ {r['id']} ({r['flavor']}): adjustments {adjs}"
                f"  [{esc}/{len(r['runs'])} escalated]"
            )


if __name__ == "__main__":
    main(sys.argv[1:])

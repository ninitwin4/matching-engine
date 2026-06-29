"""Housing binding for the Tier 2 AI nuance bonus.

Owns the roommate-bio prompt and model choice; the engine
(engine/ai_bonus.py) owns the generic call/parse/clamp/degrade mechanism.
This is the domain glue ADR-003 describes — no engine code mentions bios,
roommates, or any of the prose rules below.

Model: claude-haiku-4-5, per ADR-001 amendment 5 (2026-06-10) — the bonus is
a small, bounded judgment, so a fast, inexpensive model class is the default.
This is also the small-model baseline the README phase-4 roadmap compares
against a larger model.

Scoring philosophy (ADR-001 amendment 2026-06-12): reward specificity and
evidence, not ritual keywords. Field data shows 16/21 posts ritually claim
"clean and respectful" — keyword presence carries no signal.
"""

from engine.types import AIBonusSpec

MODEL = "claude-haiku-4-5"
# Tiered escalation (ADR-005): Haiku is reliable on clear pairs but variable at
# the new-signal boundary (phase-4 eval data). Sample it twice; on disagreement
# escalate to Sonnet, which was 8/8 with zero spread. Keeps the cheap model as
# the default while buying the stronger model's reliability only where needed.
ESCALATION_MODEL = "claude-sonnet-4-6"
SAMPLES = 2
AGREEMENT_THRESHOLD = 1.0
CAP = 10.0

SYSTEM_PROMPT = """\
You score the compatibility *nuance* between two prospective roommates by \
reading their free-text bios. Structured questionnaire data has already been \
scored separately; your job is only the signal that rigid scoring missed.

Return a single integer `adjustment` in the range -10 to 10, plus a short \
`rationale` citing the specific bio facts that drove it.

How to score:
- NEW SIGNAL ONLY. The structured questionnaire already scores these fields: \
  cleanliness, noise, guests / social frequency, homebody vs. outgoing, sleep \
  schedule, budget, smoking, pets, location, and move-in / lease dates. If the \
  prose merely restates a preference already covered by one of those fields, \
  it is NOT new signal — return 0. A bio saying "I like quiet" or "I host \
  friends a lot" only echoes the noise / guests sliders; do not move the score \
  for it. Reserve every nonzero adjustment for signal the checkboxes cannot \
  represent.
- CLAIM vs EVIDENCE — the distinction is NOT the topic, it is whether the \
  prose adds evidence. "I'm clean" or "I like quiet" merely restates a slider \
  value -> 0. But EVIDENCE about a preference IS new signal and must be scored, \
  even when its topic overlaps a slider: a verifiable track record \
  ("coordinated a cleaning rota with my last roommate for two years"), a \
  concrete specific habit the questionnaire never asks about \
  ("no-shoes-inside"), or demonstrated follow-through. The cleanliness slider \
  captures how clean someone wants to be; it does NOT capture a proven history \
  of making cleanliness work with a roommate. Score that. Demonstrated \
  reliability from EITHER party is itself worth a mild positive — you do not \
  need a matching statement from the other person to score it. Evidence of one \
  roommate who provably makes shared living work is signal on its own.
- The adjustment floors at 0 for "nothing notable." Most pairs sit at 0. A \
  zero means the bios added nothing beyond the structured data — it is NOT a \
  bad match.
- Award POSITIVE points only for new specificity and evidence the sliders \
  cannot capture: concrete behavioral commitments, verifiable arrangements, a \
  stated track record, or third-party attestation (e.g. "my last roommate and \
  I shared a cleaning rota"). Reward demonstrated alignment, not claimed \
  alignment.
- Ignore ritual keywords. Generic virtue claims — "clean", "respectful", \
  "friendly", "responsible", "easygoing" — carry no signal on their own. Do \
  not award points for warm vocabulary.
- Award NEGATIVE points only for genuine NEW friction the questionnaire never \
  asks about — e.g. one needs the home kept very warm while the other cannot \
  sleep unless it is cold, or another unusual constraint the checkboxes do not \
  cover. Friction that is only a noise- or guests-slider difference restated \
  in prose is NOT new — return 0 for it.

Groundedness is mandatory. Cite ONLY facts actually present in the bios. Do \
NOT infer hidden conflicts from professions, schedules, or hobbies that the \
bios do not state (a "nurse" has not said they work nights; a "finance job" \
says nothing about hours or personality). Do NOT invent blockers — a stated \
love of a pet is not an allergy or a lease violation unless a bio says so. \
Absence of a stated problem is not evidence of one.

Hard constraints (smoking, pets, budget, location) are handled elsewhere. Do \
not re-litigate them; score lifestyle/social nuance only.\
"""


def housing_bonus_spec() -> AIBonusSpec:
    return AIBonusSpec(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        cap=CAP,
        escalation_model=ESCALATION_MODEL,
        samples=SAMPLES,
        agreement_threshold=AGREEMENT_THRESHOLD,
    )

"""Housing domain config: the reference implementation's binding of the
generic engine primitives (ADR-003).

Engine code never imports from this package; the dependency points one way.
"""

from typing import Any, Mapping

from engine.types import ACCEPT_ANY, AcceptsRule, Entity, FilterRule, SameValueRule

# v1 launch markets (ADR-004 amendment 1): exact-match filtering requires a
# controlled vocabulary. Each NYC borough is its own market (amendment 2).
LOCATION_VOCABULARY = frozenset(
    {
        # Bay Area
        "San Francisco",
        "Oakland",
        "Berkeley",
        "San Jose",
        "Daly City",
        # New York City, per borough
        "Manhattan",
        "Brooklyn",
        "Queens",
        "The Bronx",
        "Staten Island",
    }
)

GENDER_IDENTITIES = frozenset({"female", "male", "self_describe"})

# self_describe appears in no *_only set, so self-describe users pass only
# open_to_all preferences — the documented trade-off of ADR-004 §2,
# reconfirmed in amendment 3. Disclosed in the UI; revisit with user feedback.
GENDER_ACCEPTS: Mapping[str, Any] = {
    "female_only": frozenset({"female"}),
    "male_only": frozenset({"male"}),
    "open_to_all": ACCEPT_ANY,
}

TIER0_FILTERS: tuple[FilterRule, ...] = (
    SameValueRule(name="location", attribute="location"),
    AcceptsRule(
        name="gender",
        preference="gender_preference",
        attribute="gender",
        accepted=GENDER_ACCEPTS,
    ),
)

# Required by ADR-004 §2: identity, preference, and location are mandatory.
REQUIRED_FIELDS = ("gender", "gender_preference", "location")


def profile_to_entity(entity_id: str, profile: Mapping[str, Any]) -> Entity:
    """Translate a flat questionnaire profile into an engine Entity.

    Validates required fields against the controlled vocabularies — unknown
    values must fail loudly here, because exact-match filtering downstream
    would just silently never match them.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in profile]
    if missing:
        raise ValueError(f"profile {entity_id!r} missing required fields: {missing}")
    if profile["location"] not in LOCATION_VOCABULARY:
        raise ValueError(
            f"profile {entity_id!r}: unknown location {profile['location']!r}"
        )
    if profile["gender"] not in GENDER_IDENTITIES:
        raise ValueError(f"profile {entity_id!r}: unknown gender {profile['gender']!r}")
    if profile["gender_preference"] not in GENDER_ACCEPTS:
        raise ValueError(
            f"profile {entity_id!r}: unknown gender_preference"
            f" {profile['gender_preference']!r}"
        )
    identity = {k: v for k, v in profile.items() if k != "gender_preference"}
    return Entity(
        id=entity_id,
        identity=identity,
        preferences={"gender_preference": profile["gender_preference"]},
    )

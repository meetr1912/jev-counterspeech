"""Synthetic, legally distributable examples for the jev-counterspeech demo.

Everything returned by this module was written for this repository. No
third-party dataset text is copied, and no real slur or real named person or
group ever appears. Placeholders such as ``[SLUR]`` and invented community names
keep the data safe to ship under CC0-1.0 while still exercising every triage
category.

The module is pure stdlib and deterministic: ``random.Random(seed)`` fully
determines the output for a given ``(seed, n)``. There is no network access and
no file read. See ``data/README.md`` for provenance and responsible-use notes.
"""

from __future__ import annotations

import random

from jev_counterspeech.schemas import CATEGORIES, HANDLING, Example

#: Provenance tag placed on every shipped example.
SYNTHETIC_SOURCE = "synthetic"

#: Extension point for a user-supplied local sample. We deliberately ship an
#: empty tuple: third-party toxic text is not redistributed by this repository.
PUBLIC_SAMPLES: tuple[Example, ...] = ()

_CATEGORY_SET = frozenset(CATEGORIES)
_HANDLING_SET = frozenset(HANDLING)

#: Invented communities used for the ``{group}`` slot. None of these is real.
_GROUPS: tuple[str, ...] = (
    "the Northland community",
    "the Riverfolk",
    "Group A",
    "the coastal diaspora",
    "the Vale settlers",
    "the Marrowborn",
    "the Eastreach collective",
    "the Sunfield migrants",
)

#: Neutral sentence openers that add surface variety without changing meaning.
_OPENERS: tuple[str, ...] = (
    "",
    "Honestly. ",
    "For real. ",
    "I mean it. ",
    "Here's the thing. ",
    "No joke. ",
    "I'll say it. ",
    "Look. ",
)

#: Roughly 12-15 low-confidence examples are carved out of the plan below.
_N_AMBIGUOUS = 13

#: Relative profile frequencies. Repeated a hundred times so counts stay stable
#: for the default ``n`` regardless of the shuffle.
_PROFILE_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("none", 22),
    ("stereotype", 18),
    ("othering", 18),
    ("slur", 14),
    ("dehumanization", 12),
    ("threat", 8),
    ("individual", 8),
)

#: Per-profile generative configuration. ``hateful`` / ``targets_group`` /
#: ``severity`` / ``slur`` pin the defining label for a profile when the text
#: would otherwise be incoherent; ``None`` means "derive from the probability".
_PROFILES: dict[str, dict] = {
    "none": {
        "category": "none",
        "p_hateful": (0.02, 0.20),
        "p_targets_group": (0.02, 0.10),
        "p_has_slur": (0.01, 0.05),
        "p_severity": (1.00, 1.25),
        "handling": ("ignore", "ignore", "ignore", "human_review"),
        "hateful": 0,
        "targets_group": 0,
        "severity": 1,
        "slur": 0,
    },
    "stereotype": {
        "category": "stereotype",
        "p_hateful": (0.70, 0.92),
        "p_targets_group": (0.62, 0.88),
        "p_has_slur": (0.02, 0.12),
        "p_severity": (2.70, 3.30),
        "handling": ("reply", "reply", "reply", "reply", "human_review"),
        "hateful": None,
        "targets_group": None,
        "severity": None,
        "slur": None,
    },
    "othering": {
        "category": "othering",
        "p_hateful": (0.72, 0.93),
        "p_targets_group": (0.65, 0.90),
        "p_has_slur": (0.02, 0.12),
        "p_severity": (2.70, 3.30),
        "handling": ("reply", "reply", "reply", "reply", "human_review"),
        "hateful": None,
        "targets_group": None,
        "severity": None,
        "slur": None,
    },
    "slur": {
        "category": "slur",
        "p_hateful": (0.82, 0.96),
        "p_targets_group": (0.70, 0.92),
        "p_has_slur": (0.85, 0.97),
        "p_severity": (3.60, 4.40),
        "handling": ("reply", "reply", "reply", "reply", "human_review"),
        "hateful": None,
        "targets_group": None,
        "severity": None,
        "slur": 1,
    },
    "dehumanization": {
        "category": "dehumanization",
        "p_hateful": (0.85, 0.97),
        "p_targets_group": (0.70, 0.93),
        "p_has_slur": (0.82, 0.96),
        "p_severity": (3.60, 4.40),
        "handling": ("report", "report", "report", "human_review", "human_review"),
        "hateful": None,
        "targets_group": None,
        "severity": None,
        "slur": 1,
    },
    "threat": {
        "category": "threat",
        "p_hateful": (0.93, 0.99),
        "p_targets_group": (0.45, 0.85),
        "p_has_slur": (0.10, 0.35),
        "p_severity": (4.70, 5.00),
        "handling": ("report", "report", "report", "human_review", "human_review"),
        "hateful": 1,
        "targets_group": None,
        "severity": 5,
        "slur": None,
    },
    "individual": {
        "category": "othering",
        "p_hateful": (0.64, 0.86),
        "p_targets_group": (0.03, 0.18),
        "p_has_slur": (0.10, 0.35),
        "p_severity": (3.00, 4.00),
        "handling": ("report", "report", "human_review", "human_review"),
        "hateful": 1,
        "targets_group": 0,
        "severity": None,
        "slur": None,
    },
}

_TEMPLATES: dict[str, tuple[str, ...]] = {
    "none": (
        "I disagree with the policy, but I understand why people feel strongly about it.",
        "Thanks for sharing this; I had not considered the {group}'s perspective before.",
        "The weekend forecast looks great for the festival downtown.",
        "Has anyone tried the new bakery on Fifth? The bread is excellent.",
        "We can disagree about the budget without making it personal.",
        "Reading the comments, I appreciate how civil most people have been.",
        "I would like to learn more about how {group} celebrates the harvest season.",
        "The council meeting ran long, but the minutes are online now.",
        "My neighbor brought over soup when I was sick; small kindnesses matter.",
        "Let us focus on the actual numbers rather than speculation.",
    ),
    "stereotype": (
        "People from {group} are always so loud and pushy; it is just how they are.",
        "You cannot expect {group} to follow the same rules as everyone else.",
        "{group} never contribute anything useful to the neighborhood.",
        "Everyone knows {group} are bad with money and always looking for handouts.",
        "I have met a few from {group} and they all had the same attitude.",
        "{group} think they are entitled to special treatment everywhere they go.",
        "It is not hateful to notice that {group} cause most of the problems here.",
        "The trouble with {group} is that they refuse to integrate.",
        "{group} would rather complain than do an honest day's work.",
    ),
    "othering": (
        "{group} do not belong here; they should go back to where they came from.",
        "This was our town before {group} started moving in and changing everything.",
        "{group} will never really be one of us, no matter how long they stay.",
        "Why do we keep letting {group} in? They do not share our values.",
        "{group} are a foreign element that does not fit our way of life.",
        "Our culture is being erased because of {group}.",
        "I do not want my kids growing up around {group}; they are not like us.",
        "{group} should stay in their own neighborhoods and leave ours alone.",
        "The presence of {group} makes me feel like a stranger in my own country.",
    ),
    "slur": (
        "Another [SLUR] from {group} moved in down the street. Great.",
        "I am so tired of these [SLUR]; {group} ruin everything they touch.",
        "That [SLUR] from {group} was shouting at the store again.",
        "Of course a [SLUR] like that would say something so stupid.",
        "Keep the [SLUR] out of our schools.",
        "The [SLUR] in {group} need to learn their place.",
        "Every single [SLUR] I have dealt with has been the same.",
        "Look at these [SLUR] and tell me we should let them stay.",
        "Nobody wants a [SLUR] for a neighbor.",
    ),
    "dehumanization": (
        "{group} are vermin, and these [SLUR] should be kept away from decent people.",
        "{group} breed like animals; we will be overrun by these [SLUR] if we do nothing.",
        "These [SLUR] are nothing but rats crawling out of the sewers.",
        "{group} are a disease, and every [SLUR] among them spreads it.",
        "You cannot reason with [SLUR] cockroaches; that is simply what they are.",
        "{group} are a plague of [SLUR] spreading through our towns.",
        "They are not fully human, just [SLUR] swarming in from the border.",
        "{group} are parasites, [SLUR] draining everything good from our country.",
        "Like locusts, these [SLUR] strip everything and leave nothing behind.",
    ),
    "threat": (
        "Someone needs to burn down the {group} community center and send a message.",
        "We should take up arms and drive {group} out by force.",
        "I hope {group} get exactly what is coming to them, and soon.",
        "If {group} keep this up, people are going to start hurting them.",
        "It is time to fight back; violence is the only language {group} understand.",
        "Let us find out where {group} live and pay them a visit they will not forget.",
        "Every member of {group} should be run out of town, by any means necessary.",
        "The {group} shelters need to be torched, every single one.",
        "I am ready to do whatever it takes to make {group} leave, even if it turns bloody.",
    ),
    "individual": (
        "This person is a disgusting [SLUR] and should be driven off the platform.",
        "That blogger is subhuman and deserves to lose everything.",
        "I cannot wait until that activist gets what is coming to her.",
        "Everyone should pile on that journalist until she deletes her account.",
        "This person is vermin and does not deserve to live in our town.",
        "We should make that speaker's life a living hell.",
        "That reporter is a [SLUR] and should be run out of the country.",
        "Somebody ought to shut that organizer up for good.",
        "Look at this freak; people like that should not be near children.",
    ),
}

#: Benign-but-edgy and plausibly-hateful texts used for low-confidence cases.
_AMBIGUOUS: dict[str, tuple[str, ...]] = {
    "none": (
        "I am not saying anything bad about {group}, but I would not want my daughter dating one.",
        "People can say what they want about {group}; I just prefer to keep my distance.",
        "I have nothing against {group}; I just think they should stay in their own areas.",
        "No offense to {group}, but I would rather not have them as neighbors.",
    ),
    "stereotype": (
        "I do not hate {group}, but you have to admit the stereotypes exist for a reason.",
        "Not all of {group} are like that, but most of the ones I have met are.",
        "I am not prejudiced, I just think {group} could try harder to fit in.",
    ),
    "othering": (
        "I am not against immigration; I just think {group} should wait their turn.",
        "It is not about race, but {group} really do not fit in around here.",
        "I have no problem with {group}, as long as they remember where they are.",
    ),
    "slur": (
        "I would not use the word [SLUR], but that is basically what {group} are.",
        "Call me old-fashioned, but [SLUR] is not the worst word for {group}.",
    ),
    "dehumanization": (
        "I am not saying {group} are animals, but some of them really act like it.",
        "Maybe vermin is too strong a word, but you see my point about {group}.",
    ),
    "threat": (
        "I am not calling for violence, but someone should make {group} think twice.",
        "I would never hurt anyone, but if {group} keep pushing I cannot promise others will not.",
    ),
    "individual": (
        "I do not wish this person harm, but someone should teach them a lesson.",
        "I am not threatening anyone, but that blogger needs to watch their back.",
    ),
}


def _u(rng: random.Random, lo: float, hi: float) -> float:
    """One continuous probability, rounded so smoke tests print cleanly."""

    return round(rng.uniform(lo, hi), 4)


def _severity(rng: random.Random, mean: float) -> int:
    """Sample a 1..5 severity with ``mean`` as its continuous center."""

    return max(1, min(5, int(round(rng.gauss(mean, 0.3)))))


def _plan(rng: random.Random, n: int) -> list[str]:
    """A shuffled profile schedule that covers every profile for ``n >= 7``."""

    base = [name for name, _ in _PROFILE_WEIGHTS]
    weighted = [name for name, weight in _PROFILE_WEIGHTS for _ in range(weight)]
    plan = (base + weighted * (n // len(weighted) + 1))[:n]
    rng.shuffle(plan)
    return plan


def _text_schedule(rng: random.Random, profile_name: str, count: int) -> list[tuple[str, str]]:
    """A shuffled template/opener queue that avoids repeats within a cycle."""

    if count <= 0:
        return []

    templates = list(_TEMPLATES[profile_name])
    openers = list(_OPENERS)
    schedule: list[tuple[str, str]] = []
    while len(schedule) < count:
        combos = [(template, opener) for template in templates for opener in openers]
        rng.shuffle(combos)
        schedule.extend(combos)
    return schedule[:count]


def _ambiguous_indices(plan: list[str]) -> set[int]:
    """Spread the low-confidence carve-out across profiles, deterministically."""

    by_profile: dict[str, list[int]] = {}
    for index, name in enumerate(plan):
        by_profile.setdefault(name, []).append(index)

    chosen: list[int] = []
    round_no = 0
    while len(chosen) < _N_AMBIGUOUS:
        added = False
        for name, _ in _PROFILE_WEIGHTS:
            indices = by_profile.get(name, [])
            if round_no < len(indices):
                chosen.append(indices[round_no])
                added = True
                if len(chosen) >= _N_AMBIGUOUS:
                    break
        if not added:
            break
        round_no += 1
    return set(chosen)


def _build(rng: random.Random, index: int, profile_name: str, text: str, ambiguous: bool) -> Example:
    profile = _PROFILES[profile_name]
    category = str(profile["category"])

    if ambiguous:
        p_hateful = _u(rng, 0.42, 0.62)
        p_targets_group = _u(rng, 0.28, 0.68)
        p_has_slur = _u(rng, 0.60, 0.90) if "[SLUR]" in text else _u(rng, 0.04, 0.22)
        p_severity = _u(rng, *profile["p_severity"])
    else:
        p_hateful = _u(rng, *profile["p_hateful"])
        p_targets_group = _u(rng, *profile["p_targets_group"])
        p_has_slur = _u(rng, *profile["p_has_slur"])
        p_severity = _u(rng, *profile["p_severity"])

    label_hateful = int(rng.random() < p_hateful)
    label_targets_group = int(rng.random() < p_targets_group)
    label_has_slur = int(rng.random() < p_has_slur)
    label_severity = _severity(rng, p_severity)

    forced_hateful = profile["hateful"]
    forced_targets = profile["targets_group"]
    forced_severity = profile["severity"]
    forced_slur = profile["slur"]

    if forced_hateful is not None and not ambiguous:
        label_hateful = int(forced_hateful)
    if forced_targets is not None:
        label_targets_group = int(forced_targets)
    if forced_severity is not None:
        label_severity = int(forced_severity)
    if forced_slur is not None and not ambiguous:
        label_has_slur = int(forced_slur)

    if "[SLUR]" in text:
        label_has_slur = 1
    if category == "none":
        label_hateful = 0
        label_targets_group = 0
        label_has_slur = 0
        label_severity = 1
    if profile_name == "threat":
        label_severity = 5
    if profile_name == "individual":
        label_targets_group = 0
        label_severity = min(4, max(3, label_severity))

    handling = rng.choice(profile["handling"])
    assert category in _CATEGORY_SET
    assert handling in _HANDLING_SET

    if ambiguous:
        notes = "individual-targeted; ambiguous" if profile_name == "individual" else "ambiguous"
    elif profile_name == "individual":
        notes = "individual-targeted"
    else:
        notes = ""

    return Example(
        id=f"synthetic-{index:04d}",
        text=text,
        label_hateful=label_hateful,
        label_targets_protected_group=label_targets_group,
        label_has_slur=label_has_slur,
        label_severity=label_severity,
        label_category=category,
        label_handling=handling,
        p_hateful=p_hateful,
        p_targets_group=p_targets_group,
        p_has_slur=p_has_slur,
        p_severity=p_severity,
        source=SYNTHETIC_SOURCE,
        license="CC0-1.0",
        notes=notes,
    )


def synthetic_examples(seed: int = 7, n: int = 120) -> list[Example]:
    """Generate ``n`` deterministic synthetic examples for ``seed``.

    Output is fully determined by ``(seed, n)``; no network or file access.
    """

    if n <= 0:
        return []

    rng = random.Random(seed)
    plan = _plan(rng, n)
    ambiguous = _ambiguous_indices(plan)

    remaining: dict[str, int] = {}
    for name, _ in _PROFILE_WEIGHTS:
        total = plan.count(name)
        carved = sum(1 for index, key in enumerate(plan) if key == name and index in ambiguous)
        remaining[name] = total - carved
    queues = {name: _text_schedule(rng, name, remaining[name]) for name, _ in _PROFILE_WEIGHTS}

    examples: list[Example] = []
    for index, name in enumerate(plan):
        is_ambiguous = index in ambiguous
        if is_ambiguous:
            template = rng.choice(_AMBIGUOUS[name])
            text = template.format(group=rng.choice(_GROUPS))
        else:
            template, opener = queues[name].pop()
            text = opener + template.format(group=rng.choice(_GROUPS))
        examples.append(_build(rng, index, name, text, is_ambiguous))
    return examples


def load_examples(seed: int = 7, limit: int | None = None, include_public: bool = False) -> list[Example]:
    """Synthetic examples, optionally extended with a local ``PUBLIC_SAMPLES``.

    ``PUBLIC_SAMPLES`` ships empty; a user may point it at their own locally
    licensed sample. ``limit`` truncates the combined list when not ``None``.
    """

    examples = list(synthetic_examples(seed))
    if include_public:
        examples.extend(PUBLIC_SAMPLES)
    if limit is not None:
        examples = examples[:limit]
    return examples


def example_by_id(seed: int = 7) -> dict[str, Example]:
    """Lookup table keyed by ``Example.id`` for the default corpus."""

    return {example.id: example for example in load_examples(seed=seed, include_public=True)}

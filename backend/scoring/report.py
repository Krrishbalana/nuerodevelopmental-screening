"""Clinical report: findings, likelihood, recommendations, and what wasn't assessed.

Every sentence is either a measured fact from this session or a number from a cited study
(see evidence.py). Recommendations come from published guidelines (AAP), not from our own
thresholds.

Outcome (guideline rules, in priority order):
  refer          an autism-linked finding met a published cut-off at an age the study covered
                 -> developmental evaluation + early intervention (AAP 2020)
  hearing_check  child turned to name at most once -> hearing evaluation (AAP 2007)
  incomplete     nothing flagged, but a module couldn't be measured
  no_signs       everything measured, nothing flagged
"""

from typing import Any, Literal

from . import config as C
from .evidence import ASD_PRIOR, TIER_A, TIER_B, cite
from .gaze import CalibrationResult
from .metrics import MetricResult
from .quality import WindowQuality

Outcome = Literal["refer", "hearing_check", "incomplete", "no_signs"]

QUALITY_TIPS = {
    "too_dark": "Use a brighter room, with light falling on your child's face (not behind them).",
    "too_far": "Seat your child closer to the screen, about an arm's length away.",
    "too_close": "Seat your child a little further back, about an arm's length away.",
    "face_often_missing": "Keep your child seated and facing the screen, on your lap if that helps.",
    "calibration": "Make sure your child can see the screen clearly and is following the moving toy.",
}

# When a module couldn't be scored but recording conditions were fine, say what to do differently.
MODULE_TIPS = {
    "social_preference": "Keep your child seated and watching the screen during the videos.",
    "name_response": (
        "When \"Call the name now\" appears, call your child's name once, clearly, from behind them, "
        "while your child is facing the screen."
    ),
}

NOT_ASSESSED = [
    {
        "area": "Hearing",
        "detail": "Not tested directly in this session.",
        "how": "Audiologist: hearing test suited to age (e.g. OAE, visual reinforcement audiometry).",
    },
    {
        "area": "Speech and language",
        "detail": "Not measured by the camera session.",
        "how": "Omli speech assessment (3+ years) or a speech-language pathologist.",
    },
    {
        "area": "Pointing, pretend play, repetitive behaviours, sensory reactions",
        "detail": "Need everyday observation, not a 3-minute session.",
        "how": "Parent questionnaire (M-CHAT-R/F at 16-30 months) and clinician observation.",
    },
    {
        "area": "Motor skills",
        "detail": "Not measured.",
        "how": "Paediatrician / physiotherapist developmental check.",
    },
    {
        "area": "Attention (ADHD)",
        "detail": "Not measured. Clinical ADHD guidelines start at age 4.",
        "how": "From age 4: paediatrician with parent and teacher rating scales.",
    },
]

OUTCOME_TEXT: dict[Outcome, tuple[str, str]] = {
    "refer": (
        "Signs linked to autism were seen: a developmental evaluation is recommended",
        "Your child's responses matched patterns that research has linked to autism. The next step is "
        "an evaluation by a developmental specialist. You don't need to wait for it to start support: "
        "early intervention can begin now.",
    ),
    "hearing_check": (
        "Your child rarely turned to their name: a hearing test is recommended",
        "Not turning to their name can happen when a child doesn't hear clearly. A hearing test is the "
        "first step.",
    ),
    "incomplete": (
        "We couldn't complete the check",
        "Some parts couldn't be measured clearly. Please try again using the tips below.",
    ),
    "no_signs": (
        "No autism-linked signs were seen in this session",
        "In the parts we measured, your child's responses didn't match the patterns research links to "
        "autism. This session didn't look at everything (see below).",
    ),
}

NOTE = "This is a screening result. A developmental specialist confirms any diagnosis."


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _in_age(key: str, age: float) -> bool:
    lo, hi = TIER_A[key].age_months
    return lo <= age <= hi


# --- findings -----------------------------------------------------------------------


def _social_finding(m: MetricResult, age: float) -> dict[str, Any]:
    e = TIER_A["social_preference"]
    d = m.details
    social = m.value or 0.0
    swapped = (
        f" The children's videos were the main focus in {d['social_majority_trials']} of "
        f"{d['valid_trials']} videos as they switched sides."
    )
    measured = (
        f"Looked at the children's videos {_pct(social)} of the time and at the moving shapes "
        f"{_pct(1 - social)}, across {d['valid_trials']} usable videos." + swapped
    )
    if m.status == "flagged":
        meaning = (
            "This is above the cut-off of 69% looking at moving shapes. About 8 in 10 toddlers above it "
            "are autistic. Most autistic toddlers (83%) stay below it, so it picks out a subgroup."
        )
    else:
        meaning = (
            "This is below the cut-off of 69% looking at moving shapes. Most autistic toddlers (83%) are "
            "also below it, so on its own this result doesn't rule autism out."
        )
    return {
        "key": m.key,
        "title": "Interest in people vs. objects",
        "status": m.status,
        "confidence": m.confidence,
        "measured": measured,
        "meaning": meaning,
        "tier": "A",
        "used_in_likelihood": _in_age(m.key, age),
        "age_note": None if _in_age(m.key, age) else _age_note(m.key, age),
        "sources": cite(e.sources),
    }


def _name_finding(m: MetricResult, age: float) -> dict[str, Any]:
    e = TIER_A["name_response"]
    d = m.details
    measured = f"Turned when their name was called on {d['turned']} of {d['valid_trials']} usable calls."
    if m.status == "flagged":
        meaning = (
            "Turning on at most one call is seen in about 9 in 10 autistic toddlers and about 4 in 10 "
            "other toddlers. Not turning to a name is also a sign of hearing difficulty."
        )
    else:
        meaning = (
            "Turning on more than one call is seen in about 6 in 10 non-autistic toddlers and fewer than "
            "1 in 10 autistic toddlers."
        )
    return {
        "key": m.key,
        "title": "Response to name",
        "status": m.status,
        "confidence": m.confidence,
        "measured": measured,
        "meaning": meaning,
        "tier": "A",
        "used_in_likelihood": _in_age(m.key, age),
        "age_note": None if _in_age(m.key, age) else _age_note(m.key, age),
        "sources": cite(e.sources),
    }


def _age_note(key: str, age: float) -> str:
    lo, hi = TIER_A[key].age_months
    return (
        f"This cut-off was set for children aged {lo}-{hi} months. At {age:.0f} months the "
        "result is reported but not used in the likelihood estimate."
    )


def _tier_b_findings(metrics: dict[str, MetricResult]) -> list[dict[str, Any]]:
    out = []
    name = metrics.get("name_response")
    if name and name.status != "insufficient" and name.details.get("median_latency_ms") is not None:
        out.append({
            "key": "name_latency",
            "status": None,  # Tier B: reported, never flagged
            "confidence": None,
            "title": "Speed of turning to name",
            "measured": f"Median time to turn: {name.details['median_latency_ms'] / 1000:.1f} s.",
            "meaning": TIER_B["name_latency"].finding,
            "tier": "B",
            "sources": cite(TIER_B["name_latency"].sources),
        })
    social = metrics.get("social_preference")
    if social and social.status != "insufficient" and social.details.get("attention_fraction") is not None:
        out.append({
            "key": "attention",
            "status": None,  # Tier B: reported, never flagged
            "confidence": None,
            "title": "Attention to the videos",
            "measured": f"Watched the screen {_pct(social.details['attention_fraction'])} of the video time.",
            "meaning": TIER_B["attention"].finding,
            "tier": "B",
            "sources": cite(TIER_B["attention"].sources),
        })
    return out


FINDERS = {"social_preference": _social_finding, "name_response": _name_finding}
TITLES = {"social_preference": "Interest in people vs. objects", "name_response": "Response to name"}


def findings(metrics: list[MetricResult], age: float) -> list[dict[str, Any]]:
    rows = []
    for m in metrics:
        if m.status == "insufficient":
            rows.append({
                "key": m.key, "title": TITLES[m.key], "status": "insufficient", "confidence": None,
                "measured": f"Could not be measured: {m.reasons[0] if m.reasons else 'not enough data'}.",
                "meaning": None, "tier": "A", "used_in_likelihood": False, "age_note": None, "sources": [],
            })
        else:
            rows.append(FINDERS[m.key](m, age))
    return rows + _tier_b_findings({m.key: m for m in metrics})


# --- profile (the radial "spectrum" chart) ---------------------------------------------
#
# Autism isn't one scale, so the report draws a profile: one slice per area. A slice's size is a
# direct measurement from this session, as "share of the session showing the pattern research links
# to autism" (0..1). Slices carry the published cut-off where one exists (Tier A); Tier B slices show
# the published group averages instead; areas we don't measure are drawn empty as "not assessed".

NOT_MEASURED_AREAS = [
    ("joint_attention", "Following a point or gaze", "Planned camera module (gaze following)."),
    ("communication", "Speech & language", "Omli speech assessment or a speech-language pathologist."),
    ("repetitive", "Repetitive movements & routines", "Clinician observation, parent questionnaire."),
    ("sensory", "Sensory reactions", "Clinician observation, parent questionnaire."),
    ("play", "Play & imitation", "Planned camera module (imitation game, 3+ years)."),
    ("motor", "Motor skills", "Paediatrician / physiotherapist check."),
]


def profile(metrics: list[MetricResult]) -> list[dict[str, Any]]:
    by_key = {m.key: m for m in metrics}
    areas: list[dict[str, Any]] = []

    def area(key: str, label: str, tier: str | None, value: float | None, status: str, measured: str, **extra: Any) -> None:
        areas.append({"key": key, "label": label, "tier": tier, "value": value, "status": status,
                      "measured": measured, "cutoff": None, "markers": [], "sources": [], **extra})

    m = by_key.get("social_preference")
    if m and m.status != "insufficient" and m.value is not None:
        area("social_attention", "Interest in people", "A", round(1 - m.value, 3), m.status,
             f"Looked at moving shapes instead of people {_pct(1 - m.value)} of the time",
             cutoff=round(1 - C.SPLIT_SOCIAL_FLAG_BELOW, 2), cutoff_label="GeoPref cut-off 69%",
             sources=cite(TIER_A["social_preference"].sources))
    else:
        area("social_attention", "Interest in people", "A", None, "insufficient", "Could not be measured")

    m = by_key.get("name_response")
    if m and m.status != "insufficient":
        valid, turned = m.details["valid_trials"], m.details["turned"]
        area("name_response", "Response to name", "A", round((valid - turned) / valid, 3), m.status,
             f"Didn't turn on {valid - turned} of {valid} calls",
             # flagged when turned <= NAME_FLAG_MAX_TURNS, i.e. missed >= valid - that
             cutoff=round((valid - C.NAME_FLAG_MAX_TURNS) / valid, 3), cutoff_label="Campbell 2019: turned at most once",
             sources=cite(TIER_A["name_response"].sources))
        latency = m.details.get("median_latency_ms")
        if latency is not None:
            window = C.NAME_RESPONSE_END_MS
            area("turn_speed", "Speed of turning", "B", round(min(1.0, latency / window), 3), "reported",
                 f"Took {latency / 1000:.1f} s of the {window / 1000:.0f} s response window",
                 markers=[{"value": 1060 / window, "label": "others 1.1 s"}, {"value": 2020 / window, "label": "autistic 2.0 s"}],
                 sources=cite(TIER_B["name_latency"].sources))
    else:
        area("name_response", "Response to name", "A", None, "insufficient", "Could not be measured")

    if m := by_key.get("social_preference"):
        attention = m.details.get("attention_fraction") if m.status != "insufficient" else None
        if attention is not None:
            area("attention", "Attention to the videos", "B", round(1 - attention, 3), "reported",
                 f"Looked away from the screen {_pct(1 - attention)} of the video time",
                 sources=cite(TIER_B["attention"].sources))

    for key, label, how in NOT_MEASURED_AREAS:
        area(key, label, None, None, "not_assessed", f"Not assessed in this session. {how}")
    return areas


# --- likelihood ---------------------------------------------------------------------


def asd_likelihood(metrics: list[MetricResult], age: float) -> dict[str, Any]:
    prior = ASD_PRIOR.probability
    odds = prior / (1 - prior)
    used, excluded = [], []
    for m in metrics:
        e = TIER_A.get(m.key)
        if e is None:
            continue
        if m.status == "insufficient":
            excluded.append({"key": m.key, "reason": "not measured in this session"})
            continue
        if not _in_age(m.key, age):
            excluded.append({"key": m.key, "reason": _age_note(m.key, age)})
            continue
        lr = e.lr_flagged if m.status == "flagged" else e.lr_not_flagged
        odds *= lr
        used.append({
            "key": m.key, "result": m.status, "lr": lr, "derivation": e.derivation, "sources": cite(e.sources),
        })

    base = {
        "condition": "ASD",
        "prior": prior,
        "prior_note": ASD_PRIOR.note,
        "prior_sources": cite((ASD_PRIOR.source,)),
        "evidence_used": used,
        "evidence_excluded": excluded,
        "assumption": "Findings are combined as independent given autism status (naive Bayes). "
        "Correlated findings would make the estimate somewhat too extreme in either direction.",
    }
    if not used:
        return {**base, "available": False, "posterior": None}
    posterior = odds / (1 + odds)
    return {
        **base,
        "available": True,
        "posterior": round(posterior, 4),
        "per_100": round(posterior * 100, 1),
        "times_population": round(posterior / prior, 1),
    }


# --- recommendations ------------------------------------------------------------------


def outcome_for(metrics: list[MetricResult], age: float) -> Outcome:
    by_key = {m.key: m for m in metrics}
    if any(m.status == "flagged" and m.key in TIER_A and _in_age(m.key, age) for m in metrics):
        return "refer"
    if by_key.get("name_response") and by_key["name_response"].status == "flagged":
        return "hearing_check"
    if any(m.status == "insufficient" for m in metrics):
        return "incomplete"
    return "no_signs"


def recommendations(metrics: list[MetricResult], outcome: Outcome, age: float) -> list[dict[str, Any]]:
    recs = []
    name_flagged = any(m.key == "name_response" and m.status == "flagged" for m in metrics)
    if outcome == "refer":
        recs.append({
            "action": "Developmental evaluation by a developmental paediatrician or child psychologist.",
            "why": "A screening finding linked to autism met a published cut-off. Guidelines recommend "
            "referral for diagnostic evaluation and starting early intervention without waiting for it.",
            "sources": cite(("aap2020",)),
        })
    if name_flagged:
        recs.append({
            "action": "Hearing test by an audiologist.",
            "why": "The child turned to their name on at most one call. Guidelines recommend a hearing evaluation for children "
            "who don't attend to language.",
            "sources": cite(("aap2007",)),
        })
    if outcome == "no_signs" and age <= 30:
        recs.append({
            "action": "Routine autism screening at the 18- and 24-month check-ups.",
            "why": "Recommended for all children, whatever this session showed.",
            "sources": cite(("aap2020",)),
        })
    if outcome == "incomplete":
        recs.append({
            "action": "Repeat the session.",
            "why": "Not every part could be measured, so the result is incomplete.",
            "sources": [],
        })
    return recs


# --- the two views --------------------------------------------------------------------


def _tips(metrics: list[MetricResult], calibration: CalibrationResult, quality: dict[str, WindowQuality]) -> list[str]:
    if not any(m.status == "insufficient" for m in metrics):
        return []
    flags = {flag for q in quality.values() for flag in q.flags}
    tips = [tip for flag, tip in QUALITY_TIPS.items() if flag in flags]
    if not calibration.passed:
        tips.append(QUALITY_TIPS["calibration"])
    return tips or [MODULE_TIPS[m.key] for m in metrics if m.status == "insufficient"]


def _parent_likelihood(lk: dict[str, Any]) -> str | None:
    if not lk["available"]:
        return None
    n = lk["per_100"]
    if n < 1:
        share = "fewer than 1 in 100"
    elif n < 10:
        share = f"about {n:.1f} in 100"
    else:
        share = f"about {n:.0f} in 100"
    return (
        f"Among children with the same results, {share} are autistic, compared with about 1 in 100 "
        "children in India overall. This estimate uses published studies; it will get more precise as "
        "we validate it with Indian children."
    )


def build(
    metrics: list[MetricResult],
    calibration: CalibrationResult,
    quality: dict[str, WindowQuality],
    age: float,
) -> dict[str, Any]:
    outcome = outcome_for(metrics, age)
    rows = findings(metrics, age)
    likelihood = asd_likelihood(metrics, age)
    recs = recommendations(metrics, outcome, age)
    title, message = OUTCOME_TEXT[outcome]

    wheel = profile(metrics)
    parent = {
        "outcome": outcome,
        "title": title,
        "message": message,
        "findings": [
            {"title": f["title"], "status": f.get("status"), "text": f["measured"]}
            for f in rows
            if f["tier"] == "A"
        ],
        "profile": wheel,
        "likelihood": _parent_likelihood(likelihood),
        "next_steps": [r["action"] for r in recs],
        "not_checked": [n["area"] for n in NOT_ASSESSED],
        "tips": _tips(metrics, calibration, quality),
        "note": NOTE,
    }
    clinician = {
        "outcome": outcome,
        "outcome_rule": "refer if any autism-linked finding met its published cut-off within the studied "
        "age range (AAP 2020); else hearing_check if no response to name (AAP 2007); else incomplete if "
        "any module unmeasured; else no_signs",
        "findings": rows,
        "profile": wheel,
        "likelihood": likelihood,
        "recommendations": recs,
        "not_assessed": NOT_ASSESSED,
    }
    return {"parent": parent, "clinician": clinician}

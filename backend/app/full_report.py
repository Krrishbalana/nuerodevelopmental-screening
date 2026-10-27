"""The adaptive report: one engine (Saathi) result from the camera findings and the parent's answers.

What a child's report contains depends on the child: the development wheel shows only the areas that
were looked at, and only conditions the engine shows (band possible or above) get a section, most
likely first. A child with a speech delay gets a language-first report; autism appears only if the
evidence points there. Everything is recomputed from the stored measurements and answers on each
request, so a new dataset version updates old reports too.
"""

from typing import Any

from saathi.domain.enums import AnswerKey, Born, Sex
from saathi.domain.session_state import ChildProfile, SessionState
from saathi.engine.formulas.odds import sigmoid
from saathi.engine.formulas.priors import prior_logit
from saathi.engine.posterior import compute_posterior
from saathi.engine.results import build_results

from . import observations as camera_obs
from . import questionnaire as qn
from .storage import linked_questionnaire

# Saathi's 15 domains grouped into the slices a parent can read. CRS (course, regression, medical
# history) isn't a slice: its concerns appear as red flags.
WHEEL = [
    ("social", "Social & conversation", ["SOC", "PRAG"]),
    ("gestures", "Gestures & babble", ["PRE"]),
    ("understanding", "Understanding words", ["REC"]),
    ("talking", "Talking", ["EXP"]),
    ("speech", "Speech clarity & fluency", ["SPE"]),
    ("play", "Play & imitation", ["PLAY"]),
    ("repetitive", "Repetitive behaviour", ["RRB"]),
    ("sensory", "Sensory reactions", ["SEN"]),
    ("motor", "Movement", ["MOT"]),
    ("behaviour", "Behaviour & attention", ["REG", "ATT"]),
    ("daily", "Eating, sleep & self-care", ["FS"]),
    ("literacy", "Early reading skills", ["LIT"]),
]

# Autism wheel: the autism-linked items grouped by the DSM-5-TR criterion they describe. Social
# communication needs all of A1-A3; restricted/repetitive behaviour needs at least 2 of B1-B4. Items
# linked to autism only as associated or differential signs (language delay, motor, attention,
# regression) aren't on this wheel; they still count in the engine.
AUTISM_WHEEL = [
    ("A1", "Back-and-forth & sharing", [
        "soc_response_name", "soc_shared_enjoyment", "soc_showing", "soc_empathy", "play_social_games",
        "pre_vocal_turns", "exp_request_only", "prag_back_forth",
    ], ["obs_name_response"]),
    ("A2", "Eye contact, gestures & expressions", [
        "soc_eye_contact", "soc_social_smile", "soc_follow_point", "soc_point_interest", "soc_hand_as_tool",
        "pre_gestures", "pre_no_compensation",
    ], []),
    ("A3", "Interest in people & pretend play", [
        "soc_interest_children", "soc_peer_play", "play_pretend", "play_imitation", "prag_context",
    ], ["obs_social_preference"]),
    ("B1", "Repetitive movements, object use & speech", [
        "rrb_motor", "rrb_objects", "exp_echolalia", "exp_pronoun", "exp_idiosyncratic",
    ], []),
    ("B2", "Sameness & routines", ["rrb_sameness", "play_repetitive", "att_sticky"], []),
    ("B3", "Intense or narrow interests", ["rrb_interests"], []),
    ("B4", "Sensory reactions", [
        "sen_sound_over", "sen_tactile", "sen_under", "sen_seeking", "sen_vestibular", "rrb_visual", "fs_selective",
    ], []),
]

ANSWER_LABEL = {"y": "Yes", "py": "Probably", "dk": "Don't know", "pn": "Probably not", "n": "No"}
ANSWER_WEIGHT = {"y": 1.0, "py": 0.5, "pn": 0.0, "n": 0.0}

ACTION_MESSAGE = {
    "urgent": "One or more of your answers describes a sign that needs a prompt check by a doctor. Please book that "
    "first; the rest of this report can wait.",
    "refer": "The signs below are worth a full developmental assessment. An assessment is how you find out for sure, "
    "and support works best when it starts early.",
    "watch": "A few things are worth keeping an eye on. Most children like this do well; check again at the time "
    "below, sooner if you notice new concerns.",
    "on_track": "Nothing stood out from what we looked at. Keep enjoying talking and playing together, and check "
    "again at your child's next milestone.",
}

# Plain-language line per condition for parents (the dataset's notes are written for clinicians).
ABOUT = {
    "ASD": "Differences in social communication and repetitive or very focused behaviour.",
    "LT": "Using fewer words than most children of the same age. Many late talkers catch up; some need support.",
    "DLD": "Ongoing difficulty learning and using language, beyond the toddler years.",
    "SSD": "Trouble saying speech sounds clearly for their age.",
    "CAS": "Difficulty planning the mouth movements for speech.",
    "STUT": "Repeating or getting stuck on sounds and words while speaking.",
    "SPCD": "Difficulty with the social use of language, like conversation and taking turns.",
    "HL": "Not hearing clearly, which affects understanding and talking.",
    "GDD": "Being behind in several areas of development at the same time.",
    "MOTD": "Being behind in movement skills like sitting, walking or using hands.",
    "DCD": "Clumsiness and difficulty with coordinated movement.",
    "ADHD": "Ongoing difficulty with attention, activity level and impulse control.",
    "SPD": "Unusually strong or weak reactions to sounds, touch, light or movement.",
    "ANX": "Worry or fear that gets in the way of everyday life.",
    "SM": "Talking normally in some places but not speaking in others.",
    "TIC": "Sudden repeated movements or sounds the child can't easily stop.",
    "RETT": "A rare genetic condition with loss of hand use and skills. Needs urgent specialist review.",
    "FXS": "A genetic condition linked to developmental delay and autism-like signs.",
    "LKS": "A rare condition where a child loses language they had. Needs urgent specialist review.",
    "DYS": "Early signs that learning to read may be harder.",
    "HYP": "Reading words very early but with weaker understanding of language.",
}


def _camera_only_state(report: dict[str, Any]) -> SessionState:
    """No questionnaire yet: the engine runs on the camera findings alone."""
    age = int(report["clinician"]["age_months"])
    return SessionState(
        session_id="camera-only",
        profile=ChildProfile(age_years=age // 12, age_months=age % 12, sex=Sex.NA, born=Born.TERM),
        observations=tuple(camera_obs.from_report(report, qn.confidence_weights())),
    )


def _evidence_text(item_id: str, answers: dict[str, str], observed: dict[str, str], b) -> tuple[str, str]:
    """Readable line and source for an evidence item (a question id or obs:<id>)."""
    if item_id.startswith("obs:"):
        definition = b.index.observations_by_id.get(item_id[4:])
        label = definition.label if definition else item_id
        seen = observed.get(item_id[4:]) == "flagged"
        return f"{label} ({'seen' if seen else 'not seen'})", "camera"
    q = b.index.questions_by_id.get(item_id)
    if q is None:
        return item_id, "parent"
    return f"{q.clinical_name} (you answered: {ANSWER_LABEL.get(answers.get(item_id, ''), '?')})", "parent"


def _slice(key: str, label: str, codes: list[str], state: SessionState, b, has_question, has_obs) -> dict[str, Any]:
    """Share of the checked signs in one slice that were reported ('Yes' 1, 'Probably' 0.5) or seen on camera."""
    scored = 0
    concern = 0.0
    items: list[str] = []
    for ans in state.answers:
        q = b.index.questions_by_id[ans.question_id]
        if not has_question(q) or ans.key is AnswerKey.DONT_KNOW:
            continue
        scored += 1
        concern += ANSWER_WEIGHT[ans.key.value]
        if ans.key in (AnswerKey.YES, AnswerKey.PROBABLY):
            items.append(q.clinical_name)
    for obs in state.observations:
        definition = b.index.observations_by_id.get(obs.id)
        if definition is None or not has_obs(definition):
            continue
        scored += 1
        if obs.outcome == "flagged":
            concern += 1.0
            items.append(f"Camera: {definition.label}")
    value = concern / scored if scored else None
    return {
        "key": key,
        "label": label,
        "domains": codes,
        "value": None if value is None else round(value, 3),
        "checked": scored,
        "signs": items,
        "status": "not_assessed" if value is None else "concern" if value >= 0.5 else "some" if value > 0 else "clear",
    }


def _wheel(state: SessionState, b) -> list[dict[str, Any]]:
    return [
        _slice(key, label, domains, state, b, lambda q, d=domains: q.domain in d, lambda o, d=domains: o.domain in d)
        for key, label, domains in WHEEL
    ]


def _autism_wheel(state: SessionState, b) -> dict[str, Any]:
    slices = [
        _slice(code, label, [code], state, b, lambda q, ids=set(qids): q.id in ids, lambda o, ids=set(oids): o.id in ids)
        for code, label, qids, oids in AUTISM_WHEEL
    ]

    def count(prefix: str) -> dict[str, int]:
        group = [s for s in slices if s["key"].startswith(prefix)]
        return {
            "with_signs": sum(s["status"] == "concern" for s in group),
            "checked": sum(s["status"] != "not_assessed" for s in group),
            "total": len(group),
        }

    return {
        "slices": slices,
        "social": {**count("A"), "dsm_needs": 3},
        "repetitive": {**count("B"), "dsm_needs": 2},
    }


def build(session_id: str, camera_report: dict[str, Any]) -> dict[str, Any]:
    b = qn.bundle()
    qid = linked_questionnaire(session_id)
    state = qn.state_of(qid) if qid else _camera_only_state(camera_report)
    posterior = compute_posterior(state, b.dataset, b.index, b.rules_config)
    results = build_results(state, b.dataset, b.index, b.rules_config)
    answers = {a.question_id: a.key.value for a in state.answers}
    observed = {o.id: o.outcome for o in state.observations}

    sections = []
    for shown in results.conditions:
        c = b.index.conditions_by_key[shown.key]
        support = [e for e in shown.evidence if e.delta > 0][:5]
        against = [e for e in shown.evidence if e.delta < 0][:3]

        def lines(items):
            out = []
            for e in items:
                text, source = _evidence_text(e.question_id, answers, observed, b)
                out.append({"text": text, "source": source, "delta": round(e.delta, 3), "id": e.question_id})
            return out

        sections.append({
            "key": c.key,
            "name": c.name,
            "short_name": c.short_name,
            "group": c.group,
            "band": shown.band.value,
            "probability": round(shown.probability, 4),
            "eligibility": shown.eligibility.value,
            "about": ABOUT.get(c.key, c.name),
            "clinical_note": c.note,
            "dx_age": c.dx_age_text,
            "refer": c.refer,
            "for": lines(support),
            "against": lines(against),
        })

    red_flags = [
        b.index.questions_by_id[a.question_id].clinical_name
        for a in state.answers
        if b.index.questions_by_id[a.question_id].is_urgent and a.key in (AnswerKey.YES, AnswerKey.PROBABLY)
    ]
    all_conditions = sorted(
        (
            {
                "key": c.key,
                "name": c.short_name,
                "probability": round(posterior.probabilities[c.key], 4),
                "prior": round(sigmoid(prior_logit(c, state.profile, b.dataset)), 4),
                "eligibility": posterior.eligibility[c.key].value,
            }
            for c in b.dataset.conditions
        ),
        key=lambda x: -x["probability"],
    )
    return {
        "has_questionnaire": qid is not None,
        "questionnaire_id": qid,
        "questions_asked": len(state.answers),
        "age_months": state.profile.chronological_age_m,
        "action": results.action.value,
        "title": results.title,
        "message": ACTION_MESSAGE[results.action.value],
        "steps": list(results.steps),
        "hearing_test": results.hearing_test,
        "recheck": results.recheck,
        "red_flags": red_flags,
        "wheel": _wheel(state, b),
        "autism_wheel": _autism_wheel(state, b),
        "conditions": sections,
        "all_conditions": all_conditions,
        "observations": qn.observation_view(state),
        "answers": [
            {
                "question_id": a.question_id,
                "question": b.index.questions_by_id[a.question_id].question,
                "clinical_name": b.index.questions_by_id[a.question_id].clinical_name,
                "domain": b.index.questions_by_id[a.question_id].domain,
                "answer": ANSWER_LABEL[a.key.value],
            }
            for a in state.answers
        ],
        "provenance": {
            "dataset_version": b.dataset.meta.version,
            "model_version": b.dataset.meta.model_version,
            "dataset_hash": b.version_hash[:16],
            "note": "Question likelihood ratios are estimates from the evidence base and are being re-estimated from "
            "screening outcomes. Camera likelihood ratios are published where marked.",
        },
    }

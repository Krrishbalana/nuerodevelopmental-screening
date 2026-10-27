"""Saathi parent questionnaire, served by this backend (replaces Saathi's Mongo-backed service).

Same orchestration as Saathi's session_service: the session stores only the profile, answers and
acknowledgements, and the engine recomputes everything from them on every call. Sessions are JSON
files next to the screening sessions: data/questionnaires/<id>.json.
"""

import dataclasses
import json
import math
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from saathi.dataset_service import DatasetBundle, load_bundle, selectable_family_factors
from saathi.domain.enums import AnswerKey, StepType
from saathi.domain.session_state import ChildProfile, Observation, SessionState
from saathi.engine.posterior import compute_posterior
from saathi.engine.branching import PATTERN_ACK_KEY, Step, next_step
from saathi.engine.results import build_results
from saathi.errors import NoCurrentQuestionError, WrongQuestionError

from .storage import DATA_DIR, link_questionnaire

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "saathi" / "adaptive-screening-dataset.json"
OBSERVATIONS_PATH = DATASET_PATH.parent / "observations.json"
QUESTIONNAIRE_DIR = DATA_DIR.parent / "questionnaires"


class QuestionnaireNotFound(KeyError):
    pass


@lru_cache(maxsize=1)
def bundle() -> DatasetBundle:
    return load_bundle(DATASET_PATH, observations_path=OBSERVATIONS_PATH)


def _path(session_id: str) -> Path:
    try:
        uuid.UUID(session_id)
    except ValueError as exc:
        raise QuestionnaireNotFound(session_id) from exc
    return QUESTIONNAIRE_DIR / f"{session_id}.json"


def _load(session_id: str) -> tuple[SessionState, dict[str, Any]]:
    path = _path(session_id)
    if not path.exists():
        raise QuestionnaireNotFound(session_id)
    record = json.loads(path.read_text())
    return SessionState.model_validate(record["state"]), record


def _save(state: SessionState, record: dict[str, Any]) -> None:
    QUESTIONNAIRE_DIR.mkdir(parents=True, exist_ok=True)
    record["state"] = state.model_dump(mode="json")
    _path(state.session_id).write_text(json.dumps(record))


def _next(state: SessionState) -> Step:
    b = bundle()
    return next_step(state, b.dataset, b.index, b.rules_config)


def step_view(step: Step) -> dict[str, Any]:
    """What the UI needs for one step (Saathi's StepResponse without the debugging candidates)."""
    q = step.question
    return {
        "type": step.type.value,
        "number": step.number,
        "question": None if q is None else {
            "id": q.id,
            "domain": q.domain,
            "type": q.type.value,
            "question": q.question,
            "typical": q.typical,
            "is_urgent": q.is_urgent,
        },
        "reason_kind": step.reason_kind,
        "reason_conditions": list(step.reason_conditions),
        "urgent_question_ids": list(step.urgent_question_ids),
        "pattern_condition": step.pattern_condition,
        "pattern_probability": step.pattern_probability,
    }


def meta() -> dict[str, Any]:
    b = bundle()
    return {
        "dataset_version": b.dataset.meta.version,
        "dataset_hash": b.version_hash,
        "family_factors": [{"factor": pm.factor, "label": pm.label} for pm in selectable_family_factors(b.dataset)],
        "domains": [{"key": d.key, "name": d.name} for d in b.dataset.domains],
        "conditions": [{"key": c.key, "name": c.name, "short_name": c.short_name} for c in b.dataset.conditions],
    }


def observation_view(state: SessionState) -> list[dict[str, Any]]:
    """Each observation with the evidence it actually applied (condition, LR, source) at this age."""
    b = bundle()
    posterior = compute_posterior(state, b.dataset, b.index, b.rules_config)
    return [
        {
            "id": e.observation.id,
            "label": b.index.observations_by_id[e.observation.id].label if e.observation.id in b.index.observations_by_id else None,
            "outcome": e.observation.outcome,
            "confidence": e.observation.confidence,
            "terms": [
                {"condition": t.condition, "lr": round(math.exp(t.ln_lr), 4), "delta": round(t.delta, 4),
                 "source": t.source, "ref": t.ref}
                for t in e.terms
            ],
        }
        for e in posterior.observation_log
    ]


def confidence_weights() -> dict[str, float]:
    return bundle().dataset.observation_config.confidence_weights


def create(
    profile: ChildProfile, observations: list[Observation] | None = None, screening_session_id: str | None = None
) -> dict[str, Any]:
    b = bundle()
    valid = {pm.factor for pm in selectable_family_factors(b.dataset)}
    unknown = set(profile.family_factors) - valid
    if unknown:
        raise ValueError(f"Unknown family factors: {sorted(unknown)}")
    for obs in observations or []:
        definition = b.index.observations_by_id.get(obs.id)
        if definition is None or definition.outcome(obs.outcome) is None:
            raise ValueError(f"Unknown observation {obs.id}/{obs.outcome}")
    state = SessionState(session_id=str(uuid.uuid4()), profile=profile, observations=tuple(observations or ()))
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_hash": b.version_hash,
        "screening_session_id": screening_session_id,
        "results": None,
    }
    _save(state, record)
    return {
        "session_id": state.session_id,
        "chronological_age_m": profile.chronological_age_m,
        "observations": observation_view(state),
        "step": step_view(_next(state)),
    }


def current(session_id: str) -> dict[str, Any]:
    state, _ = _load(session_id)
    return step_view(_next(state))


def answer(session_id: str, question_id: str, key: AnswerKey) -> dict[str, Any]:
    state, record = _load(session_id)
    step = _next(state)
    if step.type is not StepType.QUESTION or step.question is None:
        raise NoCurrentQuestionError(session_id)
    if step.question.id != question_id:
        raise WrongQuestionError(expected=step.question.id, got=question_id)
    state = state.with_answer(question_id, key)
    _save(state, record)
    return step_view(_next(state))


def undo(session_id: str) -> dict[str, Any]:
    state, record = _load(session_id)
    state = state.without_last_answer()
    _save(state, record)
    return step_view(_next(state))


def ack_urgent(session_id: str) -> dict[str, Any]:
    state, record = _load(session_id)
    for question_id in _next(state).urgent_question_ids:
        state = state.with_ack(question_id)
    _save(state, record)
    return step_view(_next(state))


def ack_pattern(session_id: str) -> dict[str, Any]:
    state, record = _load(session_id)
    state = state.with_ack(PATTERN_ACK_KEY)
    _save(state, record)
    return step_view(_next(state))


def complete(session_id: str) -> dict[str, Any]:
    state, record = _load(session_id)
    b = bundle()
    results = json.loads(json.dumps(dataclasses.asdict(build_results(state, b.dataset, b.index, b.rules_config))))
    record["results"] = results
    _save(state, record)
    if record.get("screening_session_id"):
        link_questionnaire(record["screening_session_id"], session_id)
    return results


def get_results(session_id: str) -> dict[str, Any] | None:
    _, record = _load(session_id)
    return record["results"]


def state_of(session_id: str) -> SessionState:
    return _load(session_id)[0]

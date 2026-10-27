import json
import math
from pathlib import Path

import pytest

from saathi.dataset_service import load_bundle, validate_observations
from saathi.domain.dataset import Dataset
from saathi.domain.enums import AnswerKey, Born, Sex, StepType
from saathi.domain.session_state import ChildProfile, Observation, SessionState
from saathi.engine.branching import PATTERN_ACK_KEY, next_step
from saathi.engine.posterior import compute_posterior
from saathi.engine.results import build_results
from saathi.engine.rules import hearing_first_triggered
from tests.saathi.conftest import DATASET_PATH

OBS_PATH = DATASET_PATH.parent / "observations.json"


@pytest.fixture(scope="module")
def b():
    return load_bundle(DATASET_PATH, observations_path=OBS_PATH)


def state(age_m: int, observations=(), answers=()):
    s = SessionState(
        session_id="t",
        profile=ChildProfile(age_years=age_m // 12, age_months=age_m % 12, sex=Sex.NA, born=Born.TERM),
        observations=tuple(observations),
    )
    for qid, key in answers:
        s = s.with_answer(qid, AnswerKey(key))
    return s


def post(b, s):
    return compute_posterior(s, b.dataset, b.index, b.rules_config)


def test_no_observations_changes_nothing(b):
    plain = load_bundle(DATASET_PATH)
    s = state(26, answers=[("soc_eye_contact", "y")])
    assert post(b, s).logits == post(plain, s).logits


def test_observation_adds_ln_lr_times_confidence(b):
    base = post(b, state(26)).logits["ASD"]
    p = post(b, state(26, [Observation(id="obs_social_preference", outcome="flagged", confidence=0.7)]))
    assert p.logits["ASD"] - base == pytest.approx(math.log(8.5) * 0.7)
    term = p.observation_log[0].terms[0]
    assert (term.source, term.ref) == ("published", "wen2022")


def test_outside_studied_ages_uses_the_extrapolated_entry(b):
    p = post(b, state(60, [Observation(id="obs_social_preference", outcome="flagged")]))
    assert p.observation_log[0].terms[0].source == "extrapolated"
    name = post(b, state(40, [Observation(id="obs_name_response", outcome="flagged")]))
    sources = {t.condition: t.source for t in name.observation_log[0].terms}
    assert sources == {"ASD": "extrapolated", "HL": "estimated", "GDD": "estimated"}


def test_agreeing_parent_answer_is_damped_not_double_counted(b):
    obs = [Observation(id="obs_name_response", outcome="flagged")]
    alone = post(b, state(26, answers=[("soc_response_name", "y")])).evidence_log[0].terms
    damped = post(b, state(26, obs, answers=[("soc_response_name", "y")])).evidence_log[0].terms
    for a, d in zip(alone, damped):
        if a.condition in ("ASD", "HL", "GDD"):
            assert d.delta == pytest.approx(a.delta * 0.5)
        else:
            assert d.delta == pytest.approx(a.delta)


def test_disagreeing_parent_answer_counts_in_full(b):
    obs = [Observation(id="obs_name_response", outcome="flagged")]  # camera: didn't turn
    alone = post(b, state(26, answers=[("soc_response_name", "n")])).evidence_log[0].terms
    mixed = post(b, state(26, obs, answers=[("soc_response_name", "n")])).evidence_log[0].terms
    assert [t.delta for t in mixed] == pytest.approx([t.delta for t in alone])


def test_camera_name_flag_puts_hearing_first(b):
    s = state(26, [Observation(id="obs_name_response", outcome="flagged")])
    assert hearing_first_triggered(s, b.dataset, b.index, b.rules_config)
    assert not hearing_first_triggered(state(26), b.dataset, b.index, b.rules_config)


def test_results_list_observations_as_evidence(b):
    s = state(26, [Observation(id="obs_social_preference", outcome="flagged")], answers=[("soc_eye_contact", "y")])
    results = build_results(s, b.dataset, b.index, b.rules_config)
    asd = next(c for c in results.conditions if c.key == "ASD")
    assert "obs:obs_social_preference" in [e.question_id for e in asd.evidence]


def _questions_asked(b, s, n: int) -> list[str]:
    asked = []
    while len(asked) < n:
        step = next_step(s, b.dataset, b.index, b.rules_config)
        if step.type is StepType.URGENT:
            for qid in step.urgent_question_ids:
                s = s.with_ack(qid)
            continue
        if step.type is StepType.PATTERN:
            s = s.with_ack(PATTERN_ACK_KEY)
            continue
        if step.type is StepType.DONE:
            break
        asked.append(step.question.id)
        s = s.with_answer(step.question.id, AnswerKey.DONT_KNOW)
    return asked


def test_questions_adapt_to_camera_findings(b):
    # Same child, same (uninformative) answers: autism-linked camera findings steer the engine
    # towards social-communication questions earlier.
    flagged = [Observation(id="obs_social_preference", outcome="flagged"), Observation(id="obs_name_response", outcome="flagged")]
    plain = _questions_asked(b, state(26), 12)
    steered = _questions_asked(b, state(26, flagged), 12)
    assert plain != steered
    soc = {q.id for q in b.dataset.questions if q.domain == "SOC"}
    assert sum(q in soc for q in steered) > sum(q in soc for q in plain)


def test_invalid_observation_file_is_rejected(b):
    raw = json.loads(OBS_PATH.read_text())
    raw.pop("_note")
    raw["observations"][0]["outcomes"][0]["lrs"][0]["condition"] = "NOPE"
    raw["observations"][1]["construct_question_ids"] = ["no_such_question"]
    dataset = Dataset.model_validate({**json.loads(DATASET_PATH.read_text()), "observation_config": raw})
    problems = validate_observations(dataset)
    assert any("NOPE" in p for p in problems) and any("no_such_question" in p for p in problems)

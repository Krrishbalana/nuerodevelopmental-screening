import dataclasses
import hashlib
import json

from saathi.domain.enums import AnswerKey, Born, Sex
from saathi.domain.session_state import ChildProfile, SessionState
from saathi.engine.trace import TraceStep, build_trace
from saathi.dataset_service import DatasetBundle


def _hash_steps(trace_steps: tuple[TraceStep, ...]) -> str:
    payload = json.dumps([dataclasses.asdict(s) for s in trace_steps], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def test_trace_is_deterministic_across_rebuilds(bundle: DatasetBundle) -> None:
    profile = ChildProfile(age_years=2, age_months=2, sex=Sex.NA, born=Born.TERM, family_factors=())
    state = SessionState(session_id="s", profile=profile)
    state = state.with_answer("crs_regression", AnswerKey.NO)
    state = state.with_answer("rec_sounds", AnswerKey.NO)
    state = state.with_answer("crs_hearing_risk", AnswerKey.NO)
    state = state.with_answer("soc_point_interest", AnswerKey.YES)

    trace_a = build_trace(state, bundle.dataset, bundle.index, bundle.rules_config)
    trace_b = build_trace(state, bundle.dataset, bundle.index, bundle.rules_config)

    assert _hash_steps(trace_a.steps) == _hash_steps(trace_b.steps)
    assert trace_a.final_step == trace_b.final_step
    assert len(trace_a.steps) == 4

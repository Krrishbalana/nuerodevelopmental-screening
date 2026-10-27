from pathlib import Path

import pytest

from saathi.domain.dataset import (
    AgeLens,
    AgeLensExponents,
    AgeWindow,
    Condition,
    EligibilityConfig,
    Link,
    PrematurityCorrection,
    Question,
)
from saathi.domain.enums import AnswerKey, QuestionType, Situation, StepType
from saathi.domain.session_state import SessionState
from saathi.engine.branching import PATTERN_ACK_KEY, next_step
from saathi.dataset_service import DatasetBundle, load_bundle

DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "saathi" / "adaptive-screening-dataset.json"


@pytest.fixture(scope="session")
def bundle() -> DatasetBundle:
    return load_bundle(DATASET_PATH)


def make_age_lens(
    *,
    applies_below_m: int = 24,
    lt32_subtract_m: int = 3,
    thirty_two_36_subtract_m: int = 1,
    hidden_margin_m: int = 12,
    present_overrides: dict[Situation, float] | None = None,
    absent_overrides: dict[Situation, float] | None = None,
) -> AgeLens:
    present = {
        Situation.WELL_PAST_RED_FLAG: 1.5,
        Situation.PAST_RED_FLAG: 1.0,
        Situation.PAST_TYPICAL: 0.7,
        Situation.BEFORE_TYPICAL: 0.5,
        Situation.UNUSUAL_BEHAVIOR: 1.0,
        Situation.HISTORY_ITEM: 1.0,
    }
    absent = {
        Situation.PAST_RED_FLAG: 1.0,
        Situation.PAST_TYPICAL: 0.5,
        Situation.BEFORE_TYPICAL: 0.2,
        Situation.UNUSUAL_BEHAVIOR: 0.3,
        Situation.HISTORY_ITEM: 0.15,
    }
    present.update(present_overrides or {})
    absent.update(absent_overrides or {})
    return AgeLens(
        prematurity_correction=PrematurityCorrection(
            applies_below_m=applies_below_m,
            lt32_subtract_m=lt32_subtract_m,
            thirty_two_36_subtract_m=thirty_two_36_subtract_m,
        ),
        eligibility=EligibilityConfig(rule="test", hidden_margin_m=hidden_margin_m),
        askable="test",
        situation_rule=["test"],
        exponents=AgeLensExponents(present=present, absent=absent),
    )


def make_condition(
    key: str = "TEST",
    *,
    dx_min_m: int = 0,
    dx_max_m: int | None = None,
    base_rate: float = 0.05,
    transitions_to: str | None = None,
) -> Condition:
    return Condition(
        key=key,
        name=key,
        short_name=key,
        group="Test",
        is_ndd_dsm=False,
        dx_min_m=dx_min_m,
        dx_max_m=dx_max_m,
        dx_age_text="",
        base_rate=base_rate,
        base_rate_note="",
        transitions_to=transitions_to,
        note="",
        refer="See a specialist.",
    )


def make_question(
    id: str = "q1",  # noqa: A002
    *,
    domain: str = "SOC",
    type: QuestionType = QuestionType.MILESTONE,  # noqa: A002
    window_start_m: int = 0,
    window_end_m: int = 72,
    typical_m: int | None = 12,
    red_flag_m: int | None = 18,
    is_urgent: bool = False,
    ask_first: int | None = None,
    is_background: bool = False,
    links: list[Link] | None = None,
    follow_ups_if_yes: list[str] | None = None,
) -> Question:
    return Question(
        id=id,
        domain=domain,
        type=type,
        question="Does your child do the thing?",
        clinical_name="",
        typical="",
        age=AgeWindow(
            window_start_m=window_start_m,
            window_end_m=window_end_m,
            typical_m=typical_m,
            red_flag_m=red_flag_m,
        ),
        is_urgent=is_urgent,
        ask_first=ask_first,
        is_background=is_background,
        background_note=None,
        links=links or [],
        follow_ups_if_yes=follow_ups_if_yes or [],
        differentiation="",
        sources=[],
        data_fix=None,
    )


def make_link(
    condition: str, strength: int = 3, lr_present: float = 6.0, lr_absent: float = 0.5
) -> Link:
    return Link(
        condition=condition,
        strength=strength,
        lr_present=lr_present,
        lr_absent=lr_absent,
        lr_source="test",
    )


def run_adaptive_loop(
    bundle: DatasetBundle, state: SessionState, yes_to: set[str], max_iterations: int = 200
) -> tuple[SessionState, list[StepType]]:
    """Drives the real adaptive loop (next_step -> answer -> ...) to completion,
    answering Yes to every id in `yes_to` and No to everything else, auto-acking
    urgent/pattern interstitials. Used by regression and branching tests alike,
    since question order is adaptive and can't be scripted in advance."""
    types: list[StepType] = []
    for _ in range(max_iterations):
        step = next_step(state, bundle.dataset, bundle.index, bundle.rules_config)
        types.append(step.type)
        if step.type is StepType.DONE:
            return state, types
        if step.type is StepType.URGENT:
            state = state.with_ack(step.urgent_question_ids[0])
            continue
        if step.type is StepType.PATTERN:
            state = state.with_ack(PATTERN_ACK_KEY)
            continue
        assert step.question is not None
        key = AnswerKey.YES if step.question.id in yes_to else AnswerKey.NO
        state = state.with_answer(step.question.id, key)
    raise AssertionError("adaptive loop did not terminate")

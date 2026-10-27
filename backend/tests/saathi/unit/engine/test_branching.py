from saathi.domain.enums import AnswerKey, Born, Sex, StepType
from saathi.domain.session_state import ChildProfile, SessionState
from saathi.engine.branching import next_step
from saathi.dataset_service import DatasetBundle
from tests.saathi.conftest import run_adaptive_loop


def _profile(age_years: int = 2, age_months: int = 2) -> ChildProfile:
    return ChildProfile(
        age_years=age_years, age_months=age_months, sex=Sex.NA, born=Born.TERM, family_factors=()
    )


def test_first_question_is_always_crs_regression(bundle: DatasetBundle) -> None:
    state = SessionState(session_id="s", profile=_profile())
    step = next_step(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert step.type is StepType.QUESTION
    assert step.question is not None
    assert step.question.id == "crs_regression"
    assert step.reason_kind == "first"


def test_always_first_questions_precede_adaptive_scoring(bundle: DatasetBundle) -> None:
    # at 9 months all three always-first questions are still askable (rec_sounds'
    # window closes at 12 months); at the default 26-month test age rec_sounds is
    # correctly skipped, which is exercised separately below.
    state = SessionState(session_id="s", profile=_profile(age_years=0, age_months=9))
    seen: list[str] = []
    for _ in range(3):
        step = next_step(state, bundle.dataset, bundle.index, bundle.rules_config)
        assert step.question is not None
        seen.append(step.question.id)
        state = state.with_answer(step.question.id, AnswerKey.NO)
    assert seen == list(bundle.dataset.branching.always_first)


def test_always_first_question_skipped_once_no_longer_askable(bundle: DatasetBundle) -> None:
    # rec_sounds' window closes at 12 months, so at 26 months it must be skipped
    # even though it's listed in always_first, while the order of the other two
    # always-first questions is preserved.
    state = SessionState(session_id="s", profile=_profile())
    seen: list[str] = []
    for _ in range(2):
        step = next_step(state, bundle.dataset, bundle.index, bundle.rules_config)
        assert step.question is not None
        seen.append(step.question.id)
        state = state.with_answer(step.question.id, AnswerKey.NO)
    assert seen == ["crs_regression", "crs_hearing_risk"]


def test_urgent_answer_short_circuits_next_step(bundle: DatasetBundle) -> None:
    urgent_q = next(q for q in bundle.dataset.questions if q.is_urgent)
    state = SessionState(session_id="s", profile=_profile()).with_answer(urgent_q.id, AnswerKey.YES)
    step = next_step(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert step.type is StepType.URGENT
    assert urgent_q.id in step.urgent_question_ids

    acked_state = state.with_ack(urgent_q.id)
    step_after_ack = next_step(acked_state, bundle.dataset, bundle.index, bundle.rules_config)
    assert step_after_ack.type is not StepType.URGENT


def test_max_questions_stop_rule(bundle: DatasetBundle) -> None:
    state = SessionState(session_id="s", profile=_profile())
    _, types = run_adaptive_loop(bundle, state, yes_to=set())
    question_steps = sum(1 for t in types if t is StepType.QUESTION)
    assert question_steps <= bundle.dataset.branching.stop_rules.max_questions


def test_pattern_message_fires_at_most_once(bundle: DatasetBundle) -> None:
    autism_yes_to = {
        "exp_two_word",
        "exp_vocab",
        "play_imitation",
        "play_pretend",
        "pre_gestures",
        "pre_no_compensation",
        "rrb_motor",
        "rrb_objects",
        "rrb_sameness",
        "soc_follow_point",
        "soc_hand_as_tool",
        "soc_point_interest",
        "soc_response_name",
        "soc_shared_enjoyment",
        "soc_showing",
    }
    state = SessionState(session_id="s", profile=_profile())
    _, types = run_adaptive_loop(bundle, state, yes_to=autism_yes_to)
    assert types.count(StepType.PATTERN) <= 1


def test_done_when_no_askable_questions_remain(bundle: DatasetBundle) -> None:
    # a 3-month-old has very few askable questions; after exhausting always-first +
    # whatever is askable, the engine must reach DONE well before 28 questions.
    state = SessionState(session_id="s", profile=_profile(age_years=0, age_months=3))
    _, types = run_adaptive_loop(bundle, state, yes_to=set())
    assert types[-1] is StepType.DONE
    assert (
        sum(1 for t in types if t is StepType.QUESTION)
        < bundle.dataset.branching.stop_rules.max_questions
    )

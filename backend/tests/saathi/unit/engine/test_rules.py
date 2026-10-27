from collections.abc import Callable

from saathi.domain.dataset import Question
from saathi.domain.enums import AnswerKey, Born, QuestionType, RuleId, Sex
from saathi.domain.session_state import ChildProfile, SessionState
from saathi.engine.formulas.age import assessed_age
from saathi.engine.rules import (
    apply_rules,
    hearing_first_triggered,
    late_talker_cap_applies,
    major_milestone_missed,
    pending_urgent_questions,
    spcd_cap_applies,
    urgent_answered_question_ids,
)
from saathi.dataset_service import DatasetBundle


def _state(
    answers: list[tuple[str, AnswerKey]], acks: frozenset[str] = frozenset()
) -> SessionState:
    profile = ChildProfile(age_years=2, age_months=2, sex=Sex.NA, born=Born.TERM, family_factors=())
    state = SessionState(session_id="s", profile=profile, acks=acks)
    for qid, key in answers:
        state = state.with_answer(qid, key)
    return state


def _find(bundle: DatasetBundle, predicate: Callable[[Question], bool]) -> Question:
    return next(q for q in bundle.dataset.questions if predicate(q))


def test_spcd_cap_applies_only_with_rrb_yes(bundle: DatasetBundle) -> None:
    rrb_q = _find(bundle, lambda q: q.domain == "RRB")
    non_rrb_q = _find(bundle, lambda q: q.domain != "RRB")

    fired = _state([(rrb_q.id, AnswerKey.YES)])
    not_fired = _state([(non_rrb_q.id, AnswerKey.NO)])

    assert spcd_cap_applies(fired, bundle.dataset, bundle.index, bundle.rules_config)
    assert not spcd_cap_applies(not_fired, bundle.dataset, bundle.index, bundle.rules_config)


def test_late_talker_cap_requires_two_core_asd_social_signs(bundle: DatasetBundle) -> None:
    rc = bundle.rules_config
    candidates = [
        q
        for q in bundle.dataset.questions
        if q.domain in rc.late_talker_domains
        and any(link.condition == rc.asd_condition_key and link.strength == 3 for link in q.links)
    ]
    assert len(candidates) >= 2, "fixture assumption: dataset has >=2 such questions"

    one_answer = _state([(candidates[0].id, AnswerKey.YES)])
    two_answers = _state([(candidates[0].id, AnswerKey.YES), (candidates[1].id, AnswerKey.YES)])

    assert not late_talker_cap_applies(one_answer, bundle.dataset, bundle.index, rc)
    assert late_talker_cap_applies(two_answers, bundle.dataset, bundle.index, rc)


def test_major_milestone_missed_requires_milestone_type_and_1_5x_red_flag(
    bundle: DatasetBundle,
) -> None:
    q = _find(
        bundle,
        lambda q: q.type is QuestionType.MILESTONE and q.age.red_flag_m is not None,
    )
    assert q.age.red_flag_m is not None
    exact_threshold = bundle.rules_config.milestone_red_flag_multiplier * q.age.red_flag_m
    clearly_over = int(exact_threshold) + 2
    clearly_under = q.age.red_flag_m

    missed = _state([(q.id, AnswerKey.YES)])
    assert major_milestone_missed(
        missed, clearly_over, bundle.dataset, bundle.index, bundle.rules_config
    )
    assert not major_milestone_missed(
        missed, clearly_under, bundle.dataset, bundle.index, bundle.rules_config
    )

    not_missed = _state([(q.id, AnswerKey.NO)])
    assert not major_milestone_missed(
        not_missed, clearly_over, bundle.dataset, bundle.index, bundle.rules_config
    )


def test_hearing_first_triggered_by_any_hl_linked_yes(bundle: DatasetBundle) -> None:
    hl_q = _find(bundle, lambda q: any(link.condition == "HL" for link in q.links))
    non_hl_q = _find(bundle, lambda q: not any(link.condition == "HL" for link in q.links))

    assert hearing_first_triggered(
        _state([(hl_q.id, AnswerKey.YES)]), bundle.dataset, bundle.index, bundle.rules_config
    )
    assert not hearing_first_triggered(
        _state([(non_hl_q.id, AnswerKey.NO)]), bundle.dataset, bundle.index, bundle.rules_config
    )


def test_pending_urgent_excludes_acknowledged_but_urgent_answered_does_not(
    bundle: DatasetBundle,
) -> None:
    urgent_q = _find(bundle, lambda q: q.is_urgent)

    unacked = _state([(urgent_q.id, AnswerKey.YES)])
    assert urgent_q.id in pending_urgent_questions(unacked, bundle.dataset, bundle.index)
    assert urgent_q.id in urgent_answered_question_ids(unacked, bundle.dataset, bundle.index)

    acked = _state([(urgent_q.id, AnswerKey.YES)], acks=frozenset({urgent_q.id}))
    assert urgent_q.id not in pending_urgent_questions(acked, bundle.dataset, bundle.index)
    assert urgent_q.id in urgent_answered_question_ids(acked, bundle.dataset, bundle.index)


def test_apply_rules_caps_spcd_and_lt_probabilities(bundle: DatasetBundle) -> None:
    rc = bundle.rules_config
    rrb_q = _find(bundle, lambda q: q.domain == "RRB")
    state = _state([(rrb_q.id, AnswerKey.YES)])
    a = assessed_age(state.profile.chronological_age_m, state.profile.born, bundle.dataset.age_lens)

    uncapped = {c.key: 0.9 for c in bundle.dataset.conditions}
    capped, events = apply_rules(uncapped, state, a, bundle.dataset, bundle.index, rc)

    assert capped[rc.spcd_condition_key] <= rc.spcd_cap
    fired_ids = {e.rule_id for e in events if e.fired}
    assert RuleId.SPCD_REQUIRES_NO_RRB in fired_ids

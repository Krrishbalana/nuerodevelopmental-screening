from saathi.domain.enums import AnswerKey, Born, Sex
from saathi.domain.session_state import ChildProfile, SessionState
from saathi.engine.posterior import compute_posterior
from saathi.dataset_service import DatasetBundle


def _profile() -> ChildProfile:
    return ChildProfile(age_years=2, age_months=2, sex=Sex.NA, born=Born.TERM, family_factors=())


def test_probability_cap_enforced_under_overwhelming_evidence(bundle: DatasetBundle) -> None:
    rc = bundle.rules_config
    core_asd_questions = [
        q
        for q in bundle.dataset.questions
        if any(link.condition == rc.asd_condition_key and link.strength == 3 for link in q.links)
        and q.age.window_start_m <= 26 <= q.age.window_end_m
    ][:15]
    assert len(core_asd_questions) >= 5

    state = SessionState(session_id="s", profile=_profile())
    for q in core_asd_questions:
        state = state.with_answer(q.id, AnswerKey.YES)

    posterior = compute_posterior(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert posterior.probabilities[rc.asd_condition_key] <= bundle.dataset.update.probability_cap


def test_dont_know_answer_does_not_change_logits(bundle: DatasetBundle) -> None:
    q = bundle.index.questions_by_id["soc_point_interest"]
    state = SessionState(session_id="s", profile=_profile())

    before = compute_posterior(state, bundle.dataset, bundle.index, bundle.rules_config)
    after_dk = compute_posterior(
        state.with_answer(q.id, AnswerKey.DONT_KNOW),
        bundle.dataset,
        bundle.index,
        bundle.rules_config,
    )

    assert before.logits == after_dk.logits
    assert len(after_dk.evidence_log) == 1
    assert after_dk.evidence_log[0].terms == ()


def test_evidence_log_length_matches_answer_count(bundle: DatasetBundle) -> None:
    state = SessionState(session_id="s", profile=_profile())
    state = state.with_answer("soc_point_interest", AnswerKey.YES)
    state = state.with_answer("soc_follow_point", AnswerKey.NO)
    posterior = compute_posterior(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert len(posterior.evidence_log) == 2


def test_posterior_is_pure_and_deterministic(bundle: DatasetBundle) -> None:
    state = SessionState(session_id="s", profile=_profile())
    state = state.with_answer("soc_point_interest", AnswerKey.YES)
    first = compute_posterior(state, bundle.dataset, bundle.index, bundle.rules_config)
    second = compute_posterior(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert first.probabilities == second.probabilities
    assert first.logits == second.logits

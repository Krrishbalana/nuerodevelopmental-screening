from saathi.domain.enums import AnswerKey, Eligibility
from saathi.domain.session_state import Answer
from saathi.engine.formulas.selection import (
    ScoreBreakdown,
    candidate_details,
    follow_up_sources,
    pick_chance,
    question_score,
    rank_candidates,
)
from saathi.dataset_service import DatasetBundle


def test_tie_break_by_question_id() -> None:
    breakdowns = [
        ScoreBreakdown("zzz", 5.0, {}, ()),
        ScoreBreakdown("aaa", 5.0, {}, ()),
        ScoreBreakdown("mmm", 5.0, {}, ()),
    ]
    ranked = rank_candidates(breakdowns)
    assert [b.question_id for b in ranked] == ["aaa", "mmm", "zzz"]


def test_rank_candidates_orders_by_score_descending() -> None:
    breakdowns = [
        ScoreBreakdown("low", 1.0, {}, ()),
        ScoreBreakdown("high", 9.0, {}, ()),
        ScoreBreakdown("mid", 5.0, {}, ()),
    ]
    ranked = rank_candidates(breakdowns)
    assert [b.question_id for b in ranked] == ["high", "mid", "low"]


def test_pick_chance_shares_sum_to_one_over_top_k() -> None:
    ranked = rank_candidates([ScoreBreakdown("a", 3.0, {}, ()), ScoreBreakdown("b", 1.0, {}, ())])
    shares = pick_chance(ranked, top_k=5)
    assert abs(sum(s.share for s in shares) - 1.0) < 1e-9
    assert shares[0].rank == 1
    assert shares[0].gap_to_top == 0.0
    assert shares[1].gap_to_top == 2.0


def test_pick_chance_empty_candidates_returns_empty() -> None:
    assert pick_chance([]) == []


def test_hidden_eligibility_contributes_nothing_to_score(bundle: DatasetBundle) -> None:
    question = bundle.index.questions_by_id["soc_point_interest"]
    probabilities = {link.condition: 0.5 for link in question.links}
    all_hidden = {link.condition: Eligibility.HIDDEN for link in question.links}
    breakdown = question_score(
        question, probabilities, all_hidden, 20, frozenset(), 0, frozenset(), bundle.dataset
    )
    assert breakdown.raw_score == 0.0
    assert breakdown.per_condition == {}


def test_new_domain_bonus_applies_only_within_window(bundle: DatasetBundle) -> None:
    question = bundle.index.questions_by_id["soc_point_interest"]
    probabilities = {link.condition: 0.5 for link in question.links}
    all_ok = {link.condition: Eligibility.OK for link in question.links}

    fresh_domain = question_score(
        question, probabilities, all_ok, 20, frozenset(), 0, frozenset(), bundle.dataset
    )
    assert "new_domain" in fresh_domain.bonuses_applied

    already_asked_domain = question_score(
        question,
        probabilities,
        all_ok,
        20,
        frozenset({question.domain}),
        0,
        frozenset(),
        bundle.dataset,
    )
    assert "new_domain" not in already_asked_domain.bonuses_applied

    past_answer_window = question_score(
        question,
        probabilities,
        all_ok,
        20,
        frozenset(),
        bundle.dataset.branching.bonuses.new_domain_until_answers,
        frozenset(),
        bundle.dataset,
    )
    assert "new_domain" not in past_answer_window.bonuses_applied


def test_urgent_bonus_applies_only_to_urgent_questions(bundle: DatasetBundle) -> None:
    urgent_q = bundle.index.questions_by_id["crs_regression"]
    assert urgent_q.is_urgent
    probabilities = {link.condition: 0.5 for link in urgent_q.links}
    all_ok = {link.condition: Eligibility.OK for link in urgent_q.links}
    breakdown = question_score(
        urgent_q,
        probabilities,
        all_ok,
        20,
        frozenset({urgent_q.domain}),
        20,
        frozenset(),
        bundle.dataset,
    )
    assert "urgent_question" in breakdown.bonuses_applied


def test_follow_up_bonus_applies_when_question_is_an_active_follow_up(
    bundle: DatasetBundle,
) -> None:
    question = bundle.index.questions_by_id["soc_point_interest"]
    probabilities = {link.condition: 0.5 for link in question.links}
    all_ok = {link.condition: Eligibility.OK for link in question.links}

    without_follow_up = question_score(
        question,
        probabilities,
        all_ok,
        20,
        frozenset({question.domain}),
        20,
        frozenset(),
        bundle.dataset,
    )
    with_follow_up = question_score(
        question,
        probabilities,
        all_ok,
        20,
        frozenset({question.domain}),
        20,
        frozenset({question.id}),
        bundle.dataset,
    )
    assert "follow_up" not in without_follow_up.bonuses_applied
    assert "follow_up" in with_follow_up.bonuses_applied
    assert with_follow_up.raw_score > without_follow_up.raw_score


def test_uncertainty_peaks_at_probability_one_half(bundle: DatasetBundle) -> None:
    question = bundle.index.questions_by_id["soc_point_interest"]
    all_ok = {link.condition: Eligibility.OK for link in question.links}

    at_half = question_score(
        question,
        {link.condition: 0.5 for link in question.links},
        all_ok,
        20,
        frozenset({question.domain}),
        20,
        frozenset(),
        bundle.dataset,
    )
    at_extreme = question_score(
        question,
        {link.condition: 0.97 for link in question.links},
        all_ok,
        20,
        frozenset({question.domain}),
        20,
        frozenset(),
        bundle.dataset,
    )
    assert at_half.raw_score > at_extreme.raw_score


def test_follow_up_sources_maps_follow_up_to_its_trigger(bundle: DatasetBundle) -> None:
    source_question = next(q for q in bundle.dataset.questions if q.follow_ups_if_yes)
    follow_up_id = source_question.follow_ups_if_yes[0]

    answers = (Answer(question_id=source_question.id, key=AnswerKey.YES, answered_at_step=1),)
    sources = follow_up_sources(answers, bundle.dataset, bundle.index.questions_by_id)

    assert sources[follow_up_id] == source_question.id


def test_follow_up_sources_most_recent_trigger_wins(bundle: DatasetBundle) -> None:
    # soc_response_name is listed as a follow-up by both soc_eye_contact and
    # att_sticky -> whichever was answered Yes most recently should win.
    follow_up_id = "soc_response_name"
    first_id, second_id = "soc_eye_contact", "att_sticky"
    assert follow_up_id in bundle.index.questions_by_id[first_id].follow_ups_if_yes
    assert follow_up_id in bundle.index.questions_by_id[second_id].follow_ups_if_yes

    answers = (
        Answer(question_id=first_id, key=AnswerKey.YES, answered_at_step=1),
        Answer(question_id=second_id, key=AnswerKey.YES, answered_at_step=2),
    )
    sources = follow_up_sources(answers, bundle.dataset, bundle.index.questions_by_id)
    assert sources[follow_up_id] == second_id


def test_candidate_details_includes_score_breakdown() -> None:
    ranked = [
        ScoreBreakdown("a", 3.0, {"ASD": 2.0, "GDD": 1.0}, ("new_domain",)),
        ScoreBreakdown("b", 1.0, {"LT": 1.0}, ()),
    ]
    details = candidate_details(ranked)
    assert details[0].question_id == "a"
    assert details[0].per_condition == {"ASD": 2.0, "GDD": 1.0}
    assert details[0].bonuses_applied == ("new_domain",)
    assert details[1].bonuses_applied == ()

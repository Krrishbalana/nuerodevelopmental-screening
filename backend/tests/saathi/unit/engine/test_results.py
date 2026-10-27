from saathi.domain.enums import Action, AnswerKey, Band, Born, Sex
from saathi.domain.session_state import ChildProfile, SessionState
from saathi.engine.results import _band_for, _recheck_text, build_results
from saathi.dataset_service import DatasetBundle
from tests.saathi.conftest import run_adaptive_loop


def _profile(age_years: int = 2, age_months: int = 6) -> ChildProfile:
    return ChildProfile(
        age_years=age_years, age_months=age_months, sex=Sex.NA, born=Born.TERM, family_factors=()
    )


def test_band_boundaries(bundle: DatasetBundle) -> None:
    bands = bundle.dataset.results.bands
    assert _band_for(0.60, bands) is Band.STRONG
    assert _band_for(0.599, bands) is Band.LIKELY
    assert _band_for(0.30, bands) is Band.LIKELY
    assert _band_for(0.299, bands) is Band.POSSIBLE
    assert _band_for(0.10, bands) is Band.POSSIBLE
    assert _band_for(0.099, bands) is Band.UNLIKELY
    assert _band_for(0.0, bands) is Band.UNLIKELY


def test_recheck_text_boundaries(bundle: DatasetBundle) -> None:
    ranges = bundle.dataset.results.recheck
    assert _recheck_text(0, ranges) == _recheck_text(23, ranges)
    assert _recheck_text(24, ranges) == _recheck_text(59, ranges)
    assert _recheck_text(23, ranges) != _recheck_text(24, ranges)
    assert _recheck_text(60, ranges) != _recheck_text(59, ranges)


def test_on_track_when_nothing_shown(bundle: DatasetBundle) -> None:
    state, _ = run_adaptive_loop(
        bundle, SessionState(session_id="s", profile=_profile()), yes_to=set()
    )
    results = build_results(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert results.action is Action.ON_TRACK
    assert results.conditions == ()
    assert results.activities == ()
    assert results.recheck  # always present (14: recheck_always)


def test_a_single_autism_sign_alone_is_not_shown(bundle: DatasetBundle) -> None:
    # one strength-3 ASD sign fully past its red flag at 26 months. With Saathi's US prior (3%) this
    # was p ~ 0.157 ('possible'); with the Indian prior (1%, INCLEN 2018) it is p ~ 0.057, below the
    # 0.10 'possible' line, so one sign on its own doesn't put autism on the report.
    # Built directly (not via the adaptive loop) so this is the *only* answer.
    state = SessionState(session_id="s", profile=_profile(age_years=2, age_months=2)).with_answer(
        "soc_point_interest", AnswerKey.YES
    )
    results = build_results(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert all(c.key != "ASD" for c in results.conditions)
    assert results.action is not Action.REFER


def test_refer_action_when_an_ok_condition_crosses_threshold(bundle: DatasetBundle) -> None:
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
    state, _ = run_adaptive_loop(
        bundle,
        SessionState(session_id="s", profile=_profile(age_years=2, age_months=2)),
        autism_yes_to,
    )
    results = build_results(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert results.action is Action.REFER


def test_activities_are_capped_and_tied_to_shown_conditions(bundle: DatasetBundle) -> None:
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
    state, _ = run_adaptive_loop(
        bundle,
        SessionState(session_id="s", profile=_profile(age_years=2, age_months=2)),
        autism_yes_to,
    )
    results = build_results(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert 0 < len(results.activities) <= bundle.dataset.activities_config.max_shown
    shown_keys = {c.key for c in results.conditions}
    for activity in results.activities:
        assert shown_keys.intersection(activity.conditions)
    # ranked by strongest matching condition's probability, descending
    def _best_probability(activity_conditions: tuple[str, ...]) -> float:
        by_key = {c.key: c.probability for c in results.conditions}
        return max(by_key[k] for k in activity_conditions if k in by_key)

    probabilities = [_best_probability(a.conditions) for a in results.activities]
    assert probabilities == sorted(probabilities, reverse=True)


def test_urgent_action_survives_acknowledgment(bundle: DatasetBundle) -> None:
    urgent_q = next(q for q in bundle.dataset.questions if q.is_urgent)
    state = SessionState(session_id="s", profile=_profile())
    state = state.with_answer(urgent_q.id, AnswerKey.YES)
    state = state.with_ack(urgent_q.id)
    results = build_results(state, bundle.dataset, bundle.index, bundle.rules_config)
    assert results.action is Action.URGENT

from saathi.domain.enums import Eligibility
from saathi.engine.formulas.eligibility import askable, eligibility
from tests.saathi.conftest import make_condition, make_question

HIDDEN_MARGIN_M = 12


def test_past_when_above_dx_max_m() -> None:
    c = make_condition(dx_min_m=18, dx_max_m=42)
    assert eligibility(c, 43, HIDDEN_MARGIN_M) is Eligibility.PAST


def test_ok_at_exactly_dx_max_m() -> None:
    c = make_condition(dx_min_m=18, dx_max_m=42)
    assert eligibility(c, 42, HIDDEN_MARGIN_M) is Eligibility.OK


def test_never_past_when_dx_max_m_is_none() -> None:
    c = make_condition(dx_min_m=12, dx_max_m=None)
    assert eligibility(c, 1000, HIDDEN_MARGIN_M) is Eligibility.OK


def test_hidden_below_dx_min_minus_margin() -> None:
    c = make_condition(dx_min_m=12, dx_max_m=None)
    assert eligibility(c, 12 - HIDDEN_MARGIN_M - 1, HIDDEN_MARGIN_M) is Eligibility.HIDDEN


def test_watch_at_hidden_boundary() -> None:
    c = make_condition(dx_min_m=12, dx_max_m=None)
    assert eligibility(c, 12 - HIDDEN_MARGIN_M, HIDDEN_MARGIN_M) is Eligibility.WATCH


def test_watch_just_below_dx_min_m() -> None:
    c = make_condition(dx_min_m=12, dx_max_m=None)
    assert eligibility(c, 11, HIDDEN_MARGIN_M) is Eligibility.WATCH


def test_ok_at_exactly_dx_min_m() -> None:
    c = make_condition(dx_min_m=12, dx_max_m=None)
    assert eligibility(c, 12, HIDDEN_MARGIN_M) is Eligibility.OK


def test_askable_requires_within_window() -> None:
    q = make_question(window_start_m=12, window_end_m=36, typical_m=None)
    assert not askable(q, 11)
    assert askable(q, 12)
    assert askable(q, 36)
    assert not askable(q, 37)


def test_askable_blocked_before_typical_m() -> None:
    q = make_question(window_start_m=0, window_end_m=72, typical_m=18)
    assert not askable(q, 17)
    assert askable(q, 18)


def test_askable_null_typical_m_has_no_lower_bound_beyond_window() -> None:
    q = make_question(window_start_m=0, window_end_m=72, typical_m=None)
    assert askable(q, 0)


def test_background_question_never_askable() -> None:
    q = make_question(window_start_m=0, window_end_m=72, typical_m=None, is_background=True)
    assert not askable(q, 30)

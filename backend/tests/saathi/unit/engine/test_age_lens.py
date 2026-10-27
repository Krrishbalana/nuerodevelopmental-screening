from saathi.domain.enums import Direction, Situation
from saathi.engine.formulas.age_lens import exponent, situation
from tests.saathi.conftest import make_age_lens, make_question

AGE_LENS = make_age_lens()


def test_crs_domain_absent_is_always_history_item_regardless_of_age() -> None:
    q = make_question(
        domain="CRS", window_start_m=0, window_end_m=72, typical_m=None, red_flag_m=None
    )
    assert situation(q, 3, Direction.ABSENT) is Situation.HISTORY_ITEM
    assert situation(q, 72, Direction.ABSENT) is Situation.HISTORY_ITEM


def test_crs_domain_present_is_not_history_item() -> None:
    q = make_question(
        domain="CRS", window_start_m=0, window_end_m=72, typical_m=None, red_flag_m=None
    )
    assert situation(q, 30, Direction.PRESENT) is Situation.UNUSUAL_BEHAVIOR


def test_well_past_red_flag_requires_present_direction_and_1_5x_age() -> None:
    q = make_question(red_flag_m=18, typical_m=15)
    assert situation(q, 27, Direction.PRESENT) is Situation.WELL_PAST_RED_FLAG
    assert situation(q, 26, Direction.PRESENT) is Situation.PAST_RED_FLAG


def test_well_past_red_flag_never_fires_for_absent_direction() -> None:
    q = make_question(red_flag_m=18, typical_m=15)
    assert situation(q, 100, Direction.ABSENT) is Situation.PAST_RED_FLAG


def test_red_flag_below_6_months_never_reaches_well_past_red_flag() -> None:
    q = make_question(red_flag_m=5, typical_m=2)
    # even at a huge multiple of the red flag age, well_past_red_flag requires red_flag_m >= 6
    assert situation(q, 50, Direction.PRESENT) is Situation.PAST_RED_FLAG


def test_past_red_flag_when_age_at_or_above_red_flag() -> None:
    q = make_question(red_flag_m=18, typical_m=15)
    assert situation(q, 18, Direction.ABSENT) is Situation.PAST_RED_FLAG
    assert situation(q, 18, Direction.PRESENT) is Situation.PAST_RED_FLAG


def test_null_typical_m_is_unusual_behavior_once_past_red_flag_window() -> None:
    q = make_question(red_flag_m=None, typical_m=None)
    assert situation(q, 30, Direction.PRESENT) is Situation.UNUSUAL_BEHAVIOR
    assert situation(q, 30, Direction.ABSENT) is Situation.UNUSUAL_BEHAVIOR


def test_past_typical_and_before_typical_boundary() -> None:
    q = make_question(red_flag_m=None, typical_m=15)
    assert situation(q, 14, Direction.PRESENT) is Situation.BEFORE_TYPICAL
    assert situation(q, 15, Direction.PRESENT) is Situation.PAST_TYPICAL


def test_exponent_table_lookup_present_and_absent() -> None:
    assert exponent(Situation.PAST_TYPICAL, Direction.PRESENT, AGE_LENS) == 0.7
    assert exponent(Situation.PAST_TYPICAL, Direction.ABSENT, AGE_LENS) == 0.5
    assert exponent(Situation.BEFORE_TYPICAL, Direction.PRESENT, AGE_LENS) == 0.5
    assert exponent(Situation.BEFORE_TYPICAL, Direction.ABSENT, AGE_LENS) == 0.2


def test_exponent_well_past_red_flag_absent_falls_back_to_past_red_flag() -> None:
    # the absent table has no well_past_red_flag entry; defensive fallback (3.3.4)
    expected = exponent(Situation.PAST_RED_FLAG, Direction.ABSENT, AGE_LENS)
    assert exponent(Situation.WELL_PAST_RED_FLAG, Direction.ABSENT, AGE_LENS) == expected


def test_exponent_well_past_red_flag_present_has_its_own_value() -> None:
    assert exponent(Situation.WELL_PAST_RED_FLAG, Direction.PRESENT, AGE_LENS) == 1.5

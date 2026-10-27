from saathi.domain.enums import Born
from saathi.engine.formulas.age import assessed_age
from tests.saathi.conftest import make_age_lens

AGE_LENS = make_age_lens(applies_below_m=24, lt32_subtract_m=3, thirty_two_36_subtract_m=1)


def test_term_birth_never_corrected() -> None:
    assert assessed_age(10, Born.TERM, AGE_LENS) == 10
    assert assessed_age(30, Born.TERM, AGE_LENS) == 30


def test_lt32_corrected_below_threshold() -> None:
    assert assessed_age(12, Born.LT32, AGE_LENS) == 9


def test_32_36_corrected_below_threshold() -> None:
    assert assessed_age(12, Born.WEEKS_32_36, AGE_LENS) == 11


def test_correction_boundary_at_applies_below_m() -> None:
    # chronological age == applies_below_m is NOT "< applies_below_m", so no correction
    assert assessed_age(24, Born.LT32, AGE_LENS) == 24


def test_correction_just_under_boundary() -> None:
    assert assessed_age(23, Born.LT32, AGE_LENS) == 20


def test_floor_at_one_month() -> None:
    assert assessed_age(2, Born.LT32, AGE_LENS) == 1


def test_lt32_not_corrected_once_past_applies_below_m() -> None:
    assert assessed_age(25, Born.LT32, AGE_LENS) == 25

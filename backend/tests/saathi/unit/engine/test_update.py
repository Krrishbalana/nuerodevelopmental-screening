import math

import pytest

from saathi.domain.dataset import DampingConfig
from saathi.domain.enums import Direction, Situation
from saathi.engine.formulas.damping import DampingCounters
from saathi.engine.formulas.update import evidence_delta
from tests.saathi.conftest import make_age_lens, make_link, make_question

AGE_LENS = make_age_lens()
DAMPING = DampingConfig(applies_to="test", same_domain=0.8, same_condition=0.93, formula="test")


def test_delta_equals_ln_lr_times_exponent_times_weight_times_damping() -> None:
    q = make_question(domain="SOC", typical_m=12, red_flag_m=18)
    link = make_link("ASD", strength=3, lr_present=6.0, lr_absent=0.5)
    counters = DampingCounters()

    term = evidence_delta(link, q, Direction.PRESENT, 1.0, 18, counters, AGE_LENS, DAMPING)

    assert term.situation is Situation.PAST_RED_FLAG
    assert term.exponent == 1.0
    assert term.ln_lr == math.log(6.0)
    assert term.damping == 1.0
    assert math.isclose(term.delta, math.log(6.0) * 1.0 * 1.0 * 1.0)


def test_absent_direction_uses_lr_absent() -> None:
    q = make_question(domain="SOC", typical_m=12, red_flag_m=18)
    link = make_link("ASD", strength=3, lr_present=6.0, lr_absent=0.5)
    counters = DampingCounters()

    term = evidence_delta(link, q, Direction.ABSENT, 1.0, 18, counters, AGE_LENS, DAMPING)

    assert term.ln_lr == math.log(0.5)
    assert term.delta < 0  # "No" to a core sign should push log-odds down


def test_weight_scales_delta_linearly() -> None:
    q = make_question(domain="SOC", typical_m=12, red_flag_m=18)
    link = make_link("ASD", strength=3, lr_present=6.0, lr_absent=0.5)
    counters = DampingCounters()

    full = evidence_delta(link, q, Direction.PRESENT, 1.0, 18, counters, AGE_LENS, DAMPING)
    half = evidence_delta(link, q, Direction.PRESENT, 0.5, 18, counters, AGE_LENS, DAMPING)

    assert math.isclose(half.delta, full.delta / 2)


def test_unknown_direction_is_rejected() -> None:
    q = make_question(domain="SOC", typical_m=12, red_flag_m=18)
    link = make_link("ASD")
    counters = DampingCounters()
    with pytest.raises(AssertionError):
        evidence_delta(link, q, Direction.UNKNOWN, 0.0, 18, counters, AGE_LENS, DAMPING)

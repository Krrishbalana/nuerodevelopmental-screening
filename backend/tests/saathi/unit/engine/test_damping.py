from saathi.domain.dataset import DampingConfig
from saathi.domain.enums import Direction
from saathi.engine.formulas.damping import DampingCounters

CONFIG = DampingConfig(applies_to="test", same_domain=0.8, same_condition=0.93, formula="test")


def test_no_prior_answers_has_factor_one() -> None:
    counters = DampingCounters()
    assert counters.factor("ASD", "SOC", Direction.PRESENT, CONFIG) == 1.0


def test_same_domain_and_condition_damps_on_second_yes() -> None:
    counters = DampingCounters().incremented("ASD", "SOC", Direction.PRESENT)
    factor = counters.factor("ASD", "SOC", Direction.PRESENT, CONFIG)
    assert factor == CONFIG.same_domain * CONFIG.same_condition


def test_same_condition_different_domain_only_damps_by_condition_factor() -> None:
    counters = DampingCounters().incremented("ASD", "SOC", Direction.PRESENT)
    factor = counters.factor("ASD", "PRE", Direction.PRESENT, CONFIG)
    assert factor == CONFIG.same_condition


def test_directions_are_damped_independently() -> None:
    counters = DampingCounters().incremented("ASD", "SOC", Direction.PRESENT)
    # a prior Yes must not damp a subsequent No for the same condition/domain
    assert counters.factor("ASD", "SOC", Direction.ABSENT, CONFIG) == 1.0


def test_different_conditions_are_independent() -> None:
    counters = DampingCounters().incremented("ASD", "SOC", Direction.PRESENT)
    assert counters.factor("GDD", "SOC", Direction.PRESENT, CONFIG) == 1.0


def test_damping_compounds_across_multiple_answers() -> None:
    counters = DampingCounters()
    counters = counters.incremented("ASD", "SOC", Direction.PRESENT)
    counters = counters.incremented("ASD", "SOC", Direction.PRESENT)
    factor = counters.factor("ASD", "SOC", Direction.PRESENT, CONFIG)
    assert factor == (CONFIG.same_domain**2) * (CONFIG.same_condition**2)


def test_original_counters_unchanged_after_incremented_is_immutable() -> None:
    original = DampingCounters()
    updated = original.incremented("ASD", "SOC", Direction.PRESENT)
    assert original.factor("ASD", "SOC", Direction.PRESENT, CONFIG) == 1.0
    assert updated.factor("ASD", "SOC", Direction.PRESENT, CONFIG) != 1.0

import math

from saathi.engine.formulas.odds import logit, sigmoid


def test_logit_sigmoid_are_inverses() -> None:
    for p in (0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99):
        assert math.isclose(sigmoid(logit(p)), p, abs_tol=1e-9)


def test_logit_half_is_zero() -> None:
    assert math.isclose(logit(0.5), 0.0, abs_tol=1e-12)


def test_sigmoid_zero_is_half() -> None:
    assert math.isclose(sigmoid(0.0), 0.5, abs_tol=1e-12)


def test_sigmoid_large_positive_approaches_one() -> None:
    assert sigmoid(50.0) > 0.999999


def test_sigmoid_large_negative_approaches_zero() -> None:
    assert sigmoid(-50.0) < 0.000001

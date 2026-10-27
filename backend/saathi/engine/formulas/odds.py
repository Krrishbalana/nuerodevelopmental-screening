"""Odds/log-odds conversions. design doc section 3 (notation) and section 8.3."""

import math


def logit(p: float) -> float:
    """ln(p / (1-p)). `p` must be strictly between 0 and 1."""
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    """1 / (1 + e^-x); inverse of `logit`."""
    return 1.0 / (1.0 + math.exp(-x))

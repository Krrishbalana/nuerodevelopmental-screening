"""Condition eligibility and question askability. design doc section 4.2-4.3,
BUILD_PROMPT 3.3.2-3.3.3.
"""

from saathi.domain.dataset import Condition, Question
from saathi.domain.enums import Eligibility


def eligibility(condition: Condition, a: int, hidden_margin_m: int) -> Eligibility:
    if condition.dx_max_m is not None and a > condition.dx_max_m:
        return Eligibility.PAST
    if a < condition.dx_min_m - hidden_margin_m:
        return Eligibility.HIDDEN
    if a < condition.dx_min_m:
        return Eligibility.WATCH
    return Eligibility.OK


def askable(question: Question, a: int) -> bool:
    if question.is_background:
        return False
    window = question.age
    if not (window.window_start_m <= a <= window.window_end_m):
        return False
    return window.typical_m is None or a >= window.typical_m

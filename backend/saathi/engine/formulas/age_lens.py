"""Age situation and exponent lookup. adaptive-screening-dataset.json `age_lens`,
BUILD_PROMPT 3.3.4 (JSON wins over design-doc section 4.4: adds `well_past_red_flag`).
"""

from saathi.domain.dataset import AgeLens, Question
from saathi.domain.enums import Direction, Situation


def situation(question: Question, a: int, direction: Direction) -> Situation:
    window = question.age
    if direction is Direction.ABSENT and question.domain == "CRS":
        return Situation.HISTORY_ITEM
    if (
        direction is Direction.PRESENT
        and window.red_flag_m is not None
        and window.red_flag_m >= 6
        and a >= 1.5 * window.red_flag_m
    ):
        return Situation.WELL_PAST_RED_FLAG
    if window.red_flag_m is not None and a >= window.red_flag_m:
        return Situation.PAST_RED_FLAG
    if window.typical_m is None:
        return Situation.UNUSUAL_BEHAVIOR
    if a >= window.typical_m:
        return Situation.PAST_TYPICAL
    return Situation.BEFORE_TYPICAL


def exponent(given_situation: Situation, direction: Direction, age_lens: AgeLens) -> float:
    if direction is Direction.ABSENT and given_situation is Situation.WELL_PAST_RED_FLAG:
        given_situation = Situation.PAST_RED_FLAG  # absent table has no such key
    table = (
        age_lens.exponents.present if direction is Direction.PRESENT else age_lens.exponents.absent
    )
    return table[given_situation]

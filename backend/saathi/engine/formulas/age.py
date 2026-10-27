"""Assessed (prematurity-corrected) age. design doc section 4.1, BUILD_PROMPT 3.3.1."""

from saathi.domain.dataset import AgeLens
from saathi.domain.enums import Born


def assessed_age(chronological_age_m: int, born: Born, age_lens: AgeLens) -> int:
    correction = age_lens.prematurity_correction
    if chronological_age_m < correction.applies_below_m:
        if born is Born.LT32:
            chronological_age_m -= correction.lt32_subtract_m
        elif born is Born.WEEKS_32_36:
            chronological_age_m -= correction.thirty_two_36_subtract_m
    return max(1, chronological_age_m)

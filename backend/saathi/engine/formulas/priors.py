"""Prior log-odds from base rate plus background-factor multipliers.
design doc section 5.1, BUILD_PROMPT 3.3.5.
"""

import math

from saathi.domain.dataset import Condition, Dataset
from saathi.domain.enums import Born, Sex
from saathi.domain.session_state import ChildProfile
from saathi.engine.formulas.odds import logit


def _active_factors(profile: ChildProfile) -> frozenset[str]:
    factors = set(profile.family_factors)
    if profile.born is Born.LT32:
        factors.add("preterm_lt32")
    elif profile.born is Born.WEEKS_32_36:
        factors.add("preterm_32_36")
    if profile.sex is Sex.BOY:
        factors.add("sex_boy")
    elif profile.sex is Sex.GIRL:
        factors.add("sex_girl")
    return frozenset(factors)


def prior_logit(condition: Condition, profile: ChildProfile, dataset: Dataset) -> float:
    log_odds = logit(condition.base_rate)
    factors = _active_factors(profile)
    for modifier in dataset.prior_modifiers:
        if modifier.factor in factors and condition.key in modifier.odds_multipliers:
            log_odds += math.log(modifier.odds_multipliers[condition.key])
    return log_odds

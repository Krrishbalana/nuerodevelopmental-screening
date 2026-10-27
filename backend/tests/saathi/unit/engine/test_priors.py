import math

from saathi.domain.enums import Born, Sex
from saathi.domain.session_state import ChildProfile
from saathi.engine.formulas.odds import logit, sigmoid
from saathi.engine.formulas.priors import prior_logit
from saathi.dataset_service import DatasetBundle


def _profile(
    sex: Sex = Sex.NA, born: Born = Born.TERM, family_factors: tuple[str, ...] = ()
) -> ChildProfile:
    return ChildProfile(
        age_years=2, age_months=0, sex=sex, born=born, family_factors=family_factors
    )


def test_no_factors_equals_base_rate(bundle: DatasetBundle) -> None:
    asd = bundle.index.conditions_by_key["ASD"]
    assert math.isclose(prior_logit(asd, _profile(), bundle.dataset), logit(asd.base_rate))


def test_sibling_asd_multiplier_matches_design_doc_worked_example(bundle: DatasetBundle) -> None:
    asd = bundle.index.conditions_by_key["ASD"]
    profile = _profile(family_factors=("sibling_asd",))
    p = sigmoid(prior_logit(asd, profile, bundle.dataset))
    # design doc 5.3 worked example with the Indian base rate: odds 0.01/0.99 * 6.5 = 0.0657 -> p ~ 6.2%
    assert math.isclose(p, 0.0616, abs_tol=0.001)


def test_na_sex_applies_no_sex_multiplier(bundle: DatasetBundle) -> None:
    asd = bundle.index.conditions_by_key["ASD"]
    na_logit = prior_logit(asd, _profile(sex=Sex.NA), bundle.dataset)
    assert math.isclose(na_logit, logit(asd.base_rate))


def test_boy_and_girl_multipliers_differ(bundle: DatasetBundle) -> None:
    asd = bundle.index.conditions_by_key["ASD"]
    boy_logit = prior_logit(asd, _profile(sex=Sex.BOY), bundle.dataset)
    girl_logit = prior_logit(asd, _profile(sex=Sex.GIRL), bundle.dataset)
    assert boy_logit > girl_logit


def test_preterm_lt32_increases_gdd_prior(bundle: DatasetBundle) -> None:
    gdd = bundle.index.conditions_by_key["GDD"]
    term_logit = prior_logit(gdd, _profile(born=Born.TERM), bundle.dataset)
    preterm_logit = prior_logit(gdd, _profile(born=Born.LT32), bundle.dataset)
    assert preterm_logit > term_logit


def test_multiple_factors_compound_additively_in_log_space(bundle: DatasetBundle) -> None:
    adhd = bundle.index.conditions_by_key["ADHD"]
    base = logit(adhd.base_rate)
    one_factor = prior_logit(adhd, _profile(family_factors=("family_adhd",)), bundle.dataset)
    two_factors = prior_logit(
        adhd, _profile(sex=Sex.BOY, family_factors=("family_adhd",)), bundle.dataset
    )
    assert two_factors > one_factor > base

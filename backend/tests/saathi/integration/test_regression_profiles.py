"""Regression tests: every profile in dataset.validation_profiles.profiles must
reproduce questions_asked exactly and each result_top probability within ±0.02,
driving the REAL adaptive loop (question order is adaptive, not scripted).
BUILD_PROMPT.md section 3.6.
"""

import pytest

from saathi.domain.dataset import ValidationProfile
from saathi.domain.enums import Born, Sex
from saathi.domain.session_state import ChildProfile, SessionState
from saathi.engine.results import build_results
from saathi.dataset_service import DatasetBundle, load_bundle
from tests.saathi.conftest import DATASET_PATH, run_adaptive_loop

_VALIDATION_PROFILES = load_bundle(DATASET_PATH).dataset.validation_profiles.profiles

PROBABILITY_TOLERANCE = 0.02


@pytest.mark.parametrize(
    "profile", _VALIDATION_PROFILES, ids=[p.profile for p in _VALIDATION_PROFILES]
)
def test_validation_profile_regression(bundle: DatasetBundle, profile: ValidationProfile) -> None:
    child_profile = ChildProfile(
        age_years=profile.age_m // 12,
        age_months=profile.age_m % 12,
        sex=Sex.NA,
        born=Born.TERM,
        family_factors=(),
    )
    state = SessionState(session_id="regression", profile=child_profile)
    final_state, _ = run_adaptive_loop(bundle, state, yes_to=set(profile.yes_to))

    assert len(final_state.answers) == profile.questions_asked, (
        f"{profile.profile}: questions_asked got={len(final_state.answers)} "
        f"expected={profile.questions_asked}"
    )

    results = build_results(final_state, bundle.dataset, bundle.index, bundle.rules_config)
    probabilities = {c.key: c.probability for c in results.conditions}
    for expected in profile.result_top:
        got = probabilities.get(expected.condition, 0.0)
        diff = abs(got - expected.p)
        assert diff <= PROBABILITY_TOLERANCE, (
            f"{profile.profile}: {expected.condition} got={got:.4f} "
            f"expected={expected.p:.4f} diff={diff:.4f}"
        )

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from saathi.errors import DatasetIntegrityError
from saathi.domain.dataset import Dataset
from saathi.engine.rules_config import RulesConfig
from saathi.dataset_service import (
    load_bundle,
    validate_referential_integrity,
    validate_rules_config,
)
from tests.saathi.conftest import DATASET_PATH

RawDataset = dict[str, Any]


@pytest.fixture(scope="module")
def raw_dataset() -> RawDataset:
    result: RawDataset = json.loads(DATASET_PATH.read_bytes())
    return result


def test_valid_dataset_has_no_violations(raw_dataset: RawDataset) -> None:
    dataset = Dataset.model_validate(raw_dataset)
    assert validate_referential_integrity(dataset) == []
    assert validate_rules_config(dataset, RulesConfig()) == []


def test_dangling_follow_up_id_is_detected(raw_dataset: RawDataset) -> None:
    corrupted = copy.deepcopy(raw_dataset)
    corrupted["questions"][0]["follow_ups_if_yes"].append("no_such_question")
    dataset = Dataset.model_validate(corrupted)
    violations = validate_referential_integrity(dataset)
    assert any("no_such_question" in v for v in violations)


def test_dangling_link_condition_is_detected(raw_dataset: RawDataset) -> None:
    corrupted = copy.deepcopy(raw_dataset)
    corrupted["questions"][0]["links"][0]["condition"] = "NOPE"
    dataset = Dataset.model_validate(corrupted)
    violations = validate_referential_integrity(dataset)
    assert any("NOPE" in v for v in violations)


def test_dangling_transitions_to_is_detected(raw_dataset: RawDataset) -> None:
    corrupted = copy.deepcopy(raw_dataset)
    corrupted["conditions"][0]["transitions_to"] = "NOPE"
    dataset = Dataset.model_validate(corrupted)
    violations = validate_referential_integrity(dataset)
    assert any("NOPE" in v for v in violations)


def test_all_violations_collected_not_just_the_first(raw_dataset: RawDataset) -> None:
    corrupted = copy.deepcopy(raw_dataset)
    corrupted["questions"][0]["follow_ups_if_yes"].append("no_such_question")
    corrupted["questions"][1]["links"][0]["condition"] = "NOPE"
    dataset = Dataset.model_validate(corrupted)
    violations = validate_referential_integrity(dataset)
    assert any("no_such_question" in v for v in violations)
    assert any("NOPE" in v for v in violations)
    assert len(violations) >= 2


def test_load_bundle_raises_dataset_integrity_error_on_corruption(
    raw_dataset: RawDataset, tmp_path: Path
) -> None:
    corrupted = copy.deepcopy(raw_dataset)
    corrupted["branching"]["always_first"].append("no_such_question")
    corrupted_path = tmp_path / "corrupted.json"
    corrupted_path.write_text(json.dumps(corrupted))

    with pytest.raises(DatasetIntegrityError) as exc_info:
        load_bundle(corrupted_path)
    assert "no_such_question" in str(exc_info.value)


def test_unknown_rules_config_condition_key_is_detected(raw_dataset: RawDataset) -> None:
    dataset = Dataset.model_validate(raw_dataset)
    bad_config = RulesConfig(spcd_condition_key="NOPE")
    violations = validate_rules_config(dataset, bad_config)
    assert any("NOPE" in v for v in violations)


def test_late_talker_age_mismatch_is_detected(raw_dataset: RawDataset) -> None:
    dataset = Dataset.model_validate(raw_dataset)
    bad_config = RulesConfig(late_talker_to_dld_age_m=999)
    violations = validate_rules_config(dataset, bad_config)
    assert any("999" in v for v in violations)

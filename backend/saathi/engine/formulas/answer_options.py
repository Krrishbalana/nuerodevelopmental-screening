"""Maps an answer key to its (direction, weight) pair from `answer_options` in the
dataset, so these numbers are never hardcoded (design doc section 6).
"""

from saathi.domain.dataset import Dataset
from saathi.domain.enums import AnswerKey, Direction


def direction_and_weight(key: AnswerKey, dataset: Dataset) -> tuple[Direction, float]:
    for option in dataset.answer_options:
        if option.key == key.value:
            return Direction(option.direction), option.weight
    raise KeyError(f"Unknown answer key: {key!r}")

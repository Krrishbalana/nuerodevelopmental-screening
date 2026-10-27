"""Lookup indices derived from a validated Dataset. Pure data + a pure builder
function, kept in `domain/` (not `services/`) so `app/engine/` can depend on it
without crossing into the services layer.
"""

from dataclasses import dataclass

from saathi.domain.dataset import Activity, Condition, Dataset, LikelihoodRatioDefault, Question
from saathi.domain.observations import ObservationDef


@dataclass(frozen=True)
class DatasetIndex:
    questions_by_id: dict[str, Question]
    conditions_by_key: dict[str, Condition]
    lr_defaults_by_strength: dict[int, LikelihoodRatioDefault]
    always_first_questions: tuple[Question, ...]
    activities_by_id: dict[str, Activity]
    observations_by_id: dict[str, ObservationDef]


def build_dataset_index(dataset: Dataset) -> DatasetIndex:
    questions_by_id = {q.id: q for q in dataset.questions}
    conditions_by_key = {c.key: c for c in dataset.conditions}
    lr_defaults_by_strength = {d.strength: d for d in dataset.likelihood_ratio_defaults}
    always_first = tuple(questions_by_id[qid] for qid in dataset.branching.always_first)
    activities_by_id = {a.id: a for a in dataset.activities}
    return DatasetIndex(
        questions_by_id=questions_by_id,
        conditions_by_key=conditions_by_key,
        lr_defaults_by_strength=lr_defaults_by_strength,
        always_first_questions=always_first,
        activities_by_id=activities_by_id,
        observations_by_id={o.id: o for o in dataset.observation_config.observations},
    )

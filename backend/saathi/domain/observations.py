"""Observations: evidence measured by the app (camera, later speech), not answered by a parent.

Definitions live in data/saathi/observations.json. Each outcome carries per-condition likelihood
ratios with their provenance and the ages they are valid for; the engine uses the first entry whose
age range contains the child's assessed age.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ObservationLR(_Frozen):
    condition: str
    lr: float = Field(gt=0)
    source: Literal["published", "extrapolated", "estimated"]
    ref: str
    age_months: tuple[int, int] | None = None  # None = any age

    def applies_at(self, age_m: int) -> bool:
        return self.age_months is None or self.age_months[0] <= age_m <= self.age_months[1]


class ObservationOutcome(_Frozen):
    key: str
    label: str
    lrs: list[ObservationLR]


class ObservationDef(_Frozen):
    id: str
    label: str
    domain: str
    # Saathi questions about the same behaviour; their evidence is damped when it agrees (no double counting).
    construct_question_ids: list[str] = []
    outcomes: list[ObservationOutcome]

    def outcome(self, key: str) -> ObservationOutcome | None:
        return next((o for o in self.outcomes if o.key == key), None)


class ObservationConfig(_Frozen):
    construct_damping: float = Field(default=0.5, gt=0, le=1)
    confidence_weights: dict[str, float] = {"high": 1.0, "medium": 0.7}
    observations: list[ObservationDef] = []

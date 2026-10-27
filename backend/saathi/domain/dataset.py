"""Declarative models of adaptive-screening-dataset.json.

Field names and nesting mirror the JSON exactly so that `Dataset.model_validate(raw)`
succeeds with `extra="forbid"` and no silent data loss. These models hold data only;
derived lookups (by-id / by-key indices) are built separately by
`services/dataset_service.py` so the models here stay purely declarative.
"""

from pydantic import BaseModel, ConfigDict, Field

from saathi.domain.observations import ObservationConfig
from saathi.domain.enums import Band, Eligibility, MediaType, QuestionType, RuleId, Situation


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AnswerOption(_Frozen):
    key: str
    label: str
    direction: int
    weight: float


class Domain(_Frozen):
    key: str
    name: str
    order: int


class Condition(_Frozen):
    key: str
    name: str
    short_name: str
    group: str
    is_ndd_dsm: bool
    dx_min_m: int
    dx_max_m: int | None
    dx_age_text: str
    base_rate: float
    base_rate_note: str
    transitions_to: str | None
    note: str
    refer: str


class PriorModifier(_Frozen):
    factor: str
    label: str
    odds_multipliers: dict[str, float]


class LikelihoodRatioDefault(_Frozen):
    strength: int
    meaning: str
    lr_present: float
    lr_absent: float


class PrematurityCorrection(_Frozen):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    applies_below_m: int
    lt32_subtract_m: int
    thirty_two_36_subtract_m: int = Field(alias="32_36_subtract_m")


class EligibilityConfig(_Frozen):
    rule: str
    hidden_margin_m: int


class AgeLensExponents(_Frozen):
    present: dict[Situation, float]
    absent: dict[Situation, float]


class AgeLens(_Frozen):
    prematurity_correction: PrematurityCorrection
    eligibility: EligibilityConfig
    askable: str
    situation_rule: list[str]
    exponents: AgeLensExponents


class DampingConfig(_Frozen):
    applies_to: str
    same_domain: float
    same_condition: float
    formula: str


class UpdateConfig(_Frozen):
    formula: str
    damping: DampingConfig
    probability_cap: float


class EligibilityWeights(_Frozen):
    ok: float
    watch: float
    hidden: float
    past: float

    def weight_for(self, eligibility: Eligibility) -> float:
        return getattr(self, eligibility.value)  # type: ignore[no-any-return]


class Bonuses(_Frozen):
    new_domain: float
    new_domain_until_answers: int
    urgent_question: float
    follow_up: float
    follow_up_horizon_answers: int


class StopRules(_Frozen):
    max_questions: int
    min_answers_for_results: int
    stop_when_best_score_below: float


class PatternMessage(_Frozen):
    threshold: float
    min_answers: int
    once_per_session: bool


class ReasonText(_Frozen):
    first: str
    separate: str
    check: str


class BranchingConfig(_Frozen):
    always_first: list[str]
    selection_score: str
    eligibility_weights: EligibilityWeights
    bonuses: Bonuses
    follow_up_rule: str
    stop_rules: StopRules
    pattern_message: PatternMessage
    reason_text: ReasonText


class Rule(_Frozen):
    id: RuleId
    when: str
    then: str
    priority: int


class Link(_Frozen):
    condition: str
    strength: int
    lr_present: float
    lr_absent: float
    lr_source: str


class AgeWindow(_Frozen):
    window_start_m: int
    window_end_m: int
    typical_m: int | None
    red_flag_m: int | None


class Question(_Frozen):
    id: str
    domain: str
    type: QuestionType
    question: str
    clinical_name: str
    typical: str
    age: AgeWindow
    is_urgent: bool
    ask_first: int | None
    is_background: bool
    background_note: str | None
    links: list[Link]
    follow_ups_if_yes: list[str]
    differentiation: str
    sources: list[str]
    data_fix: str | None


class ActivityAgeWindow(_Frozen):
    window_start_m: int
    window_end_m: int


class Activity(_Frozen):
    id: str
    title: str
    media_type: MediaType
    instructions: str
    what_we_look_for: str
    domain: str
    conditions: list[str]
    min_band: Band
    age: ActivityAgeWindow
    priority: int


class ActivitiesConfig(_Frozen):
    max_shown: int


class BandCfg(_Frozen):
    band: str
    min: float


class ResultAction(_Frozen):
    action: str
    when: str
    title: str


class RecheckRange(_Frozen):
    min_m: int
    max_m: int
    text: str


class ResultsShowIf(_Frozen):
    ok: float
    watch: float


class ResultsConfig(_Frozen):
    show_if: ResultsShowIf
    bands: list[BandCfg]
    actions: list[ResultAction]
    recheck: list[RecheckRange]
    sharpen_count: int


class ValidationResultTop(_Frozen):
    condition: str
    p: float


class ValidationProfile(_Frozen):
    profile: str
    age_m: int
    yes_to: list[str]
    all_other_answers: str
    questions_asked: int
    result_top: list[ValidationResultTop]
    expected: str


class ValidationProfiles(_Frozen):
    note: str
    profiles: list[ValidationProfile]


class Source(_Frozen):
    key: str
    citation: str


class Meta(_Frozen):
    name: str
    version: str
    model_version: str
    created: str
    age_range_months: tuple[int, int]
    counts: dict[str, int]
    disclaimer: str
    question_polarity: str
    provenance: str
    askable_questions_by_age: dict[str, int]


class Dataset(_Frozen):
    meta: Meta
    answer_options: list[AnswerOption]
    domains: list[Domain]
    conditions: list[Condition]
    prior_modifiers: list[PriorModifier]
    likelihood_ratio_defaults: list[LikelihoodRatioDefault]
    age_lens: AgeLens
    update: UpdateConfig
    branching: BranchingConfig
    rules: list[Rule]
    results: ResultsConfig
    activities_config: ActivitiesConfig
    questions: list[Question]
    activities: list[Activity]
    sources: list[Source]
    validation_profiles: ValidationProfiles
    observation_config: ObservationConfig = ObservationConfig()

"""Final results: shown conditions with bands/evidence, overall action, recheck
interval, sharpening questions. design doc section 12, BUILD_PROMPT 3.3.11.
"""

from dataclasses import dataclass

from saathi.domain.dataset import Activity, BandCfg, Dataset, RecheckRange
from saathi.domain.dataset_index import DatasetIndex
from saathi.domain.enums import Action, Band, Eligibility, MediaType
from saathi.domain.session_state import SessionState
from saathi.engine.branching import rank_remaining
from saathi.engine.posterior import Posterior, compute_posterior
from saathi.engine.rules import (
    hearing_first_triggered,
    major_milestone_missed,
    urgent_answered_question_ids,
)
from saathi.engine.rules_config import RulesConfig


@dataclass(frozen=True)
class EvidenceItem:
    question_id: str
    delta: float


@dataclass(frozen=True)
class ShownCondition:
    key: str
    probability: float
    band: Band
    eligibility: Eligibility
    evidence: tuple[EvidenceItem, ...]


@dataclass(frozen=True)
class SharpenQuestion:
    question_id: str
    question_text: str


@dataclass(frozen=True)
class SuggestedActivity:
    id: str
    title: str
    media_type: MediaType
    instructions: str
    what_we_look_for: str
    conditions: tuple[str, ...]


@dataclass(frozen=True)
class Results:
    action: Action
    title: str
    steps: tuple[str, ...]
    hearing_test: bool
    recheck: str
    conditions: tuple[ShownCondition, ...]
    sharpen: tuple[SharpenQuestion, ...]
    activities: tuple[SuggestedActivity, ...]
    questions_asked: int


_BAND_RANK: dict[Band, int] = {
    Band.UNLIKELY: 0,
    Band.POSSIBLE: 1,
    Band.LIKELY: 2,
    Band.STRONG: 3,
}


def _select_activities(
    dataset: Dataset, assessed_age_m: int, shown: tuple[ShownCondition, ...]
) -> tuple[SuggestedActivity, ...]:
    """Picks activities whose linked conditions actually showed up in this
    child's results, at or above the activity's own `min_band` threshold, and
    whose age window fits the child's assessed age. Ranked by the strongest
    matching condition's probability, so the activities with the clearest
    reason to ask for a clip surface first."""
    shown_by_key = {c.key: c for c in shown}
    candidates: list[tuple[Activity, float]] = []
    for activity in dataset.activities:
        if not (activity.age.window_start_m <= assessed_age_m <= activity.age.window_end_m):
            continue
        min_rank = _BAND_RANK[activity.min_band]
        matching = [
            shown_by_key[key]
            for key in activity.conditions
            if key in shown_by_key and _BAND_RANK[shown_by_key[key].band] >= min_rank
        ]
        if not matching:
            continue
        candidates.append((activity, max(c.probability for c in matching)))

    candidates.sort(key=lambda pair: (-pair[1], pair[0].priority, pair[0].id))

    return tuple(
        SuggestedActivity(
            id=activity.id,
            title=activity.title,
            media_type=activity.media_type,
            instructions=activity.instructions,
            what_we_look_for=activity.what_we_look_for,
            conditions=tuple(activity.conditions),
        )
        for activity, _ in candidates[: dataset.activities_config.max_shown]
    )


def _band_for(p: float, bands: list[BandCfg]) -> Band:
    # bands are validated at load time to be sorted descending with a 0.0 floor
    for b in bands:
        if p >= b.min:
            return Band(b.band)
    return Band.UNLIKELY


def _recheck_text(a: int, recheck_ranges: list[RecheckRange]) -> str:
    for r in recheck_ranges:
        if r.min_m <= a <= r.max_m:
            return r.text
    return recheck_ranges[-1].text


def _evidence_for(condition_key: str, posterior: Posterior) -> tuple[EvidenceItem, ...]:
    items = [
        EvidenceItem(question_id=step.answer.question_id, delta=term.delta)
        for step in posterior.evidence_log
        for term in step.terms
        if term.condition == condition_key
    ] + [
        # measured evidence is listed as "obs:<observation id>"
        EvidenceItem(question_id=f"obs:{entry.observation.id}", delta=term.delta)
        for entry in posterior.observation_log
        for term in entry.terms
        if term.condition == condition_key
    ]
    return tuple(sorted(items, key=lambda i: -abs(i.delta)))


def _shown_conditions(dataset: Dataset, posterior: Posterior) -> tuple[ShownCondition, ...]:
    show_if = dataset.results.show_if
    shown = []
    for condition in dataset.conditions:
        elig = posterior.eligibility[condition.key]
        p = posterior.probabilities[condition.key]
        is_shown = (elig is Eligibility.OK and p >= show_if.ok) or (
            elig is Eligibility.WATCH and p >= show_if.watch
        )
        if not is_shown:
            continue
        shown.append(
            ShownCondition(
                key=condition.key,
                probability=p,
                band=_band_for(p, dataset.results.bands),
                eligibility=elig,
                evidence=_evidence_for(condition.key, posterior),
            )
        )
    return tuple(sorted(shown, key=lambda c: -c.probability))


def _resolve_action(
    state: SessionState,
    dataset: Dataset,
    index: DatasetIndex,
    rules_config: RulesConfig,
    posterior: Posterior,
    shown: tuple[ShownCondition, ...],
) -> Action:
    if urgent_answered_question_ids(state, dataset, index):
        return Action.URGENT
    if major_milestone_missed(state, posterior.assessed_age_m, dataset, index, rules_config):
        return Action.REFER
    if any(c.eligibility is Eligibility.OK and c.probability >= 0.30 for c in shown):
        return Action.REFER
    if shown:
        return Action.WATCH
    return Action.ON_TRACK


def build_results(
    state: SessionState, dataset: Dataset, index: DatasetIndex, rules_config: RulesConfig
) -> Results:
    posterior = compute_posterior(state, dataset, index, rules_config)
    shown = _shown_conditions(dataset, posterior)
    action = _resolve_action(state, dataset, index, rules_config, posterior, shown)

    action_cfg = next(a for a in dataset.results.actions if a.action == action.value)
    recheck_text = _recheck_text(posterior.assessed_age_m, dataset.results.recheck)
    title = action_cfg.title.format(recheck=recheck_text)

    hearing_test = hearing_first_triggered(state, dataset, index, rules_config)

    steps: list[str] = []
    if hearing_test:
        steps.append("Get a hearing test first.")
    for shown_condition in shown:
        if shown_condition.eligibility is Eligibility.OK and shown_condition.band in (
            Band.STRONG,
            Band.LIKELY,
        ):
            steps.append(index.conditions_by_key[shown_condition.key].refer)
    steps.append(f"Check development again {recheck_text}.")

    ranked_remaining = rank_remaining(state, dataset, index, posterior)
    sharpen = tuple(
        SharpenQuestion(
            question_id=c.question_id,
            question_text=index.questions_by_id[c.question_id].question,
        )
        for c in ranked_remaining[: dataset.results.sharpen_count]
    )

    activities = _select_activities(dataset, posterior.assessed_age_m, shown)

    return Results(
        action=action,
        title=title,
        steps=tuple(steps),
        hearing_test=hearing_test,
        recheck=recheck_text,
        conditions=shown,
        sharpen=sharpen,
        activities=activities,
        questions_asked=len(state.answers),
    )

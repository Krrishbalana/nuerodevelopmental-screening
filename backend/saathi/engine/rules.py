"""Safety rules that sit above the probability math. design doc section 14,
BUILD_PROMPT 3.3.9. Each rule is a small pure function; `apply_rules` combines
the two that cap probabilities (spcd_requires_no_rrb, late_talker_requires_typical_social)
and reports fired/not-fired events for every rule that conditionally fires on
answers (the always-true rules age_gates / no_diagnosis_language / recheck_always
are structural invariants enforced elsewhere and are not reported as events).
"""

from collections.abc import Iterator
from dataclasses import dataclass

from saathi.domain.dataset import Dataset, Question
from saathi.domain.dataset_index import DatasetIndex
from saathi.domain.enums import Direction, QuestionType, RuleId
from saathi.domain.session_state import Answer, SessionState
from saathi.engine.formulas.answer_options import direction_and_weight
from saathi.engine.rules_config import RulesConfig


@dataclass(frozen=True)
class RuleEvent:
    rule_id: RuleId
    fired: bool


def _present_answers(
    state: SessionState, dataset: Dataset, index: DatasetIndex
) -> Iterator[tuple[Answer, Question]]:
    for ans in state.answers:
        direction, _weight = direction_and_weight(ans.key, dataset)
        if direction is Direction.PRESENT:
            yield ans, index.questions_by_id[ans.question_id]


def pending_urgent_questions(
    state: SessionState, dataset: Dataset, index: DatasetIndex
) -> frozenset[str]:
    """Urgent questions answered Yes/Probably and not yet acknowledged — gates the
    live question flow (blocks `next_step` until acknowledged)."""
    return frozenset(
        ans.question_id
        for ans, q in _present_answers(state, dataset, index)
        if q.is_urgent and ans.question_id not in state.acks
    )


def urgent_answered_question_ids(
    state: SessionState, dataset: Dataset, index: DatasetIndex
) -> frozenset[str]:
    """Urgent questions ever answered Yes/Probably, regardless of acknowledgment —
    used for the final results action (design doc 12.3 / 14.1: once a red flag is
    present the result stays 'urgent' even after the parent acknowledges it)."""
    return frozenset(
        ans.question_id for ans, q in _present_answers(state, dataset, index) if q.is_urgent
    )


def major_milestone_missed(
    state: SessionState, a: int, dataset: Dataset, index: DatasetIndex, rules_config: RulesConfig
) -> bool:
    for _ans, q in _present_answers(state, dataset, index):
        if (
            q.type is QuestionType.MILESTONE
            and q.age.red_flag_m is not None
            and a >= rules_config.milestone_red_flag_multiplier * q.age.red_flag_m
        ):
            return True
    return False


def hearing_first_triggered(
    state: SessionState, dataset: Dataset, index: DatasetIndex, rules_config: RulesConfig
) -> bool:
    for _ans, q in _present_answers(state, dataset, index):
        if any(link.condition == rules_config.hl_condition_key for link in q.links):
            return True
    # A measured finding that raises hearing loss (e.g. no turn to name on camera) also puts hearing first.
    for obs in state.observations:
        definition = index.observations_by_id.get(obs.id)
        outcome = definition.outcome(obs.outcome) if definition else None
        if outcome and any(lr.condition == rules_config.hl_condition_key and lr.lr > 1 for lr in outcome.lrs):
            return True
    return False


def spcd_cap_applies(
    state: SessionState, dataset: Dataset, index: DatasetIndex, rules_config: RulesConfig
) -> bool:
    return any(
        q.domain == rules_config.rrb_domain_key
        for _ans, q in _present_answers(state, dataset, index)
    )


def late_talker_cap_applies(
    state: SessionState, dataset: Dataset, index: DatasetIndex, rules_config: RulesConfig
) -> bool:
    count = 0
    for _ans, q in _present_answers(state, dataset, index):
        if q.domain not in rules_config.late_talker_domains:
            continue
        if any(
            link.condition == rules_config.asd_condition_key
            and link.strength == rules_config.late_talker_asd_strength
            for link in q.links
        ):
            count += 1
    return count >= rules_config.late_talker_threshold_count


def late_talker_is_past(a: int, dataset: Dataset, rules_config: RulesConfig) -> bool:
    lt_dx_max_m = next(
        c.dx_max_m for c in dataset.conditions if c.key == rules_config.lt_condition_key
    )
    return lt_dx_max_m is not None and a > lt_dx_max_m


def apply_rules(
    probabilities: dict[str, float],
    state: SessionState,
    a: int,
    dataset: Dataset,
    index: DatasetIndex,
    rules_config: RulesConfig,
) -> tuple[dict[str, float], list[RuleEvent]]:
    capped = dict(probabilities)
    events: list[RuleEvent] = []

    pending = pending_urgent_questions(state, dataset, index)
    events.append(RuleEvent(RuleId.URGENT_RED_FLAG, bool(pending)))

    events.append(
        RuleEvent(
            RuleId.MAJOR_MILESTONE_MISSED,
            major_milestone_missed(state, a, dataset, index, rules_config),
        )
    )
    events.append(
        RuleEvent(
            RuleId.HEARING_FIRST, hearing_first_triggered(state, dataset, index, rules_config)
        )
    )

    spcd_fired = spcd_cap_applies(state, dataset, index, rules_config)
    if spcd_fired:
        key = rules_config.spcd_condition_key
        capped[key] = min(capped[key], rules_config.spcd_cap)
    events.append(RuleEvent(RuleId.SPCD_REQUIRES_NO_RRB, spcd_fired))

    lt_fired = late_talker_cap_applies(state, dataset, index, rules_config)
    if lt_fired:
        key = rules_config.lt_condition_key
        capped[key] = min(capped[key], rules_config.lt_cap)
    events.append(RuleEvent(RuleId.LATE_TALKER_REQUIRES_TYPICAL_SOCIAL, lt_fired))

    events.append(
        RuleEvent(RuleId.LATE_TALKER_TO_DLD, late_talker_is_past(a, dataset, rules_config))
    )

    return capped, events

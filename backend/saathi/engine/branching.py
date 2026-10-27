"""Next-step decision: urgent -> pattern (once) -> max-questions stop -> always-first
-> best-scored candidate -> done. design doc section 11.2, BUILD_PROMPT 3.3.10.
"""

from dataclasses import dataclass

from saathi.domain.dataset import Dataset, Question
from saathi.domain.dataset_index import DatasetIndex
from saathi.domain.enums import Eligibility, StepType
from saathi.domain.session_state import SessionState
from saathi.engine.formulas.eligibility import askable
from saathi.engine.formulas.selection import (
    CandidateDetail,
    ScoreBreakdown,
    active_follow_up_ids,
    candidate_details,
    question_score,
    rank_candidates,
)
from saathi.engine.posterior import Posterior, compute_posterior
from saathi.engine.rules import pending_urgent_questions
from saathi.engine.rules_config import RulesConfig

PATTERN_ACK_KEY = "__pattern_shown__"


@dataclass(frozen=True)
class Step:
    type: StepType
    question: Question | None = None
    number: int | None = None
    reason_kind: str | None = None  # "first" | "separate" | "check"
    reason_conditions: tuple[str, ...] = ()
    candidates: tuple[CandidateDetail, ...] = ()
    urgent_question_ids: tuple[str, ...] = ()
    pattern_condition: str | None = None
    pattern_probability: float | None = None
    preempted_by: str | None = None


def _askable_unanswered_questions(
    state: SessionState, dataset: Dataset, index: DatasetIndex, a: int
) -> list[Question]:
    answered = state.answered_question_ids()
    return [q for q in dataset.questions if q.id not in answered and askable(q, a)]


def _top_reason(breakdown: ScoreBreakdown) -> tuple[str, tuple[str, ...]]:
    ranked_conditions = sorted(breakdown.per_condition.items(), key=lambda kv: -kv[1])
    top_conditions = tuple(key for key, _contribution in ranked_conditions[:2] if _contribution > 0)
    if len(top_conditions) >= 2:
        return "separate", top_conditions[:2]
    if len(top_conditions) == 1:
        return "check", top_conditions
    return "check", ()


def rank_remaining(
    state: SessionState, dataset: Dataset, index: DatasetIndex, posterior: Posterior
) -> list[ScoreBreakdown]:
    """Askable, unanswered questions ranked by selection score (best first)."""
    a = posterior.assessed_age_m
    candidates = _askable_unanswered_questions(state, dataset, index, a)
    answered_domains = frozenset(
        index.questions_by_id[ans.question_id].domain for ans in state.answers
    )
    follow_up_active = active_follow_up_ids(state.answers, dataset, index.questions_by_id)

    scored = [
        question_score(
            q,
            posterior.probabilities,
            posterior.eligibility,
            a,
            answered_domains,
            len(state.answers),
            follow_up_active,
            dataset,
        )
        for q in candidates
    ]
    return rank_candidates(scored)


def next_step(
    state: SessionState, dataset: Dataset, index: DatasetIndex, rules_config: RulesConfig
) -> Step:
    posterior: Posterior = compute_posterior(state, dataset, index, rules_config)
    a = posterior.assessed_age_m

    pending_urgent = pending_urgent_questions(state, dataset, index)
    if pending_urgent:
        return Step(type=StepType.URGENT, urgent_question_ids=tuple(sorted(pending_urgent)))

    pattern_cfg = dataset.branching.pattern_message
    if PATTERN_ACK_KEY not in state.acks and len(state.answers) >= pattern_cfg.min_answers:
        ok_probs = {
            key: p
            for key, p in posterior.probabilities.items()
            if posterior.eligibility[key] is Eligibility.OK
        }
        if ok_probs:
            top_key = max(ok_probs, key=lambda k: ok_probs[k])
            top_p = ok_probs[top_key]
            if top_p >= pattern_cfg.threshold:
                return Step(
                    type=StepType.PATTERN, pattern_condition=top_key, pattern_probability=top_p
                )

    if len(state.answers) >= dataset.branching.stop_rules.max_questions:
        return Step(type=StepType.DONE)

    for question in index.always_first_questions:
        if question.id not in state.answered_question_ids() and askable(question, a):
            return Step(
                type=StepType.QUESTION,
                question=question,
                number=len(state.answers) + 1,
                reason_kind="first",
                preempted_by="always_first",
            )

    ranked = rank_remaining(state, dataset, index, posterior)

    if not ranked or ranked[0].raw_score < dataset.branching.stop_rules.stop_when_best_score_below:
        return Step(type=StepType.DONE)

    best = ranked[0]
    best_question = index.questions_by_id[best.question_id]
    reason_kind, reason_conditions = _top_reason(best)

    return Step(
        type=StepType.QUESTION,
        question=best_question,
        number=len(state.answers) + 1,
        reason_kind=reason_kind,
        reason_conditions=reason_conditions,
        candidates=tuple(candidate_details(ranked)),
    )

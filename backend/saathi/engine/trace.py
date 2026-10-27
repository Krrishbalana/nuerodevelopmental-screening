"""Per-step trace for the visual path explorer: for every answered question,
its evidence terms, the probabilities/logits/eligibility after it, rule events,
and the candidate ranking that led to it being asked. design doc section 1.3 / 16.

Deterministic and clock-free: recomputes the posterior at each answer prefix
(O(n^2) in answer count, which is fine for <=28 answers).
"""

from dataclasses import dataclass

from saathi.domain.dataset import Dataset
from saathi.domain.dataset_index import DatasetIndex
from saathi.domain.enums import Eligibility
from saathi.domain.session_state import SessionState
from saathi.engine.branching import Step, next_step, rank_remaining
from saathi.engine.formulas.selection import CandidateDetail, candidate_details, follow_up_sources
from saathi.engine.formulas.update import EvidenceTerm
from saathi.engine.posterior import compute_posterior
from saathi.engine.rules import RuleEvent
from saathi.engine.rules_config import RulesConfig


@dataclass(frozen=True)
class TraceStep:
    step_index: int
    question_id: str
    question_text: str
    domain: str
    question_type: str
    is_urgent: bool
    answer_key: str
    assessed_age_m: int
    evidence: tuple[EvidenceTerm, ...]
    probabilities: dict[str, float]
    logits: dict[str, float]
    eligibility: dict[str, Eligibility]
    rule_events: tuple[RuleEvent, ...]
    candidates: tuple[CandidateDetail, ...]
    chosen_next_question_id: str | None
    triggered_by: str | None


@dataclass(frozen=True)
class Trace:
    steps: tuple[TraceStep, ...]
    final_step: Step


def build_trace(
    state: SessionState, dataset: Dataset, index: DatasetIndex, rules_config: RulesConfig
) -> Trace:
    steps: list[TraceStep] = []

    for i, ans in enumerate(state.answers):
        prior_state = state.model_copy(update={"answers": state.answers[:i]})
        prior_posterior = compute_posterior(prior_state, dataset, index, rules_config)
        ranked = rank_remaining(prior_state, dataset, index, prior_posterior)
        chosen = ranked[0].question_id if ranked else None
        triggered_by = follow_up_sources(prior_state.answers, dataset, index.questions_by_id).get(
            ans.question_id
        )

        after_state = state.model_copy(update={"answers": state.answers[: i + 1]})
        after_posterior = compute_posterior(after_state, dataset, index, rules_config)
        question = index.questions_by_id[ans.question_id]

        steps.append(
            TraceStep(
                step_index=i + 1,
                question_id=question.id,
                question_text=question.question,
                domain=question.domain,
                question_type=question.type.value,
                is_urgent=question.is_urgent,
                answer_key=ans.key.value,
                assessed_age_m=after_posterior.assessed_age_m,
                evidence=after_posterior.evidence_log[i].terms,
                probabilities=after_posterior.probabilities,
                logits=after_posterior.logits,
                eligibility=after_posterior.eligibility,
                rule_events=after_posterior.rule_events,
                candidates=tuple(candidate_details(ranked)),
                chosen_next_question_id=chosen,
                triggered_by=triggered_by,
            )
        )

    final_step = next_step(state, dataset, index, rules_config)
    return Trace(steps=tuple(steps), final_step=final_step)

"""Rebuilds the full posterior (log-odds, probabilities, eligibility, evidence log,
rule events) from scratch given a session's profile and ordered answers.
design doc section 11.3, BUILD_PROMPT 3.3.5-3.3.9.
"""

import math
from dataclasses import dataclass, replace

from saathi.domain.dataset import Dataset
from saathi.domain.dataset_index import DatasetIndex
from saathi.domain.enums import Direction, Eligibility
from saathi.domain.session_state import Answer, Observation, SessionState
from saathi.engine.formulas.age import assessed_age
from saathi.engine.formulas.answer_options import direction_and_weight
from saathi.engine.formulas.damping import DampingCounters
from saathi.engine.formulas.eligibility import eligibility
from saathi.engine.formulas.odds import sigmoid
from saathi.engine.formulas.priors import prior_logit
from saathi.engine.formulas.update import EvidenceTerm, evidence_delta
from saathi.engine.rules import RuleEvent, apply_rules
from saathi.engine.rules_config import RulesConfig


@dataclass(frozen=True)
class StepEvidence:
    answer: Answer
    terms: tuple[EvidenceTerm, ...]


@dataclass(frozen=True)
class ObservationTerm:
    condition: str
    ln_lr: float
    confidence: float
    delta: float
    source: str  # published | extrapolated | estimated
    ref: str


@dataclass(frozen=True)
class ObservationEvidence:
    observation: Observation
    terms: tuple[ObservationTerm, ...]


@dataclass(frozen=True)
class Posterior:
    assessed_age_m: int
    logits: dict[str, float]
    probabilities: dict[str, float]
    eligibility: dict[str, Eligibility]
    evidence_log: tuple[StepEvidence, ...]
    rule_events: tuple[RuleEvent, ...]
    observation_log: tuple[ObservationEvidence, ...] = ()


def compute_posterior(
    state: SessionState, dataset: Dataset, index: DatasetIndex, rules_config: RulesConfig
) -> Posterior:
    a = assessed_age(state.profile.chronological_age_m, state.profile.born, dataset.age_lens)

    logits = {c.key: prior_logit(c, state.profile, dataset) for c in dataset.conditions}
    counters = DampingCounters()
    evidence_log: list[StepEvidence] = []

    # Measured observations first: ln(LR) x confidence. No age lens (the LR is already for this
    # age, or labelled extrapolated) and no domain damping (that models one parent's overall worry).
    observation_log: list[ObservationEvidence] = []
    # question id -> condition -> sign of the observation's evidence, for construct damping
    construct_sign: dict[str, dict[str, float]] = {}
    obs_config = dataset.observation_config
    for obs in state.observations:
        definition = index.observations_by_id.get(obs.id)
        outcome = definition.outcome(obs.outcome) if definition else None
        if definition is None or outcome is None:
            observation_log.append(ObservationEvidence(observation=obs, terms=()))
            continue
        obs_terms: list[ObservationTerm] = []
        used: set[str] = set()
        for lr in outcome.lrs:
            if lr.condition in used or not lr.applies_at(a):
                continue
            used.add(lr.condition)
            ln_lr = math.log(lr.lr)
            delta = ln_lr * obs.confidence
            logits[lr.condition] += delta
            obs_terms.append(ObservationTerm(lr.condition, ln_lr, obs.confidence, delta, lr.source, lr.ref))
            if delta != 0:
                for qid in definition.construct_question_ids:
                    construct_sign.setdefault(qid, {})[lr.condition] = math.copysign(1.0, delta)
        observation_log.append(ObservationEvidence(observation=obs, terms=tuple(obs_terms)))

    for ans in state.answers:
        direction, weight = direction_and_weight(ans.key, dataset)
        if direction is Direction.UNKNOWN:
            evidence_log.append(StepEvidence(answer=ans, terms=()))
            continue

        question = index.questions_by_id[ans.question_id]
        terms: list[EvidenceTerm] = []
        for link in question.links:
            term = evidence_delta(
                link,
                question,
                direction,
                weight,
                a,
                counters,
                dataset.age_lens,
                dataset.update.damping,
            )
            # Same behaviour already measured and pointing the same way: count the answer at half weight.
            measured = construct_sign.get(ans.question_id, {}).get(link.condition)
            if measured is not None and term.delta != 0 and math.copysign(1.0, term.delta) == measured:
                cd = obs_config.construct_damping
                term = replace(term, damping=term.damping * cd, delta=term.delta * cd)
            logits[link.condition] += term.delta
            terms.append(term)
            counters = counters.incremented(link.condition, question.domain, direction)
        evidence_log.append(StepEvidence(answer=ans, terms=tuple(terms)))

    raw_probabilities = {
        key: min(dataset.update.probability_cap, sigmoid(value)) for key, value in logits.items()
    }
    probabilities, rule_events = apply_rules(
        raw_probabilities, state, a, dataset, index, rules_config
    )

    eligibility_map = {
        c.key: eligibility(c, a, dataset.age_lens.eligibility.hidden_margin_m)
        for c in dataset.conditions
    }

    return Posterior(
        assessed_age_m=a,
        logits=logits,
        probabilities=probabilities,
        eligibility=eligibility_map,
        evidence_log=tuple(evidence_log),
        rule_events=tuple(rule_events),
        observation_log=tuple(observation_log),
    )

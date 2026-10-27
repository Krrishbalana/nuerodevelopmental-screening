"""Next-question scoring and 'chance of being picked'. design doc section 10,
BUILD_PROMPT 3.3.8 and 3.4.
"""

import math
from dataclasses import dataclass

from saathi.domain.dataset import Dataset, Question
from saathi.domain.enums import Direction, Eligibility
from saathi.domain.session_state import Answer
from saathi.engine.formulas.age_lens import exponent, situation
from saathi.engine.formulas.answer_options import direction_and_weight


@dataclass(frozen=True)
class ScoreBreakdown:
    question_id: str
    raw_score: float
    per_condition: dict[str, float]
    bonuses_applied: tuple[str, ...]


@dataclass(frozen=True)
class PickShare:
    question_id: str
    rank: int
    raw_score: float
    share: float
    gap_to_top: float


@dataclass(frozen=True)
class CandidateDetail:
    """PickShare plus the ScoreBreakdown it was ranked from, for the "why this
    question" panel (per-condition contribution + which bonuses applied)."""

    question_id: str
    rank: int
    raw_score: float
    share: float
    gap_to_top: float
    per_condition: dict[str, float]
    bonuses_applied: tuple[str, ...]


def follow_up_sources(
    answers: tuple[Answer, ...], dataset: Dataset, questions_by_id: dict[str, Question]
) -> dict[str, str]:
    """Maps a follow-up question id to the question id of the Yes/Probably
    answer that put it on the follow-up list (the most recent one, if more
    than one earlier answer lists it), for the path-graph's dotted link."""
    horizon = dataset.branching.bonuses.follow_up_horizon_answers
    recent = answers[-horizon:] if horizon > 0 else ()
    sources: dict[str, str] = {}
    for ans in recent:
        direction, _weight = direction_and_weight(ans.key, dataset)
        if direction is Direction.PRESENT:
            for follow_up_id in questions_by_id[ans.question_id].follow_ups_if_yes:
                sources[follow_up_id] = ans.question_id
    return sources


def active_follow_up_ids(
    answers: tuple[Answer, ...], dataset: Dataset, questions_by_id: dict[str, Question]
) -> frozenset[str]:
    return frozenset(follow_up_sources(answers, dataset, questions_by_id).keys())


def question_score(
    question: Question,
    probabilities: dict[str, float],
    eligibility_map: dict[str, Eligibility],
    a: int,
    answered_domains: frozenset[str],
    answers_so_far: int,
    follow_up_active_ids: frozenset[str],
    dataset: Dataset,
) -> ScoreBreakdown:
    weights = dataset.branching.eligibility_weights
    per_condition: dict[str, float] = {}
    base = 0.0
    for link in question.links:
        elig = eligibility_map.get(link.condition)
        if elig is None:
            continue
        w_elig = weights.weight_for(elig)
        if w_elig == 0:
            continue
        p = probabilities[link.condition]
        exp_present = exponent(
            situation(question, a, Direction.PRESENT), Direction.PRESENT, dataset.age_lens
        )
        exp_absent = exponent(
            situation(question, a, Direction.ABSENT), Direction.ABSENT, dataset.age_lens
        )
        leverage = (
            abs(math.log(link.lr_present)) * exp_present
            + abs(math.log(link.lr_absent)) * exp_absent
        )
        contribution = w_elig * p * (1 - p) * leverage
        per_condition[link.condition] = contribution
        base += contribution

    bonuses = dataset.branching.bonuses
    multiplier = 1.0
    applied: list[str] = []
    if (
        question.domain not in answered_domains
        and answers_so_far < bonuses.new_domain_until_answers
    ):
        multiplier *= bonuses.new_domain
        applied.append("new_domain")
    if question.is_urgent:
        multiplier *= bonuses.urgent_question
        applied.append("urgent_question")
    if question.id in follow_up_active_ids:
        multiplier *= bonuses.follow_up
        applied.append("follow_up")

    return ScoreBreakdown(
        question_id=question.id,
        raw_score=multiplier * base,
        per_condition=per_condition,
        bonuses_applied=tuple(applied),
    )


def rank_candidates(candidates: list[ScoreBreakdown]) -> list[ScoreBreakdown]:
    """Deterministic ranking: highest score first, ties broken by question id (3.3.8)."""
    return sorted(candidates, key=lambda c: (-c.raw_score, c.question_id))


def pick_chance(ranked: list[ScoreBreakdown], top_k: int = 5) -> list[PickShare]:
    top = ranked[:top_k]
    total = sum(c.raw_score for c in top)
    top_score = ranked[0].raw_score if ranked else 0.0
    return [
        PickShare(
            question_id=c.question_id,
            rank=i + 1,
            raw_score=c.raw_score,
            share=(c.raw_score / total) if total else 0.0,
            gap_to_top=top_score - c.raw_score,
        )
        for i, c in enumerate(top)
    ]


def candidate_details(ranked: list[ScoreBreakdown], top_k: int = 5) -> list[CandidateDetail]:
    shares = pick_chance(ranked, top_k)
    by_id = {c.question_id: c for c in ranked}
    return [
        CandidateDetail(
            question_id=s.question_id,
            rank=s.rank,
            raw_score=s.raw_score,
            share=s.share,
            gap_to_top=s.gap_to_top,
            per_condition=by_id[s.question_id].per_condition,
            bonuses_applied=by_id[s.question_id].bonuses_applied,
        )
        for s in shares
    ]

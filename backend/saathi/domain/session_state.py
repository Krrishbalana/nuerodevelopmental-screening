"""Immutable session state. The engine recomputes everything from this on every call;
no derived value (probabilities, eligibility, step) is ever stored here.
"""

from pydantic import BaseModel, ConfigDict

from saathi.domain.enums import AnswerKey, Born, Sex


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ChildProfile(_Frozen):
    age_years: int
    age_months: int
    sex: Sex
    born: Born
    family_factors: tuple[str, ...] = ()

    @property
    def chronological_age_m(self) -> int:
        return self.age_years * 12 + self.age_months


class Answer(_Frozen):
    question_id: str
    key: AnswerKey
    answered_at_step: int


class Observation(_Frozen):
    """A measured finding (e.g. from the camera session): which observation, which outcome, how sure."""

    id: str
    outcome: str
    confidence: float = 1.0  # 0..1, multiplies the evidence


class SessionState(_Frozen):
    session_id: str
    profile: ChildProfile
    observations: tuple[Observation, ...] = ()
    answers: tuple[Answer, ...] = ()
    acks: frozenset[str] = frozenset()
    branch_point: int | None = None

    def with_answer(self, question_id: str, key: AnswerKey) -> "SessionState":
        next_step = len(self.answers) + 1
        return self.model_copy(
            update={
                "answers": (
                    *self.answers,
                    Answer(question_id=question_id, key=key, answered_at_step=next_step),
                )
            }
        )

    def without_last_answer(self) -> "SessionState":
        if not self.answers:
            return self
        dropped = self.answers[-1]
        remaining_acks = frozenset(a for a in self.acks if a != dropped.question_id)
        return self.model_copy(update={"answers": self.answers[:-1], "acks": remaining_acks})

    def with_ack(self, key: str) -> "SessionState":
        return self.model_copy(update={"acks": self.acks | {key}})

    def answered_question_ids(self) -> frozenset[str]:
        return frozenset(a.question_id for a in self.answers)

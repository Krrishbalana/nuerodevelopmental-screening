"""Per-answer, per-condition evidence delta. design doc section 8.2, BUILD_PROMPT 3.3.6.

`delta = ln(LR_d) * exponent * weight * damping`. Callers must skip direction ==
Direction.UNKNOWN (don't-know answers carry no information and must not be
damped); this module asserts that invariant rather than silently handling it.
"""

import math
from dataclasses import dataclass

from saathi.domain.dataset import AgeLens, DampingConfig, Link, Question
from saathi.domain.enums import Direction, Situation
from saathi.engine.formulas.age_lens import exponent, situation
from saathi.engine.formulas.damping import DampingCounters


@dataclass(frozen=True)
class EvidenceTerm:
    condition: str
    ln_lr: float
    exponent: float
    weight: float
    damping: float
    delta: float
    situation: Situation


def evidence_delta(
    link: Link,
    question: Question,
    direction: Direction,
    weight: float,
    a: int,
    counters: DampingCounters,
    age_lens: AgeLens,
    damping_config: DampingConfig,
) -> EvidenceTerm:
    assert direction is not Direction.UNKNOWN, "dk answers must be filtered out by the caller"

    sit = situation(question, a, direction)
    exp = exponent(sit, direction, age_lens)
    lr = link.lr_present if direction is Direction.PRESENT else link.lr_absent
    damping = counters.factor(link.condition, question.domain, direction, damping_config)
    ln_lr = math.log(lr)
    delta = ln_lr * exp * weight * damping

    return EvidenceTerm(
        condition=link.condition,
        ln_lr=ln_lr,
        exponent=exp,
        weight=weight,
        damping=damping,
        delta=delta,
        situation=sit,
    )

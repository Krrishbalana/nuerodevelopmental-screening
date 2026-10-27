"""Damping for correlated evidence. design doc section 8.1,
BUILD_PROMPT 3.3.6: both directions damped, counted separately; counters
incremented *after* the current answer's delta is computed.
"""

from dataclasses import dataclass, field

from saathi.domain.dataset import DampingConfig
from saathi.domain.enums import Direction

_DomainKey = tuple[str, str, Direction]
_ConditionKey = tuple[str, Direction]


@dataclass(frozen=True)
class DampingCounters:
    same_domain: dict[_DomainKey, int] = field(default_factory=dict)
    same_condition: dict[_ConditionKey, int] = field(default_factory=dict)

    def factor(
        self, condition_key: str, domain: str, direction: Direction, config: DampingConfig
    ) -> float:
        n_domain = self.same_domain.get((condition_key, domain, direction), 0)
        n_cond = self.same_condition.get((condition_key, direction), 0)
        return (config.same_domain**n_domain) * (config.same_condition**n_cond)

    def incremented(
        self, condition_key: str, domain: str, direction: Direction
    ) -> "DampingCounters":
        domain_key: _DomainKey = (condition_key, domain, direction)
        cond_key: _ConditionKey = (condition_key, direction)
        new_domain = {**self.same_domain, domain_key: self.same_domain.get(domain_key, 0) + 1}
        new_cond = {**self.same_condition, cond_key: self.same_condition.get(cond_key, 0) + 1}
        return DampingCounters(same_domain=new_domain, same_condition=new_cond)

"""Numeric constants for the 9 rules in adaptive-screening-dataset.json that are
expressed only as prose (`rules[].when` / `.then`), not structured data.

TODO(dataset v2): migrate these into the dataset JSON (e.g. a `rules_config` block
per rule) so rule thresholds version alongside the rest of the clinical content
instead of living in code. Tracked per BUILD_PROMPT.md section 3.3.9.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RulesConfig:
    spcd_cap: float = 0.10
    """rules[id=spcd_requires_no_rrb].then: 'Cap SPCD at 0.10'"""

    lt_cap: float = 0.25
    """rules[id=late_talker_requires_typical_social].then: 'Cap LT at 0.25'"""

    milestone_red_flag_multiplier: float = 1.5
    """rules[id=major_milestone_missed].when: 'at least 1.5 times its red-flag age'"""

    late_talker_domains: frozenset[str] = field(
        default_factory=lambda: frozenset({"SOC", "PRE", "PLAY"})
    )
    """rules[id=late_talker_requires_typical_social].when: questions in SOC/PRE/PLAY"""

    late_talker_asd_strength: int = 3
    """rules[id=late_talker_requires_typical_social].when: 'core autism signs (strength 3)'"""

    late_talker_threshold_count: int = 2
    """rules[id=late_talker_requires_typical_social].when: '2 or more Yes/Probably answers'"""

    late_talker_to_dld_age_m: int = 42
    """rules[id=late_talker_to_dld].when: 'Age above 42 months' (must equal LT.dx_max_m)"""

    spcd_condition_key: str = "SPCD"
    lt_condition_key: str = "LT"
    asd_condition_key: str = "ASD"
    rrb_domain_key: str = "RRB"
    hl_condition_key: str = "HL"

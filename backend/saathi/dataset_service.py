"""Loads adaptive-screening-dataset.json once at startup, validates it, and builds
the lookup indices the engine needs. The app refuses to start if validation fails.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from saathi.errors import DatasetIntegrityError
from saathi.domain.dataset import Dataset, PriorModifier
from saathi.domain.dataset_index import DatasetIndex, build_dataset_index
from saathi.engine.rules_config import RulesConfig


def selectable_family_factors(dataset: Dataset) -> list[PriorModifier]:
    """`prior_modifiers` entries a parent can actually pick in the setup form -
    excludes preterm_*/sex_* which are derived from the born/sex profile fields."""
    return [pm for pm in dataset.prior_modifiers if not pm.factor.startswith(("preterm_", "sex_"))]


@dataclass(frozen=True)
class DatasetBundle:
    dataset: Dataset
    index: DatasetIndex
    rules_config: RulesConfig
    version_hash: str


def validate_referential_integrity(dataset: Dataset) -> list[str]:
    """Collects *all* violations rather than failing on the first, so a single
    startup error message is complete.
    """
    violations: list[str] = []

    question_ids = {q.id for q in dataset.questions}
    condition_keys = {c.key for c in dataset.conditions}
    domain_keys = {d.key for d in dataset.domains}
    lr_strengths = {d.strength for d in dataset.likelihood_ratio_defaults}

    seen_question_ids: set[str] = set()
    for q in dataset.questions:
        if q.id in seen_question_ids:
            violations.append(f"questions: duplicate id {q.id!r}")
        seen_question_ids.add(q.id)

        if q.domain not in domain_keys:
            violations.append(f"questions[{q.id}].domain: unknown domain {q.domain!r}")

        for fid in q.follow_ups_if_yes:
            if fid not in question_ids:
                violations.append(
                    f"questions[{q.id}].follow_ups_if_yes: unknown question id {fid!r}"
                )

        for link in q.links:
            if link.condition not in condition_keys:
                violations.append(f"questions[{q.id}].links: unknown condition {link.condition!r}")
            if link.strength not in lr_strengths:
                violations.append(
                    f"questions[{q.id}].links: unknown strength tier {link.strength!r}"
                )

        if q.age.window_start_m > q.age.window_end_m:
            violations.append(
                f"questions[{q.id}].age: window_start_m ({q.age.window_start_m}) "
                f"> window_end_m ({q.age.window_end_m})"
            )

    seen_condition_keys: set[str] = set()
    for c in dataset.conditions:
        if c.key in seen_condition_keys:
            violations.append(f"conditions: duplicate key {c.key!r}")
        seen_condition_keys.add(c.key)

        if c.transitions_to is not None and c.transitions_to not in condition_keys:
            violations.append(
                f"conditions[{c.key}].transitions_to: unknown condition {c.transitions_to!r}"
            )
        if c.dx_max_m is not None and c.dx_min_m > c.dx_max_m:
            violations.append(
                f"conditions[{c.key}]: dx_min_m ({c.dx_min_m}) > dx_max_m ({c.dx_max_m})"
            )

    for pm in dataset.prior_modifiers:
        for cond_key in pm.odds_multipliers:
            if cond_key not in condition_keys:
                violations.append(
                    f"prior_modifiers[{pm.factor}].odds_multipliers: unknown condition {cond_key!r}"
                )

    for qid in dataset.branching.always_first:
        if qid not in question_ids:
            violations.append(f"branching.always_first: unknown question id {qid!r}")

    sorted_bands = sorted(dataset.results.bands, key=lambda b: b.min, reverse=True)
    if [b.min for b in dataset.results.bands] != [b.min for b in sorted_bands]:
        violations.append("results.bands: must be sorted descending by `min`")
    if not dataset.results.bands or min(b.min for b in dataset.results.bands) != 0.0:
        violations.append("results.bands: must include a band with min == 0.0")

    seen_activity_ids: set[str] = set()
    for a in dataset.activities:
        if a.id in seen_activity_ids:
            violations.append(f"activities: duplicate id {a.id!r}")
        seen_activity_ids.add(a.id)

        if a.domain not in domain_keys:
            violations.append(f"activities[{a.id}].domain: unknown domain {a.domain!r}")

        for cond_key in a.conditions:
            if cond_key not in condition_keys:
                violations.append(
                    f"activities[{a.id}].conditions: unknown condition {cond_key!r}"
                )

        if a.age.window_start_m > a.age.window_end_m:
            violations.append(
                f"activities[{a.id}].age: window_start_m ({a.age.window_start_m}) "
                f"> window_end_m ({a.age.window_end_m})"
            )

    for vp in dataset.validation_profiles.profiles:
        for qid in vp.yes_to:
            if qid not in question_ids:
                violations.append(
                    f"validation_profiles[{vp.profile}].yes_to: unknown question id {qid!r}"
                )
        for rt in vp.result_top:
            if rt.condition not in condition_keys:
                violations.append(
                    f"validation_profiles[{vp.profile}].result_top: "
                    f"unknown condition {rt.condition!r}"
                )

    return violations


def validate_rules_config(dataset: Dataset, rules_config: RulesConfig) -> list[str]:
    """Cross-checks the hardcoded rules_config constants against the dataset
    (see app/engine/rules_config.py docstring)."""
    violations: list[str] = []
    condition_keys = {c.key for c in dataset.conditions}
    domain_keys = {d.key for d in dataset.domains}

    for key in (
        rules_config.spcd_condition_key,
        rules_config.lt_condition_key,
        rules_config.asd_condition_key,
        rules_config.hl_condition_key,
    ):
        if key not in condition_keys:
            violations.append(f"rules_config: unknown condition key {key!r}")

    if rules_config.rrb_domain_key not in domain_keys:
        violations.append(f"rules_config: unknown domain key {rules_config.rrb_domain_key!r}")

    for domain in rules_config.late_talker_domains:
        if domain not in domain_keys:
            violations.append(f"rules_config.late_talker_domains: unknown domain {domain!r}")

    lt = next((c for c in dataset.conditions if c.key == rules_config.lt_condition_key), None)
    if lt is not None and lt.dx_max_m != rules_config.late_talker_to_dld_age_m:
        violations.append(
            f"rules_config.late_talker_to_dld_age_m "
            f"({rules_config.late_talker_to_dld_age_m}) does not match "
            f"conditions[LT].dx_max_m ({lt.dx_max_m})"
        )

    return violations


def load_dataset(path: Path, observations_path: Path | None = None) -> tuple[Dataset, str]:
    raw_bytes = path.read_bytes()
    raw = json.loads(raw_bytes)
    digest = hashlib.sha256(raw_bytes)
    if observations_path is not None:
        obs_bytes = observations_path.read_bytes()
        obs = json.loads(obs_bytes)
        obs.pop("_note", None)
        raw["observation_config"] = obs
        digest.update(obs_bytes)
    dataset = Dataset.model_validate(raw)
    return dataset, digest.hexdigest()


def validate_observations(dataset: Dataset) -> list[str]:
    violations: list[str] = []
    conditions = {c.key for c in dataset.conditions}
    questions = {q.id for q in dataset.questions}
    domains = {d.key for d in dataset.domains}
    seen: set[str] = set()
    for obs in dataset.observation_config.observations:
        if obs.id in seen:
            violations.append(f"observation {obs.id}: duplicate id")
        seen.add(obs.id)
        if obs.domain not in domains:
            violations.append(f"observation {obs.id}: unknown domain {obs.domain!r}")
        for qid in obs.construct_question_ids:
            if qid not in questions:
                violations.append(f"observation {obs.id}: unknown construct question {qid!r}")
        keys = [o.key for o in obs.outcomes]
        if len(keys) != len(set(keys)):
            violations.append(f"observation {obs.id}: duplicate outcome keys")
        for outcome in obs.outcomes:
            for lr in outcome.lrs:
                if lr.condition not in conditions:
                    violations.append(f"observation {obs.id}/{outcome.key}: unknown condition {lr.condition!r}")
                if lr.age_months is not None and lr.age_months[0] > lr.age_months[1]:
                    violations.append(f"observation {obs.id}/{outcome.key}: age range reversed")
    return violations


def load_bundle(
    path: Path, rules_config: RulesConfig | None = None, observations_path: Path | None = None
) -> DatasetBundle:
    rules_config = rules_config or RulesConfig()
    dataset, version_hash = load_dataset(path, observations_path)

    violations = validate_referential_integrity(dataset)
    violations += validate_observations(dataset)
    violations += validate_rules_config(dataset, rules_config)
    if violations:
        raise DatasetIntegrityError(violations)

    index = build_dataset_index(dataset)
    return DatasetBundle(
        dataset=dataset, index=index, rules_config=rules_config, version_hash=version_hash
    )

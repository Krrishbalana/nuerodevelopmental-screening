"""Camera session report → Saathi observations.

Only measured results become evidence: a module that couldn't be measured ("insufficient") adds
nothing. Confidence (high/medium) scales the evidence using the weights in observations.json.
"""

from typing import Any

from saathi.domain.session_state import Observation

# camera metric key -> Saathi observation id
METRIC_TO_OBSERVATION = {
    "social_preference": "obs_social_preference",
    "name_response": "obs_name_response",
}


def from_report(report: dict[str, Any], confidence_weights: dict[str, float]) -> list[Observation]:
    observations = []
    for metric in report["clinician"]["metrics"]:
        obs_id = METRIC_TO_OBSERVATION.get(metric["key"])
        if obs_id is None or metric["status"] not in ("flagged", "not_flagged"):
            continue
        weight = confidence_weights.get(metric.get("confidence") or "", 0.0)
        if weight <= 0:
            continue
        observations.append(Observation(id=obs_id, outcome=metric["status"], confidence=weight))
    return observations

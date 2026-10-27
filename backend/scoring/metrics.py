from typing import Any, Literal

from pydantic import BaseModel

# flagged = met a published cut-off; not_flagged = didn't; insufficient = couldn't be measured.
Status = Literal["flagged", "not_flagged", "insufficient"]
Confidence = Literal["high", "medium", "low"]


class MetricResult(BaseModel):
    key: str
    label: str
    status: Status
    confidence: Confidence | None
    value: float | None
    unit: str
    # Clinician-facing one-liner; parent wording lives in report.py.
    summary: str
    reasons: list[str] = []
    trials: list[dict[str, Any]] = []
    thresholds: dict[str, Any] = {}
    reference: str = ""
    # Structured numbers the report generator reads (no parsing of summary text).
    details: dict[str, Any] = {}

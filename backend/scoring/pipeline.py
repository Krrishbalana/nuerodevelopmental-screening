"""Entry point: a full session upload in, both reports out. Pure: no I/O."""

from typing import Any

from . import config as C
from .gaze import calibrate
from .models import SessionUpload
from .name_response import score_name_response
from .quality import window_quality
from . import report
from .split_screen import score_split_screen
from .timeline import Timeline


class InvalidSession(ValueError):
    pass


def age_in_months(upload: SessionUpload) -> float:
    return (upload.child.session_date - upload.child.dob).days / 30.4375


def score_session(upload: SessionUpload) -> dict[str, Any]:
    age = age_in_months(upload)
    if not C.MIN_AGE_MONTHS <= age <= C.MAX_AGE_MONTHS:
        raise InvalidSession(
            f"Child is {age:.1f} months old; this check supports "
            f"{C.MIN_AGE_MONTHS}-{C.MAX_AGE_MONTHS} months"
        )
    if not upload.frames:
        raise InvalidSession("Session has no camera frames")

    frames = Timeline(upload.frames)
    audio = Timeline(upload.audio)
    brightness = Timeline(upload.brightness)

    calibration = calibrate(upload.frames, upload.calibration_points)
    metrics = [
        score_split_screen(frames, upload.split_screen_trials, calibration),
        score_name_response(frames, audio, upload.name_call_trials, upload.voice_check),
    ]

    windows = {
        "calibration": upload.calibration_points,
        "split_screen": upload.split_screen_trials,
        "name_call": upload.name_call_trials,
    }
    quality = {
        name: window_quality(frames, brightness, min(s.t_start for s in segs), max(s.t_end for s in segs))
        for name, segs in windows.items()
        if segs
    }

    views = report.build(metrics, calibration, quality, age)
    clinician = {
        **views["clinician"],
        "age_months": round(age, 1),
        "scoring_version": C.SCORING_VERSION,
        "stimulus_set": upload.stimulus_set,
        "thresholds_provisional": C.THRESHOLDS_PROVISIONAL,
        "calibration": calibration.summary(),
        "quality": {name: q.model_dump() for name, q in quality.items()},
        "metrics": [m.model_dump() for m in metrics],
        "viewport": upload.viewport.model_dump(),
        "frame_count": len(upload.frames),
        "median_frame_interval_ms": round(frames.median_dt(), 1),
    }
    return {"parent": views["parent"], "clinician": clinician}

"""Everything the analysis replay shows, computed by the same code that produces the report.

The replay must never disagree with the report, so nothing here re-implements a rule: gaze comes
from the session's calibration model, gaze classes from split_screen._classify_frame, name-call
onsets and turns from name_response. This module only lays the results out on a timeline.
"""

from statistics import median
from typing import Any

from . import config as C
from .gaze import calibrate
from .models import SessionUpload
from .name_response import score_name_response, voice_profile
from .split_screen import _classify_frame, score_split_screen
from .timeline import Timeline


def _r(x: float | None, nd: int = 3) -> float | None:
    return None if x is None else round(x, nd)


def build_replay(upload: SessionUpload) -> dict[str, Any]:
    frames = Timeline(upload.frames)
    audio = Timeline(upload.audio)
    calibration = calibrate(upload.frames, upload.calibration_points)
    model = calibration.model

    split_windows = [(t.t_start + C.SPLIT_SETTLE_MS, t.t_end) for t in upload.split_screen_trials]

    def in_split(t: float) -> bool:
        return any(a <= t <= b for a, b in split_windows)

    # Columnar per-frame series (compact JSON).
    cols: dict[str, list] = {
        "t": [], "face": [], "gx": [], "gy": [], "yaw": [], "pitch": [], "ix": [], "iy": [], "gaze": [],
    }
    for f in frames.items:
        gaze = model.predict(f) if model is not None else None
        cols["t"].append(round(f.t, 1))
        cols["face"].append(1 if f.face else 0)
        cols["gx"].append(_r(gaze[0]) if gaze else None)
        cols["gy"].append(_r(gaze[1]) if gaze else None)
        cols["yaw"].append(_r(f.yaw, 1))
        cols["pitch"].append(_r(f.pitch, 1))
        cols["ix"].append(_r(f.iris_x))
        cols["iy"].append(_r(f.iris_y))
        cols["gaze"].append(_classify_frame(gaze) if in_split(f.t) else None)

    split = score_split_screen(frames, upload.split_screen_trials, calibration)
    split_rows = {row["index"]: row for row in split.trials}
    split_trials = [
        {
            "index": t.index,
            "clip": t.clip if t.clip is not None else t.index,
            "social_side": t.social_side,
            "t_start": t.t_start,
            "t_end": t.t_end,
            "settle_end": t.t_start + C.SPLIT_SETTLE_MS,
            **{k: split_rows.get(t.index, {}).get(k) for k in ("valid", "looking_ms", "social_fraction")},
        }
        for t in upload.split_screen_trials
    ]

    name = score_name_response(frames, audio, upload.name_call_trials, upload.voice_check)
    name_rows = {row["index"]: row for row in name.trials}
    name_trials = []
    for t in upload.name_call_trials:
        row = name_rows.get(t.index, {})
        onset = t.t_start + row["onset_ms"] if row.get("onset_ms") is not None else t.cue_t
        turn_t = onset + row["latency_ms"] if row.get("latency_ms") is not None else None
        peak_turn = None
        if row.get("baseline_yaw") is not None:
            window = frames.between(onset + C.NAME_RESPONSE_START_MS, onset + C.NAME_RESPONSE_END_MS)
            devs = [abs(f.yaw - row["baseline_yaw"]) for f in window if f.face and f.yaw is not None]
            peak_turn = round(max(devs), 1) if devs else None
        name_trials.append({
            "index": t.index,
            "t_start": t.t_start,
            "cue_t": t.cue_t,
            "t_end": t.t_end,
            "onset_t": onset,
            "window_end": onset + C.NAME_RESPONSE_END_MS,
            "turn_t": turn_t,
            "peak_turn_deg": peak_turn,
            **{k: row.get(k) for k in (
                "onset_detected", "valid", "responded", "latency_ms", "latency_estimated", "mode", "reason",
                "baseline_yaw",
            )},
        })

    profile = voice_profile(audio, upload.voice_check)
    return {
        "duration_ms": frames.items[-1].t if frames.items else 0,
        "frames": cols,
        "audio": {"t": [round(a.t, 1) for a in audio.items], "rms": [round(a.rms, 4) for a in audio.items]},
        "calibration": {
            "summary": calibration.summary(),
            "points": [p.model_dump() for p in upload.calibration_points],
        },
        "split_trials": split_trials,
        "split_summary": {"status": split.status, "value": split.value, "summary": split.summary},
        "voice_check": None if upload.voice_check is None else {
            **upload.voice_check.model_dump(),
            "heard": profile is not None,
            **(profile.summary() if profile else {}),
        },
        "name_trials": name_trials,
        "name_summary": {"status": name.status, "value": name.value, "summary": name.summary},
        "settings": {
            "split_settle_ms": C.SPLIT_SETTLE_MS,
            "name_turn_deg": C.NAME_TURN_DEG,
            "social_flag_below": C.SPLIT_SOCIAL_FLAG_BELOW,
            "median_yaw": _r(median([y for y in cols["yaw"] if y is not None]), 1) if any(
                y is not None for y in cols["yaw"]) else None,
        },
    }

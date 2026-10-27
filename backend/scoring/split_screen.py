"""Social vs non-social preference (GeoPref-style split screen).

Each trial shows social content on one half and geometric motion on the
other; sides alternate so a child who simply prefers one side of the screen
is caught (side bias) instead of being scored.
"""

from . import config as C
from .gaze import CalibrationResult
from .metrics import Confidence, MetricResult
from .models import Frame, SplitScreenTrial
from .timeline import Timeline

LABEL = "Preference for social content"
REFERENCE = "Pierce et al. 2011, 2016 (GeoPref)"


def _classify_frame(gaze: tuple[float, float] | None) -> str:
    # Only the horizontal estimate is used: calibration validates x (left/right targets) but
    # never y, and webcam vertical gaze is too unreliable to call a frame off-screen.
    if gaze is None:
        return "invalid"
    gx = gaze[0]
    if not -C.SPLIT_OFFSCREEN_MARGIN <= gx <= 1 + C.SPLIT_OFFSCREEN_MARGIN:
        return "off"
    if C.SPLIT_CENTER_BAND[0] <= gx <= C.SPLIT_CENTER_BAND[1]:
        return "center"
    return "left" if gx < 0.5 else "right"


def score_split_screen(
    frames: Timeline[Frame],
    trials: list[SplitScreenTrial],
    calibration: CalibrationResult,
) -> MetricResult:
    thresholds = {
        "flag_below_social": C.SPLIT_SOCIAL_FLAG_BELOW,
        "min_look_ms_per_trial": C.SPLIT_MIN_LOOK_MS_PER_TRIAL,
        "min_valid_trials": C.SPLIT_MIN_VALID_TRIALS,
    }

    def insufficient(reason: str, trial_rows: list[dict] | None = None) -> MetricResult:
        return MetricResult(
            key="social_preference",
            label=LABEL,
            status="insufficient",
            confidence=None,
            value=None,
            unit="fraction",
            summary=f"Not scored: {reason}",
            reasons=[reason],
            trials=trial_rows or [],
            thresholds=thresholds,
            reference=REFERENCE,
        )

    if not trials:
        return insufficient("module not run")
    if calibration.model is None or not calibration.passed:
        return insufficient(f"gaze calibration {calibration.quality}")

    rows: list[dict] = []
    social_ms = geometric_ms = left_ms = right_ms = 0.0
    shown_ms = looked_total_ms = 0.0  # all trials, for the attention finding
    valid = 0
    sides_seen: set[str] = set()

    for trial in trials:
        counts = {"left": 0, "right": 0, "center": 0, "off": 0, "invalid": 0}
        window = frames.between(trial.t_start + C.SPLIT_SETTLE_MS, trial.t_end)
        for frame in window:
            counts[_classify_frame(calibration.model.predict(frame))] += 1
        # Frame gaps are uneven (detection loop and camera run at different rates), so time is
        # the share of frames times the window length, not frame count times a typical gap.
        dt = (trial.t_end - trial.t_start - C.SPLIT_SETTLE_MS) / len(window) if window else 0.0
        trial_left, trial_right = counts["left"] * dt, counts["right"] * dt
        looked = trial_left + trial_right
        trial_social = trial_left if trial.social_side == "left" else trial_right
        is_valid = looked >= C.SPLIT_MIN_LOOK_MS_PER_TRIAL
        shown_ms += trial.t_end - trial.t_start - C.SPLIT_SETTLE_MS
        looked_total_ms += looked
        rows.append(
            {
                "index": trial.index,
                "social_side": trial.social_side,
                "valid": is_valid,
                "looking_ms": round(looked),
                "social_fraction": round(trial_social / looked, 3) if looked else None,
                "frames": counts,
            }
        )
        if not is_valid:
            continue
        valid += 1
        sides_seen.add(trial.social_side)
        social_ms += trial_social
        geometric_ms += looked - trial_social
        left_ms += trial_left
        right_ms += trial_right

    if valid < C.SPLIT_MIN_VALID_TRIALS:
        return insufficient(f"only {valid} trial(s) with enough looking time", rows)

    left_share = left_ms / (left_ms + right_ms)
    if len(sides_seen) == 2 and max(left_share, 1 - left_share) > C.SPLIT_SIDE_BIAS:
        return insufficient(
            f"looked at one side {max(left_share, 1 - left_share):.0%} of the time regardless of content",
            rows,
        )

    social = social_ms / (social_ms + geometric_ms)
    status = "flagged" if social < C.SPLIT_SOCIAL_FLAG_BELOW else "not_flagged"

    reasons: list[str] = []
    if calibration.quality == "good" and valid >= 3 and len(sides_seen) == 2:
        confidence: Confidence = "high"
    else:
        confidence = "medium"
        if calibration.quality != "good":
            reasons.append("calibration only fair")
        if valid < 3:
            reasons.append(f"only {valid} valid trials")
        if len(sides_seen) < 2:
            reasons.append("social content was on the same side in all valid trials")

    return MetricResult(
        key="social_preference",
        label=LABEL,
        status=status,
        confidence=confidence,
        value=round(social, 3),
        unit="fraction",
        summary=f"Looked at social content {social:.0%} of on-screen time across {valid} valid trials",
        reasons=reasons,
        trials=rows,
        thresholds=thresholds,
        reference=REFERENCE,
        details={
            "valid_trials": valid,
            # Trials where most looking went to the social side; shows whether the preference
            # held when the sides swapped.
            "social_majority_trials": sum(
                1 for r in rows if r["valid"] and r["social_fraction"] is not None and r["social_fraction"] >= 0.5
            ),
            "attention_fraction": round(looked_total_ms / shown_ms, 3) if shown_ms else None,
        },
    )

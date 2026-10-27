"""Per-session gaze calibration.

Webcam gaze is coarse, so the modules only ever ask "which half of the
screen?" or "on screen at all?". We fit a small ridge regression per axis
from iris position + head pose + face position to the screen coordinates of
the calibration targets, then measure its error on held-out validation
targets. A session whose calibration is poor gets no gaze-based scores.
"""

from dataclasses import dataclass
from statistics import median
from typing import Literal

import numpy as np

from . import config as C
from .models import CalibrationPoint, Frame
from .timeline import Timeline

X_FEATURES = ("iris_x", "yaw", "face_x")
Y_FEATURES = ("iris_y", "pitch", "face_y")

# Smallest spread a feature is standardised by. A child who keeps very still during calibration
# gives face_y a spread of ~0.003; standardising by that turns a 1% head shift later into a huge
# extrapolation. These floors are roughly the noise level of each feature.
MIN_STD = {"iris_x": 0.02, "iris_y": 0.02, "yaw": 2.0, "pitch": 2.0, "face_x": 0.02, "face_y": 0.02}

CalibrationQuality = Literal["good", "fair", "poor"]


def is_usable(frame: Frame) -> bool:
    return (
        frame.face
        and frame.blink < C.BLINK_MAX
        and all(getattr(frame, name) is not None for name in X_FEATURES + Y_FEATURES)
    )


def _vector(frame: Frame, names: tuple[str, ...]) -> list[float]:
    return [float(getattr(frame, name)) for name in names]


@dataclass(frozen=True)
class _AxisModel:
    names: tuple[str, ...]
    mean: np.ndarray
    std: np.ndarray
    weights: np.ndarray  # [bias, *features]

    def predict(self, frame: Frame) -> float:
        z = (np.array(_vector(frame, self.names)) - self.mean) / self.std
        return float(self.weights[0] + z @ self.weights[1:])

    def params(self) -> dict:
        return {
            "names": list(self.names),
            "mean": [float(v) for v in self.mean],
            "std": [float(v) for v in self.std],
            "weights": [float(v) for v in self.weights],
        }


def _fit_axis(
    names: tuple[str, ...], frames: list[Frame], targets: list[float], fixed: dict[str, float] | None = None
) -> _AxisModel:
    """Ridge fit. `fixed` pins a feature's coefficient (in target units per raw feature unit)."""
    raw = np.array([_vector(f, names) for f in frames])
    mean = raw.mean(axis=0)
    std = np.maximum(raw.std(axis=0), [MIN_STD[name] for name in names])
    z = (raw - mean) / std
    y = np.array(targets, dtype=float)
    pinned = {names.index(k): gain * std[names.index(k)] for k, gain in (fixed or {}).items()}
    for i, w in pinned.items():
        y = y - w * z[:, i]
    free = [i for i in range(len(names)) if i not in pinned]
    design = np.hstack([np.ones((len(frames), 1)), z[:, free]])
    penalty = C.CALIB_RIDGE_LAMBDA * np.eye(design.shape[1])
    penalty[0, 0] = 0.0  # don't shrink the bias
    solved = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    weights = np.zeros(len(names) + 1)
    weights[0] = solved[0]
    weights[[1 + i for i in free]] = solved[1:]
    for i, w in pinned.items():
        weights[1 + i] = w
    return _AxisModel(names, mean, std, weights)


def _yaw_gain(model: _AxisModel) -> float:
    """Fitted horizontal gaze shift per degree of head yaw (screen widths)."""
    i = model.names.index("yaw")
    return float(model.weights[1 + i] / model.std[i])


def _fit_x(frames: list[Frame], targets: list[float], yaw_spread: float) -> tuple[_AxisModel, str]:
    """Horizontal model with the head-yaw coefficient kept physically plausible (see config).

    The fitted coefficient is only replaced when it is physically wrong: the wrong direction, larger
    than the screen geometry allows, or (when the head barely moved, so there was nothing to learn
    from) smaller than a typical screen implies.
    """
    model = _fit_axis(X_FEATURES, frames, targets)
    gain = _yaw_gain(model)

    def pinned(value: float, source: str) -> tuple[_AxisModel, str]:
        return _fit_axis(X_FEATURES, frames, targets, {"yaw": C.CALIB_YAW_SIGN * value}), source

    if gain * C.CALIB_YAW_SIGN < 0:  # wrong direction: noise, not head movement
        return pinned(C.CALIB_YAW_GAIN_DEFAULT, "default")
    if abs(gain) > C.CALIB_YAW_GAIN_MAX:
        return pinned(C.CALIB_YAW_GAIN_MAX, "bounded")
    if yaw_spread < C.CALIB_YAW_MIN_SPREAD_DEG and abs(gain) < C.CALIB_YAW_GAIN_DEFAULT:
        return pinned(C.CALIB_YAW_GAIN_DEFAULT, "default")
    return model, "fitted"


@dataclass(frozen=True)
class GazeModel:
    x: _AxisModel
    y: _AxisModel

    def predict(self, frame: Frame) -> tuple[float, float] | None:
        """Viewport-normalized gaze point, or None if the frame can't be used."""
        if not is_usable(frame):
            return None
        return self.x.predict(frame), self.y.predict(frame)

    def params(self) -> dict:
        """Everything the browser needs to run the same prediction live (ui/src/cv/gaze.ts)."""
        return {"x": self.x.params(), "y": self.y.params(), "blink_max": C.BLINK_MAX,
                "required": list(X_FEATURES + Y_FEATURES)}


@dataclass(frozen=True)
class CalibrationResult:
    quality: CalibrationQuality
    model: GazeModel | None
    fit_points_used: int
    validation_samples: int
    mean_abs_err_x: float | None
    side_accuracy: float | None
    reason: str | None
    yaw_gain: float | None = None  # screen widths per degree of head yaw
    yaw_gain_source: str | None = None  # fitted | bounded | default
    yaw_spread_deg: float | None = None

    @property
    def passed(self) -> bool:
        return self.quality != "poor"

    def summary(self) -> dict:
        return {
            "passed": self.passed,
            "quality": self.quality,
            "fit_points_used": self.fit_points_used,
            "validation_samples": self.validation_samples,
            "mean_abs_err_x": None if self.mean_abs_err_x is None else round(self.mean_abs_err_x, 3),
            "side_accuracy": None if self.side_accuracy is None else round(self.side_accuracy, 3),
            "reason": self.reason,
            "yaw_gain": None if self.yaw_gain is None else round(self.yaw_gain, 4),
            "yaw_gain_source": self.yaw_gain_source,
            "yaw_spread_deg": None if self.yaw_spread_deg is None else round(self.yaw_spread_deg, 1),
        }


def point_samples(timeline: Timeline[Frame], point: CalibrationPoint) -> list[Frame]:
    """Frames where the child was plausibly fixating this target.

    Drops the eye-travel period at the start, then drops frames far from the
    point's median iris/head position (the child glanced elsewhere).
    """
    frames = [f for f in timeline.between(point.t_start + C.CALIB_SETTLE_MS, point.t_end) if is_usable(f)]
    if not frames:
        return []
    mid_iris = median(f.iris_x for f in frames)  # type: ignore[type-var]
    mid_yaw = median(f.yaw for f in frames)  # type: ignore[type-var]
    return [
        f
        for f in frames
        if abs(f.iris_x - mid_iris) <= C.CALIB_OUTLIER_IRIS  # type: ignore[operator]
        and abs(f.yaw - mid_yaw) <= C.CALIB_OUTLIER_YAW_DEG  # type: ignore[operator]
    ]


def _poor(reason: str, fit_points: int = 0, model: GazeModel | None = None) -> CalibrationResult:
    return CalibrationResult("poor", model, fit_points, 0, None, None, reason)


def calibrate(frames: list[Frame], points: list[CalibrationPoint]) -> CalibrationResult:
    timeline = Timeline(frames)

    fit_frames: list[Frame] = []
    fit_targets: list[tuple[float, float]] = []
    point_yaws: list[float] = []
    fit_points = 0
    for point in (p for p in points if p.phase == "fit"):
        samples = point_samples(timeline, point)
        if len(samples) < C.CALIB_MIN_SAMPLES_PER_POINT:
            continue
        fit_points += 1
        fit_frames.extend(samples)
        fit_targets.extend([(point.x, point.y)] * len(samples))
        point_yaws.append(median(f.yaw for f in samples))  # type: ignore[type-var]

    if fit_points < C.CALIB_MIN_FIT_POINTS:
        return _poor(f"Child looked at only {fit_points} calibration targets", fit_points)

    yaw_spread = max(point_yaws) - min(point_yaws)
    x_model, yaw_source = _fit_x(fit_frames, [x for x, _ in fit_targets], yaw_spread)
    model = GazeModel(x=x_model, y=_fit_axis(Y_FEATURES, fit_frames, [y for _, y in fit_targets]))
    yaw_info = {"yaw_gain": _yaw_gain(x_model), "yaw_gain_source": yaw_source, "yaw_spread_deg": yaw_spread}

    errors: list[float] = []
    side_hits: list[bool] = []
    for point in (p for p in points if p.phase == "validate"):
        for frame in point_samples(timeline, point):
            gx = model.x.predict(frame)
            errors.append(abs(gx - point.x))
            side_hits.append((gx < 0.5) == (point.x < 0.5))

    if len(errors) < C.CALIB_MIN_SAMPLES_PER_POINT:
        return CalibrationResult("poor", model, fit_points, 0, None, None, "Not enough data on the validation targets", **yaw_info)

    mean_err = float(np.mean(errors))
    side_acc = float(np.mean(side_hits))
    if side_acc >= C.CALIB_GOOD["side_accuracy"] and mean_err <= C.CALIB_GOOD["mean_abs_err_x"]:
        quality: CalibrationQuality = "good"
    elif side_acc >= C.CALIB_FAIR["side_accuracy"] and mean_err <= C.CALIB_FAIR["mean_abs_err_x"]:
        quality = "fair"
    else:
        quality = "poor"
    reason = None if quality != "poor" else "Gaze error on validation targets is too high"
    return CalibrationResult(quality, model, fit_points, len(errors), mean_err, side_acc, reason, **yaw_info)

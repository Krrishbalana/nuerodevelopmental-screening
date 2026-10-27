"""Input data contract shared by the API and the scoring engine.

The browser runs MediaPipe on-device and sends only per-frame features
(never raw video). All timestamps are milliseconds since session start,
on one clock shared by frames, audio and module segments.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Frame(BaseModel):
    t: float
    face: bool
    # Iris position inside the eye opening, 0..1 (image coordinates, averaged over both eyes).
    iris_x: float | None = None
    iris_y: float | None = None
    # Head pose in degrees, from MediaPipe's facial transformation matrix.
    yaw: float | None = None
    pitch: float | None = None
    roll: float | None = None
    # Face bounding box in normalized image coordinates. face_w doubles as a distance proxy.
    face_x: float | None = None
    face_y: float | None = None
    face_w: float | None = None
    # MediaPipe blendshape scores, 0..1.
    blink: float = 0.0
    smile: float = 0.0


class AudioSample(BaseModel):
    t: float
    rms: float = Field(ge=0)


class BrightnessSample(BaseModel):
    t: float
    luma: float = Field(ge=0, le=255)


class CalibrationPoint(BaseModel):
    """One calibration target. x, y are normalized to the viewport (0..1)."""

    x: float
    y: float
    phase: Literal["fit", "validate"]
    t_start: float
    t_end: float


class SplitScreenTrial(BaseModel):
    index: int
    social_side: Literal["left", "right"]
    clip: int | None = None  # which stimulus pair was shown (repeat trials reuse a pair)
    t_start: float
    t_end: float


class NameCallTrial(BaseModel):
    index: int
    t_start: float
    # When the parent was cued to call the name. The actual call is found from the mic.
    cue_t: float
    t_end: float


class VoiceCheck(BaseModel):
    """Before the name trials: room quiet, then the parent says the name once from behind the child."""

    quiet_start: float
    quiet_end: float
    speak_start: float
    speak_end: float


class ChildInfo(BaseModel):
    dob: date
    session_date: date


class Viewport(BaseModel):
    width: int
    height: int


class SessionUpload(BaseModel):
    child: ChildInfo
    viewport: Viewport
    frames: list[Frame]
    audio: list[AudioSample] = []
    brightness: list[BrightnessSample] = []
    calibration_points: list[CalibrationPoint]
    split_screen_trials: list[SplitScreenTrial] = []
    name_call_trials: list[NameCallTrial] = []
    voice_check: VoiceCheck | None = None
    # Parent opted in to keeping the camera recording with this session (default off).
    recording_consent: bool = False
    # Which stimulus clips were shown. Thresholds are only valid for the set they were validated on.
    stimulus_set: str = "unspecified"
    client: dict[str, str] = {}


class CalibrationRequest(BaseModel):
    frames: list[Frame]
    calibration_points: list[CalibrationPoint]

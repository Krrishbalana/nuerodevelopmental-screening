"""Simulated child sessions with known ground truth, for testing the scoring engine.

A simple "eye model" maps where the child looks (gx, gy in viewport units)
to the features the browser would send. The mapping is unknown to the
scoring code; calibration has to learn it.
"""

import random
from dataclasses import dataclass, field
from datetime import date

from scoring.models import (
    AudioSample,
    BrightnessSample,
    CalibrationPoint,
    ChildInfo,
    Frame,
    NameCallTrial,
    VoiceCheck,
    SessionUpload,
    SplitScreenTrial,
    Viewport,
)

FPS_MS = 1000 / 30
FIT_POINTS = [(0.5, 0.5), (0.15, 0.2), (0.85, 0.2), (0.15, 0.8), (0.85, 0.8)]
VALIDATE_POINTS = [(0.2, 0.5), (0.8, 0.5)]
CALIB_POINT_MS = 1800
SPLIT_TRIAL_MS = 10_000
NAME_TRIAL_MS = 12_000
NAME_CUE_AT_MS = 5000
GAP_MS = 1500


@dataclass
class Child:
    social_preference: float = 0.7  # share of split-screen time spent on social side
    name_responses: list[bool] = field(default_factory=lambda: [True, True, True])
    response_delay_ms: float = 800
    looks_at_calibration: bool = True
    always_left: bool = False  # side bias
    noise: float = 0.01
    voice_detectable: bool = True
    voice_rms: float = 0.2  # parent's call level; room baseline is ~0.006
    voice_check_rms: float | None = None  # call level in the voice check; None = same as voice_rms, 0 = no check
    noise_burst_rms: float = 0.0  # a room sound 1.5 s after each name cue (door, cough...)
    still_during_calibration: bool = False  # head perfectly still, so face position barely varies
    head_shift_after_calibration: float = 0.0  # face_y offset for the rest of the session
    eyes_only_calibration: bool = False  # head kept still while following the calibration targets
    head_turn_deg: float = 0.0  # extra head yaw towards the looked-at side during the split screen
    vertical_eye_signal: float = 1.0  # <1: iris_y/pitch barely track vertical gaze (common on webcams)
    age_months: int = 24


class _Recorder:
    def __init__(self, child: Child, seed: int):
        self.child = child
        self.rng = random.Random(seed)
        self.t = 0.0
        self.frames: list[Frame] = []
        self.face_y_offset = 0.0
        self.head_gain = 15.0  # degrees of yaw per screen width of gaze
        self.extra_turn = 0.0
        self.face_noise = child.noise / 2

    # Gaze angle = head angle + eye-in-head angle. The screen spans 30°, so looking at gx (0..1) means a
    # total angle of 30 * (gx - 0.5); whatever the head doesn't turn, the eyes do. With the default
    # head_gain of 15 this gives the original features: yaw -15 and iris -0.25 per screen width.
    def _head_angle(self, gx: float) -> float:
        turn = self.extra_turn if gx > 0.5 else -self.extra_turn if gx < 0.5 else 0.0
        return self.head_gain * (gx - 0.5) + turn

    def _eye_angle(self, gx: float) -> float:
        return 30 * (gx - 0.5) - self._head_angle(gx)

    def frame(self, gx: float, gy: float, yaw_offset: float = 0.0, face: bool = True) -> None:
        n = self.child.noise
        g = self.rng.gauss
        fn = self.face_noise
        if face:
            self.frames.append(
                Frame(
                    t=self.t,
                    face=True,
                    iris_x=0.5 - self._eye_angle(gx) / 60 + g(0, n),
                    iris_y=0.45 + 0.2 * self.child.vertical_eye_signal * (gy - 0.5) + g(0, n),
                    yaw=-self._head_angle(gx) + yaw_offset + g(0, n * 30),
                    pitch=-10 * self.child.vertical_eye_signal * (gy - 0.5) + g(0, n * 30),
                    roll=0.0,
                    face_x=0.5 + g(0, fn),
                    # The head follows vertical targets very slightly, as real heads do.
                    face_y=0.45 + 0.004 * (gy - 0.5) + self.face_y_offset + g(0, fn),
                    face_w=0.25,
                    blink=0.05,
                )
            )
        else:
            self.frames.append(Frame(t=self.t, face=False))
        self.t += FPS_MS

    def hold(self, ms: float, gx: float, gy: float) -> None:
        end = self.t + ms
        while self.t < end:
            self.frame(gx, gy)


def make_session(child: Child | None = None, seed: int = 0) -> SessionUpload:
    child = child or Child()
    rec = _Recorder(child, seed)
    rng = random.Random(seed + 1)

    points: list[CalibrationPoint] = []
    if child.still_during_calibration:
        rec.face_noise = 0.001
    if child.eyes_only_calibration:
        rec.head_gain = 1.0  # head follows the targets a tiny bit (~0.7° across the screen), as in a46aa142
    for phase, targets in (("fit", FIT_POINTS), ("validate", VALIDATE_POINTS)):
        for x, y in targets:
            start = rec.t
            rec.hold(300, 0.5, 0.5)  # eyes still travelling
            if child.looks_at_calibration:
                rec.hold(CALIB_POINT_MS - 300, x, y)
            else:
                end = start + CALIB_POINT_MS
                while rec.t < end:
                    rec.frame(rng.random(), rng.random())
            points.append(CalibrationPoint(x=x, y=y, phase=phase, t_start=start, t_end=rec.t))

    rec.face_noise = child.noise / 2
    rec.face_y_offset = child.head_shift_after_calibration
    rec.head_gain = 15.0
    rec.extra_turn = child.head_turn_deg

    split: list[SplitScreenTrial] = []
    for i in range(4):
        rec.hold(GAP_MS, 0.5, 0.5)
        social_side = "left" if i % 2 == 0 else "right"
        start = rec.t
        social_seconds = round(10 * child.social_preference)
        for second in range(10):
            if child.always_left:
                gx = 0.25
            else:
                on_social = second < social_seconds
                left = (social_side == "left") == on_social
                gx = 0.25 if left else 0.75
            rec.hold(1000, gx, 0.5)
        split.append(SplitScreenTrial(index=i, social_side=social_side, t_start=start, t_end=rec.t))
    rec.extra_turn = 0.0

    name: list[NameCallTrial] = []
    sounds: list[tuple[float, float, float]] = []  # (start, end, rms)
    check_rms = child.voice_rms if child.voice_check_rms is None else child.voice_check_rms
    voice_check = None
    if check_rms > 0:
        quiet_start = rec.t
        rec.hold(1500, 0.5, 0.5)
        speak_start = rec.t
        sounds.append((speak_start + 800, speak_start + 1600, check_rms))
        rec.hold(3000, 0.5, 0.5)
        voice_check = VoiceCheck(quiet_start=quiet_start, quiet_end=speak_start, speak_start=speak_start, speak_end=rec.t)
    for i, responds in enumerate(child.name_responses):
        rec.hold(GAP_MS, 0.5, 0.5)
        start = rec.t
        rec.hold(NAME_CUE_AT_MS, 0.5, 0.5)
        cue = rec.t
        onset = cue + 600
        if child.voice_detectable:
            sounds.append((onset, onset + 800, child.voice_rms))
        if child.noise_burst_rms:
            sounds.append((cue + 1500, cue + 1650, child.noise_burst_rms))
        if responds:
            rec.hold(600 + child.response_delay_ms, 0.5, 0.5)
            for step in range(12):  # 400ms turn to 60 degrees, then out of view
                rec.frame(0.5, 0.5, yaw_offset=5 * (step + 1))
            out_until = rec.t + 1500
            while rec.t < out_until:
                rec.frame(0.5, 0.5, face=False)
        end = start + NAME_TRIAL_MS
        rec.hold(end - rec.t, 0.5, 0.5)
        name.append(NameCallTrial(index=i, t_start=start, cue_t=cue, t_end=rec.t))

    audio = []
    t = 0.0
    while t < rec.t:
        level = max((rms for a, b, rms in sounds if a <= t <= b), default=0.005 + rng.random() * 0.002)
        audio.append(AudioSample(t=t, rms=level))
        t += 50
    brightness = [BrightnessSample(t=t, luma=120) for t in range(0, int(rec.t), 500)]

    today = date(2026, 10, 26)
    dob = date.fromordinal(today.toordinal() - round(child.age_months * 30.4375))
    return SessionUpload(
        child=ChildInfo(dob=dob, session_date=today),
        viewport=Viewport(width=1440, height=900),
        frames=rec.frames,
        audio=audio,
        brightness=brightness,
        calibration_points=points,
        split_screen_trials=split,
        name_call_trials=name,
        voice_check=voice_check,
    )

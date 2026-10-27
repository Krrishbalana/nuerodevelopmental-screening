"""Response to name.

The parent sits behind the child and calls the name when the app cues them.
The actual call time comes from the microphone (voice onset after the cue),
and a response is a head turn away from the screen within 4 seconds. If the
child turns far enough that the camera loses the face, that also counts,
provided the head was already turning just before the face was lost.

Before the trials the parent does a voice check (quiet, then says the name once).
The level of that call sets this session's voice threshold, so a quiet parent on a
weak laptop mic is still heard and a loud one isn't confused with room sounds.
"""

from dataclasses import dataclass
from statistics import median

from . import config as C
from .metrics import Confidence, MetricResult
from .models import AudioSample, Frame, NameCallTrial, VoiceCheck
from .timeline import Timeline

LABEL = "Response to name"
REFERENCE = "Campbell et al. 2019; Perochon et al. 2023 (SenseToKnow)"


def _sustained_peak(samples: list[AudioSample]) -> float:
    """Highest level held for NAME_AUDIO_SUSTAIN consecutive samples (ignores single clicks)."""
    n = C.NAME_AUDIO_SUSTAIN
    return max((min(s.rms for s in samples[i : i + n]) for i in range(len(samples) - n + 1)), default=0.0)


@dataclass(frozen=True)
class VoiceProfile:
    """How loud the parent's call was above the room during the voice check."""

    baseline: float
    peak: float

    @property
    def level(self) -> float:
        return self.peak - self.baseline

    def summary(self) -> dict:
        return {"baseline_rms": round(self.baseline, 4), "call_rms": round(self.peak, 4)}


def voice_profile(audio: Timeline[AudioSample], check: VoiceCheck | None) -> VoiceProfile | None:
    """None if there was no check or the call wasn't clearly heard; scoring then uses defaults."""
    if check is None:
        return None
    quiet = [s.rms for s in audio.between(check.quiet_start, check.quiet_end)]
    if not quiet:
        return None
    base = median(quiet)
    peak = _sustained_peak(audio.between(check.speak_start, check.speak_end))
    if peak < base * C.NAME_VOICE_CHECK_MIN_RATIO or peak - base < C.NAME_AUDIO_MIN_DELTA:
        return None
    return VoiceProfile(base, peak)


def onset_threshold(base: float, profile: VoiceProfile | None) -> float:
    if profile is None:
        return max(base * C.NAME_AUDIO_RATIO, base + C.NAME_AUDIO_MIN_DELTA)
    return base + max(C.NAME_AUDIO_MIN_DELTA, C.NAME_VOICE_FRACTION * profile.level)


def detect_voice_onset(
    audio: Timeline[AudioSample], cue_t: float, profile: VoiceProfile | None = None
) -> tuple[float, bool]:
    """Time the parent started calling the name, and whether it was actually detected.

    If no voice is found, the cue time is returned so a turn soon after the cue still counts.
    """
    baseline = [s.rms for s in audio.between(cue_t - C.NAME_AUDIO_BASELINE_MS, cue_t)]
    base = median(baseline) if baseline else 0.0
    threshold = onset_threshold(base, profile)
    window = audio.between(cue_t, cue_t + C.NAME_ONSET_SEARCH_MS)
    for i in range(len(window) - C.NAME_AUDIO_SUSTAIN + 1):
        if all(s.rms > threshold for s in window[i : i + C.NAME_AUDIO_SUSTAIN]):
            return window[i].t, True
    return cue_t, False


def _deviation(frame: Frame, base_yaw: float, base_pitch: float) -> float:
    if frame.yaw is None or frame.pitch is None:
        return 0.0
    return max(abs(frame.yaw - base_yaw), abs(frame.pitch - base_pitch))


def score_trial(
    frames: Timeline[Frame],
    audio: Timeline[AudioSample],
    trial: NameCallTrial,
    profile: VoiceProfile | None = None,
) -> dict:
    onset, onset_detected = detect_voice_onset(audio, trial.cue_t, profile)
    row: dict = {
        "index": trial.index,
        "onset_ms": round(onset - trial.t_start),
        "onset_detected": onset_detected,
        "valid": False,
        "responded": False,
        "latency_ms": None,
        # Without a detected voice, latency is measured from the cue and not used for "slow" checks.
        "latency_estimated": not onset_detected,
        "mode": None,
        "reason": None,
    }

    before = frames.between(onset - C.NAME_BASELINE_MS, onset)
    faced = [f for f in before if f.face and f.yaw is not None and f.pitch is not None]
    if not before or len(faced) / len(before) < C.NAME_BASELINE_FACE_RATIO:
        row["reason"] = "child was not facing the screen when the name was called"
        return row
    base_yaw = median(f.yaw for f in faced)  # type: ignore[type-var]
    base_pitch = median(f.pitch for f in faced)  # type: ignore[type-var]
    row.update(baseline_yaw=round(base_yaw, 1), baseline_pitch=round(base_pitch, 1))

    last_face = faced[-1]
    lost_since: float | None = None
    streak: list[Frame] = []
    for frame in frames.between(onset + C.NAME_RESPONSE_START_MS, onset + C.NAME_RESPONSE_END_MS):
        if not frame.face:
            lost_since = frame.t if lost_since is None else lost_since
            streak = []
            if frame.t - lost_since >= C.NAME_FACE_LOST_MS:
                if _deviation(last_face, base_yaw, base_pitch) >= C.NAME_PRE_LOSS_TURN_DEG:
                    row.update(valid=True, responded=True, mode="turned_out_of_view",
                               latency_ms=round(max(last_face.t - onset, 0)))
                else:
                    row["reason"] = "face lost without a head turn (child moved away?)"
                return row
            continue

        lost_since = None
        last_face = frame
        if _deviation(frame, base_yaw, base_pitch) >= C.NAME_TURN_DEG:
            streak.append(frame)
            if len(streak) >= C.NAME_TURN_SUSTAIN_FRAMES:
                row.update(valid=True, responded=True, mode="head_turn",
                           latency_ms=round(streak[0].t - onset))
                return row
        else:
            streak = []

    if not onset_detected:
        # Not turning only means something if we know the name was actually called.
        row["reason"] = "no turn, and the name call wasn't heard on the microphone"
        return row
    row.update(valid=True, mode="no_turn")
    return row


def score_name_response(
    frames: Timeline[Frame],
    audio: Timeline[AudioSample],
    trials: list[NameCallTrial],
    voice_check: VoiceCheck | None = None,
) -> MetricResult:
    profile = voice_profile(audio, voice_check)
    thresholds = {
        "flag_if_turned_at_most": C.NAME_FLAG_MAX_TURNS,
        "turn_deg": C.NAME_TURN_DEG,
        "response_window_ms": C.NAME_RESPONSE_END_MS,
        "voice_threshold": "from voice check" if profile else "default (no usable voice check)",
        **({"voice_check": profile.summary()} if profile else {}),
    }
    rows = [score_trial(frames, audio, t, profile) for t in trials]
    valid = [r for r in rows if r["valid"]]

    if len(valid) < C.NAME_MIN_VALID_TRIALS:
        reason = "module not run" if not trials else f"only {len(valid)} usable trial(s)"
        return MetricResult(
            key="name_response", label=LABEL, status="insufficient", confidence=None,
            value=None, unit="fraction", summary=f"Not scored: {reason}", reasons=[reason],
            trials=rows, thresholds=thresholds, reference=REFERENCE,
        )

    responded = [r for r in valid if r["responded"]]
    rate = len(responded) / len(valid)
    measured = [r["latency_ms"] for r in responded if not r["latency_estimated"]]
    latency = median(measured) if measured else None

    reasons: list[str] = []
    status = "flagged" if len(responded) <= C.NAME_FLAG_MAX_TURNS else "not_flagged"

    undetected = sum(not r["onset_detected"] for r in valid)
    if len(valid) >= 3 and undetected == 0:
        confidence: Confidence = "high"
    else:
        confidence = "medium"
        if len(valid) < 3:
            reasons.append(f"only {len(valid)} usable trials")
        if undetected:
            reasons.append(f"parent's voice not detected in {undetected} trial(s); timed from the on-screen cue")

    latency_text = f", median latency {latency / 1000:.1f}s" if latency is not None else ""
    return MetricResult(
        key="name_response",
        label=LABEL,
        status=status,
        confidence=confidence,
        value=round(rate, 3),
        unit="fraction",
        summary=f"Turned to name in {len(responded)} of {len(valid)} usable trials{latency_text}",
        reasons=reasons,
        trials=rows,
        thresholds=thresholds,
        reference=REFERENCE,
        details={"turned": len(responded), "valid_trials": len(valid), "median_latency_ms": latency},
    )

import type { Side } from "./types";

export const MEDIAPIPE_WASM = "/mediapipe/wasm";
export const FACE_MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

// Stimulus videos live in public/stimuli/ (see tools/stimuli/ to generate and measure them).
// An empty list falls back to a drawn placeholder: fine for development, NOT for real screening.
// Trial i shows social_i next to geometric_i, which was generated to match it (tools/stimuli --pair).
export const STIMULI: { social: string[]; geometric: string[] } = {
  social: [1, 2, 3, 4].map((i) => `/stimuli/social_${i}.mp4`),
  geometric: [1, 2, 3, 4].map((i) => `/stimuli/geometric_${i}.mp4`),
};

// Thresholds are only valid for the stimulus set they were validated on, so every session records
// which set it used. Bump this whenever any clip changes.
export const STIMULUS_SET = "pilot-1 (Pexels social + pair-matched geometric)";

export const AGE_MONTHS = { min: 12, max: 72 };

// Live camera-check thresholds. Same values as backend/scoring/config.py.
export const QUALITY = { faceWMin: 0.1, faceWMax: 0.6, lumaMin: 50 };

export const CALIBRATION = {
  pointMs: 1800,
  maxAttempts: 3,
  fit: [
    [0.5, 0.5],
    [0.15, 0.2],
    [0.85, 0.2],
    [0.15, 0.8],
    [0.85, 0.8],
  ] as [number, number][],
  validate: [
    [0.2, 0.5],
    [0.8, 0.5],
  ] as [number, number][],
};

export const SPLIT_SCREEN = {
  trialMs: 10_000,
  gapMs: 1500,
  // A trial where the face was visible less than this is repeated (same pair, same side), up to maxExtraTrials.
  minFaceRatio: 0.6,
  maxExtraTrials: 2,
  // Counterbalanced so a side preference can't masquerade as a content preference.
  socialSides: ["left", "right", "right", "left"] as Side[],
};

// Same acceptance rule as backend NAME_VOICE_CHECK_MIN_RATIO / NAME_AUDIO_MIN_DELTA.
export const VOICE_CHECK = {
  goBehindS: 4,
  quietMs: 1500,
  speakMaxMs: 4000,
  afterVoiceMs: 600,
  minRatio: 1.6,
  minDelta: 0.004,
  maxAttempts: 3,
};

export const NAME_CALL = {
  trials: 3,
  cueMinMs: 4000,
  cueMaxMs: 7000,
  cueShowMs: 4000,
  afterCueMs: 1500,
  // The cue only appears once the child has faced the screen this long (gives up after gateMaxMs).
  facingHoldMs: 800,
  facingMaxDeg: 20,
  gateMaxMs: 6000,
  // Same rule the scoring uses: the child must face the screen in the 1.5 s before the call.
  minFacingBeforeCue: 0.7,
  maxExtraTrials: 2,
  gapMs: 1500,
  countdownS: 5,
};

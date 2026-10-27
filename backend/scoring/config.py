"""Every threshold the scoring engine uses, in one place.

Cut-offs that drive findings come from published studies (see evidence.py); the
rest are measurement settings (when is a frame usable, what counts as a head turn).
THRESHOLDS_PROVISIONAL stays True until they are validated on Indian children in a
clinician-labelled study.
"""

SCORING_VERSION = "0.2.0"
THRESHOLDS_PROVISIONAL = True

MIN_AGE_MONTHS = 12
MAX_AGE_MONTHS = 72

# --- Frame usability -------------------------------------------------------
BLINK_MAX = 0.5  # frames with blink score above this are not used for gaze

# --- Calibration -----------------------------------------------------------
CALIB_SETTLE_MS = 600  # ignore the start of each target while the eyes travel
CALIB_MIN_SAMPLES_PER_POINT = 5
CALIB_MIN_FIT_POINTS = 4
CALIB_OUTLIER_IRIS = 0.08  # max deviation from the point's median iris position
CALIB_OUTLIER_YAW_DEG = 8.0
CALIB_RIDGE_LAMBDA = 0.1
# Head-yaw → horizontal gaze. With the eyes fixed in the head, turning the head 1° moves the gaze
# point 1°. A laptop/phone screen at arm's length spans at least ~20°, so 1° of yaw can move the gaze
# at most 1/20 of the screen width. A calibration done mostly with the eyes (head still) can't learn
# this coefficient and extrapolates wildly when the head later turns (real session a46aa142: gaze
# landed at 2x screen width while the child was looking at the screen), so it is bounded:
CALIB_YAW_GAIN_MAX = 1 / 20  # screen widths per degree, upper bound
CALIB_YAW_GAIN_DEFAULT = 1 / 30  # used when calibration had too little head movement (~30° wide screen)
CALIB_YAW_MIN_SPREAD_DEG = 3.0  # less head movement than this across targets: coefficient not learnable
# Sign of the pipeline (MediaPipe matrix, unmirrored camera): looking towards screen-right gives a more
# negative yaw. Verified on 3 real sessions with known looking direction (629dae38, f9d193b8, a46aa142).
CALIB_YAW_SIGN = -1
# Quality bands, measured on held-out validation targets.
CALIB_GOOD = {"side_accuracy": 0.90, "mean_abs_err_x": 0.15}
CALIB_FAIR = {"side_accuracy": 0.80, "mean_abs_err_x": 0.25}

# --- Session quality -------------------------------------------------------
FACE_RATIO_MIN = 0.6
LUMA_MIN = 50.0
FACE_W_MIN = 0.10  # smaller = child too far from camera
FACE_W_MAX = 0.60  # larger = too close

# --- Social vs non-social split screen --------------------------------------
# Reference: Pierce et al. 2011 (Arch Gen Psychiatry), 2016 (Biol Psychiatry), GeoPref test.
# Toddlers who looked at geometric images >69% of the time were very likely
# to be on the autism spectrum (high specificity, modest sensitivity).
SPLIT_SETTLE_MS = 500
SPLIT_CENTER_BAND = (0.45, 0.55)  # too close to the middle to call a side
SPLIT_OFFSCREEN_MARGIN = 0.15
SPLIT_MIN_LOOK_MS_PER_TRIAL = 3000
SPLIT_MIN_VALID_TRIALS = 2
SPLIT_SIDE_BIAS = 0.90  # one side >90% regardless of content = can't interpret
# Published cut-off (GeoPref): >69% geometric looking. No other band is published, so there is
# no "borderline" zone: below this is flagged, anything else is not.
SPLIT_SOCIAL_FLAG_BELOW = 0.31

# --- Response to name --------------------------------------------------------
# Reference: Campbell et al. 2019 (Autism), Perochon et al. 2023 (Nature Medicine), SenseToKnow.
NAME_ONSET_SEARCH_MS = 5000  # look for the parent's voice this long after the cue
NAME_AUDIO_BASELINE_MS = 2000
# Tuned on 3 real laptop sessions (2026-10-26): a name called from ~1 m behind peaks at only
# 2.8-4.9x the room baseline (RMS 0.008-0.017). 2.5x / +0.004 caught 6/6 real calls, 0/3 silent
# name trials, and 2/51 silent probes elsewhere (room sounds). RMS alone can't tell voice from noise.
NAME_AUDIO_RATIO = 2.5
NAME_AUDIO_MIN_DELTA = 0.004
NAME_AUDIO_SUSTAIN = 2  # consecutive audio samples above threshold
# With a voice check, the onset threshold sits this far up from the room baseline towards the
# parent's check-call level (floored at NAME_AUDIO_MIN_DELTA).
NAME_VOICE_FRACTION = 0.35
# The check is a moment we know the parent spoke, so it is accepted at a lower ratio than an
# unannounced call; otherwise it could never help the quiet parents it exists for.
NAME_VOICE_CHECK_MIN_RATIO = 1.6
NAME_BASELINE_MS = 1500
NAME_BASELINE_FACE_RATIO = 0.7
NAME_RESPONSE_START_MS = 200
NAME_RESPONSE_END_MS = 4000
NAME_TURN_DEG = 25.0
NAME_TURN_SUSTAIN_FRAMES = 3
NAME_FACE_LOST_MS = 500  # head turned so far the face left the camera
NAME_PRE_LOSS_TURN_DEG = 10.0
NAME_MIN_VALID_TRIALS = 2
# Published split (Campbell 2019): turned on more than one trial vs at most one.
NAME_FLAG_MAX_TURNS = 1

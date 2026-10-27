# Omli Behavior Screening — Product Spec (v0.1, draft)

> **Status:** Draft for discussion. Nothing here is final.
> **What it is:** A home screening feature where a child watches short videos (and, if old enough, plays simple games) on a screen while the camera measures attention, social response and movement.
> **What it is not:** A diagnosis. Output is a risk level + recommended action, never "autism detected".

---

## 1. Decisions made so far

| Topic | Decision |
|---|---|
| Product shape | **A + B**: child watches videos (A) + plays games (B), age-adaptive |
| User | Parent, at home |
| Target device | Phone (eventually). **Development: laptop + webcam** |
| Placement | Standalone feature for now; integrate into Omli later wherever it fits |
| Report | Two versions: **Parent report** (simple) + **Clinician report** (detailed) |
| Top priority | **Accuracy** |

---

## 2. Age-adaptive session flows

Parent enters child's DOB → app picks the flow. Small children can watch but cannot play rule-based games, so games scale with age.

| Flow | Age | Contents | Length |
|---|---|---|---|
| **F1** | 12–24 mo | Videos only. Can sit on parent's lap. | ~4–5 min |
| **F2** | 24–36 mo | Videos + "touch anything" cause-effect (bubble pop). No rules, no win/lose. **Optional, never required for a result.** | ~6 min |
| **F3** | 3–6 yr | Videos + real games (drag, follow, imitate, emotion match). | ~8–10 min |

The camera runs throughout every flow. Session can stop early; report uses whatever valid data exists and says so.

**Why touch starts at 24 months, not 18:** research (SenseToKnow) ran bubble-pop from ~17 months, but in clinics on tablets with trained staff. At home on a phone, an 18-month-old mostly bangs or swipes randomly and the data isn't usable. Even at 24–36 months touch is a bonus signal: if there aren't enough valid touches, the module is skipped and the result relies on video metrics alone.

---

## 3. Modules and what each measures

### 3.1 Videos (all flows)

| Module | Stimulus | Measures | Why |
|---|---|---|---|
| **Calibration** | Animated toy moves to 5 screen points with sound | Per-session gaze mapping + gaze-error estimate | Without calibration, gaze numbers are noise |
| **Social vs non-social** | Split screen: children/people playing vs moving geometric shapes (sides swap) | % gaze time on social side | Reduced social preference is a well-replicated early marker (GeoPref paradigm) |
| **Response to name** | App silently cues the parent (who sits behind the child) to call the name, 3 times | Head-turn yes/no, latency | Strong early marker; same approach as SenseToKnow |
| **Social attention** | Person talking / singing to camera | Attention on face, attention drop-offs | Social engagement |
| **Affect** | Funny/engaging moments | Facial expression (smile) frequency & timing | Shared affect / emotional responsiveness |
| **Throughout** | — | Head movement rate, hand/arm repetitive motion (periodicity), face-in-frame % | Repetitive movements; data quality |

### 3.2 Touch (F2)
- **Bubble pop:** bubbles appear; any touch pops them.
- Measures: touch accuracy (distance from target), touch speed, repeated touches on the same spot (perseveration), number of touches.

### 3.3 Games (F3)

| Game | Measures |
|---|---|
| Drag object to target | Fine motor control, path smoothness |
| Follow the moving object with finger | Visuo-motor coordination |
| Imitate (character claps / raises hands; camera watches) | Imitation, gross motor, left–right symmetry |
| Which face is happy? | Emotion recognition |

---

## 4. Accuracy strategy (top priority)

Accuracy is not one model. It comes from these layers:

1. **Use proven paradigms.** Every module is based on a published screening method (GeoPref, SenseToKnow, EarliPoint). We don't invent signals.
2. **Need only coarse gaze.** Webcam/phone gaze is not precise. Design stimuli so we only need **left vs right half** or **on-screen vs off-screen**, not "eyes vs mouth". This is reliable with webcams.
3. **Calibration + validation per session.** Measure gaze error at the start. If it is too high, mark gaze metrics as unreliable instead of guessing.
4. **Quality gates on every metric.** Face detected %, lighting, distance from camera, child on screen. A metric with too little valid data is marked "not enough data", never scored.
5. **Confidence in the output.** Every metric and the final result carries a confidence level.
6. **Repeated trials.** Name called 3×, split-screen sides swapped, so one bad moment doesn't decide the result.
7. **Validation study (required before any accuracy claim).** Ground truth from clinicians (developmental pediatrician / ADOS-2 assessment). Report sensitivity, specificity, PPV/NPV per age band. Until then, thresholds come from literature and are labelled **provisional**.
8. **Data for improvement.** Optional, separately consented "research mode" that saves raw video for clinician labelling. Without labelled data accuracy cannot improve.

---

## 5. Tech approach (development)

- **Frontend:** React + TypeScript (Vite). Runs the session, plays stimuli, records touch events.
- **On-device CV:** MediaPipe Tasks Vision in the browser:
  - FaceLandmarker (iris landmarks, head pose matrix, blendshapes for smile)
  - PoseLandmarker + HandLandmarker (repetitive movement, imitation, symmetry)
- **Privacy default:** raw video stays on the device; only per-frame features (timestamps, gaze, head pose, landmarks) go to the backend. Raw video is saved only in research mode with explicit consent.
- **Backend:** FastAPI (Python). Stores sessions, computes metrics from features, applies quality gates, scores against age norms, generates both reports.
- **Scoring code** is a pure Python package (no I/O) so it is fully unit-testable and can be re-run on old sessions when thresholds change.

---

## 6. Reports

### Parent report
- One of three outcomes:
  - **"Development looks on track"**
  - **"Keep an eye; re-check in 2–3 months"**
  - **"We recommend meeting a developmental specialist"**
- 2–3 plain-language observations (e.g. "Your child responded to their name 2 out of 3 times").
- Session quality note if data was limited.
- Clear "this is a screening, not a diagnosis" text.

### Clinician report
- Every metric: value, age-norm comparison, confidence, quality flags.
- Per-trial details (e.g. name-call latencies, gaze % per split-screen trial).
- Session conditions (calibration error, face-detected %, duration).
- Scoring version + whether thresholds are provisional.

---

## 7. Privacy & compliance

- Verifiable parental consent before the camera starts (DPDP Act 2023, children's data).
- Separate opt-in for research mode (raw video).
- No "diagnosis" language anywhere in UI or reports.
- Check CDSCO medical-device software rules before making any clinical claims.

---

## 8. Proposed build order

| Step | Build | Why first |
|---|---|---|
| **1** | Camera pipeline + calibration + quality gates | Everything else depends on it; proves webcam accuracy |
| **2** | Social vs non-social split-screen module | Strongest, simplest signal (only left/right gaze) |
| **3** | Response-to-name module | Second strongest signal |
| **4** | Metrics + scoring engine + both reports | End-to-end F1 flow working |
| 5 | Repetitive movement + affect metrics | Adds to all flows |
| 6 | F2 bubble-pop touch module (needs a touch device) | Adds touch signal for 24–36 mo |
| 7 | F3 games | Unlocks 3–6 yr |
| 8 | Research mode + clinician labelling tool | Needed for validation study |

**Steps 1–4 = first working feature** (F1 video flow, end to end, on laptop).

---

## 9. Open questions

1. **Stimulus videos:** Who creates them? They should be culturally Indian (Indian kids, faces, music). Use placeholders for development?
2. **Clinician partner** for the validation study: anyone in mind?
3. **Languages** for parent instructions and report (Hindi, English, others?).
4. **Integration with existing work:** the speech assessment could feed one combined developmental report later.

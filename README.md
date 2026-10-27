# Terminal 1 — backend (port 8010)
cd /Users/krishbalana/Desktop/omli/omli-behavior-screening/backend
uv sync
uv run uvicorn app.main:app --port 8010 --reload

# Terminal 2 — frontend (port 5173, proxies /api to backend)
cd /Users/krishbalana/Desktop/omli/omli-behavior-screening/ui
npm install
npm run dev


Camera-based developmental screening at home: the child watches short videos while the camera measures where they look and whether they turn to their name. **Screening, not diagnosis.** Product spec: [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md).

This is the first feature (spec steps 1–4): camera pipeline, calibration, social-vs-geometric split screen, response to name, scoring, and parent + clinician reports. It is built for a laptop with a webcam.

## Run

```bash
# backend (port 8010)
cd backend && uv sync && uv run uvicorn app.main:app --port 8010 --reload

# frontend (port 5173, proxies /api to the backend)
cd ui && npm install && npm run dev
```

Open http://localhost:5173 in Chrome and allow camera + microphone. A saved report can be reopened at `http://localhost:5173/?session=<session_id>`.

Tests: `cd backend && uv run pytest`

## How it works

```
Browser (on-device)                                   Backend (FastAPI)
─────────────────────────────────────                 ─────────────────────────────────────
MediaPipe FaceLandmarker per frame                    scoring/ (pure, unit-tested)
  → iris position, head pose, face box,                 gaze.py         per-session ridge gaze model,
    blink, smile  (cv/features.ts)                                      validated on held-out targets
Mic → RMS every 50 ms (voice onset)                     split_screen.py social vs geometric preference
Camera → brightness every 500 ms                        name_response.py voice onset → head turn
                                                        quality.py      face visible, light, distance
Stages: Setup → Camera check → Calibration              report.py       outcome + parent/clinician text
  → Split screen (4×10 s) → Name call (3×12 s)        app/  API + JSON file storage (data/sessions/)
```

Raw video and audio never leave the browser; only the numbers above are uploaded.

## Accuracy safeguards

- Gaze is only used to decide **left vs right half**, which a webcam can do reliably.
- Every session is calibrated, and the gaze model is checked on 2 targets it wasn't fitted on. If calibration is poor, gaze metrics are **not scored** (not guessed).
- Split-screen sides are counterbalanced; a child who looks at one side regardless of content gets "insufficient", not a score.
- The name-call time comes from the parent's voice on the mic, not just the on-screen cue.
- Any metric that can't be measured makes the outcome **incomplete**, never "on track".
- All thresholds live in `backend/scoring/config.py` with their research references. They are **provisional** until a clinician-labelled validation study.

## Stimulus clips

Clips live in `ui/public/stimuli/` and are listed in `ui/src/config.ts` (`STIMULI`, plus `STIMULUS_SET`, which every session records). Tools in `tools/stimuli/` (need ffmpeg):

```bash
cd tools/stimuli && uv sync

# luma / contrast / motion energy of any clips
uv run python measure.py ../../ui/public/stimuli/*.mp4

# 4 geometric clips; with --match, brightness and motion are tuned to the social clips
uv run python generate_geometric.py --out ../../ui/public/stimuli --match path/to/social_*.mp4
```

Social and geometric clips must match on luma, contrast and motion, or a child may look at one side just because it is brighter or busier.

Current set **`pilot-1`**: 4 Pexels clips of Indian children (sources, credits and segments in `tools/stimuli/social_clips.json`), trimmed/cropped by `prepare_social.py`, each paired with a geometric clip generated to match it (`--pair`). For development and pilot only; replace with our own shoot before real screening. Raw downloads go in `tools/stimuli/raw/` (git-ignored):

```bash
uv run python prepare_social.py --out ../../ui/public/stimuli
uv run python generate_geometric.py --out ../../ui/public/stimuli --pair \
  --match ../../ui/public/stimuli/social_{1,2,3,4}.mp4
```

## Before real use

- Own-shoot social clips (Indian children, silent, 10–12 s, subject centred, steady camera), then re-run the two commands above and bump `STIMULUS_SET`.
- Validation study with a clinical partner, to set thresholds and measure sensitivity/specificity.
- Parent text in Hindi and other languages.

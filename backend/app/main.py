from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from saathi.domain.enums import AnswerKey, Born, Sex
from saathi.domain.session_state import ChildProfile, Observation
from saathi.errors import NoCurrentQuestionError, WrongQuestionError
from fastapi.middleware.cors import CORSMiddleware

from scoring import InvalidSession, calibrate, score_session
from scoring import config as C
from scoring.config import SCORING_VERSION
from scoring.models import CalibrationRequest, SessionUpload
from scoring.replay import build_replay

from . import full_report
from . import observations as camera_obs
from . import questionnaire as qn
from . import recordings
from .storage import linked_questionnaire, load_report, load_upload, save_session

app = FastAPI(title="Omli Behavior Screening", version=SCORING_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "scoring_version": SCORING_VERSION}


@app.post("/api/calibration/evaluate")
def evaluate_calibration(body: CalibrationRequest) -> dict:
    """Called right after calibration so the app can offer a retry before the real modules.

    Also returns the fitted gaze model and the split-screen rules, so the browser can check each
    trial live with exactly the scoring's own maths and repeat trials the scoring would reject.
    """
    result = calibrate(body.frames, body.calibration_points)
    return {
        **result.summary(),
        "model": result.model.params() if result.model is not None and result.passed else None,
        "rules": {
            "settle_ms": C.SPLIT_SETTLE_MS,
            "center_band": list(C.SPLIT_CENTER_BAND),
            "offscreen_margin": C.SPLIT_OFFSCREEN_MARGIN,
            "min_look_ms": C.SPLIT_MIN_LOOK_MS_PER_TRIAL,
        },
    }


@app.post("/api/sessions")
def create_session(body: SessionUpload) -> dict:
    try:
        report = score_session(body)
    except InvalidSession as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"session_id": save_session(body, report), "report": report}


@app.get("/api/sessions/{session_id}/report")
def get_report(session_id: str) -> dict:
    report = load_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return report


@app.get("/api/sessions/{session_id}/replay")
def get_replay(session_id: str) -> dict:
    """Timeline for the analysis replay, recomputed from the stored measurements."""
    upload = load_upload(session_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return build_replay(upload)


def _consented_upload(session_id: str):
    upload = load_upload(session_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not upload.recording_consent:
        raise HTTPException(status_code=403, detail="Parent did not consent to keeping the recording")
    return upload


@app.put("/api/sessions/{session_id}/recording")
async def put_recording(session_id: str, request: Request, start_t: float) -> dict:
    """Stores the camera recording. Only allowed when the session was submitted with recording consent."""
    _consented_upload(session_id)
    try:
        return await recordings.save(session_id, request.headers.get("content-type", ""), start_t, request.stream())
    except recordings.RecordingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/sessions/{session_id}/recording/keypoints")
def put_keypoints(session_id: str, keypoints: list[dict]) -> dict:
    _consented_upload(session_id)
    try:
        recordings.save_keypoints(session_id, keypoints)
    except recordings.RecordingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "count": len(keypoints)}


@app.get("/api/sessions/{session_id}/recording")
def get_recording(session_id: str) -> FileResponse:
    found = recordings.video_path(session_id)
    if found is None:
        raise HTTPException(status_code=404, detail="No saved recording")
    path, content_type = found
    return FileResponse(path, media_type=content_type)  # supports Range requests, so the replay can seek


@app.get("/api/sessions/{session_id}/recording/meta")
def get_recording_meta(session_id: str) -> dict:
    m = recordings.meta(session_id)
    if m is None or recordings.video_path(session_id) is None:
        raise HTTPException(status_code=404, detail="No saved recording")
    return m


@app.delete("/api/sessions/{session_id}/recording")
def delete_recording(session_id: str) -> dict:
    if not recordings.delete(session_id):
        raise HTTPException(status_code=404, detail="No saved recording")
    return {"deleted": True}


# --- Saathi parent questionnaire ------------------------------------------------------------


class QuestionnaireProfile(BaseModel):
    age_years: int = Field(ge=0, le=6)
    age_months: int = Field(ge=0, le=11)
    sex: Sex = Sex.NA
    born: Born = Born.TERM
    family_factors: list[str] = []
    # Camera session whose findings start the questionnaire as evidence (the adaptive questions follow them).
    screening_session_id: str | None = None
    # Or explicit observations (e.g. from another measuring app).
    observations: list[Observation] = []


class QuestionnaireAnswer(BaseModel):
    question_id: str
    key: AnswerKey


def _qn(call):
    try:
        return call()
    except qn.QuestionnaireNotFound as exc:
        raise HTTPException(status_code=404, detail="Questionnaire not found") from exc
    except (WrongQuestionError, NoCurrentQuestionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/questionnaire/meta")
def questionnaire_meta() -> dict:
    return qn.meta()


@app.post("/api/questionnaire")
def questionnaire_create(body: QuestionnaireProfile) -> dict:
    profile = ChildProfile(age_years=body.age_years, age_months=body.age_months, sex=body.sex, born=body.born,
                           family_factors=tuple(body.family_factors))
    observations = list(body.observations)
    if body.screening_session_id:
        report = load_report(body.screening_session_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Screening session not found")
        observations += camera_obs.from_report(report, qn.confidence_weights())
    return _qn(lambda: qn.create(profile, observations, body.screening_session_id))


@app.get("/api/questionnaire/{session_id}")
def questionnaire_current(session_id: str) -> dict:
    return _qn(lambda: qn.current(session_id))


@app.post("/api/questionnaire/{session_id}/answers")
def questionnaire_answer(session_id: str, body: QuestionnaireAnswer) -> dict:
    return _qn(lambda: qn.answer(session_id, body.question_id, body.key))


@app.delete("/api/questionnaire/{session_id}/answers/last")
def questionnaire_undo(session_id: str) -> dict:
    return _qn(lambda: qn.undo(session_id))


@app.post("/api/questionnaire/{session_id}/ack/{kind}")
def questionnaire_ack(session_id: str, kind: Literal["urgent", "pattern"]) -> dict:
    return _qn(lambda: qn.ack_urgent(session_id) if kind == "urgent" else qn.ack_pattern(session_id))


@app.post("/api/questionnaire/{session_id}/complete")
def questionnaire_complete(session_id: str) -> dict:
    return _qn(lambda: qn.complete(session_id))


@app.get("/api/questionnaire/{session_id}/results")
def questionnaire_results(session_id: str) -> dict:
    results = _qn(lambda: qn.get_results(session_id))
    if results is None:
        raise HTTPException(status_code=404, detail="Questionnaire not completed yet")
    return results


@app.get("/api/sessions/{session_id}/questionnaire")
def session_questionnaire(session_id: str) -> dict:
    """The completed parent questionnaire for a screening session, with the observations it started from."""
    qid = linked_questionnaire(session_id)
    if qid is None:
        raise HTTPException(status_code=404, detail="No questionnaire for this session")
    results = _qn(lambda: qn.get_results(qid))
    state = _qn(lambda: qn.state_of(qid))
    return {"questionnaire_id": qid, "results": results, "observations": qn.observation_view(state),
            "answers": [a.model_dump(mode="json") for a in state.answers]}


@app.get("/api/sessions/{session_id}/full-report")
def get_full_report(session_id: str) -> dict:
    """The adaptive report: Saathi engine over the camera findings plus the parent's answers (if any)."""
    report = load_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {**full_report.build(session_id, report), "camera": report}


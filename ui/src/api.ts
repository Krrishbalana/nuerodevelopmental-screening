import type { ReplayData, ReplayMedia } from "./replay/data";
import type {
  AnswerKey,
  CalibrationPoint,
  CalibrationSummary,
  Frame,
  Intake,
  ObservationApplied,
  QuestionnaireMeta,
  QuestionnaireResults,
  QuestionStep,
  Report,
  SessionQuestionnaire,
  FullReport,
  SessionUpload,
} from "./types";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(typeof detail?.detail === "string" ? detail.detail : `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function evaluateCalibration(frames: Frame[], points: CalibrationPoint[]): Promise<CalibrationSummary> {
  return post("/api/calibration/evaluate", { frames, calibration_points: points });
}

export async function getReport(sessionId: string): Promise<Report> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/report`);
  if (!res.ok) throw new Error(res.status === 404 ? "Session not found" : `Request failed (${res.status})`);
  return res.json() as Promise<Report>;
}

export async function getReplay(sessionId: string): Promise<ReplayData> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/replay`);
  if (!res.ok) throw new Error(res.status === 404 ? "Session not found" : `Request failed (${res.status})`);
  return res.json() as Promise<ReplayData>;
}

/** Only called when the parent opted in to saving the recording. */
export async function saveRecording(sessionId: string, blob: Blob, startT: number, keypoints: ReplayMedia["keypoints"]) {
  const id = encodeURIComponent(sessionId);
  const res = await fetch(`/api/sessions/${id}/recording?start_t=${startT}`, {
    method: "PUT",
    headers: { "Content-Type": blob.type || "video/webm" },
    body: blob,
  });
  if (!res.ok) throw new Error(`Saving the recording failed (${res.status})`);
  const kp = await fetch(`/api/sessions/${id}/recording/keypoints`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(keypoints),
  });
  if (!kp.ok) throw new Error(`Saving the face points failed (${kp.status})`);
}

/** The saved recording for a past session, or null if none was saved. */
export async function getSavedRecording(sessionId: string): Promise<ReplayMedia | null> {
  const id = encodeURIComponent(sessionId);
  const res = await fetch(`/api/sessions/${id}/recording/meta`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  const meta = (await res.json()) as { start_t: number; keypoints: ReplayMedia["keypoints"] };
  return { src: `/api/sessions/${id}/recording`, startT: meta.start_t, keypoints: meta.keypoints };
}

export async function deleteRecording(sessionId: string): Promise<void> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/recording`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) throw new Error(`Deleting failed (${res.status})`);
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(typeof detail?.detail === "string" ? detail.detail : `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const questionnaireMeta = () => send<QuestionnaireMeta>("GET", "/api/questionnaire/meta");

/** Starts the parent questionnaire from the camera session's findings. */
export function startQuestionnaire(ageMonths: number, intake: Intake, screeningSessionId: string | null) {
  return send<{ session_id: string; chronological_age_m: number; observations: ObservationApplied[]; step: QuestionStep }>(
    "POST",
    "/api/questionnaire",
    {
      age_years: Math.floor(ageMonths / 12),
      age_months: ageMonths % 12,
      sex: intake.sex,
      born: intake.born,
      family_factors: intake.familyFactors,
      screening_session_id: screeningSessionId,
    },
  );
}

export const answerQuestion = (id: string, questionId: string, key: AnswerKey) =>
  send<QuestionStep>("POST", `/api/questionnaire/${id}/answers`, { question_id: questionId, key });
export const undoAnswer = (id: string) => send<QuestionStep>("DELETE", `/api/questionnaire/${id}/answers/last`);
export const ackStep = (id: string, kind: "urgent" | "pattern") => send<QuestionStep>("POST", `/api/questionnaire/${id}/ack/${kind}`);
export const completeQuestionnaire = (id: string) => send<QuestionnaireResults>("POST", `/api/questionnaire/${id}/complete`);

export async function getSessionQuestionnaire(sessionId: string): Promise<SessionQuestionnaire | null> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/questionnaire`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json() as Promise<SessionQuestionnaire>;
}

export async function getFullReport(sessionId: string): Promise<FullReport> {
  const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/full-report`);
  if (!res.ok) throw new Error(res.status === 404 ? "Session not found" : `Request failed (${res.status})`);
  return res.json() as Promise<FullReport>;
}

export function submitSession(upload: SessionUpload): Promise<{ session_id: string; report: Report }> {
  return post("/api/sessions", upload);
}

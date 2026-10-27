import { useEffect, useRef, useState } from "react";
import { getReport, saveRecording, submitSession } from "./api";
import type { LiveGaze } from "./cv/gaze";
import type { ReplayMedia } from "./replay/data";
import { STIMULUS_SET } from "./config";
import { Tracker } from "./cv/tracker";
import { Calibration } from "./stages/Calibration";
import { CameraCheck } from "./stages/CameraCheck";
import { NameCall } from "./stages/NameCall";
import { Questionnaire } from "./stages/Questionnaire";
import { Report } from "./stages/Report";
import { ageInMonths, Setup } from "./stages/Setup";
import { SplitScreen } from "./stages/SplitScreen";
import type {
  CalibrationPoint,
  NameCallTrial,
  Report as ReportData,
  SessionUpload,
  SplitScreenTrial,
  Intake,
  VoiceCheck,
} from "./types";

export type RecordingStatus = null | "saving" | "saved" | "deleted" | `failed: ${string}`;

type Stage = "setup" | "camera" | "calibration" | "split" | "name" | "submitting" | "questions" | "report" | "error";

function localDate(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function App() {
  const [stage, setStage] = useState<Stage>("setup");
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ id: string; report: ReportData } | null>(null);
  const [replayMedia, setReplayMedia] = useState<ReplayMedia | null>(null);
  const [recordingStatus, setRecordingStatus] = useState<RecordingStatus>(null);
  const recordingBlob = useRef<Blob | null>(null);
  const tracker = useRef(new Tracker()).current;
  const session = useRef({
    dob: "",
    viewport: { width: 0, height: 0 },
    calibration: [] as CalibrationPoint[],
    split: [] as SplitScreenTrial[],
    name: [] as NameCallTrial[],
    voiceCheck: null as VoiceCheck | null,
    saveRecording: false,
    intake: { sex: "na", born: "term", familyFactors: [] } as Intake,
    ageMonths: 0,
    gaze: null as LiveGaze | null, // live copy of the gaze model, for repeating unusable trials
  }).current;

  const fail = (message: string) => {
    setError(message);
    setStage("error");
  };

  // ?session=<id> reopens a saved report (e.g. a clinician opening a shared link);
  // ?session=<id>&questions=1 starts (or restarts) the parent questions for that session.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("session");
    if (!id) return;
    getReport(id)
      .then((report) => {
        setResult({ id, report });
        session.ageMonths = Math.floor(report.clinician.age_months);
        setStage(params.get("questions") === "1" ? "questions" : "report");
      })
      .catch((e: unknown) => fail(e instanceof Error ? e.message : String(e)));
  }, []);

  const submit = async () => {
    setStage("submitting");
    // The recording stays in this browser for the analysis replay, and is uploaded only with consent.
    if (!recordingBlob.current) {
      recordingBlob.current = await tracker.stopRecording();
      if (recordingBlob.current && tracker.recordingStartT !== null) {
        setReplayMedia({
          src: URL.createObjectURL(recordingBlob.current),
          startT: tracker.recordingStartT,
          keypoints: tracker.keypoints,
        });
      }
    }
    tracker.stop();
    void document.exitFullscreen?.().catch(() => undefined);
    const upload: SessionUpload = {
      child: { dob: session.dob, session_date: localDate() },
      viewport: session.viewport,
      frames: tracker.frames,
      audio: tracker.audio,
      brightness: tracker.brightness,
      calibration_points: session.calibration,
      split_screen_trials: session.split,
      name_call_trials: session.name,
      voice_check: session.voiceCheck,
      recording_consent: session.saveRecording,
      stimulus_set: STIMULUS_SET,
      client: { user_agent: navigator.userAgent },
    };
    try {
      const res = await submitSession(upload);
      setResult({ id: res.session_id, report: res.report });
      session.ageMonths = Math.floor(ageInMonths(session.dob));
      setStage("questions"); // the child's part is over: now the parent's adaptive questions
      const blob = recordingBlob.current;
      if (session.saveRecording && blob && tracker.recordingStartT !== null) {
        setRecordingStatus("saving");
        saveRecording(res.session_id, blob, tracker.recordingStartT, tracker.keypoints)
          .then(() => setRecordingStatus("saved"))
          .catch((e: unknown) => setRecordingStatus(`failed: ${e instanceof Error ? e.message : String(e)}`));
      }
    } catch (e) {
      fail(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className={stage === "calibration" || stage === "split" || stage === "name" ? "app immersive" : "app"}>
      {stage === "setup" && (
        <Setup
          onStart={(dob, keep, intake) => {
            session.intake = intake;
            session.dob = dob;
            session.saveRecording = keep;
            setStage("camera");
          }}
        />
      )}
      {stage === "camera" && (
        <CameraCheck
          tracker={tracker}
          onReady={() => {
            tracker.startRecording();
            setStage("calibration");
          }}
        />
      )}
      {stage === "calibration" && (
        <Calibration
          tracker={tracker}
          onDone={(points, summary) => {
            session.calibration = points;
            session.gaze = summary.model && summary.rules ? { model: summary.model, rules: summary.rules } : null;
            session.viewport = { width: window.innerWidth, height: window.innerHeight };
            setStage("split");
          }}
        />
      )}
      {stage === "split" && (
        <SplitScreen
          gaze={session.gaze}
          tracker={tracker}
          onError={fail}
          onDone={(trials) => {
            session.split = trials;
            setStage("name");
          }}
        />
      )}
      {stage === "name" && (
        <NameCall
          gaze={session.gaze}
          tracker={tracker}
          onError={fail}
          onDone={(trials, voiceCheck) => {
            session.name = trials;
            session.voiceCheck = voiceCheck;
            void submit();
          }}
        />
      )}
      {stage === "submitting" && <div className="panel"><p>Analysing the session…</p></div>}
      {stage === "questions" && result && (
        <Questionnaire
          ageMonths={session.ageMonths}
          intake={session.intake}
          screeningSessionId={result.id}
          onDone={() => {
            // Drop "&questions=1" so a refresh shows the report instead of restarting the questions.
            window.history.replaceState(null, "", `?session=${encodeURIComponent(result.id)}`);
            setStage("report");
          }}
        />
      )}
      {stage === "report" && result && <Report report={result.report} sessionId={result.id} replayMedia={replayMedia} recordingStatus={recordingStatus} />}
      {stage === "error" && (
        <div className="panel">
          <h1>Something went wrong</h1>
          <p className="error">{error}</p>
          {tracker.frames.length > 0 && session.name.length > 0 && (
            <button className="primary" onClick={() => void submit()}>Retry upload</button>
          )}
        </div>
      )}
    </div>
  );
}

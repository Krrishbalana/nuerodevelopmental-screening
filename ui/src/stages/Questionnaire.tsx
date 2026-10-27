import { useEffect, useRef, useState } from "react";
import { ackStep, answerQuestion, completeQuestionnaire, startQuestionnaire, undoAnswer } from "../api";
import type { AnswerKey, Intake, ObservationApplied, QuestionStep } from "../types";

const ANSWERS: { key: AnswerKey; label: string }[] = [
  { key: "y", label: "Yes" },
  { key: "py", label: "Probably" },
  { key: "dk", label: "Don't know" },
  { key: "pn", label: "Probably not" },
  { key: "n", label: "No" },
];

interface Props {
  ageMonths: number;
  intake: Intake;
  screeningSessionId: string | null;
  onDone: (questionnaireId: string | null) => void;
}

/**
 * Saathi's adaptive parent questions, started from what the camera saw. The engine picks every next
 * question from the evidence so far; "pattern" interludes are skipped silently (a half-finished
 * probability isn't useful to a parent), "urgent" ones are shown.
 */
export function Questionnaire({ ageMonths, intake, screeningSessionId, onDone }: Props) {
  const [qid, setQid] = useState<string | null>(null);
  const [step, setStep] = useState<QuestionStep | null>(null);
  const [observations, setObservations] = useState<ObservationApplied[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const started = useRef(false);

  const run = async (action: () => Promise<QuestionStep>) => {
    setBusy(true);
    try {
      setStep(await action());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    startQuestionnaire(ageMonths, intake, screeningSessionId)
      .then((res) => {
        setQid(res.session_id);
        setObservations(res.observations);
        setStep(res.step);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [ageMonths, intake, screeningSessionId]);

  useEffect(() => {
    if (!qid || !step) return;
    if (step.type === "pattern") void run(() => ackStep(qid, "pattern"));
    if (step.type === "done") {
      completeQuestionnaire(qid)
        .then(() => onDone(qid))
        .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
    }
    // onDone comes from App unmemoised; only the step matters here.
  }, [qid, step]);

  const finishNow = async () => {
    if (!qid) return onDone(null);
    setBusy(true);
    try {
      await completeQuestionnaire(qid);
      onDone(qid);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  if (error) {
    return (
      <div className="panel">
        <h1>Questions unavailable</h1>
        <p className="error">{error}</p>
        <p className="muted">The report will use the camera session only.</p>
        <button className="primary" onClick={() => onDone(null)}>Continue to report</button>
      </div>
    );
  }

  if (!step || !qid || step.type === "pattern" || step.type === "done") {
    return (
      <div className="panel">
        <p className="muted">{step?.type === "done" ? "Preparing your report…" : "Loading questions…"}</p>
      </div>
    );
  }

  if (step.type === "urgent") {
    return (
      <div className="panel">
        <div className="outcome alert">
          <h1>Please see a doctor within the next few days</h1>
          <p>
            One of your answers describes a sign that needs a prompt check by a doctor. You can finish the questions now;
            the report will include this too.
          </p>
        </div>
        <button className="primary" disabled={busy} onClick={() => void run(() => ackStep(qid, "urgent"))}>
          I understand, continue
        </button>
      </div>
    );
  }

  const q = step.question!;
  const seen = observations.filter((o) => o.terms.length > 0);
  return (
    <div className="panel">
      <p className="muted small">Your child's part is done · a few questions for you · question {step.number}</p>
      {step.number === 1 && seen.length > 0 && (
        <p className="small notice">
          These questions follow from the camera session. We'll ask more about the areas where the camera saw
          something, and the rest more briefly.
        </p>
      )}
      <h1 className="question">{q.question}</h1>
      <p className="muted small">Usually: {q.typical}</p>
      <div className="answers">
        {ANSWERS.map((a) => (
          <button
            key={a.key}
            className="answer"
            disabled={busy}
            onClick={() => void run(() => answerQuestion(qid, q.id, a.key))}
          >
            {a.label}
          </button>
        ))}
      </div>
      <div className="row">
        {step.number !== null && step.number > 1 && (
          <button className="link" disabled={busy} onClick={() => void run(() => undoAnswer(qid))}>
            ← Back
          </button>
        )}
        <button className="link" disabled={busy} onClick={() => void finishNow()}>
          Finish now and see the report
        </button>
      </div>
    </div>
  );
}

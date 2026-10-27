import { useEffect, useRef, useState } from "react";
import { evaluateCalibration } from "../api";
import { StimulusCanvas, type DrawFn } from "../components/StimulusCanvas";
import { CALIBRATION } from "../config";
import type { Tracker } from "../cv/tracker";
import { chime } from "../sound";
import { drawAttention, drawToy } from "../stimuli/draw";
import { runSequence, wait } from "../timing";
import type { CalibrationPoint, CalibrationSummary } from "../types";

interface Target {
  x: number;
  y: number;
  shownAt: number;
}

interface Props {
  tracker: Tracker;
  onDone: (points: CalibrationPoint[], summary: CalibrationSummary) => void;
}

/** A toy appears at 5 fit + 2 validation positions; the backend fits and checks the gaze model. */
export function Calibration({ tracker, onDone }: Props) {
  const [attempt, setAttempt] = useState(1);
  const [phase, setPhase] = useState<"running" | "evaluating" | "result">("running");
  const [result, setResult] = useState<{ points: CalibrationPoint[]; summary: CalibrationSummary } | null>(null);
  const [error, setError] = useState("");
  const target = useRef<Target | null>(null);

  useEffect(() => {
    setPhase("running");
    setError("");
    return runSequence(
      async (token) => {
        target.current = null;
        chime();
        await wait(1500, token); // attention-getter in the centre first

        const points: CalibrationPoint[] = [];
        const all = [
          ...CALIBRATION.fit.map((p) => ["fit", p] as const),
          ...CALIBRATION.validate.map((p) => ["validate", p] as const),
        ];
        for (const [phase, [x, y]] of all) {
          target.current = { x, y, shownAt: performance.now() };
          chime();
          const t_start = tracker.now();
          await wait(CALIBRATION.pointMs, token);
          points.push({ x, y, phase, t_start, t_end: tracker.now() });
        }
        target.current = null;

        setPhase("evaluating");
        const frames = tracker.framesBetween(points[0].t_start, points[points.length - 1].t_end);
        const summary = await evaluateCalibration(frames, points);
        if (token.cancelled) return;
        setResult({ points, summary });
        setPhase("result");
      },
      (e) => setError(e instanceof Error ? e.message : String(e)),
    );
  }, [attempt, tracker]);

  const draw: DrawFn = (ctx, w, h, t) => {
    const tg = target.current;
    if (!tg) return drawAttention(ctx, w, h, t);
    ctx.fillStyle = "#101828";
    ctx.fillRect(0, 0, w, h);
    // Shrinks over the dwell so the eyes settle on its centre.
    const progress = Math.min(1, (performance.now() - tg.shownAt) / CALIBRATION.pointMs);
    const r = Math.min(w, h) * (0.09 - 0.05 * progress);
    drawToy(ctx, tg.x * w, tg.y * h, r, t);
  };

  if (error) {
    return (
      <div className="panel">
        <p className="error">Calibration failed: {error}</p>
        <button className="primary" onClick={() => setAttempt((a) => a + 1)}>Try again</button>
      </div>
    );
  }

  if (phase === "result" && result) {
    const { summary } = result;
    const canRetry = attempt < CALIBRATION.maxAttempts;
    return (
      <div className="panel">
        <h1>{summary.passed ? "Calibration done" : "Calibration wasn't clear enough"}</h1>
        <p className="muted">
          Quality: <b>{summary.quality}</b>
          {summary.side_accuracy !== null && <> · side accuracy {(summary.side_accuracy * 100).toFixed(0)}%</>}
          {summary.mean_abs_err_x !== null && <> · error {(summary.mean_abs_err_x * 100).toFixed(0)}% of screen width</>}
        </p>
        {!summary.passed && (
          <p>
            {summary.reason}. Make sure your child is facing the screen and following the moving star.
            {!canRetry && " Where your child looked won't be scored this time; the name test will still run."}
          </p>
        )}
        <div className="row">
          {summary.passed ? (
            <button className="primary" onClick={() => onDone(result.points, summary)}>Continue</button>
          ) : (
            <>
              {canRetry && (
                <button className="primary" onClick={() => setAttempt((a) => a + 1)}>
                  Try again ({CALIBRATION.maxAttempts - attempt} left)
                </button>
              )}
              <button className={canRetry ? "link" : "primary"} onClick={() => onDone(result.points, summary)}>
                Continue anyway
              </button>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="stage">
      <StimulusCanvas draw={draw} />
      {phase === "evaluating" && <div className="overlay-note">Checking…</div>}
    </div>
  );
}

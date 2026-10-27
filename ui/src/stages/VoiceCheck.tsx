import { useEffect, useState } from "react";
import { VOICE_CHECK } from "../config";
import type { Tracker } from "../cv/tracker";
import { runSequence, wait } from "../timing";
import type { AudioSample, VoiceCheck as VoiceCheckData } from "../types";

type Phase = "ready" | "goBehind" | "quiet" | "speak" | "result";

interface Props {
  tracker: Tracker;
  onDone: (check: VoiceCheckData) => void;
  onError: (message: string) => void;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
}

/** Highest level held for 2 consecutive samples, like the backend (ignores single clicks). */
function sustainedPeak(samples: AudioSample[]): number {
  let peak = 0;
  for (let i = 0; i + 1 < samples.length; i++) peak = Math.max(peak, Math.min(samples[i].rms, samples[i + 1].rms));
  return peak;
}

/**
 * Measures how loud the parent's call is from where they will stand, so the name test can set
 * this session's voice threshold. The parent says "hello", not the child's name: hearing the
 * name an extra time before the test would weaken the child's response to it.
 */
export function VoiceCheck({ tracker, onDone, onError }: Props) {
  const [phase, setPhase] = useState<Phase>("ready");
  const [run, setRun] = useState(0);
  const [countdown, setCountdown] = useState(0);
  const [level, setLevel] = useState(0);
  const [result, setResult] = useState<{ check: VoiceCheckData; heard: boolean } | null>(null);

  useEffect(() => {
    if (run === 0) return;
    return runSequence(
      async (token) => {
        setPhase("goBehind");
        for (let s = VOICE_CHECK.goBehindS; s > 0; s--) {
          setCountdown(s);
          await wait(1000, token);
        }

        setPhase("quiet");
        const quiet_start = tracker.now();
        await wait(VOICE_CHECK.quietMs, token);
        const quiet_end = tracker.now();
        const base = median(tracker.audioBetween(quiet_start, quiet_end).map((a) => a.rms));

        setPhase("speak");
        const speak_start = tracker.now();
        let heardAt: number | null = null;
        while (tracker.now() - speak_start < VOICE_CHECK.speakMaxMs) {
          await wait(100, token);
          const peak = sustainedPeak(tracker.audioBetween(speak_start, tracker.now()));
          if (heardAt === null && peak >= base * VOICE_CHECK.minRatio && peak - base >= VOICE_CHECK.minDelta) {
            heardAt = tracker.now();
          }
          if (heardAt !== null && tracker.now() - heardAt > VOICE_CHECK.afterVoiceMs) break;
        }
        setResult({ check: { quiet_start, quiet_end, speak_start, speak_end: tracker.now() }, heard: heardAt !== null });
        setPhase("result");
      },
      (e) => onError(String(e)),
    );
    // onError comes from App unmemoised; re-running on its identity would restart the check.
  }, [run, tracker]);

  useEffect(() => {
    if (phase !== "speak") return;
    const id = window.setInterval(() => setLevel(tracker.audio[tracker.audio.length - 1]?.rms ?? 0), 50);
    return () => clearInterval(id);
  }, [phase, tracker]);

  if (phase === "ready") {
    return (
      <div className="panel">
        <h1>Quick sound check</h1>
        <p>
          So we can hear you call the name, we first check your voice from where you'll stand. Don't say your child's
          name yet.
        </p>
        <ol>
          <li>Press start, then go and stand about 1 metre behind your child.</li>
          <li>Stay quiet for a moment.</li>
          <li>
            When the screen says <b>"Say hello now"</b>, say <b>"hello"</b> once, in the same voice you'll use to call
            the name.
          </li>
        </ol>
        <button className="primary" onClick={() => setRun((r) => r + 1)}>Start sound check</button>
      </div>
    );
  }

  if (phase === "result" && result) {
    const canRetry = run < VOICE_CHECK.maxAttempts;
    return (
      <div className="panel">
        <h1 className="big-prompt">{result.heard ? "Got it ✓" : "We couldn't hear you clearly"}</h1>
        {!result.heard && (
          <p>Say it a little louder, the way you'll call your child's name. Check that the microphone isn't muted.</p>
        )}
        <div className="row">
          {result.heard || !canRetry ? (
            <button className="primary" onClick={() => onDone(result.check)}>Continue</button>
          ) : (
            <>
              <button className="primary" onClick={() => setRun((r) => r + 1)}>
                Try again ({VOICE_CHECK.maxAttempts - run} left)
              </button>
              <button className="link" onClick={() => onDone(result.check)}>Continue anyway</button>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      {phase === "goBehind" && <h1 className="big-prompt">Go behind your child… {countdown}</h1>}
      {phase === "quiet" && <h1 className="big-prompt">Stay quiet…</h1>}
      {phase === "speak" && (
        <>
          <h1 className="big-prompt">Say "hello" now</h1>
          <div className="meter">
            <div style={{ width: `${Math.min(100, (level / 0.05) * 100)}%` }} />
          </div>
        </>
      )}
    </div>
  );
}

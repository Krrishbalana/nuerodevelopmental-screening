import { useEffect, useRef, useState } from "react";
import { StimulusCanvas } from "../components/StimulusCanvas";
import { NAME_CALL } from "../config";
import { isFacing, neutralYaw } from "../cv/attention";
import { onScreen, type LiveGaze } from "../cv/gaze";
import type { Tracker } from "../cv/tracker";
import { chime } from "../sound";
import { drawAttention, drawCalm } from "../stimuli/draw";
import { runSequence, wait } from "../timing";
import type { Frame, NameCallTrial, VoiceCheck as VoiceCheckData } from "../types";
import { VoiceCheck } from "./VoiceCheck";

interface Props {
  tracker: Tracker;
  gaze: LiveGaze | null;
  onDone: (trials: NameCallTrial[], voiceCheck: VoiceCheckData | null) => void;
  onError: (message: string) => void;
}

type Phase = "intro" | "voice" | "countdown" | "running";

/**
 * The parent stands behind the child and calls the name when a small cue appears at the top.
 * The calm animation is silent so the parent's voice is easy to find in the mic signal.
 */
export function NameCall({ tracker, gaze, onDone, onError }: Props) {
  const [phase, setPhase] = useState<Phase>("intro");
  const [countdown, setCountdown] = useState(NAME_CALL.countdownS);
  const [gap, setGap] = useState(false);
  const [cue, setCue] = useState(false);
  const [trialNo, setTrialNo] = useState(0);
  const voiceCheck = useRef<VoiceCheckData | null>(null);

  useEffect(() => {
    if (phase !== "countdown") return;
    return runSequence(
      async (token) => {
        for (let s = NAME_CALL.countdownS; s > 0; s--) {
          setCountdown(s);
          await wait(1000, token);
        }
        setPhase("running");
      },
      (e) => onError(String(e)),
    );
    // Callbacks from App are not memoised; re-running on their identity would restart the countdown.
  }, [phase]);

  useEffect(() => {
    if (phase !== "running") return;
    return runSequence(
      async (token) => {
        const trials: NameCallTrial[] = [];
        const neutral = neutralYaw(tracker);
        // Looking at the screen: head roughly straight, and (when calibrated) gaze on the screen.
        const looking = (f: Frame | null) =>
          isFacing(f, neutral, NAME_CALL.facingMaxDeg) && (!gaze || onScreen(gaze, f));
        let planned: number = NAME_CALL.trials;
        for (let index = 0; index < planned; index++) {
          setTrialNo(index + 1);
          setGap(true);
          chime();
          await wait(NAME_CALL.gapMs, token);
          setGap(false);

          const t_start = tracker.now();
          await wait(NAME_CALL.cueMinMs + Math.random() * (NAME_CALL.cueMaxMs - NAME_CALL.cueMinMs), token);
          // Only cue the parent once the child is facing the screen, so a turn means something.
          const gateUntil = tracker.now() + NAME_CALL.gateMaxMs;
          let facingSince: number | null = null;
          while (tracker.now() < gateUntil) {
            const now = tracker.now();
            facingSince = looking(tracker.latest) ? (facingSince ?? now) : null;
            if (facingSince !== null && now - facingSince >= NAME_CALL.facingHoldMs) break;
            await wait(100, token);
          }
          const cue_t = tracker.now();
          setCue(true);
          await wait(NAME_CALL.cueShowMs, token);
          setCue(false);
          await wait(NAME_CALL.afterCueMs, token);
          trials.push({ index, t_start, cue_t, t_end: tracker.now() });

          // Child wasn't facing the screen at the call: the scoring will drop this trial, so add one.
          const before = tracker.framesBetween(cue_t - 1500, cue_t);
          const facing = before.length ? before.filter(looking).length / before.length : 0;
          if (facing < NAME_CALL.minFacingBeforeCue && planned < NAME_CALL.trials + NAME_CALL.maxExtraTrials) planned++;
        }
        onDone(trials, voiceCheck.current);
      },
      (e) => onError(String(e)),
    );
  }, [phase, tracker]);

  if (phase === "intro") {
    return (
      <div className="panel">
        <h1>Next: calling your child's name</h1>
        <ol>
          <li>Seat your child facing the screen (a chair, or another adult's lap).</li>
          <li>Stand or sit about 1 metre <b>behind</b> your child, out of their sight.</li>
          <li>
            When <b>"Call the name now"</b> appears at the top of the screen, call your child's name <b>once</b>, in
            your normal voice. Don't touch them or repeat it.
          </li>
          <li>This happens {NAME_CALL.trials} times. Stay quiet otherwise.</li>
        </ol>
        <p className="muted">First, a 10-second sound check.</p>
        <button className="primary" onClick={() => setPhase("voice")}>
          I'm ready
        </button>
      </div>
    );
  }

  if (phase === "voice") {
    return (
      <VoiceCheck
        tracker={tracker}
        onError={onError}
        onDone={(check) => {
          voiceCheck.current = check;
          setPhase("countdown");
        }}
      />
    );
  }

  if (phase === "countdown") {
    return (
      <div className="stage">
        <StimulusCanvas draw={drawCalm} />
        <div className="overlay-note big">Go behind your child… {countdown}</div>
      </div>
    );
  }

  return (
    <div className="stage">
      <StimulusCanvas draw={gap ? drawAttention : drawCalm} />
      {cue && <div className="parent-cue">🔔 Call the name now ({trialNo}/{NAME_CALL.trials})</div>}
    </div>
  );
}

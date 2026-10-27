import { useEffect, useState } from "react";
import { HalfStimulus } from "../components/HalfStimulus";
import { StimulusCanvas } from "../components/StimulusCanvas";
import { SPLIT_SCREEN } from "../config";
import { facingRatio } from "../cv/attention";
import { trialLooking, type LiveGaze } from "../cv/gaze";
import type { Tracker } from "../cv/tracker";
import { chime } from "../sound";
import { drawAttention } from "../stimuli/draw";
import { runSequence, wait } from "../timing";
import type { Side, SplitScreenTrial } from "../types";

interface Props {
  tracker: Tracker;
  gaze: LiveGaze | null;
  onDone: (trials: SplitScreenTrial[]) => void;
  onError: (message: string) => void;
}

/** Social content on one half, geometric motion on the other; sides swap between trials. */
export function SplitScreen({ tracker, gaze, onDone, onError }: Props) {
  const [active, setActive] = useState<{ index: number; socialSide: Side; clip: number } | null>(null);

  useEffect(
    () =>
      runSequence(
        async (token) => {
          const trials: SplitScreenTrial[] = [];
          const queue = SPLIT_SCREEN.socialSides.map((socialSide, clip) => ({ socialSide, clip }));
          let extra = 0;
          for (let index = 0; queue.length > 0; index++) {
            const { socialSide, clip } = queue.shift()!;
            setActive(null);
            chime();
            await wait(SPLIT_SCREEN.gapMs, token); // re-centre attention between trials
            setActive({ index, socialSide, clip });
            const t_start = tracker.now();
            await wait(SPLIT_SCREEN.trialMs, token);
            const t_end = tracker.now();
            trials.push({ index, social_side: socialSide, clip, t_start, t_end });
            // Trial the scoring won't count (too little looking at either half, or child out of view):
            // repeat the same pair on the same side, keeping sides balanced. With a calibrated gaze
            // model this is the scoring's own rule; without one, fall back to face visibility.
            const unusable = gaze
              ? !trialLooking(gaze, tracker.framesBetween(t_start, t_end), t_start, t_end).valid
              : facingRatio(tracker, t_start, t_end, null, 0) < SPLIT_SCREEN.minFaceRatio;
            if (unusable && extra < SPLIT_SCREEN.maxExtraTrials) {
              queue.push({ socialSide, clip });
              extra++;
            }
          }
          setActive(null);
          onDone(trials);
        },
        (e) => onError(String(e)),
      ),
    [tracker],
  );

  if (!active) {
    return (
      <div className="stage">
        <StimulusCanvas draw={drawAttention} />
      </div>
    );
  }

  const kindFor = (side: Side) => (side === active.socialSide ? "social" : "geometric");
  return (
    <div className="stage split" key={active.index}>
      <div className="half">
        <HalfStimulus kind={kindFor("left")} trialIndex={active.clip} />
      </div>
      <div className="half">
        <HalfStimulus kind={kindFor("right")} trialIndex={active.clip} />
      </div>
    </div>
  );
}

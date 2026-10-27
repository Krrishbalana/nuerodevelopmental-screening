import { STIMULI } from "../config";
import { drawGeometric, drawSocial } from "../stimuli/draw";
import { StimulusCanvas } from "./StimulusCanvas";

/** One half of the split screen: a real stimulus video if configured, else a drawn placeholder. */
export function HalfStimulus({ kind, trialIndex }: { kind: "social" | "geometric"; trialIndex: number }) {
  const videos = STIMULI[kind];
  if (videos.length > 0) {
    return (
      <video
        className="half-video"
        src={videos[trialIndex % videos.length]}
        autoPlay
        muted
        loop
        playsInline
      />
    );
  }
  return <StimulusCanvas draw={kind === "social" ? drawSocial : drawGeometric} />;
}

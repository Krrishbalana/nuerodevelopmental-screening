import type { Frame } from "../types";
import type { Tracker } from "./tracker";

/** The child's "looking at the screen" head angle: median yaw over recent frames with a face. */
export function neutralYaw(tracker: Tracker, windowMs = 30_000): number {
  const yaws = tracker
    .framesBetween(tracker.now() - windowMs, tracker.now())
    .flatMap((f) => (f.face && f.yaw !== undefined ? [f.yaw] : []))
    .sort((a, b) => a - b);
  return yaws.length ? yaws[Math.floor(yaws.length / 2)] : 0;
}

export function isFacing(f: Frame | null, neutral: number, maxDeg: number): boolean {
  return !!f?.face && f.yaw !== undefined && f.pitch !== undefined && Math.abs(f.yaw - neutral) < maxDeg && Math.abs(f.pitch) < maxDeg + 10;
}

/** Share of frames in [start, end] where the child faced the screen (or just had a face, if neutral is null). */
export function facingRatio(tracker: Tracker, start: number, end: number, neutral: number | null, maxDeg: number): number {
  const frames = tracker.framesBetween(start, end);
  if (!frames.length) return 0;
  const ok = frames.filter((f) => (neutral === null ? f.face : isFacing(f, neutral, maxDeg))).length;
  return ok / frames.length;
}

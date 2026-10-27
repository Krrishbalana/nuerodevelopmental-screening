// Live copy of the scoring's gaze maths (backend/scoring/gaze.py + split_screen.py), driven by the
// model and rules the backend returns after calibration. Used only to decide whether to repeat a
// trial; the report is always computed by the backend.
import type { Frame } from "../types";

export interface AxisParams {
  names: string[];
  mean: number[];
  std: number[];
  weights: number[];
}

export interface GazeParams {
  x: AxisParams;
  y: AxisParams;
  blink_max: number;
  required: string[];
}

export interface SplitRules {
  settle_ms: number;
  center_band: [number, number];
  offscreen_margin: number;
  min_look_ms: number;
}

export interface LiveGaze {
  model: GazeParams;
  rules: SplitRules;
}

type Cls = "left" | "right" | "center" | "off" | "invalid";

const feature = (f: Frame, name: string) => (f as unknown as Record<string, number | undefined>)[name];

function axis(p: AxisParams, f: Frame): number {
  let v = p.weights[0];
  p.names.forEach((n, i) => {
    v += p.weights[i + 1] * (((feature(f, n) as number) - p.mean[i]) / p.std[i]);
  });
  return v;
}

/** Same as GazeModel.predict: null when the frame isn't usable. */
export function predictGaze(m: GazeParams, f: Frame): [number, number] | null {
  if (!f.face || f.blink >= m.blink_max || m.required.some((n) => feature(f, n) === undefined)) return null;
  return [axis(m.x, f), axis(m.y, f)];
}

/** Same as split_screen._classify_frame (horizontal only). */
export function classifyGaze(g: [number, number] | null, r: SplitRules): Cls {
  if (!g) return "invalid";
  const gx = g[0];
  if (gx < -r.offscreen_margin || gx > 1 + r.offscreen_margin) return "off";
  if (gx >= r.center_band[0] && gx <= r.center_band[1]) return "center";
  return gx < 0.5 ? "left" : "right";
}

export function onScreen(live: LiveGaze, f: Frame | null): boolean {
  if (!f) return false;
  const c = classifyGaze(predictGaze(live.model, f), live.rules);
  return c !== "off" && c !== "invalid";
}

/** Same looking-time rule as score_split_screen: is this trial one the report will count? */
export function trialLooking(live: LiveGaze, frames: Frame[], tStart: number, tEnd: number): { lookingMs: number; valid: boolean } {
  const from = tStart + live.rules.settle_ms;
  const window = frames.filter((f) => f.t >= from && f.t <= tEnd);
  if (!window.length) return { lookingMs: 0, valid: false };
  const dt = (tEnd - from) / window.length;
  const sided = window.filter((f) => {
    const c = classifyGaze(predictGaze(live.model, f), live.rules);
    return c === "left" || c === "right";
  }).length;
  const lookingMs = sided * dt;
  return { lookingMs, valid: lookingMs >= live.rules.min_look_ms };
}

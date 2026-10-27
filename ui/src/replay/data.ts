import type { CalibrationPoint, CalibrationSummary, Report, Side } from "../types";

// Mirrors backend/scoring/replay.py.
export interface ReplayData {
  duration_ms: number;
  frames: {
    t: number[];
    face: number[];
    gx: (number | null)[];
    gy: (number | null)[];
    yaw: (number | null)[];
    pitch: (number | null)[];
    ix: (number | null)[];
    iy: (number | null)[];
    gaze: (string | null)[];
  };
  audio: { t: number[]; rms: number[] };
  calibration: { summary: CalibrationSummary; points: CalibrationPoint[] };
  split_trials: {
    index: number;
    clip: number;
    social_side: Side;
    t_start: number;
    t_end: number;
    settle_end: number;
    valid: boolean | null;
    looking_ms: number | null;
    social_fraction: number | null;
  }[];
  split_summary: { status: string; value: number | null; summary: string };
  voice_check: {
    quiet_start: number;
    quiet_end: number;
    speak_start: number;
    speak_end: number;
    heard: boolean;
    baseline_rms?: number;
    call_rms?: number;
  } | null;
  name_trials: {
    index: number;
    t_start: number;
    cue_t: number;
    t_end: number;
    onset_t: number;
    window_end: number;
    turn_t: number | null;
    peak_turn_deg: number | null;
    onset_detected: boolean | null;
    valid: boolean | null;
    responded: boolean | null;
    latency_ms: number | null;
    latency_estimated: boolean | null;
    mode: string | null;
    reason: string | null;
    baseline_yaw: number | null;
  }[];
  name_summary: { status: string; value: number | null; summary: string };
  settings: { split_settle_ms: number; name_turn_deg: number; social_flag_below: number; median_yaw: number | null };
}

/** The camera recording: in this browser's memory, or saved on the server when the parent opted in. */
export interface ReplayMedia {
  src: string; // object URL or /api/sessions/<id>/recording
  startT: number; // session clock (ms) at the first recorded frame
  keypoints: { t: number; p: number[] }[];
}

export type Tone = "cyan" | "magenta" | "amber" | "green" | "red" | "dim";

export interface ReplayEvent {
  t: number;
  text: string;
  tone: Tone;
}

/** Largest index i with arr[i] <= t (or -1). */
export function indexAt(arr: number[], t: number): number {
  let lo = 0;
  let hi = arr.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] <= t) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans;
}

export function bounds(d: ReplayData): { start: number; end: number } {
  const starts = [d.calibration.points[0]?.t_start, d.split_trials[0]?.t_start, d.name_trials[0]?.t_start].filter(
    (x): x is number => x !== undefined,
  );
  const ends = [
    d.calibration.points.at(-1)?.t_end,
    d.split_trials.at(-1)?.t_end,
    d.name_trials.at(-1)?.t_end,
  ].filter((x): x is number => x !== undefined);
  const start = Math.max(0, Math.min(...starts) - 1500);
  return { start, end: Math.max(...ends) + 2500 };
}

export type Phase =
  | { kind: "calibration"; index: number; point: CalibrationPoint }
  | { kind: "split"; trial: ReplayData["split_trials"][number] }
  | { kind: "voice" }
  | { kind: "name"; trial: ReplayData["name_trials"][number] }
  | { kind: "idle" };

export function phaseAt(d: ReplayData, t: number): Phase {
  const ci = d.calibration.points.findIndex((p) => p.t_start <= t && t <= p.t_end);
  if (ci >= 0) return { kind: "calibration", index: ci, point: d.calibration.points[ci] };
  const s = d.split_trials.find((x) => x.t_start <= t && t <= x.t_end);
  if (s) return { kind: "split", trial: s };
  const v = d.voice_check;
  if (v && v.quiet_start <= t && t <= v.speak_end) return { kind: "voice" };
  const n = d.name_trials.find((x) => x.t_start <= t && t <= x.t_end);
  if (n) return { kind: "name", trial: n };
  return { kind: "idle" };
}

export const PHASE_LABEL = (p: Phase): string =>
  p.kind === "calibration"
    ? `CALIBRATION ${p.index + 1}`
    : p.kind === "split"
      ? `SOCIAL vs OBJECTS · TRIAL ${p.trial.index + 1}`
      : p.kind === "voice"
        ? "SOUND CHECK"
        : p.kind === "name"
          ? `RESPONSE TO NAME · CALL ${p.trial.index + 1}`
          : "STANDBY";

const pct = (x: number | null | undefined) => (x === null || x === undefined ? "—" : `${Math.round(x * 100)}%`);
const sec = (ms: number) => `${(ms / 1000).toFixed(1)} s`;

/** The event stream shown in the side panel, in time order. Every number comes from the backend scoring. */
export function buildEvents(d: ReplayData, report: Report): ReplayEvent[] {
  const ev: ReplayEvent[] = [];
  const cal = d.calibration;
  cal.points.forEach((p, i) =>
    ev.push({
      t: p.t_start,
      text: `${p.phase === "fit" ? "CALIBRATE" : "VALIDATE"} target ${i + 1}/${cal.points.length} @ (${pct(p.x)}, ${pct(p.y)})`,
      tone: "dim",
    }),
  );
  const lastCal = cal.points.at(-1);
  if (lastCal) {
    const s = cal.summary;
    ev.push({
      t: lastCal.t_end,
      text: `GAZE MODEL ${s.quality.toUpperCase()} · side accuracy ${pct(s.side_accuracy)} · error ${pct(s.mean_abs_err_x)} of width`,
      tone: s.passed ? "cyan" : "red",
    });
  }

  for (const tr of d.split_trials) {
    ev.push({ t: tr.t_start, text: `TRIAL ${tr.index + 1} · children's video on ${tr.social_side.toUpperCase()}`, tone: "dim" });
    ev.push({
      t: tr.t_end,
      text: `TRIAL ${tr.index + 1} · social ${pct(tr.social_fraction)} · watched ${sec(tr.looking_ms ?? 0)} · ${tr.valid ? "VALID" : "NOT USABLE"}`,
      tone: tr.valid ? (tr.social_fraction !== null && tr.social_fraction >= 0.5 ? "green" : "amber") : "red",
    });
  }
  const lastSplit = d.split_trials.at(-1);
  if (lastSplit) {
    const flagged = d.split_summary.status === "flagged";
    ev.push({
      t: lastSplit.t_end + 1,
      text:
        d.split_summary.status === "insufficient"
          ? `SOCIAL PREFERENCE not measurable · ${d.split_summary.summary}`
          : `SOCIAL PREFERENCE ${pct(d.split_summary.value)} vs cut-off ${pct(d.settings.social_flag_below)} → ${flagged ? "SIGN SEEN" : "NOT SEEN"} [GeoPref]`,
      tone: d.split_summary.status === "insufficient" ? "red" : flagged ? "magenta" : "green",
    });
  }

  const v = d.voice_check;
  if (v) {
    ev.push({ t: v.speak_start, text: "SOUND CHECK · parent says “hello” from behind", tone: "dim" });
    ev.push({
      t: v.speak_end,
      text: v.heard
        ? `VOICE LEVEL ${v.call_rms} vs room ${v.baseline_rms} → session threshold set`
        : "VOICE NOT HEARD · default threshold",
      tone: v.heard ? "cyan" : "amber",
    });
  }

  for (const tr of d.name_trials) {
    ev.push({ t: tr.cue_t, text: `CALL ${tr.index + 1} · cue shown → parent calls the name`, tone: "amber" });
    if (tr.onset_detected) ev.push({ t: tr.onset_t, text: `VOICE DETECTED +${sec(tr.onset_t - tr.cue_t)} after cue`, tone: "magenta" });
    if (tr.responded && tr.turn_t !== null) {
      ev.push({
        t: tr.turn_t,
        text: `HEAD TURN ${tr.peak_turn_deg ?? "—"}° · latency ${sec(tr.latency_ms ?? 0)}${tr.latency_estimated ? " (est.)" : ""} ✓`,
        tone: "green",
      });
    } else {
      ev.push({
        t: tr.window_end,
        text: tr.valid ? `NO TURN within 4 s (peak ${tr.peak_turn_deg ?? "—"}°) ✗` : `CALL NOT USABLE · ${tr.reason ?? ""}`,
        tone: tr.valid ? "red" : "dim",
      });
    }
  }
  const lastName = d.name_trials.at(-1);
  if (lastName) {
    const valid = d.name_trials.filter((x) => x.valid);
    const turned = valid.filter((x) => x.responded).length;
    ev.push({
      t: lastName.t_end + 1,
      text:
        d.name_summary.status === "insufficient"
          ? `NAME RESPONSE not measurable · ${d.name_summary.summary}`
          : `NAME RESPONSE ${turned}/${valid.length} → ${d.name_summary.status === "flagged" ? "SIGN SEEN" : "NOT SEEN"} [Campbell 2019]`,
      tone: d.name_summary.status === "insufficient" ? "red" : d.name_summary.status === "flagged" ? "magenta" : "green",
    });
  }

  // Final computation, straight from the report.
  const end = bounds(d).end - 2000;
  const lk = report.clinician.likelihood;
  ev.push({ t: end, text: `PRIOR ${pct(lk.prior)} autism (India, INCLEN 2018)`, tone: "cyan" });
  lk.evidence_used.forEach((e, i) =>
    ev.push({ t: end + 200 * (i + 1), text: `× LR ${e.lr}  ${e.key} ${e.result === "flagged" ? "SIGN SEEN" : "not seen"}`, tone: "cyan" }),
  );
  lk.evidence_excluded.forEach((e, i) =>
    ev.push({ t: end + 600 + 100 * i, text: `– ${e.key} not used: ${e.reason.split(".")[0]}`, tone: "dim" }),
  );
  ev.push({
    t: end + 1000,
    text: lk.available ? `= LIKELIHOOD ${lk.per_100}% (${lk.times_population}× population)` : "LIKELIHOOD not estimated",
    tone: "magenta",
  });
  ev.push({ t: end + 1400, text: `OUTCOME → ${report.clinician.outcome.toUpperCase().replace("_", " ")}`, tone: "magenta" });
  return ev.sort((a, b) => a.t - b.t);
}

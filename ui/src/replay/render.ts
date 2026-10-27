import { NAME_CALL } from "../config";
import { REPLAY_POINTS } from "../cv/features";
import { drawAttention, drawCalm, drawGeometric, drawSocial, drawToy } from "../stimuli/draw";
import type { Report } from "../types";
import { bounds, indexAt, PHASE_LABEL, phaseAt, type ReplayData, type ReplayEvent, type ReplayMedia, type Tone } from "./data";

export const W = 1920;
export const H = 1080;
const MAIN = { x: 24, y: 84, w: 1400, h: 788 };
const PANEL = { x: 1448, y: 84, w: 448, h: 788 };
export const TL = { x: 24, y: 892, w: 1872, h: 168 };
const PIP = { w: 448, h: 280 };

const C: Record<Tone | "bg" | "text" | "grid" | "panel", string> = {
  bg: "#04070d",
  panel: "rgba(8, 18, 32, 0.82)",
  grid: "rgba(0, 229, 255, 0.05)",
  text: "#d6ecff",
  cyan: "#00e5ff",
  magenta: "#ff3df2",
  amber: "#ffb020",
  green: "#39ff88",
  red: "#ff4d6d",
  dim: "#6d87a6",
};
const MONO = '"JetBrains Mono", "SF Mono", ui-monospace, Menlo, monospace';

export interface RenderInput {
  d: ReplayData;
  report: Report;
  events: ReplayEvent[];
  t: number;
  video: HTMLVideoElement | null;
  keypoints: ReplayMedia["keypoints"] | null;
  keypointTimes: number[] | null; // keypoints[i].t, precomputed for lookup
  stimulus: (kind: "social" | "geometric", clip: number) => HTMLVideoElement | null;
  timelineLayer: HTMLCanvasElement;
  pip: HTMLCanvasElement;
}

const font = (px: number, weight = 500) => `${weight} ${px}px ${MONO}`;

function glowText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, color: string, px = 16, weight = 600) {
  ctx.save();
  ctx.font = font(px, weight);
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 10;
  ctx.fillText(text, x, y);
  ctx.restore();
}

function frame(ctx: CanvasRenderingContext2D, r: { x: number; y: number; w: number; h: number }, color: string, label?: string) {
  ctx.save();
  ctx.fillStyle = C.panel;
  ctx.fillRect(r.x, r.y, r.w, r.h);
  ctx.strokeStyle = color;
  ctx.globalAlpha = 0.5;
  ctx.lineWidth = 1;
  ctx.strokeRect(r.x + 0.5, r.y + 0.5, r.w - 1, r.h - 1);
  ctx.globalAlpha = 1;
  // corner brackets
  const k = 18;
  ctx.lineWidth = 3;
  ctx.shadowColor = color;
  ctx.shadowBlur = 8;
  for (const [cx, cy, dx, dy] of [
    [r.x, r.y, 1, 1],
    [r.x + r.w, r.y, -1, 1],
    [r.x, r.y + r.h, 1, -1],
    [r.x + r.w, r.y + r.h, -1, -1],
  ]) {
    ctx.beginPath();
    ctx.moveTo(cx + dx * k, cy);
    ctx.lineTo(cx, cy);
    ctx.lineTo(cx, cy + dy * k);
    ctx.stroke();
  }
  ctx.restore();
  if (label) glowText(ctx, label, r.x + 14, r.y - 8, color, 13, 600);
}

const clock = (ms: number) => {
  const s = Math.max(0, ms) / 1000;
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${(s % 60).toFixed(1).padStart(4, "0")}`;
};

function wrap(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const words = text.split(" ");
  const lines: string[] = [];
  let line = "";
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (ctx.measureText(test).width > maxW && line) {
      lines.push(line);
      line = w;
    } else line = test;
  }
  if (line) lines.push(line);
  return lines;
}

/** Frame index nearest to t (or -1 if none within 150 ms). */
function frameAt(d: ReplayData, t: number): number {
  const i = indexAt(d.frames.t, t);
  if (i < 0) return -1;
  const j = i + 1 < d.frames.t.length && d.frames.t[i + 1] - t < t - d.frames.t[i] ? i + 1 : i;
  return Math.abs(d.frames.t[j] - t) < 150 ? j : -1;
}

/** Majority gaze class over the last 300 ms (smooths single-frame flicker). */
function gazeClassAt(d: ReplayData, t: number): string | null {
  const counts: Record<string, number> = {};
  for (let i = indexAt(d.frames.t, t); i >= 0 && d.frames.t[i] >= t - 300; i--) {
    const g = d.frames.gaze[i];
    if (g) counts[g] = (counts[g] ?? 0) + 1;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
}

// --- header -----------------------------------------------------------------------------

function header(ctx: CanvasRenderingContext2D, inp: RenderInput) {
  const { d, t } = inp;
  const { start } = bounds(d);
  glowText(ctx, "OMLI", 24, 46, C.cyan, 28, 800);
  ctx.font = font(18, 500);
  ctx.fillStyle = C.text;
  ctx.fillText("BEHAVIOR SCREENING · ANALYSIS REPLAY", 112, 46);
  const phase = PHASE_LABEL(phaseAt(d, t));
  ctx.font = font(15, 600);
  const pw = ctx.measureText(phase).width + 28;
  ctx.save();
  ctx.fillStyle = "rgba(255, 61, 242, 0.12)";
  ctx.strokeStyle = C.magenta;
  ctx.shadowColor = C.magenta;
  ctx.shadowBlur = 10;
  ctx.fillRect(820, 24, pw, 32);
  ctx.strokeRect(820.5, 24.5, pw, 32);
  ctx.restore();
  glowText(ctx, phase, 834, 46, C.magenta, 15, 700);
  glowText(ctx, `T+ ${clock(t - start)}`, 1460, 46, C.cyan, 22, 700);
  ctx.font = font(12, 500);
  ctx.fillStyle = C.dim;
  const c = inp.report.clinician;
  ctx.fillText(`AGE ${c.age_months} M · SCORING v${c.scoring_version}`, 1660, 32);
  ctx.fillText(`STIMULI ${c.stimulus_set.split(" ")[0]}`, 1660, 50);
}

// --- main view --------------------------------------------------------------------------

function fitRect(vw: number, vh: number) {
  const s = Math.min(MAIN.w / vw, MAIN.h / vh);
  const w = vw * s;
  const h = vh * s;
  return { x: MAIN.x + (MAIN.w - w) / 2, y: MAIN.y + (MAIN.h - h) / 2, w, h };
}

function mainView(ctx: CanvasRenderingContext2D, inp: RenderInput) {
  const { d, t, video } = inp;
  frame(ctx, MAIN, C.cyan, "SUBJECT CAMERA");
  const fi = frameAt(d, t);
  const hasVideo = !!video && video.readyState >= 2 && video.videoWidth > 0;

  ctx.save();
  ctx.beginPath();
  ctx.rect(MAIN.x, MAIN.y, MAIN.w, MAIN.h);
  ctx.clip();
  if (hasVideo) {
    const r = fitRect(video.videoWidth, video.videoHeight);
    ctx.save();
    ctx.translate(r.x + r.w, r.y);
    ctx.scale(-1, 1); // mirror, like a selfie
    ctx.filter = "saturate(0.75) contrast(1.05)";
    ctx.drawImage(video, 0, 0, r.w, r.h);
    ctx.restore();
    ctx.fillStyle = "rgba(0, 20, 40, 0.18)";
    ctx.fillRect(r.x, r.y, r.w, r.h);
    faceOverlay(ctx, inp, r, fi);
  } else {
    wireframeHead(ctx, inp, fi);
  }
  scanlines(ctx);
  ctx.restore();
  nameTurnGauge(ctx, inp, fi);
}

function scanlines(ctx: CanvasRenderingContext2D) {
  ctx.save();
  ctx.fillStyle = "rgba(0, 0, 0, 0.12)";
  for (let y = MAIN.y; y < MAIN.y + MAIN.h; y += 4) ctx.fillRect(MAIN.x, y, MAIN.w, 1);
  ctx.restore();
}

function faceOverlay(ctx: CanvasRenderingContext2D, inp: RenderInput, r: { x: number; y: number; w: number; h: number }, fi: number) {
  const { d, t, keypoints, keypointTimes } = inp;
  const kp = keypoints && keypointTimes ? keypoints[indexAt(keypointTimes, t)] : undefined;
  const face = fi >= 0 && d.frames.face[fi] === 1;
  if (!face || !kp || Math.abs(kp.t - t) > 150) {
    glowText(ctx, "◌ NO FACE LOCK", MAIN.x + 24, MAIN.y + MAIN.h - 24, C.red, 18, 700);
    return;
  }
  const P = (k: number) => ({ x: r.x + (1 - kp.p[2 * k]) * r.w, y: r.y + kp.p[2 * k + 1] * r.h });
  const n = REPLAY_POINTS.rightEye.length;
  const eyes = [
    Array.from({ length: n }, (_, i) => P(i)),
    Array.from({ length: n }, (_, i) => P(n + i)),
  ];
  const irises = [P(2 * n), P(2 * n + 1)];
  const [nose, forehead, chin, cheekA, cheekB] = [0, 1, 2, 3, 4].map((i) => P(2 * n + 2 + i));

  // face box
  const left = Math.min(cheekA.x, cheekB.x) - 30;
  const right = Math.max(cheekA.x, cheekB.x) + 30;
  const top = forehead.y - 50;
  const bottom = chin.y + 20;
  frameBox(ctx, left, top, right - left, bottom - top, C.cyan);
  glowText(ctx, "FACE LOCK ✓", left, top - 10, C.cyan, 14, 700);

  // eyes + gaze rays
  ctx.save();
  ctx.lineWidth = 2;
  ctx.strokeStyle = C.cyan;
  ctx.shadowColor = C.cyan;
  ctx.shadowBlur = 8;
  for (const eye of eyes) {
    ctx.beginPath();
    eye.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
    ctx.closePath();
    ctx.stroke();
  }
  eyes.forEach((eye, i) => {
    const cx = eye.reduce((s, p) => s + p.x, 0) / eye.length;
    const cy = eye.reduce((s, p) => s + p.y, 0) / eye.length;
    const ir = irises[i];
    ctx.strokeStyle = C.magenta;
    ctx.shadowColor = C.magenta;
    ctx.beginPath();
    ctx.moveTo(ir.x, ir.y);
    ctx.lineTo(ir.x + (ir.x - cx) * 9, ir.y + (ir.y - cy) * 9);
    ctx.stroke();
    ctx.fillStyle = C.magenta;
    ctx.beginPath();
    ctx.arc(ir.x, ir.y, 4, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.restore();

  headAxis(ctx, nose.x, nose.y, fi, inp);
}

function frameBox(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, color: string) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.shadowColor = color;
  ctx.shadowBlur = 10;
  const k = Math.min(w, h) * 0.18;
  for (const [cx, cy, dx, dy] of [
    [x, y, 1, 1],
    [x + w, y, -1, 1],
    [x, y + h, 1, -1],
    [x + w, y + h, -1, -1],
  ]) {
    ctx.beginPath();
    ctx.moveTo(cx + dx * k, cy);
    ctx.lineTo(cx, cy);
    ctx.lineTo(cx, cy + dy * k);
    ctx.stroke();
  }
  ctx.restore();
}

function headAxis(ctx: CanvasRenderingContext2D, x: number, y: number, fi: number, inp: RenderInput) {
  const yaw = fi >= 0 ? inp.d.frames.yaw[fi] : null;
  const pitch = fi >= 0 ? inp.d.frames.pitch[fi] : null;
  if (yaw === null || pitch === null) return;
  const neutral = inp.d.settings.median_yaw ?? 0;
  const dx = -(yaw - neutral) * 5; // mirrored view
  const dy = -pitch * 5;
  ctx.save();
  ctx.strokeStyle = C.amber;
  ctx.fillStyle = C.amber;
  ctx.lineWidth = 3;
  ctx.shadowColor = C.amber;
  ctx.shadowBlur = 10;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + dx, y + dy);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(x + dx, y + dy, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
  glowText(ctx, `YAW ${(yaw - neutral).toFixed(0)}°  PITCH ${pitch.toFixed(0)}°`, x + 24, y + 6, C.amber, 14, 700);
}

/** Used when this device has no camera recording: a wireframe head driven by the recorded angles. */
function wireframeHead(ctx: CanvasRenderingContext2D, inp: RenderInput, fi: number) {
  const { d } = inp;
  const cx = MAIN.x + MAIN.w * 0.42;
  const cy = MAIN.y + MAIN.h * 0.52;
  ctx.save();
  ctx.strokeStyle = C.grid;
  for (let x = MAIN.x; x < MAIN.x + MAIN.w; x += 40) {
    ctx.beginPath();
    ctx.moveTo(x, MAIN.y);
    ctx.lineTo(x, MAIN.y + MAIN.h);
    ctx.stroke();
  }
  for (let y = MAIN.y; y < MAIN.y + MAIN.h; y += 40) {
    ctx.beginPath();
    ctx.moveTo(MAIN.x, y);
    ctx.lineTo(MAIN.x + MAIN.w, y);
    ctx.stroke();
  }
  ctx.restore();
  ctx.font = font(13, 500);
  ctx.fillStyle = C.dim;
  ctx.fillText("NO CAMERA RECORDING ON THIS DEVICE · HEAD RECONSTRUCTED FROM MEASUREMENTS", MAIN.x + 24, MAIN.y + MAIN.h - 24);

  const face = fi >= 0 && d.frames.face[fi] === 1;
  if (!face) {
    glowText(ctx, "◌ NO FACE IN FRAME", cx - 110, cy, C.red, 22, 700);
    return;
  }
  const neutral = d.settings.median_yaw ?? 0;
  const yaw = ((d.frames.yaw[fi] ?? neutral) - neutral) * (Math.PI / 180);
  const pitch = (d.frames.pitch[fi] ?? 0) * (Math.PI / 180);
  const R = 190;
  ctx.save();
  ctx.strokeStyle = C.cyan;
  ctx.shadowColor = C.cyan;
  ctx.shadowBlur = 12;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.ellipse(cx, cy, R * 0.82, R, 0, 0, Math.PI * 2);
  ctx.stroke();
  // meridians follow yaw, parallels follow pitch
  ctx.globalAlpha = 0.45;
  for (const k of [-0.6, -0.3, 0, 0.3, 0.6]) {
    const ox = Math.sin(-yaw + k) * R * 0.82;
    ctx.save();
    ctx.translate(ox, 0);
    ctx.beginPath();
    ctx.ellipse(cx, cy, Math.abs(Math.cos(-yaw + k)) * 6 + Math.abs(ox) * 0.05 + 2, R, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }
  for (const k of [-0.5, 0, 0.5]) {
    const oy = Math.sin(pitch + k) * R;
    ctx.beginPath();
    ctx.ellipse(cx, cy + oy, R * 0.82 * Math.cos(k), 10, 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  // features, shifted by head angle
  const fx = cx + Math.sin(-yaw) * R * 0.6;
  const fy = cy + Math.sin(pitch) * R * 0.5;
  const ix = (d.frames.ix[fi] ?? 0.5) - 0.5;
  const iy = (d.frames.iy[fi] ?? 0.4) - 0.4;
  for (const side of [-1, 1]) {
    const ex = fx + side * 62;
    const ey = fy - 30;
    ctx.strokeStyle = C.cyan;
    ctx.beginPath();
    ctx.ellipse(ex, ey, 34, 16, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = C.magenta;
    ctx.shadowColor = C.magenta;
    ctx.beginPath();
    ctx.arc(ex - ix * 70, ey + iy * 40, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowColor = C.cyan;
  }
  ctx.beginPath();
  ctx.moveTo(fx, fy - 5);
  ctx.lineTo(fx - 10, fy + 35);
  ctx.lineTo(fx + 8, fy + 38);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(fx, fy + 75, 34, 0.15 * Math.PI, 0.85 * Math.PI);
  ctx.stroke();
  ctx.restore();
  headAxis(ctx, fx, fy + 30, fi, inp);
}

function nameTurnGauge(ctx: CanvasRenderingContext2D, inp: RenderInput, fi: number) {
  const { d, t } = inp;
  const tr = d.name_trials.find((x) => x.onset_t - 500 <= t && t <= x.window_end + 1500);
  if (!tr || tr.baseline_yaw === null) return;
  const yaw = fi >= 0 ? d.frames.yaw[fi] : null;
  const dev = yaw === null ? null : Math.abs(yaw - tr.baseline_yaw);
  const x = MAIN.x + 24;
  const y = MAIN.y + 30;
  const w = 380;
  ctx.save();
  ctx.fillStyle = C.panel;
  ctx.fillRect(x, y, w + 24, 104);
  ctx.restore();
  glowText(ctx, `HEAD TURN · CALL ${tr.index + 1}`, x + 12, y + 24, C.amber, 14, 700);
  const thr = d.settings.name_turn_deg;
  const maxDeg = 60;
  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.fillRect(x + 12, y + 40, w, 18);
  const val = dev === null ? 0 : Math.min(dev, maxDeg);
  const over = dev !== null && dev >= thr;
  ctx.save();
  ctx.fillStyle = over ? C.green : C.amber;
  ctx.shadowColor = ctx.fillStyle;
  ctx.shadowBlur = 12;
  ctx.fillRect(x + 12, y + 40, (val / maxDeg) * w, 18);
  ctx.restore();
  ctx.strokeStyle = C.text;
  ctx.setLineDash([4, 3]);
  ctx.beginPath();
  ctx.moveTo(x + 12 + (thr / maxDeg) * w, y + 34);
  ctx.lineTo(x + 12 + (thr / maxDeg) * w, y + 64);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.font = font(13, 500);
  ctx.fillStyle = C.text;
  ctx.fillText(`${dev === null ? "face out of view" : `${dev.toFixed(0)}° from baseline`}   threshold ${thr}°`, x + 12, y + 80);
  const status =
    tr.turn_t !== null && t >= tr.turn_t
      ? { text: `TURNED · ${((tr.latency_ms ?? 0) / 1000).toFixed(1)} s ✓`, c: C.green }
      : t > tr.window_end
        ? tr.valid
          ? { text: "NO TURN IN 4 s ✗", c: C.red }
          : { text: "CALL NOT USABLE", c: C.dim }
        : t >= tr.onset_t
          ? { text: "LISTENING FOR RESPONSE…", c: C.amber }
          : { text: "WAITING FOR CALL", c: C.dim };
  glowText(ctx, status.text, x + 12, y + 98, status.c, 14, 700);
}

// --- child's screen (picture in picture) -----------------------------------------------

function pipView(ctx: CanvasRenderingContext2D, inp: RenderInput) {
  const { d, t, pip } = inp;
  const p = pip.getContext("2d")!;
  const w = PIP.w;
  const h = PIP.h;
  p.clearRect(0, 0, w, h);
  const phase = phaseAt(d, t);
  const fi = frameAt(d, t);
  const gx = fi >= 0 ? d.frames.gx[fi] : null;
  const gy = fi >= 0 ? d.frames.gy[fi] : null;
  let label = "CHILD'S SCREEN";

  if (phase.kind === "calibration") {
    p.fillStyle = "#101828";
    p.fillRect(0, 0, w, h);
    const pt = phase.point;
    const prog = Math.min(1, (t - pt.t_start) / Math.max(1, pt.t_end - pt.t_start));
    drawToy(p, pt.x * w, pt.y * h, Math.min(w, h) * (0.09 - 0.05 * prog), t);
    if (gx !== null && gy !== null) gazeDot(p, gx * w, Math.max(0, Math.min(1, gy)) * h);
    label = `CHILD'S SCREEN · TARGET ${phase.index + 1} (${pt.phase})`;
  } else if (phase.kind === "split") {
    const tr = phase.trial;
    const local = t - tr.t_start;
    const sides: ("left" | "right")[] = ["left", "right"];
    for (const side of sides) {
      const kind = side === tr.social_side ? "social" : "geometric";
      const x0 = side === "left" ? 0 : w / 2;
      p.save();
      p.beginPath();
      p.rect(x0, 0, w / 2, h);
      p.clip();
      const v = inp.stimulus(kind, tr.clip);
      if (v && v.readyState >= 2) {
        const s = Math.max(w / 2 / v.videoWidth, h / v.videoHeight);
        const vw = v.videoWidth * s;
        const vh = v.videoHeight * s;
        p.drawImage(v, x0 + (w / 2 - vw) / 2, (h - vh) / 2, vw, vh);
      } else {
        p.translate(x0, 0);
        (kind === "social" ? drawSocial : drawGeometric)(p, w / 2, h, local);
      }
      p.restore();
    }
    const cls = gazeClassAt(d, t);
    for (const side of sides) {
      const x0 = side === "left" ? 0 : w / 2;
      const looking = cls === side;
      const social = side === tr.social_side;
      if (!looking) {
        p.fillStyle = "rgba(0,0,0,0.45)";
        p.fillRect(x0, 0, w / 2, h);
      } else {
        const c = social ? C.green : C.amber;
        p.save();
        p.strokeStyle = c;
        p.lineWidth = 6;
        p.shadowColor = c;
        p.shadowBlur = 24;
        p.strokeRect(x0 + 3, 3, w / 2 - 6, h - 6);
        p.restore();
      }
      p.font = font(12, 700);
      p.fillStyle = social ? C.green : C.amber;
      p.fillText(social ? "SOCIAL" : "OBJECTS", x0 + 10, 20);
    }
    p.fillStyle = "#000";
    p.fillRect(w / 2 - 2, 0, 4, h);
    if (gx !== null && t >= tr.settle_end) {
      p.save();
      p.strokeStyle = C.cyan;
      p.shadowColor = C.cyan;
      p.shadowBlur = 12;
      p.lineWidth = 2;
      p.beginPath();
      p.moveTo(gx * w, 0);
      p.lineTo(gx * w, h);
      p.stroke();
      p.restore();
      gazeDot(p, gx * w, h / 2);
    }
    label =
      cls === "left" || cls === "right"
        ? `LOOKING AT: ${cls === tr.social_side ? "SOCIAL ▲" : "OBJECTS ▼"}`
        : cls === "center"
          ? "LOOKING AT: MIDDLE"
          : cls === "off"
            ? "LOOKING AWAY"
            : "SETTLING…";
  } else if (phase.kind === "name") {
    drawCalm(p, w, h, t);
    const tr = phase.trial;
    if (tr.cue_t <= t && t < tr.cue_t + NAME_CALL.cueShowMs) {
      p.fillStyle = "rgba(255,255,255,0.85)";
      p.fillRect(w / 2 - 120, 8, 240, 24);
      p.font = font(12, 700);
      p.fillStyle = "#333";
      p.fillText("🔔 Call the name now", w / 2 - 80, 25);
    }
    label = "CHILD'S SCREEN · CALM SCENE (SILENT)";
  } else if (phase.kind === "voice") {
    p.fillStyle = "#0b1220";
    p.fillRect(0, 0, w, h);
    p.font = font(16, 700);
    p.fillStyle = C.amber;
    p.fillText("SOUND CHECK · “hello”", 110, h / 2);
  } else {
    drawAttention(p, w, h, t);
  }

  const x = MAIN.x + MAIN.w - w - 20;
  const y = MAIN.y + 20;
  ctx.drawImage(pip, x, y, w, h);
  frameBoxOutline(ctx, x, y, w, h);
  glowText(ctx, label, x + 8, y + h + 22, C.cyan, 13, 700);
}

function frameBoxOutline(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  ctx.save();
  ctx.strokeStyle = C.cyan;
  ctx.lineWidth = 2;
  ctx.shadowColor = C.cyan;
  ctx.shadowBlur = 14;
  ctx.strokeRect(x, y, w, h);
  ctx.restore();
}

function gazeDot(p: CanvasRenderingContext2D, x: number, y: number) {
  p.save();
  p.fillStyle = "rgba(0, 229, 255, 0.25)";
  p.beginPath();
  p.arc(x, y, 18, 0, Math.PI * 2);
  p.fill();
  p.fillStyle = C.cyan;
  p.shadowColor = C.cyan;
  p.shadowBlur = 16;
  p.beginPath();
  p.arc(x, y, 6, 0, Math.PI * 2);
  p.fill();
  p.restore();
}

// --- side panel -------------------------------------------------------------------------

function sidePanel(ctx: CanvasRenderingContext2D, inp: RenderInput) {
  const { d, t, events } = inp;
  frame(ctx, PANEL, C.magenta, "LIVE ANALYSIS");
  let y = PANEL.y + 36;
  const x = PANEL.x + 20;

  // gaze model
  const lastCal = d.calibration.points.at(-1);
  const calDone = lastCal && t > lastCal.t_end;
  ctx.font = font(12, 700);
  ctx.fillStyle = C.dim;
  ctx.fillText("GAZE MODEL", x, y);
  ctx.font = font(15, 600);
  ctx.fillStyle = calDone ? (d.calibration.summary.passed ? C.cyan : C.red) : C.dim;
  ctx.fillText(
    calDone
      ? `${d.calibration.summary.quality.toUpperCase()} · side ${Math.round((d.calibration.summary.side_accuracy ?? 0) * 100)}%`
      : `calibrating ${d.calibration.points.filter((p) => p.t_start <= t).length}/${d.calibration.points.length}`,
    x + 150,
    y,
  );
  y += 34;

  // social preference (running)
  ctx.font = font(12, 700);
  ctx.fillStyle = C.dim;
  ctx.fillText("SOCIAL PREFERENCE", x, y);
  let social = 0;
  let total = 0;
  const rows: { label: string; frac: number | null; active: boolean; valid: boolean | null }[] = [];
  for (const tr of d.split_trials) {
    if (t < tr.t_start) continue;
    let s = 0;
    let n = 0;
    const end = Math.min(t, tr.t_end);
    for (let i = indexAt(d.frames.t, tr.settle_end) + 1; i < d.frames.t.length && d.frames.t[i] <= end; i++) {
      const g = d.frames.gaze[i];
      if (g === "left" || g === "right") {
        n++;
        if (g === tr.social_side) s++;
      }
    }
    if (tr.valid !== false || t <= tr.t_end) {
      social += s;
      total += n;
    }
    rows.push({ label: `T${tr.index + 1}`, frac: n ? s / n : null, active: t <= tr.t_end, valid: t > tr.t_end ? tr.valid : null });
  }
  const running = total ? social / total : null;
  glowText(
    ctx,
    running === null ? "—" : `${Math.round(running * 100)}%`,
    x + 220,
    y + 4,
    running === null ? C.dim : running < d.settings.social_flag_below ? C.magenta : C.green,
    26,
    800,
  );
  ctx.font = font(11, 500);
  ctx.fillStyle = C.dim;
  ctx.fillText(`cut-off ${Math.round(d.settings.social_flag_below * 100)}%`, x + 310, y + 2);
  y += 16;
  for (const r of rows) {
    y += 20;
    ctx.font = font(12, 600);
    ctx.fillStyle = r.active ? C.cyan : C.text;
    ctx.fillText(r.label, x, y);
    ctx.fillStyle = "rgba(255,255,255,0.08)";
    ctx.fillRect(x + 40, y - 11, 260, 12);
    if (r.frac !== null) {
      ctx.fillStyle = r.frac >= 0.5 ? C.green : C.amber;
      ctx.fillRect(x + 40, y - 11, 260 * r.frac, 12);
    }
    ctx.fillStyle = r.valid === false ? C.red : C.text;
    ctx.fillText(`${r.frac === null ? "—" : `${Math.round(r.frac * 100)}%`}${r.valid === false ? " ✗" : ""}`, x + 310, y);
  }
  y += 34;

  // name response
  ctx.font = font(12, 700);
  ctx.fillStyle = C.dim;
  ctx.fillText("RESPONSE TO NAME", x, y);
  for (const tr of d.name_trials) {
    if (t < tr.cue_t) continue;
    y += 20;
    const done = t > tr.window_end || (tr.turn_t !== null && t >= tr.turn_t);
    const turned = tr.turn_t !== null && t >= tr.turn_t;
    ctx.font = font(12, 600);
    ctx.fillStyle = C.text;
    ctx.fillText(`CALL ${tr.index + 1}`, x, y);
    ctx.fillStyle = tr.onset_detected && t >= tr.onset_t ? C.magenta : C.dim;
    ctx.fillText(tr.onset_detected && t >= tr.onset_t ? `voice +${((tr.onset_t - tr.cue_t) / 1000).toFixed(1)}s` : "voice …", x + 70, y);
    ctx.fillStyle = turned ? C.green : done ? (tr.valid ? C.red : C.dim) : C.amber;
    ctx.fillText(
      turned ? `turn ${((tr.latency_ms ?? 0) / 1000).toFixed(1)}s ✓` : done ? (tr.valid ? "no turn ✗" : "not usable") : "watching…",
      x + 210,
      y,
    );
  }
  y += 30;

  // event stream
  ctx.strokeStyle = "rgba(255,61,242,0.3)";
  ctx.beginPath();
  ctx.moveTo(x, y - 14);
  ctx.lineTo(PANEL.x + PANEL.w - 20, y - 14);
  ctx.stroke();
  ctx.font = font(12, 700);
  ctx.fillStyle = C.dim;
  ctx.fillText("EVENT STREAM", x, y + 4);
  y += 14;
  const shown = events.filter((e) => e.t <= t);
  const { start } = bounds(d);
  ctx.font = font(12.5, 500);
  const lines: { text: string; tone: Tone; stamp: string; first: boolean; age: number }[] = [];
  for (const e of shown) {
    wrap(ctx, e.text, PANEL.w - 110).forEach((line, i) =>
      lines.push({ text: line, tone: e.tone, stamp: clock(e.t - start), first: i === 0, age: t - e.t }),
    );
  }
  const maxLines = Math.floor((PANEL.y + PANEL.h - y - 12) / 19);
  for (const l of lines.slice(-maxLines)) {
    y += 19;
    ctx.globalAlpha = l.age < 600 ? 1 : 0.85;
    if (l.first) {
      ctx.fillStyle = C.dim;
      ctx.fillText(l.stamp, x, y);
    }
    ctx.fillStyle = C[l.tone];
    if (l.age < 600) {
      ctx.save();
      ctx.shadowColor = C[l.tone];
      ctx.shadowBlur = 10;
      ctx.fillText(l.text, x + 84, y);
      ctx.restore();
    } else ctx.fillText(l.text, x + 84, y);
    ctx.globalAlpha = 1;
  }
}

// --- timeline -----------------------------------------------------------------------------

const ROWS = { phase: [0, 20], gaze: [28, 48], yaw: [56, 108], audio: [116, 164] } as const;

/** Static part of the timeline, drawn once. */
export function buildTimelineLayer(d: ReplayData): HTMLCanvasElement {
  const cv = document.createElement("canvas");
  cv.width = TL.w;
  cv.height = TL.h;
  const g = cv.getContext("2d")!;
  const { start, end } = bounds(d);
  const X = (t: number) => ((t - start) / (end - start)) * TL.w;

  g.fillStyle = "rgba(8, 18, 32, 0.9)";
  g.fillRect(0, 0, TL.w, TL.h);

  // phase band
  const band = (a: number, b: number, color: string, text: string) => {
    g.fillStyle = color;
    g.globalAlpha = 0.35;
    g.fillRect(X(a), ROWS.phase[0], Math.max(2, X(b) - X(a)), ROWS.phase[1] - ROWS.phase[0]);
    g.globalAlpha = 1;
    g.font = font(10, 700);
    g.fillStyle = C.text;
    if (X(b) - X(a) > 40) g.fillText(text, X(a) + 4, ROWS.phase[1] - 6);
  };
  const cal = d.calibration.points;
  if (cal.length) band(cal[0].t_start, cal.at(-1)!.t_end, C.cyan, "CALIBRATION");
  d.split_trials.forEach((tr) => band(tr.t_start, tr.t_end, "#8b5cff", `SOCIAL ${tr.index + 1}`));
  if (d.voice_check) band(d.voice_check.quiet_start, d.voice_check.speak_end, C.amber, "SOUND");
  d.name_trials.forEach((tr) => band(tr.t_start, tr.t_end, C.magenta, `NAME ${tr.index + 1}`));

  // gaze track (split screen): social-side looking green, object-side amber
  for (let i = 0; i < d.frames.t.length; i++) {
    const cls = d.frames.gaze[i];
    if (!cls) continue;
    const tr = d.split_trials.find((x) => x.settle_end <= d.frames.t[i] && d.frames.t[i] <= x.t_end);
    if (!tr) continue;
    g.fillStyle = cls === tr.social_side ? C.green : cls === "left" || cls === "right" ? C.amber : "#334155";
    g.fillRect(X(d.frames.t[i]), ROWS.gaze[0], 2, ROWS.gaze[1] - ROWS.gaze[0]);
  }

  // head yaw (deviation from the child's usual angle), ±turn threshold dashed
  const neutral = d.settings.median_yaw ?? 0;
  const yawMid = (ROWS.yaw[0] + ROWS.yaw[1]) / 2;
  const yawScale = (ROWS.yaw[1] - ROWS.yaw[0]) / 2 / 60;
  g.setLineDash([3, 4]);
  g.strokeStyle = "rgba(255,176,32,0.35)";
  for (const s of [-1, 1]) {
    g.beginPath();
    g.moveTo(0, yawMid - s * d.settings.name_turn_deg * yawScale);
    g.lineTo(TL.w, yawMid - s * d.settings.name_turn_deg * yawScale);
    g.stroke();
  }
  g.setLineDash([]);
  g.strokeStyle = C.amber;
  g.lineWidth = 1.5;
  g.beginPath();
  let pen = false;
  for (let i = 0; i < d.frames.t.length; i++) {
    const y = d.frames.yaw[i];
    if (y === null || !d.frames.face[i]) {
      pen = false;
      continue;
    }
    const py = yawMid - Math.max(-60, Math.min(60, y - neutral)) * yawScale;
    if (pen) g.lineTo(X(d.frames.t[i]), py);
    else g.moveTo(X(d.frames.t[i]), py);
    pen = true;
  }
  g.stroke();

  // audio waveform (log scale)
  const ah = ROWS.audio[1] - ROWS.audio[0];
  const amid = ROWS.audio[0] + ah / 2;
  g.fillStyle = "rgba(0,229,255,0.75)";
  for (let i = 0; i < d.audio.t.length; i++) {
    const v = Math.min(1, Math.log10(1 + d.audio.rms[i] * 400) / Math.log10(401));
    g.fillRect(X(d.audio.t[i]), amid - (v * ah) / 2, 1.5, v * ah);
  }

  // markers
  for (const tr of d.name_trials) {
    marker(g, X(tr.cue_t), C.amber, "CUE");
    if (tr.onset_detected) marker(g, X(tr.onset_t), C.magenta, "VOICE");
    if (tr.turn_t !== null) marker(g, X(tr.turn_t), C.green, "TURN");
  }

  // row labels
  g.font = font(10, 700);
  g.fillStyle = C.dim;
  g.fillText("GAZE", 4, ROWS.gaze[1] - 5);
  g.fillText("HEAD YAW", 4, ROWS.yaw[0] + 12);
  g.fillText("AUDIO", 4, ROWS.audio[0] + 12);
  return cv;
}

function marker(g: CanvasRenderingContext2D, x: number, color: string, text: string) {
  g.save();
  g.strokeStyle = color;
  g.fillStyle = color;
  g.shadowColor = color;
  g.shadowBlur = 6;
  g.beginPath();
  g.moveTo(x, ROWS.yaw[0]);
  g.lineTo(x, ROWS.audio[1]);
  g.stroke();
  g.font = font(9, 700);
  g.fillText(text, x + 3, ROWS.audio[1] - 2);
  g.restore();
}

function timeline(ctx: CanvasRenderingContext2D, inp: RenderInput) {
  const { d, t } = inp;
  const { start, end } = bounds(d);
  ctx.drawImage(inp.timelineLayer, TL.x, TL.y);
  const x = TL.x + ((t - start) / (end - start)) * TL.w;
  ctx.save();
  ctx.strokeStyle = C.cyan;
  ctx.lineWidth = 2;
  ctx.shadowColor = C.cyan;
  ctx.shadowBlur = 14;
  ctx.beginPath();
  ctx.moveTo(x, TL.y - 6);
  ctx.lineTo(x, TL.y + TL.h);
  ctx.stroke();
  ctx.restore();
  frameBoxOutline(ctx, TL.x, TL.y, TL.w, TL.h);
}

export function timeAtTimelineX(d: ReplayData, canvasX: number): number | null {
  if (canvasX < TL.x || canvasX > TL.x + TL.w) return null;
  const { start, end } = bounds(d);
  return start + ((canvasX - TL.x) / TL.w) * (end - start);
}

export function drawReplay(ctx: CanvasRenderingContext2D, inp: RenderInput) {
  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = C.grid;
  for (let x = 0; x < W; x += 48) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  }
  header(ctx, inp);
  mainView(ctx, inp);
  pipView(ctx, inp);
  sidePanel(ctx, inp);
  timeline(ctx, inp);
}

export function makePipCanvas(): HTMLCanvasElement {
  const cv = document.createElement("canvas");
  cv.width = PIP.w;
  cv.height = PIP.h;
  return cv;
}

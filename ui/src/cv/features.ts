import type { FaceLandmarkerResult, NormalizedLandmark } from "@mediapipe/tasks-vision";
import type { Frame } from "../types";

// MediaPipe face mesh indices (subject's right eye appears on the image's left).
const RIGHT_EYE = { outer: 33, inner: 133, top: 159, bottom: 145, iris: 468 };
const LEFT_EYE = { inner: 362, outer: 263, top: 386, bottom: 374, iris: 473 };

const DEG = 180 / Math.PI;

function ratio(value: number, from: number, to: number): number {
  const span = to - from;
  return Math.abs(span) < 1e-6 ? 0.5 : (value - from) / span;
}

/** Iris position inside each eye opening, both measured left-to-right in image space, averaged. */
function irisPosition(lm: NormalizedLandmark[]): { x: number; y: number } {
  const rx = ratio(lm[RIGHT_EYE.iris].x, lm[RIGHT_EYE.outer].x, lm[RIGHT_EYE.inner].x);
  const lx = ratio(lm[LEFT_EYE.iris].x, lm[LEFT_EYE.inner].x, lm[LEFT_EYE.outer].x);
  const ry = ratio(lm[RIGHT_EYE.iris].y, lm[RIGHT_EYE.top].y, lm[RIGHT_EYE.bottom].y);
  const ly = ratio(lm[LEFT_EYE.iris].y, lm[LEFT_EYE.top].y, lm[LEFT_EYE.bottom].y);
  return { x: (rx + lx) / 2, y: (ry + ly) / 2 };
}

/** Yaw/pitch/roll in degrees from MediaPipe's column-major 4x4 transformation matrix. */
function headPose(data: number[]): { yaw: number; pitch: number; roll: number } {
  const m = (row: number, col: number) => data[col * 4 + row];
  return {
    pitch: Math.atan2(m(2, 1), m(2, 2)) * DEG,
    yaw: Math.atan2(-m(2, 0), Math.hypot(m(2, 1), m(2, 2))) * DEG,
    roll: Math.atan2(m(1, 0), m(0, 0)) * DEG,
  };
}

export function extractFrame(result: FaceLandmarkerResult, t: number): Frame {
  const lm = result.faceLandmarks[0];
  if (!lm || lm.length < 478) return { t, face: false, blink: 0, smile: 0 };

  let minX = 1, maxX = 0, minY = 1, maxY = 0;
  for (const p of lm) {
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  }

  const scores = new Map(result.faceBlendshapes[0]?.categories.map((c) => [c.categoryName, c.score]) ?? []);
  const score = (name: string) => scores.get(name) ?? 0;
  const iris = irisPosition(lm);
  const matrix = result.facialTransformationMatrixes[0];
  const pose = matrix ? headPose(matrix.data) : undefined;

  return {
    t,
    face: true,
    iris_x: iris.x,
    iris_y: iris.y,
    yaw: pose?.yaw,
    pitch: pose?.pitch,
    roll: pose?.roll,
    face_x: (minX + maxX) / 2,
    face_y: (minY + maxY) / 2,
    face_w: maxX - minX,
    blink: Math.max(score("eyeBlinkLeft"), score("eyeBlinkRight")),
    smile: (score("mouthSmileLeft") + score("mouthSmileRight")) / 2,
  };
}

// Face points kept in memory for the on-device analysis replay only (never uploaded):
// eye outlines, iris centres, nose tip, forehead, chin, cheeks.
export const REPLAY_POINTS = {
  rightEye: [33, 160, 158, 133, 153, 144],
  leftEye: [362, 385, 387, 263, 373, 380],
  irises: [468, 473],
  face: [1, 10, 152, 234, 454], // nose tip, forehead, chin, cheeks
};
const REPLAY_INDICES = [
  ...REPLAY_POINTS.rightEye,
  ...REPLAY_POINTS.leftEye,
  ...REPLAY_POINTS.irises,
  ...REPLAY_POINTS.face,
];

/** Flat [x0, y0, x1, y1, ...] in REPLAY_INDICES order, normalised image coordinates. */
export function extractReplayPoints(result: FaceLandmarkerResult): number[] | null {
  const lm = result.faceLandmarks[0];
  if (!lm || lm.length < 478) return null;
  const out: number[] = [];
  for (const i of REPLAY_INDICES) out.push(Math.round(lm[i].x * 1e4) / 1e4, Math.round(lm[i].y * 1e4) / 1e4);
  return out;
}

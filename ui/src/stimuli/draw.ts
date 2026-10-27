// Drawn placeholder stimuli. Good enough to develop and test the pipeline;
// real screening needs proper videos (see STIMULI in config.ts).

const TAU = Math.PI * 2;

/** Smiling rotating star: the calibration target and attention-getter. */
export function drawToy(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, t: number) {
  ctx.save();
  ctx.translate(cx, cy);

  ctx.save();
  ctx.rotate(t / 700);
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const rad = i % 2 === 0 ? r : r * 0.5;
    const a = (i / 10) * TAU - Math.PI / 2;
    ctx.lineTo(Math.cos(a) * rad, Math.sin(a) * rad);
  }
  ctx.closePath();
  ctx.fillStyle = `hsl(${(t / 15) % 360}, 90%, 60%)`;
  ctx.fill();
  ctx.lineWidth = r * 0.06;
  ctx.strokeStyle = "white";
  ctx.stroke();
  ctx.restore();

  // Face, kept upright so it reads as a face.
  ctx.fillStyle = "#222";
  for (const dx of [-0.17, 0.17]) {
    ctx.beginPath();
    ctx.arc(dx * r, -0.08 * r, r * 0.07, 0, TAU);
    ctx.fill();
  }
  ctx.beginPath();
  ctx.arc(0, 0.04 * r, r * 0.17, 0.15 * Math.PI, 0.85 * Math.PI);
  ctx.lineWidth = r * 0.05;
  ctx.strokeStyle = "#222";
  ctx.stroke();
  ctx.restore();
}

export function drawAttention(ctx: CanvasRenderingContext2D, w: number, h: number, t: number) {
  ctx.fillStyle = "#101828";
  ctx.fillRect(0, 0, w, h);
  drawToy(ctx, w / 2, h / 2, Math.min(w, h) * 0.08 * (1 + 0.15 * Math.sin(t / 200)), t);
}

const SKIN = ["#8d5524", "#c68642"];

function drawKid(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number, t: number, phase: number) {
  const talk = Math.max(0, Math.sin(t / 110 + phase)) * (0.5 + 0.5 * Math.sin(t / 900 + phase));
  const blinking = (t + phase * 1000) % 3200 < 140;

  // Waving hand
  const wave = Math.sin(t / 180 + phase) * 0.5;
  ctx.save();
  ctx.translate(cx + r * 1.15, cy + r * 0.6);
  ctx.rotate(wave - 0.4);
  ctx.fillStyle = SKIN[Math.round(phase) % 2];
  ctx.fillRect(-r * 0.09, -r * 0.9, r * 0.18, r * 0.9);
  ctx.beginPath();
  ctx.arc(0, -r * 0.95, r * 0.2, 0, TAU);
  ctx.fill();
  ctx.restore();

  // Head + hair
  ctx.fillStyle = SKIN[Math.round(phase) % 2];
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, TAU);
  ctx.fill();
  ctx.fillStyle = "#1b1b1b";
  ctx.beginPath();
  ctx.arc(cx, cy - r * 0.15, r * 1.02, Math.PI * 1.05, Math.PI * 1.95);
  ctx.fill();

  // Eyes look straight at the viewer
  for (const dx of [-0.35, 0.35]) {
    ctx.fillStyle = "white";
    ctx.beginPath();
    ctx.ellipse(cx + dx * r, cy - r * 0.05, r * 0.18, blinking ? r * 0.02 : r * 0.14, 0, 0, TAU);
    ctx.fill();
    if (!blinking) {
      ctx.fillStyle = "#2b1a10";
      ctx.beginPath();
      ctx.arc(cx + dx * r, cy - r * 0.05, r * 0.085, 0, TAU);
      ctx.fill();
    }
  }

  // Talking mouth
  ctx.fillStyle = "#7a1f1f";
  ctx.beginPath();
  ctx.ellipse(cx, cy + r * 0.45, r * 0.22, r * (0.04 + 0.16 * talk), 0, 0, TAU);
  ctx.fill();
}

/** Two children talking and waving at the viewer. */
export function drawSocial(ctx: CanvasRenderingContext2D, w: number, h: number, t: number) {
  ctx.fillStyle = "#fde7d4";
  ctx.fillRect(0, 0, w, h);
  const r = Math.min(w / 5, h / 4);
  const bob = (p: number) => Math.sin(t / 400 + p) * r * 0.05;
  drawKid(ctx, w * 0.3, h * 0.42 + bob(0), r, t, 0);
  drawKid(ctx, w * 0.68, h * 0.58 + bob(2), r * 0.9, t, 1.7);
  watermark(ctx, h);
}

/** Moving coloured shapes, matched roughly for motion and colour with drawSocial. */
export function drawGeometric(ctx: CanvasRenderingContext2D, w: number, h: number, t: number) {
  ctx.fillStyle = "#14213d";
  ctx.fillRect(0, 0, w, h);
  const s = Math.min(w, h);
  for (let i = 0; i < 7; i++) {
    const x = w / 2 + Math.sin(t / (900 + i * 130) + i) * w * 0.32;
    const y = h / 2 + Math.cos(t / (700 + i * 170) + i * 2) * h * 0.32;
    const size = s * (0.07 + (i % 3) * 0.03);
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(t / (500 + i * 90));
    ctx.fillStyle = `hsl(${(i * 52 + t / 20) % 360}, 85%, 60%)`;
    ctx.beginPath();
    if (i % 3 === 0) ctx.arc(0, 0, size, 0, TAU);
    else if (i % 3 === 1) ctx.rect(-size, -size, size * 2, size * 2);
    else {
      ctx.moveTo(0, -size);
      ctx.lineTo(size, size);
      ctx.lineTo(-size, size);
    }
    ctx.fill();
    ctx.restore();
  }
  watermark(ctx, h);
}

/** Calm, low-salience background for the name-call module, so a head turn means something. */
export function drawCalm(ctx: CanvasRenderingContext2D, w: number, h: number, t: number) {
  ctx.fillStyle = "#e8f1fb";
  ctx.fillRect(0, 0, w, h);
  for (let i = 0; i < 6; i++) {
    const x = w * (0.3 + 0.4 * ((i * 0.37) % 1)) + Math.sin(t / 3000 + i) * w * 0.05;
    const y = h * (1.1 - ((t / 14000 + i / 6) % 1) * 1.2);
    ctx.fillStyle = `hsla(${200 + i * 15}, 70%, 70%, 0.55)`;
    ctx.beginPath();
    ctx.arc(x, y, Math.min(w, h) * (0.05 + (i % 3) * 0.015), 0, TAU);
    ctx.fill();
  }
}

function watermark(ctx: CanvasRenderingContext2D, h: number) {
  ctx.fillStyle = "rgba(127,127,127,0.35)";
  ctx.font = "12px system-ui";
  ctx.fillText("placeholder stimulus", 10, h - 10);
}

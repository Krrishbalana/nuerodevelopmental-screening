import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";
import { FACE_MODEL_URL, MEDIAPIPE_WASM } from "../config";
import type { AudioSample, BrightnessSample, Frame } from "../types";
import { extractFrame, extractReplayPoints } from "./features";

const AUDIO_INTERVAL_MS = 50;
const BRIGHTNESS_INTERVAL_MS = 500;

/**
 * Owns the camera + mic for the whole session and records features on one clock.
 * Video frames never leave the browser: only the numbers from extractFrame() are kept.
 */
export class Tracker {
  frames: Frame[] = [];
  audio: AudioSample[] = [];
  brightness: BrightnessSample[] = [];
  latest: Frame | null = null;
  /** On-device only: face points and a camera recording for the analysis replay. Never uploaded. */
  keypoints: { t: number; p: number[] }[] = [];
  recordingStartT: number | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  latestLuma: number | null = null;
  stream: MediaStream | null = null;

  private landmarker: FaceLandmarker | null = null;
  private video = document.createElement("video");
  private audioCtx: AudioContext | null = null;
  private timers: number[] = [];
  private t0 = 0;
  private running = false;
  private lastVideoTime = -1;
  private recentFrameTimes: number[] = [];

  async init(): Promise<void> {
    if (this.landmarker) return;
    const fileset = await FilesetResolver.forVisionTasks(MEDIAPIPE_WASM);
    const options = (delegate: "GPU" | "CPU") => ({
      baseOptions: { modelAssetPath: FACE_MODEL_URL, delegate },
      runningMode: "VIDEO" as const,
      numFaces: 1,
      outputFaceBlendshapes: true,
      outputFacialTransformationMatrixes: true,
    });
    try {
      this.landmarker = await FaceLandmarker.createFromOptions(fileset, options("GPU"));
    } catch {
      this.landmarker = await FaceLandmarker.createFromOptions(fileset, options("CPU"));
    }
  }

  async start(): Promise<void> {
    if (this.running) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
      // Raw levels: voice-onset detection needs a stable baseline, so no auto gain or suppression.
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    this.video.srcObject = this.stream;
    this.video.muted = true;
    this.video.playsInline = true;
    await this.video.play();

    this.t0 = performance.now();
    this.running = true;
    this.startAudio(this.stream);
    this.timers.push(window.setInterval(() => this.sampleBrightness(), BRIGHTNESS_INTERVAL_MS));
    requestAnimationFrame(this.loop);
  }

  /** Must be called from a click: browsers keep audio suspended until a user gesture. */
  resumeAudio(): void {
    void this.audioCtx?.resume();
  }

  now(): number {
    return performance.now() - this.t0;
  }

  fps(): number {
    const times = this.recentFrameTimes;
    return times.length < 2 ? 0 : ((times.length - 1) * 1000) / (times[times.length - 1] - times[0]);
  }

  audioBetween(start: number, end: number): AudioSample[] {
    return this.audio.filter((a) => a.t >= start && a.t <= end);
  }

  framesBetween(start: number, end: number): Frame[] {
    return this.frames.filter((f) => f.t >= start && f.t <= end);
  }

  /** Starts the local recording used by the analysis replay. */
  startRecording(): void {
    if (!this.stream || this.recorder || typeof MediaRecorder === "undefined") return;
    const mimeType = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"].find((t) =>
      MediaRecorder.isTypeSupported(t),
    );
    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream, mimeType ? { mimeType, videoBitsPerSecond: 2_500_000 } : undefined);
    this.recorder.ondataavailable = (e) => e.data.size && this.chunks.push(e.data);
    this.recorder.onstart = () => (this.recordingStartT = this.now());
    this.recorder.start(1000);
  }

  /** Stops the recording and returns it (null if recording wasn't possible). */
  stopRecording(): Promise<Blob | null> {
    const recorder = this.recorder;
    if (!recorder || recorder.state === "inactive") return Promise.resolve(null);
    return new Promise((resolve) => {
      recorder.onstop = () => resolve(new Blob(this.chunks, { type: recorder.mimeType || "video/webm" }));
      recorder.stop();
    });
  }

  stop(): void {
    this.running = false;
    this.timers.forEach(clearInterval);
    this.timers = [];
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.audioCtx?.close();
    this.audioCtx = null;
  }

  private loop = () => {
    if (!this.running) return;
    const video = this.video;
    if (this.landmarker && video.readyState >= 2 && video.currentTime !== this.lastVideoTime) {
      this.lastVideoTime = video.currentTime;
      const ts = performance.now();
      const result = this.landmarker.detectForVideo(video, ts);
      const frame = extractFrame(result, ts - this.t0);
      this.frames.push(frame);
      if (this.recorder) {
        const points = extractReplayPoints(result);
        if (points) this.keypoints.push({ t: frame.t, p: points });
      }
      this.latest = frame;
      this.recentFrameTimes.push(ts);
      if (this.recentFrameTimes.length > 30) this.recentFrameTimes.shift();
    }
    requestAnimationFrame(this.loop);
  };

  private startAudio(stream: MediaStream): void {
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buffer = new Float32Array(analyser.fftSize);
    this.audioCtx = ctx;
    this.timers.push(
      window.setInterval(() => {
        analyser.getFloatTimeDomainData(buffer);
        let sum = 0;
        for (const v of buffer) sum += v * v;
        this.audio.push({ t: this.now(), rms: Math.sqrt(sum / buffer.length) });
      }, AUDIO_INTERVAL_MS),
    );
  }

  private brightnessCanvas = document.createElement("canvas");

  private sampleBrightness(): void {
    if (this.video.readyState < 2) return;
    const canvas = this.brightnessCanvas;
    canvas.width = 32;
    canvas.height = 18;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    ctx.drawImage(this.video, 0, 0, canvas.width, canvas.height);
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
    let sum = 0;
    for (let i = 0; i < data.length; i += 4) sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    this.latestLuma = sum / (data.length / 4);
    this.brightness.push({ t: this.now(), luma: this.latestLuma });
  }
}

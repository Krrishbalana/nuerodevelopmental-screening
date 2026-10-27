import { useEffect, useRef, useState } from "react";
import { QUALITY } from "../config";
import type { Tracker } from "../cv/tracker";

interface Checks {
  face: boolean;
  distance: "ok" | "too_far" | "too_close" | null;
  light: boolean | null;
  fps: number;
}

const STEADY_MS = 1500;

export function CameraCheck({ tracker, onReady }: { tracker: Tracker; onReady: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [checks, setChecks] = useState<Checks>({ face: false, distance: null, light: null, fps: 0 });
  const [steady, setSteady] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      await tracker.init();
      await tracker.start();
      if (!alive) return;
      if (videoRef.current) {
        videoRef.current.srcObject = tracker.stream;
        await videoRef.current.play();
      }
      setStatus("ready");
    })().catch((e: unknown) => {
      setStatus("error");
      setError(e instanceof Error ? e.message : String(e));
    });
    return () => {
      alive = false;
    };
  }, [tracker]);

  useEffect(() => {
    if (status !== "ready") return;
    let goodSince: number | null = null;
    const id = window.setInterval(() => {
      const f = tracker.latest;
      const face = !!f?.face;
      const w = f?.face_w;
      const distance = !face || w === undefined ? null : w < QUALITY.faceWMin ? "too_far" : w > QUALITY.faceWMax ? "too_close" : "ok";
      const light = tracker.latestLuma === null ? null : tracker.latestLuma >= QUALITY.lumaMin;
      setChecks({ face, distance, light, fps: tracker.fps() });
      const good = face && distance === "ok" && light === true;
      goodSince = good ? (goodSince ?? performance.now()) : null;
      setSteady(goodSince !== null && performance.now() - goodSince >= STEADY_MS);
    }, 200);
    return () => clearInterval(id);
  }, [status, tracker]);

  const start = () => {
    tracker.resumeAudio();
    void document.documentElement.requestFullscreen?.().catch(() => undefined);
    onReady();
  };

  return (
    <div className="panel wide">
      <h1>Camera check</h1>
      {status === "loading" && <p className="muted">Starting camera and loading the face model…</p>}
      {status === "error" && (
        <p className="error">
          Couldn't start the camera: {error}. Allow camera and microphone access in the browser and reload.
        </p>
      )}

      <div className="camera-check">
        <video ref={videoRef} className="preview" muted playsInline />
        <ul className="checklist">
          <Check ok={checks.face} label="Child's face is visible" />
          <Check
            ok={checks.distance === "ok"}
            label={
              checks.distance === "too_far"
                ? "Move closer to the screen"
                : checks.distance === "too_close"
                  ? "Move a little further back"
                  : checks.distance === "ok"
                    ? "Distance is good"
                    : "Distance from screen"
            }
          />
          <Check
            ok={checks.light === true}
            label={checks.light === false ? "Room is too dark" : checks.light ? "Lighting is good" : "Lighting"}
          />
          <li className="muted small">Camera: {checks.fps.toFixed(0)} fps</li>
        </ul>
      </div>

      <p className="muted">
        When everything is green, press start. The screen will go full-screen. Stay next to your child; the app will tell
        you when to step behind them.
      </p>
      <div className="row">
        <button className="primary" disabled={!steady} onClick={start}>
          Start session
        </button>
        {status === "ready" && !steady && (
          <button className="link" onClick={start} title="The report will flag poor recording conditions">
            Start anyway
          </button>
        )}
      </div>
    </div>
  );
}

function Check({ ok, label }: { ok: boolean; label: string }) {
  return <li className={ok ? "ok" : "bad"}>{ok ? "✓" : "•"} {label}</li>;
}

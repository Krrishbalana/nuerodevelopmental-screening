import { useEffect, useMemo, useRef, useState } from "react";
import { getReplay } from "../api";
import { STIMULI } from "../config";
import { bounds, buildEvents, type ReplayData, type ReplayMedia } from "../replay/data";
import { buildTimelineLayer, drawReplay, H, makePipCanvas, timeAtTimelineX, W } from "../replay/render";
import type { Report } from "../types";

interface Props {
  sessionId: string;
  report: Report;
  media: ReplayMedia | null;
  onClose: () => void;
}

const SPEEDS = [0.5, 1, 2, 4];

function pickMime(): string | undefined {
  return ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"].find((t) =>
    MediaRecorder.isTypeSupported(t),
  );
}

/** Makes a MediaRecorder blob seekable: its duration is Infinity until the browser scans to the end. */
function prepareVideo(v: HTMLVideoElement): Promise<void> {
  return new Promise((resolve) => {
    const done = () => {
      v.currentTime = 0;
      resolve();
    };
    v.onloadedmetadata = () => {
      if (v.duration === Infinity || Number.isNaN(v.duration)) {
        v.ondurationchange = () => {
          v.ondurationchange = null;
          done();
        };
        v.currentTime = 1e101;
      } else done();
    };
  });
}

export function Replay({ sessionId, report, media, onClose }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [data, setData] = useState<ReplayData | null>(null);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);
  const [exporting, setExporting] = useState<number | null>(null); // progress 0..1
  const [ready, setReady] = useState(!media);

  // Mutable playback state read by the render loop.
  const clock = useRef({ t: 0, playing: false, rate: 1, last: 0 });
  const childVideo = useMemo(() => {
    if (!media) return null;
    const v = document.createElement("video");
    v.src = media.src;
    v.playsInline = true;
    v.preload = "auto";
    return v;
  }, [media]);
  const stimuli = useMemo(() => {
    const make = (src: string) => {
      const v = document.createElement("video");
      v.src = src;
      v.muted = true;
      v.loop = true;
      v.playsInline = true;
      v.preload = "auto";
      return v;
    };
    return { social: STIMULI.social.map(make), geometric: STIMULI.geometric.map(make) };
  }, []);
  const audio = useRef<{ ctx: AudioContext; dest: MediaStreamAudioDestinationNode } | null>(null);

  useEffect(() => {
    getReplay(sessionId)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, [sessionId]);

  useEffect(() => {
    if (!childVideo) return;
    void prepareVideo(childVideo).then(() => setReady(true));
    return () => {
      childVideo.pause();
      childVideo.removeAttribute("src");
    };
  }, [childVideo]);

  const events = useMemo(() => (data ? buildEvents(data, report) : []), [data, report]);
  const range = useMemo(() => (data ? bounds(data) : { start: 0, end: 0 }), [data]);
  const layers = useMemo(() => (data ? { timeline: buildTimelineLayer(data), pip: makePipCanvas() } : null), [data]);
  const keypointTimes = useMemo(() => media?.keypoints.map((k) => k.t) ?? null, [media]);

  const seek = (t: number) => {
    const c = clock.current;
    c.t = Math.max(range.start, Math.min(range.end, t));
    if (childVideo && media) childVideo.currentTime = Math.max(0, (c.t - media.startT) / 1000);
  };

  const setPlay = (on: boolean) => {
    const c = clock.current;
    if (on && c.t >= range.end - 50) seek(range.start);
    c.playing = on;
    c.last = performance.now();
    setPlaying(on);
    if (childVideo) {
      if (on) {
        if (!audio.current) {
          // Route the recording's sound through Web Audio so it can be both heard and exported.
          const ctx = new AudioContext();
          const dest = ctx.createMediaStreamDestination();
          const src = ctx.createMediaElementSource(childVideo);
          src.connect(ctx.destination);
          src.connect(dest);
          audio.current = { ctx, dest };
        }
        void audio.current.ctx.resume();
        void childVideo.play();
      } else childVideo.pause();
    }
  };

  useEffect(() => {
    clock.current.rate = rate;
    if (childVideo) childVideo.playbackRate = rate;
  }, [rate, childVideo]);

  // Render loop.
  useEffect(() => {
    if (!data || !layers || !ready) return;
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    if (clock.current.t < range.start) seek(range.start);
    let raf = 0;
    const loop = () => {
      const c = clock.current;
      const now = performance.now();
      if (c.playing) {
        // The recording stops when the session is submitted, a little before the timeline ends: past
        // its end the clock runs on its own so the final computation still plays (and export finishes).
        if (!childVideo || childVideo.ended) c.t += (now - c.last) * c.rate;
        else if (media && !childVideo.paused) c.t = media.startT + childVideo.currentTime * 1000;
        if (c.t >= range.end) {
          c.t = range.end;
          setPlay(false);
        }
      }
      c.last = now;
      syncStimuli(c.t, c.playing, c.rate);
      drawReplay(ctx, {
        d: data,
        report,
        events,
        t: c.t,
        video: childVideo,
        keypoints: media?.keypoints ?? null,
        keypointTimes,
        stimulus: (kind, clip) => {
          const list = stimuli[kind];
          return list.length ? list[clip % list.length] : null;
        },
        timelineLayer: layers.timeline,
        pip: layers.pip,
      });
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
    // seek/setPlay/syncStimuli only touch refs; re-running on their identity isn't needed.
  }, [data, layers, ready]);

  /** Keeps the split-screen clips in step with the replay clock. */
  const syncStimuli = (t: number, on: boolean, r: number) => {
    const tr = data?.split_trials.find((x) => x.t_start <= t && t <= x.t_end);
    const active = new Set<HTMLVideoElement>();
    if (tr) {
      for (const list of [stimuli.social, stimuli.geometric]) {
        const v = list.length ? list[tr.clip % list.length] : null;
        if (!v || !v.duration) continue;
        active.add(v);
        const target = ((t - tr.t_start) / 1000) % v.duration;
        if (Math.abs(v.currentTime - target) > 0.3) v.currentTime = target;
        v.playbackRate = r;
        if (on && v.paused) void v.play().catch(() => undefined);
        if (!on && !v.paused) v.pause();
      }
    }
    for (const v of [...stimuli.social, ...stimuli.geometric]) if (!active.has(v) && !v.paused) v.pause();
  };

  const onCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!data || exporting !== null) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const t = timeAtTimelineX(data, ((e.clientX - rect.left) / rect.width) * W);
    if (t !== null) seek(t);
  };

  const exportVideo = async () => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    setPlay(false);
    seek(range.start);
    setRate(1);
    const tracks: MediaStreamTrack[] = [...canvas.captureStream(30).getVideoTracks()];
    if (childVideo) {
      setPlay(true); // builds the audio graph
      setPlay(false);
      seek(range.start);
      if (audio.current) tracks.push(...audio.current.dest.stream.getAudioTracks());
    }
    const mimeType = pickMime();
    const rec = new MediaRecorder(new MediaStream(tracks), mimeType ? { mimeType, videoBitsPerSecond: 8_000_000 } : undefined);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const stopped = new Promise<void>((resolve) => (rec.onstop = () => resolve()));
    rec.start(1000);
    setExporting(0);
    setPlay(true);
    await new Promise<void>((resolve) => {
      // Watchdog: if the clock stops moving (e.g. the video stalls), finish with what was recorded.
      let lastT = clock.current.t;
      let stalledSince = performance.now();
      const id = window.setInterval(() => {
        const c = clock.current;
        setExporting((c.t - range.start) / (range.end - range.start));
        if (c.t !== lastT) {
          lastT = c.t;
          stalledSince = performance.now();
        }
        if (!c.playing || c.t >= range.end || performance.now() - stalledSince > 5000) {
          clearInterval(id);
          setPlay(false);
          resolve();
        }
      }, 250);
    });
    rec.stop();
    await stopped;
    const blob = new Blob(chunks, { type: rec.mimeType || "video/webm" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `omli-analysis-${sessionId.slice(0, 8)}.${blob.type.includes("mp4") ? "mp4" : "webm"}`;
    a.click();
    URL.revokeObjectURL(a.href);
    setExporting(null);
  };

  return (
    <div className="replay">
      {error && <p className="error">Couldn't load the replay: {error}</p>}
      {!error && (!data || !ready) && <p className="replay-loading">Preparing analysis replay…</p>}
      <canvas ref={canvasRef} width={W} height={H} className="replay-canvas" onClick={onCanvasClick} />
      <div className="replay-controls">
        <button className="replay-btn primary" disabled={!data || !ready || exporting !== null} onClick={() => setPlay(!playing)}>
          {playing ? "❚❚ Pause" : "▶ Play"}
        </button>
        <button className="replay-btn" disabled={exporting !== null} onClick={() => seek(range.start)}>⟲ Restart</button>
        {SPEEDS.map((s) => (
          <button
            key={s}
            className={rate === s ? "replay-btn active" : "replay-btn"}
            disabled={exporting !== null}
            onClick={() => setRate(s)}
          >
            {s}×
          </button>
        ))}
        <span className="replay-hint">Click the timeline to jump</span>
        <button className="replay-btn" disabled={!data || !ready || exporting !== null} onClick={() => void exportVideo()}>
          {exporting === null ? "⬇ Export video" : `Recording ${Math.round(exporting * 100)}%`}
        </button>
        <button className="replay-btn" disabled={exporting !== null} onClick={onClose}>✕ Close</button>
      </div>
      {!media && data && (
        <p className="replay-note">
          No camera recording for this session (it wasn't saved, or was deleted), so the head is reconstructed from the
          measurements.
        </p>
      )}
    </div>
  );
}

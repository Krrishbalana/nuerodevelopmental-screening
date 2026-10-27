"""Measure low-level visual properties of stimulus clips.

Social and geometric clips must be matched on these, otherwise a child may
look at one side simply because it is brighter or busier, not because of
social interest.

  luma     mean brightness, 0-255
  contrast std of brightness within a frame, averaged
  motion   mean absolute brightness change between consecutive frames (motion energy)

Usage: uv run python measure.py clip1.mp4 clip2.mp4 ...
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ANALYSIS_WIDTH = 180  # downscale first so numbers don't depend on resolution
ANALYSIS_FPS = 15


def _probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    w, h = (int(v) for v in out.split(",")[:2])
    return w, h


def gray_frames(path: Path) -> np.ndarray:
    w, h = _probe_size(path)
    out_h = round(h * ANALYSIS_WIDTH / w / 2) * 2
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", f"fps={ANALYSIS_FPS},scale={ANALYSIS_WIDTH}:{out_h}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, out_h, ANALYSIS_WIDTH).astype(np.float32)


def measure(path: Path) -> dict:
    frames = gray_frames(path)
    motion = float(np.abs(np.diff(frames, axis=0)).mean()) if len(frames) > 1 else 0.0
    return {
        "file": path.name,
        "seconds": round(len(frames) / ANALYSIS_FPS, 2),
        "luma": round(float(frames.mean()), 2),
        "contrast": round(float(frames.std(axis=(1, 2)).mean()), 2),
        "motion": round(motion, 3),
    }


def summarize(rows: list[dict]) -> dict:
    return {key: round(float(np.mean([r[key] for r in rows])), 3) for key in ("luma", "contrast", "motion")}


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        sys.exit(__doc__)
    rows = [measure(p) for p in paths]
    print(json.dumps({"clips": rows, "mean": summarize(rows)}, indent=2))

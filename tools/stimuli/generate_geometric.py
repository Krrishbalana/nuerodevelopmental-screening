"""Generate geometric (non-social) split-screen clips, optionally matched to social clips.

Screensaver-style coloured shapes moving on smooth paths, like the GeoPref
"dynamic geometric images". Silent, no text, nothing face-like.

With --match, brightness and speed are tuned until mean luma and motion
energy are within tolerance of the given social clips (see measure.py).

Usage:
  uv run python generate_geometric.py --out ../../ui/public/stimuli
  uv run python generate_geometric.py --out ../../ui/public/stimuli --match social_*.mp4
  uv run python generate_geometric.py --out ../../ui/public/stimuli --pair --match social_1.mp4 social_2.mp4 ...
"""

import argparse
import colorsys
import json
import math
import random
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from measure import measure, summarize

SUPERSAMPLE = 2  # draw at 2x and downscale for smooth edges
MATCH_TOLERANCE = 0.10
MATCH_ITERATIONS = 8


@dataclass
class Params:
    width: int = 720  # half of a 1440x900 laptop screen
    height: int = 900
    fps: int = 30
    seconds: float = 12.0
    brightness: float = 1.0  # scales lightness of background and shapes
    speed: float = 1.0  # scales all motion
    size: float = 1.0  # scales all shapes (more area = more contrast)
    shapes: int = 7


@dataclass
class Shape:
    kind: str
    size: float  # fraction of min(width, height)
    fx: float
    fy: float
    phase_x: float
    phase_y: float
    spin: float
    hue: float
    hue_drift: float


def make_shapes(seed: int, count: int) -> list[Shape]:
    rng = random.Random(seed)
    kinds = ["circle", "square", "triangle", "star", "ring", "diamond"]
    return [
        Shape(
            kind=rng.choice(kinds),
            size=rng.uniform(0.06, 0.13),
            fx=rng.uniform(0.08, 0.22),
            fy=rng.uniform(0.08, 0.22),
            phase_x=rng.uniform(0, math.tau),
            phase_y=rng.uniform(0, math.tau),
            spin=rng.uniform(-1.2, 1.2),
            hue=rng.random(),
            hue_drift=rng.uniform(0.02, 0.06),
        )
        for _ in range(count)
    ]


def _rgb(h: float, lightness: float, saturation: float = 0.85) -> tuple[int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, min(max(lightness, 0.0), 0.95), saturation)
    return round(r * 255), round(g * 255), round(b * 255)


def _polygon(cx: float, cy: float, r: float, sides: int, angle: float, inner: float | None = None):
    points = []
    steps = sides * 2 if inner else sides
    for i in range(steps):
        rad = r if not inner or i % 2 == 0 else r * inner
        a = angle + i * math.tau / steps - math.pi / 2
        points.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
    return points


def render_frame(params: Params, shapes: list[Shape], t: float) -> np.ndarray:
    s = SUPERSAMPLE
    w, h = params.width * s, params.height * s
    # Background carries most of the frame, so it does most of the luma matching.
    bg_lightness = min(0.10 * params.brightness, 0.85)
    img = Image.new("RGB", (w, h), _rgb(0.62, bg_lightness, 0.5))
    # Shapes stay vivid and contrast with the background: dark shapes on light, light on dark.
    # Low contrast would make the geometric side less salient and inflate social preference.
    shape_lightness = 0.65 * min(params.brightness, 1.0) if bg_lightness < 0.4 else 0.25
    draw = ImageDraw.Draw(img)
    unit = min(w, h)
    tt = t * params.speed
    for shape in shapes:
        cx = w / 2 + math.sin(tt * shape.fx * math.tau + shape.phase_x) * w * 0.34
        cy = h / 2 + math.sin(tt * shape.fy * math.tau + shape.phase_y) * h * 0.36
        r = shape.size * unit * params.size
        angle = tt * shape.spin
        color = _rgb(shape.hue + tt * shape.hue_drift, shape_lightness)
        if shape.kind == "circle":
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        elif shape.kind == "ring":
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=max(1, round(r * 0.3)))
        elif shape.kind == "square":
            draw.polygon(_polygon(cx, cy, r * 1.2, 4, angle + math.pi / 4), fill=color)
        elif shape.kind == "diamond":
            draw.polygon(_polygon(cx, cy, r * 1.2, 4, angle), fill=color)
        elif shape.kind == "triangle":
            draw.polygon(_polygon(cx, cy, r * 1.3, 3, angle), fill=color)
        else:
            draw.polygon(_polygon(cx, cy, r * 1.3, 5, angle, inner=0.45), fill=color)
    img = img.resize((params.width, params.height), Image.Resampling.LANCZOS)
    return np.asarray(img)


def render_clip(params: Params, seed: int, out: Path) -> None:
    shapes = make_shapes(seed, params.shapes)
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{params.width}x{params.height}", "-r", str(params.fps),
         "-i", "-", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
         "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin
    for i in range(round(params.seconds * params.fps)):
        proc.stdin.write(render_frame(params, shapes, i / params.fps).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out}")


def tune(params: Params, seeds: list[int], target: dict) -> Params:
    """Adjust brightness, speed and size until luma, motion and contrast match the target.

    Renders at full size and length: short low-res previews measured differently from the final clip.
    """
    with tempfile.TemporaryDirectory() as tmp:
        for _ in range(MATCH_ITERATIONS):
            rows = []
            for seed in seeds:
                path = Path(tmp) / f"preview_{seed}.mp4"
                render_clip(params, seed, path)
                rows.append(measure(path))
            got = summarize(rows)
            luma_err = got["luma"] / target["luma"] - 1
            motion_err = got["motion"] / target["motion"] - 1
            contrast_err = got["contrast"] / target["contrast"] - 1
            print(f"  brightness={params.brightness:.2f} speed={params.speed:.2f} size={params.size:.2f} -> "
                  f"luma {got['luma']:.1f}/{target['luma']:.1f}, "
                  f"motion {got['motion']:.2f}/{target['motion']:.2f}, "
                  f"contrast {got['contrast']:.1f}/{target['contrast']:.1f}")
            if max(abs(luma_err), abs(motion_err), abs(contrast_err)) <= MATCH_TOLERANCE:
                break
            # Damped step: size changes shift luma and motion too, so don't overshoot.
            params.size = min(max(params.size * (target["contrast"] / got["contrast"]) ** 0.6, 0.5), 3.5)
            params.brightness = min(max(params.brightness * target["luma"] / got["luma"], 0.2), 9.0)
            params.speed = min(max(params.speed * target["motion"] / got["motion"], 0.05), 4.0)
    return params


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--seconds", type=float, default=12.0)
    parser.add_argument("--match", nargs="*", type=Path, default=[], help="social clips to match")
    parser.add_argument("--pair", action="store_true",
                        help="match geometric_i to the i-th --match clip instead of to their average")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    # Each job: (seed, clip params, the social clip(s) it is matched to)
    if args.pair:
        if not args.match:
            parser.error("--pair needs --match")
        jobs = [(i, [ref]) for i, ref in enumerate(args.match, start=1)]
    else:
        jobs = [(i, args.match) for i in range(1, args.count + 1)]

    shared: Params | None = None
    clips = []
    for seed, refs in jobs:
        target = summarize([measure(p) for p in refs]) if refs else None
        if args.pair:
            print(f"geometric_{seed} <- {refs[0].name} {target}")
            params = tune(Params(seconds=args.seconds), [seed], target) if target else Params(seconds=args.seconds)
        else:
            if shared is None:
                shared = Params(seconds=args.seconds)
                if target:
                    print(f"Matching social clips: {target}")
                    shared = tune(shared, [s for s, _ in jobs], target)
            params = shared
        path = args.out / f"geometric_{seed}.mp4"
        render_clip(params, seed, path)
        clips.append({**measure(path), "seed": seed, "params": asdict(params),
                      "matched_to": {"files": [p.name for p in refs], "target": target} if target else None})
        print(f"wrote {path}")

    manifest = {
        "kind": "geometric",
        "generator": "tools/stimuli/generate_geometric.py",
        "mode": "pair" if args.pair else ("average" if args.match else "unmatched"),
        "clips": clips,
        "mean": summarize(clips),
    }
    (args.out / "geometric_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest["mean"]))


if __name__ == "__main__":
    main()

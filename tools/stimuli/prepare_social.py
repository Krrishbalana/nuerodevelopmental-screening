"""Trim, crop and normalise social clips listed in social_clips.json.

Each clip is cut to its segment, cropped around `center_x` (0..1 of the source
width) to the split-screen half's aspect, scaled to 720x900 at 30 fps, and
stripped of audio. Writes a manifest with each clip's measurements.

Usage: uv run python prepare_social.py --out ../../ui/public/stimuli [--backups]
"""

import argparse
import json
import subprocess
from pathlib import Path

from measure import _probe_size, measure, summarize

OUT_W, OUT_H, FPS = 720, 900, 30
HERE = Path(__file__).resolve().parent


def prepare(clip: dict, out_dir: Path) -> Path:
    src = HERE / clip["source"]
    w, h = _probe_size(src)
    crop_w = min(w, round(h * OUT_W / OUT_H / 2) * 2)
    x = round(min(max(clip["center_x"] * w - crop_w / 2, 0), w - crop_w))
    out = out_dir / f"{clip['name']}.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(clip["start"]), "-t", str(clip["duration"]), "-i", str(src),
         "-vf", f"crop={crop_w}:{h}:{x}:0,scale={OUT_W}:{OUT_H},fps={FPS},setsar=1",
         "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart", str(out)],
        check=True,
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backups", action="store_true", help="also prepare backup clips")
    args = parser.parse_args()

    spec = json.loads((HERE / "social_clips.json").read_text())
    clips = spec["clips"] + (spec["backups"] if args.backups else [])
    args.out.mkdir(parents=True, exist_ok=True)

    rows = []
    for clip in clips:
        path = prepare(clip, args.out)
        row = {**measure(path), "content": clip["content"], "credit": clip["credit"], "url": clip["url"]}
        rows.append(row)
        print(f"wrote {path}  luma={row['luma']} motion={row['motion']}")

    main_rows = [r for r, c in zip(rows, clips) if c in spec["clips"]]
    manifest = {"kind": "social", "set": spec["set"], "note": spec["note"], "clips": rows, "mean": summarize(main_rows)}
    (args.out / "social_manifest.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

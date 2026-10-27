"""Camera recordings, stored only when the parent opted in for this session.

Files live next to the session data, never in git:
  data/recordings/<id>.<webm|mp4>      the camera recording
  data/recordings/<id>.json            consent time, content type, start time, face keypoints
Deleting removes both (the parent can withdraw consent at any time).
"""

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import DATA_DIR, valid_id

REC_DIR = DATA_DIR.parent / "recordings"
MAX_BYTES = 400 * 1024 * 1024  # ~20 min at the recorder's bitrate; a session is ~4 min
CONTENT_TYPES = {"video/webm": "webm", "video/mp4": "mp4"}


class RecordingError(ValueError):
    pass


def _meta_path(session_id: str) -> Path:
    return REC_DIR / f"{session_id}.json"


def meta(session_id: str) -> dict[str, Any] | None:
    path = _meta_path(session_id)
    return json.loads(path.read_text()) if valid_id(session_id) and path.exists() else None


def video_path(session_id: str) -> tuple[Path, str] | None:
    m = meta(session_id)
    if m is None:
        return None
    path = REC_DIR / f"{session_id}.{CONTENT_TYPES[m['content_type']]}"
    return (path, m["content_type"]) if path.exists() else None


async def save(session_id: str, content_type: str, start_t: float, chunks: AsyncIterator[bytes]) -> dict[str, Any]:
    base_type = content_type.split(";")[0].strip()
    if base_type not in CONTENT_TYPES:
        raise RecordingError(f"Unsupported content type {content_type}")
    REC_DIR.mkdir(parents=True, exist_ok=True)
    path = REC_DIR / f"{session_id}.{CONTENT_TYPES[base_type]}"
    tmp = path.with_suffix(".part")
    size = 0
    with tmp.open("wb") as f:
        async for chunk in chunks:
            size += len(chunk)
            if size > MAX_BYTES:
                f.close()
                tmp.unlink()
                raise RecordingError("Recording too large")
            f.write(chunk)
    tmp.rename(path)
    record = {
        "content_type": base_type,
        "bytes": size,
        "start_t": start_t,
        "consented_at": datetime.now(timezone.utc).isoformat(),
        "keypoints": [],
    }
    _meta_path(session_id).write_text(json.dumps(record))
    return {k: v for k, v in record.items() if k != "keypoints"}


def save_keypoints(session_id: str, keypoints: list[dict[str, Any]]) -> None:
    m = meta(session_id)
    if m is None:
        raise RecordingError("Upload the recording first")
    m["keypoints"] = keypoints
    _meta_path(session_id).write_text(json.dumps(m))


def delete(session_id: str) -> bool:
    found = False
    for path in REC_DIR.glob(f"{session_id}.*") if valid_id(session_id) else []:
        path.unlink()
        found = True
    return found

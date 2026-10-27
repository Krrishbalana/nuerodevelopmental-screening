"""File-based session store (one JSON per session). Good enough for development."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scoring.models import SessionUpload

DATA_DIR = Path(os.environ.get("BEHAVIOR_DATA_DIR", Path(__file__).resolve().parent.parent / "data" / "sessions"))
_ID = re.compile(r"^[0-9a-f]{32}$")


def save_session(upload: SessionUpload, report: dict[str, Any]) -> str:
    session_id = uuid.uuid4().hex
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "upload": upload.model_dump(mode="json"),
        "report": report,
    }
    (DATA_DIR / f"{session_id}.json").write_text(json.dumps(record))
    return session_id


def valid_id(session_id: str) -> bool:
    return bool(_ID.match(session_id))


def load_upload(session_id: str) -> SessionUpload | None:
    if not _ID.match(session_id):
        return None
    path = DATA_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    return SessionUpload(**json.loads(path.read_text())["upload"])


def link_questionnaire(session_id: str, questionnaire_id: str) -> None:
    """Remember which parent questionnaire belongs to this screening session (latest wins)."""
    path = DATA_DIR / f"{session_id}.json"
    if not _ID.match(session_id) or not path.exists():
        return
    record = json.loads(path.read_text())
    record["questionnaire_id"] = questionnaire_id
    path.write_text(json.dumps(record))


def linked_questionnaire(session_id: str) -> str | None:
    path = DATA_DIR / f"{session_id}.json"
    if not _ID.match(session_id) or not path.exists():
        return None
    return json.loads(path.read_text()).get("questionnaire_id")


def load_report(session_id: str) -> dict[str, Any] | None:
    if not _ID.match(session_id):
        return None
    path = DATA_DIR / f"{session_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())["report"]

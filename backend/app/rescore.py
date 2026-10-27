"""Re-run scoring on saved sessions (after a scoring fix or threshold change).

The previous report is kept under "previous_reports" so changes stay traceable.

Usage: uv run python -m app.rescore [session_id ...]   (no ids = all sessions)
"""

import json
import sys

from scoring import InvalidSession, score_session
from scoring.models import SessionUpload

from .storage import DATA_DIR


def rescore(session_id: str) -> str:
    path = DATA_DIR / f"{session_id}.json"
    record = json.loads(path.read_text())
    try:
        report = score_session(SessionUpload(**record["upload"]))
    except InvalidSession as exc:
        return f"{session_id}: skipped ({exc})"
    old = record["report"]
    record.setdefault("previous_reports", []).append(old)
    record["report"] = report
    path.write_text(json.dumps(record))
    return f"{session_id}: {old['clinician']['outcome']} -> {report['clinician']['outcome']}"


if __name__ == "__main__":
    ids = sys.argv[1:] or sorted(p.stem for p in DATA_DIR.glob("*.json"))
    for session_id in ids:
        print(rescore(session_id))

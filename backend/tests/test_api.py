import pytest
from fastapi.testclient import TestClient

from .synthetic import Child, make_session


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import storage
    from app.main import app

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    return TestClient(app)


def test_calibration_endpoint(client):
    s = make_session()
    body = {
        "frames": [f.model_dump() for f in s.frames],
        "calibration_points": [p.model_dump() for p in s.calibration_points],
    }
    res = client.post("/api/calibration/evaluate", json=body)
    assert res.status_code == 200
    assert res.json()["passed"] is True


def test_session_roundtrip(client):
    res = client.post("/api/sessions", json=make_session().model_dump(mode="json"))
    assert res.status_code == 200
    session_id = res.json()["session_id"]
    report = client.get(f"/api/sessions/{session_id}/report").json()
    assert report["parent"]["outcome"] == "no_signs"


def test_out_of_range_age_is_422(client):
    res = client.post("/api/sessions", json=make_session(Child(age_months=6)).model_dump(mode="json"))
    assert res.status_code == 422


def test_unknown_session_is_404(client):
    assert client.get("/api/sessions/../../etc/report").status_code == 404
    assert client.get(f"/api/sessions/{'0' * 32}/report").status_code == 404


def test_replay_matches_report(client):
    from .synthetic import Child

    res = client.post("/api/sessions", json=make_session(Child(name_responses=[True, False, False])).model_dump(mode="json"))
    session_id = res.json()["session_id"]
    report = res.json()["report"]
    replay = client.get(f"/api/sessions/{session_id}/replay").json()
    assert len(replay["frames"]["t"]) == len(replay["frames"]["gx"]) > 1000
    assert replay["calibration"]["summary"]["quality"] == report["clinician"]["calibration"]["quality"]
    name = next(m for m in report["clinician"]["metrics"] if m["key"] == "name_response")
    assert [t["responded"] for t in replay["name_trials"]] == [t["responded"] for t in name["trials"]]
    turned = replay["name_trials"][0]
    assert turned["turn_t"] > turned["onset_t"] and turned["peak_turn_deg"] >= 25
    assert {g for g in replay["frames"]["gaze"] if g} <= {"left", "right", "center", "off", "invalid"}
    assert client.get(f"/api/sessions/{'0' * 32}/replay").status_code == 404


def _session_id(client, consent: bool) -> str:
    session = make_session()
    session.recording_consent = consent
    return client.post("/api/sessions", json=session.model_dump(mode="json")).json()["session_id"]


@pytest.fixture
def rec_dir(tmp_path, monkeypatch):
    from app import recordings

    monkeypatch.setattr(recordings, "REC_DIR", tmp_path / "recordings")
    return tmp_path / "recordings"


def test_recording_refused_without_consent(client, rec_dir):
    sid = _session_id(client, consent=False)
    res = client.put(f"/api/sessions/{sid}/recording?start_t=10", content=b"x" * 100, headers={"Content-Type": "video/webm"})
    assert res.status_code == 403
    assert not rec_dir.exists() or not list(rec_dir.iterdir())


def test_recording_roundtrip_with_range_and_delete(client, rec_dir):
    sid = _session_id(client, consent=True)
    body = bytes(range(256)) * 400
    res = client.put(f"/api/sessions/{sid}/recording?start_t=1234.5", content=body,
                     headers={"Content-Type": "video/webm;codecs=vp9,opus"})
    assert res.status_code == 200 and res.json()["bytes"] == len(body)
    assert client.put(f"/api/sessions/{sid}/recording/keypoints", json=[{"t": 1300, "p": [0.1, 0.2]}]).status_code == 200

    meta = client.get(f"/api/sessions/{sid}/recording/meta").json()
    assert meta["start_t"] == 1234.5 and meta["keypoints"][0]["t"] == 1300 and meta["consented_at"]
    part = client.get(f"/api/sessions/{sid}/recording", headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == body[10:20]

    assert client.delete(f"/api/sessions/{sid}/recording").status_code == 200
    assert client.get(f"/api/sessions/{sid}/recording").status_code == 404
    assert client.get(f"/api/sessions/{sid}/recording/meta").status_code == 404


def test_recording_rejects_other_file_types(client, rec_dir):
    sid = _session_id(client, consent=True)
    res = client.put(f"/api/sessions/{sid}/recording?start_t=0", content=b"x", headers={"Content-Type": "image/png"})
    assert res.status_code == 422


def test_calibration_returns_live_model_matching_backend(client):
    from scoring import calibrate

    s = make_session()
    body = {"frames": [f.model_dump() for f in s.frames], "calibration_points": [p.model_dump() for p in s.calibration_points]}
    res = client.post("/api/calibration/evaluate", json=body).json()
    model, rules = res["model"], res["rules"]
    assert rules["min_look_ms"] == 3000 and rules["center_band"] == [0.45, 0.55]
    backend = calibrate(s.frames, s.calibration_points).model
    for f in s.frames[2000:2050]:
        if not f.face:
            continue
        x = model["x"]
        z = [(getattr(f, n) - m) / sd for n, m, sd in zip(x["names"], x["mean"], x["std"])]
        gx = x["weights"][0] + sum(w * v for w, v in zip(x["weights"][1:], z))
        assert gx == pytest.approx(backend.predict(f)[0], abs=1e-9)

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import questionnaire
    from app.main import app

    monkeypatch.setattr(questionnaire, "QUESTIONNAIRE_DIR", tmp_path / "questionnaires")
    return TestClient(app)


def _run(client, session_id: str, step: dict, answer_for) -> list[tuple[str, str]]:
    """Answer until the engine is done, acknowledging urgent/pattern steps like the UI does."""
    asked = []
    for _ in range(80):
        if step["type"] == "done":
            return asked
        if step["type"] in ("urgent", "pattern"):
            step = client.post(f"/api/questionnaire/{session_id}/ack/{step['type']}").json()
            continue
        q = step["question"]
        key = answer_for(q)
        asked.append((q["id"], key))
        res = client.post(f"/api/questionnaire/{session_id}/answers", json={"question_id": q["id"], "key": key})
        assert res.status_code == 200, res.text
        step = res.json()
    raise AssertionError("questionnaire never finished")


def test_meta_lists_dataset(client):
    meta = client.get("/api/questionnaire/meta").json()
    assert len(meta["conditions"]) == 21 and len(meta["domains"]) == 15
    assert meta["dataset_hash"]


def test_social_concerns_put_autism_first(client):
    created = client.post("/api/questionnaire", json={"age_years": 2, "age_months": 2}).json()
    assert created["chronological_age_m"] == 26
    asked = _run(client, created["session_id"], created["step"], lambda q: "y" if q["domain"] == "SOC" else "n")
    assert 5 <= len(asked) <= 60
    results = client.post(f"/api/questionnaire/{created['session_id']}/complete").json()
    assert results["conditions"][0]["key"] == "ASD"
    assert results["action"] in ("refer", "urgent")
    assert client.get(f"/api/questionnaire/{created['session_id']}/results").json() == results


def test_language_concerns_put_language_first(client):
    created = client.post("/api/questionnaire", json={"age_years": 2, "age_months": 6}).json()
    _run(client, created["session_id"], created["step"], lambda q: "y" if q["domain"] in ("EXP",) else "n")
    results = client.post(f"/api/questionnaire/{created['session_id']}/complete").json()
    top = [c["key"] for c in results["conditions"][:2]]
    assert "LT" in top or "DLD" in top


def test_answer_validation_and_undo(client):
    created = client.post("/api/questionnaire", json={"age_years": 1, "age_months": 8}).json()
    sid, first = created["session_id"], created["step"]["question"]["id"]
    wrong = client.post(f"/api/questionnaire/{sid}/answers", json={"question_id": "not_this_one", "key": "y"})
    assert wrong.status_code == 409
    client.post(f"/api/questionnaire/{sid}/answers", json={"question_id": first, "key": "n"})
    back = client.delete(f"/api/questionnaire/{sid}/answers/last").json()
    assert back["question"]["id"] == first


def test_errors(client):
    assert client.get("/api/questionnaire/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/questionnaire/../../etc").status_code == 404
    bad = client.post("/api/questionnaire", json={"age_years": 2, "age_months": 0, "family_factors": ["nope"]})
    assert bad.status_code == 422


def test_questionnaire_starts_from_camera_findings(client, tmp_path, monkeypatch):
    from app import storage

    from .synthetic import Child, make_session

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "sessions")
    screening = client.post("/api/sessions", json=make_session(
        Child(age_months=26, social_preference=0.1, name_responses=[False, False, False])).model_dump(mode="json")).json()
    created = client.post("/api/questionnaire", json={
        "age_years": 2, "age_months": 2, "screening_session_id": screening["session_id"]}).json()
    obs = {o["id"]: o for o in created["observations"]}
    assert set(obs) == {"obs_social_preference", "obs_name_response"}
    assert obs["obs_social_preference"]["outcome"] == "flagged"
    asd = next(t for t in obs["obs_social_preference"]["terms"] if t["condition"] == "ASD")
    assert asd["lr"] == 8.5 and asd["source"] == "published"

    plain = client.post("/api/questionnaire", json={"age_years": 2, "age_months": 2}).json()
    _run(client, created["session_id"], created["step"], lambda q: "dk")
    _run(client, plain["session_id"], plain["step"], lambda q: "dk")
    with_cam = client.post(f"/api/questionnaire/{created['session_id']}/complete").json()
    without = client.post(f"/api/questionnaire/{plain['session_id']}/complete").json()
    p = lambda r: next((c["probability"] for c in r["conditions"] if c["key"] == "ASD"), 0.0)
    assert p(with_cam) > p(without)
    assert with_cam["hearing_test"] is True


def test_unknown_screening_or_observation_is_rejected(client):
    assert client.post("/api/questionnaire", json={"age_years": 2, "age_months": 2,
                                                   "screening_session_id": "0" * 32}).status_code == 404
    bad = client.post("/api/questionnaire", json={"age_years": 2, "age_months": 2,
                                                  "observations": [{"id": "obs_nope", "outcome": "flagged"}]})
    assert bad.status_code == 422


def test_completed_questionnaire_is_linked_to_screening_session(client, tmp_path, monkeypatch):
    from app import storage

    from .synthetic import Child, make_session

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "sessions")
    sid = client.post("/api/sessions", json=make_session(Child(age_months=26)).model_dump(mode="json")).json()["session_id"]
    assert client.get(f"/api/sessions/{sid}/questionnaire").status_code == 404
    created = client.post("/api/questionnaire", json={"age_years": 2, "age_months": 2, "screening_session_id": sid}).json()
    _run(client, created["session_id"], created["step"], lambda q: "n")
    client.post(f"/api/questionnaire/{created['session_id']}/complete")
    linked = client.get(f"/api/sessions/{sid}/questionnaire").json()
    assert linked["questionnaire_id"] == created["session_id"]
    assert linked["results"]["questions_asked"] == len(linked["answers"]) > 0
    assert {o["id"] for o in linked["observations"]} == {"obs_social_preference", "obs_name_response"}

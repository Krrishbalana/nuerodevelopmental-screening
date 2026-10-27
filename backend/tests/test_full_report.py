import pytest
from fastapi.testclient import TestClient

from .synthetic import Child, make_session

# A typical late talker: few words and no word combinations, but understands, gestures, points and
# engages socially. (Saying "yes" to every language-domain item would also say yes to autism core
# signs like "doesn't compensate with gestures", which is not a late talker.)
LATE_TALKER = {"exp_first_words", "exp_vocab", "exp_two_word"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import questionnaire, storage
    from app.main import app

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "sessions")
    monkeypatch.setattr(questionnaire, "QUESTIONNAIRE_DIR", tmp_path / "questionnaires")
    return TestClient(app)


def screen(client, child: Child) -> str:
    return client.post("/api/sessions", json=make_session(child).model_dump(mode="json")).json()["session_id"]


def ask(client, sid: str, age_m: int, answer_for) -> None:
    created = client.post("/api/questionnaire", json={
        "age_years": age_m // 12, "age_months": age_m % 12, "screening_session_id": sid}).json()
    qid, step = created["session_id"], created["step"]
    for _ in range(80):
        if step["type"] == "done":
            break
        if step["type"] in ("urgent", "pattern"):
            step = client.post(f"/api/questionnaire/{qid}/ack/{step['type']}").json()
            continue
        q = step["question"]
        step = client.post(f"/api/questionnaire/{qid}/answers", json={"question_id": q["id"], "key": answer_for(q)}).json()
    client.post(f"/api/questionnaire/{qid}/complete")


def full(client, sid: str) -> dict:
    res = client.get(f"/api/sessions/{sid}/full-report")
    assert res.status_code == 200, res.text
    return res.json()


def test_camera_only_report_runs_through_the_engine(client):
    sid = screen(client, Child(age_months=26, social_preference=0.1, name_responses=[False, False, False]))
    r = full(client, sid)
    assert r["has_questionnaire"] is False and r["questions_asked"] == 0
    asd = next(s for s in r["conditions"] if s["key"] == "ASD")
    assert {e["source"] for e in asd["for"]} == {"camera"}
    wheel = {w["key"]: w for w in r["wheel"]}
    assert wheel["social"]["status"] == "concern" and wheel["social"]["checked"] == 2
    assert all(w["status"] == "not_assessed" for k, w in wheel.items() if k != "social")
    assert r["hearing_test"] is True
    assert r["camera"]["clinician"]["metrics"]


def test_speech_delay_child_gets_a_language_first_report(client):
    sid = screen(client, Child(age_months=30, social_preference=0.8))
    ask(client, sid, 30, lambda q: "y" if q["id"] in LATE_TALKER else "n")
    r = full(client, sid)
    keys = [s["key"] for s in r["conditions"]]
    assert keys and keys[0] in ("LT", "DLD")
    assert "ASD" not in keys
    wheel = {w["key"]: w for w in r["wheel"]}
    assert wheel["talking"]["status"] == "concern"
    assert wheel["social"]["status"] in ("clear", "some")
    lang = r["conditions"][0]
    assert lang["about"] and lang["refer"]
    assert any("(you answered: Yes)" in e["text"] for e in lang["for"])


def test_autism_child_gets_an_autism_first_report(client):
    sid = screen(client, Child(age_months=26, social_preference=0.1, name_responses=[False, False, False]))
    ask(client, sid, 26, lambda q: "y" if q["domain"] in ("SOC", "PLAY", "RRB") else "n")
    r = full(client, sid)
    assert r["conditions"][0]["key"] == "ASD"
    asd = r["conditions"][0]
    assert {e["source"] for e in asd["for"]} == {"camera", "parent"} or len(asd["for"]) == 5
    assert r["action"] in ("refer", "urgent")
    assert r["all_conditions"][0]["key"] == "ASD" and r["all_conditions"][0]["prior"] < r["all_conditions"][0]["probability"]


def test_red_flag_answer_makes_the_report_urgent(client):
    sid = screen(client, Child(age_months=26, social_preference=0.8))
    ask(client, sid, 26, lambda q: "y" if q["id"] == "crs_regression" else "n")
    r = full(client, sid)
    assert r["action"] == "urgent"
    assert r["red_flags"]


def test_unknown_session_is_404(client):
    assert client.get(f"/api/sessions/{'0' * 32}/full-report").status_code == 404


def test_autism_wheel_follows_dsm5_criteria(client):
    sid = screen(client, Child(age_months=26, social_preference=0.1, name_responses=[False, False, False]))
    ask(client, sid, 26, lambda q: "y" if q["domain"] in ("SOC", "PLAY", "RRB") else "n")
    aw = full(client, sid)["autism_wheel"]
    slices = {s["key"]: s for s in aw["slices"]}
    assert list(slices) == ["A1", "A2", "A3", "B1", "B2", "B3", "B4"]
    # camera findings land on the criterion they describe
    assert any(sign.startswith("Camera:") for sign in slices["A1"]["signs"])
    assert any(sign.startswith("Camera:") for sign in slices["A3"]["signs"])
    assert aw["social"]["with_signs"] == 3 and aw["social"]["dsm_needs"] == 3
    assert aw["repetitive"]["dsm_needs"] == 2


def test_camera_only_autism_wheel_marks_unasked_criteria(client):
    sid = screen(client, Child(age_months=26, social_preference=0.1, name_responses=[False, False, False]))
    aw = full(client, sid)["autism_wheel"]
    status = {s["key"]: s["status"] for s in aw["slices"]}
    assert status["A1"] == "concern" and status["A3"] == "concern"
    assert all(status[k] == "not_assessed" for k in ("A2", "B1", "B2", "B3", "B4"))
    assert aw["repetitive"]["checked"] == 0

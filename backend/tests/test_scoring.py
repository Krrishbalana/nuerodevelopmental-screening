import pytest

from scoring import InvalidSession, calibrate, score_session
from scoring.name_response import score_name_response
from scoring.split_screen import score_split_screen
from scoring.timeline import Timeline

from .synthetic import Child, make_session


def _metric(report: dict, key: str) -> dict:
    return next(m for m in report["clinician"]["metrics"] if m["key"] == key)


# --- calibration ---------------------------------------------------------------


def test_calibration_good_when_child_follows_targets():
    s = make_session()
    result = calibrate(s.frames, s.calibration_points)
    assert result.quality == "good"
    assert result.side_accuracy >= 0.95
    assert result.mean_abs_err_x < 0.1


def test_calibration_poor_when_child_ignores_targets():
    s = make_session(Child(looks_at_calibration=False))
    assert calibrate(s.frames, s.calibration_points).quality == "poor"


def test_calibration_poor_without_fit_points():
    s = make_session()
    validate_only = [p for p in s.calibration_points if p.phase == "validate"]
    result = calibrate(s.frames, validate_only)
    assert result.quality == "poor"
    assert result.model is None


# --- split screen --------------------------------------------------------------


def _split(child: Child):
    s = make_session(child)
    return score_split_screen(Timeline(s.frames), s.split_screen_trials, calibrate(s.frames, s.calibration_points))


def test_split_screen_social_preference_not_flagged():
    m = _split(Child(social_preference=0.8))
    assert m.status == "not_flagged"
    assert m.confidence == "high"
    assert m.value == pytest.approx(0.8, abs=0.06)


def test_split_screen_has_no_borderline_band():
    # Only the published GeoPref cut-off exists; 40% social is simply below it.
    assert _split(Child(social_preference=0.4)).status == "not_flagged"


def test_split_screen_flagged_when_geometric_dominates():
    m = _split(Child(social_preference=0.1))
    assert m.status == "flagged"
    assert m.details["social_majority_trials"] == 0
    assert m.value < 0.31


def test_split_screen_survives_head_shift_after_still_calibration():
    # Regression (real session 53299e9a): a very still head during calibration plus a small
    # vertical shift afterwards pushed predicted gaze "off-screen" and voided the module.
    m = _split(
        Child(
            social_preference=0.8,
            still_during_calibration=True,
            head_shift_after_calibration=0.01,
            vertical_eye_signal=0.05,
        )
    )
    assert m.status == "not_flagged"
    assert m.value == pytest.approx(0.8, abs=0.06)


def test_split_screen_survives_head_turns_after_eyes_only_calibration():
    # Regression (real session a46aa142): calibration followed with the eyes only (yaw spread 0.4°),
    # then the head turned ~10° while watching; the fitted yaw coefficient blew gaze up to 2x screen
    # width and every trial was "off screen" although the child was looking at the screen.
    child = Child(social_preference=0.2, eyes_only_calibration=True, head_turn_deg=10)
    s = make_session(child)
    cal = calibrate(s.frames, s.calibration_points)
    assert cal.yaw_gain_source in ("default", "bounded") and cal.yaw_spread_deg < 3
    m = score_split_screen(Timeline(s.frames), s.split_screen_trials, cal)
    assert m.status == "flagged"
    assert all(t["valid"] for t in m.trials)
    assert sum(t["frames"]["off"] for t in m.trials) < 0.05 * sum(sum(t["frames"].values()) for t in m.trials)
    assert m.value == pytest.approx(0.2, abs=0.08)


def test_split_screen_looking_time_with_uneven_frame_gaps():
    # Regression (real session 53299e9a): frames alternated 16.7/50 ms apart, the median gap
    # was 16.7 ms, and looking time came out at half its real value.
    s = make_session(Child(social_preference=0.8))
    # Same 30 fps on average, but frames arrive in bursts: gaps of 16.7, 16.7, 66.6 ms (median 16.7).
    frames = [f.model_copy(update={"t": (i // 3) * 100 + (i % 3) * 16.7}) for i, f in enumerate(s.frames)]
    m = score_split_screen(Timeline(frames), s.split_screen_trials, calibrate(s.frames, s.calibration_points))
    assert all(t["looking_ms"] > 8000 for t in m.trials)


def test_split_screen_side_bias_is_not_scored():
    m = _split(Child(always_left=True))
    assert m.status == "insufficient"
    assert "one side" in m.reasons[0]


def test_split_screen_not_scored_with_poor_calibration():
    m = _split(Child(looks_at_calibration=False))
    assert m.status == "insufficient"


# --- response to name ----------------------------------------------------------


def _name(child: Child):
    s = make_session(child)
    return score_name_response(Timeline(s.frames), Timeline(s.audio), s.name_call_trials)


def test_name_response_not_flagged():
    m = _name(Child())
    assert m.status == "not_flagged"
    assert m.confidence == "high"
    assert m.value == 1.0
    latencies = [t["latency_ms"] for t in m.trials]
    assert all(700 <= lat <= 1300 for lat in latencies)
    assert all(t["onset_detected"] for t in m.trials)


def test_name_response_flagged_when_no_turns():
    m = _name(Child(name_responses=[False, False, False]))
    assert m.status == "flagged"
    assert m.value == 0.0


def test_name_response_one_of_three_is_flagged():
    # Campbell 2019 split: turned on more than one trial vs at most one.
    assert _name(Child(name_responses=[True, False, False])).status == "flagged"
    assert _name(Child(name_responses=[True, True, False])).status == "not_flagged"


def test_slow_responses_are_reported_not_flagged():
    # Latency has only a published group difference (Tier B): shown, never flagged.
    m = _name(Child(response_delay_ms=2400))
    assert m.status == "not_flagged"
    assert m.details["median_latency_ms"] > 2000


def test_name_response_without_detected_voice_has_lower_confidence():
    m = _name(Child(voice_detectable=False))
    assert m.status == "not_flagged"
    assert m.confidence == "medium"
    assert not any(t["onset_detected"] for t in m.trials)
    assert all(t["latency_estimated"] for t in m.trials)


def test_quiet_name_call_is_detected():
    # Regression (real sessions f9d193b8, 629dae38): calls from ~1 m behind a laptop peaked at
    # ~3x the room baseline and all 6 were missed, so a non-turning child scored "insufficient".
    m = _name(Child(voice_rms=0.016, name_responses=[False, False, False]))
    assert all(t["onset_detected"] for t in m.trials)
    assert m.status == "flagged"


def _name_with_check(child: Child):
    s = make_session(child)
    return score_name_response(Timeline(s.frames), Timeline(s.audio), s.name_call_trials, s.voice_check)


def test_voice_check_catches_a_very_quiet_parent():
    # 2x the room level: below the default rule (2.5x), but matches what the check heard.
    child = Child(voice_rms=0.012, name_responses=[False, False, False])
    assert _name(child).status == "insufficient"  # no voice check: calls missed
    m = _name_with_check(child)
    assert m.thresholds["voice_threshold"] == "from voice check"
    assert all(t["onset_detected"] for t in m.trials)
    assert m.status == "flagged"


def test_voice_check_ignores_room_sounds_quieter_than_the_parent():
    # Nobody calls; a room sound happens after each cue. Default rule takes it for a call
    # and scores "didn't turn"; with a loud parent in the voice check it is ignored.
    child = Child(voice_detectable=False, noise_burst_rms=0.02, name_responses=[False, False, False])
    assert _name(child).status == "flagged"
    assert _name_with_check(child).status == "insufficient"


def test_unheard_voice_check_falls_back_to_default_threshold():
    m = _name_with_check(Child(voice_check_rms=0.006))  # check call at room level
    assert m.thresholds["voice_threshold"].startswith("default")
    assert m.status == "not_flagged"


def test_no_turn_without_heard_call_is_not_counted_as_missed():
    # Regression (real session 53299e9a): nobody called the name, yet two silent trials were
    # scored as "didn't turn" and the result became "monitor".
    m = _name(Child(voice_detectable=False, name_responses=[False, False, True]))
    assert m.status == "insufficient"
    assert [t["valid"] for t in m.trials] == [False, False, True]


def test_parent_tips_when_conditions_were_fine():
    report = score_session(make_session(Child(voice_detectable=False, name_responses=[False, False, False])))
    assert report["parent"]["outcome"] == "incomplete"
    assert any("Call the name now" in tip for tip in report["parent"]["tips"])


# --- full pipeline / report ------------------------------------------------------


def test_report_no_signs():
    session = make_session(Child(social_preference=0.8))
    session.stimulus_set = "test-set-1"
    report = score_session(session)
    assert report["parent"]["outcome"] == "no_signs"
    assert report["clinician"]["stimulus_set"] == "test-set-1"
    lk = report["clinician"]["likelihood"]
    # 1% prior x GeoPref LR- 0.85 x Campbell LR- 0.54 -> 0.46%
    assert lk["posterior"] == pytest.approx(0.0046, abs=0.0002)
    assert "fewer than 1 in 100" in report["parent"]["likelihood"]
    assert any("18- and 24-month" in step for step in report["parent"]["next_steps"])


def test_report_refers_when_both_autism_signs_flagged():
    report = score_session(make_session(Child(social_preference=0.1, name_responses=[False, False, False])))
    assert report["parent"]["outcome"] == "refer"
    lk = report["clinician"]["likelihood"]
    # 1% prior x 8.5 x 1.82 -> odds 0.156 -> 13.5%
    assert lk["posterior"] == pytest.approx(0.135, abs=0.002)
    assert [e["lr"] for e in lk["evidence_used"]] == [8.5, 1.82]
    actions = " ".join(report["parent"]["next_steps"])
    assert "Developmental evaluation" in actions and "Hearing test" in actions
    assert all(f["sources"] for f in report["clinician"]["findings"] if f["status"] != "insufficient")


def test_report_name_only_recommends_hearing_check_at_any_age():
    # 40 months: outside Campbell's 16-31 m, so not in the likelihood; the AAP hearing rule still applies.
    report = score_session(make_session(Child(age_months=40, name_responses=[False, False, False])))
    assert report["parent"]["outcome"] == "hearing_check"
    lk = report["clinician"]["likelihood"]
    assert [e["key"] for e in lk["evidence_used"]] == ["social_preference"]
    assert "16-31 months" in lk["evidence_excluded"][0]["reason"]


def test_report_no_likelihood_beyond_studied_ages():
    report = score_session(make_session(Child(age_months=60, social_preference=0.1)))
    assert report["clinician"]["likelihood"]["available"] is False
    assert report["parent"]["likelihood"] is None
    assert report["parent"]["outcome"] == "no_signs"  # flagged, but no study covers 60 months
    social = next(f for f in report["clinician"]["findings"] if f["key"] == "social_preference")
    assert social["status"] == "flagged" and "12-48 months" in social["age_note"]


def test_report_incomplete_never_says_no_signs():
    report = score_session(make_session(Child(looks_at_calibration=False)))
    assert report["parent"]["outcome"] == "incomplete"
    assert report["parent"]["tips"]
    assert _metric(report, "name_response")["status"] == "not_flagged"


def test_report_lists_what_was_not_assessed():
    report = score_session(make_session())
    assert "Hearing" in report["parent"]["not_checked"]
    assert any(n["area"].startswith("Attention") for n in report["clinician"]["not_assessed"])


@pytest.mark.parametrize("age", [8, 80])
def test_pipeline_rejects_out_of_range_age(age):
    with pytest.raises(InvalidSession):
        score_session(make_session(Child(age_months=age)))



def test_profile_slices_are_measurements_with_published_cutoffs():
    report = score_session(make_session(Child(social_preference=0.1, name_responses=[True, False, False])))
    wheel = {a["key"]: a for a in report["clinician"]["profile"]}
    social = wheel["social_attention"]
    assert social["value"] == pytest.approx(0.9, abs=0.06) and social["cutoff"] == 0.69
    assert social["status"] == "flagged" and social["sources"]
    name = wheel["name_response"]
    assert name["value"] == pytest.approx(2 / 3, abs=0.001)  # missed 2 of 3
    assert name["cutoff"] == pytest.approx(2 / 3, abs=0.001) and name["status"] == "flagged"
    assert wheel["turn_speed"]["tier"] == "B" and wheel["turn_speed"]["cutoff"] is None
    assert len(wheel["turn_speed"]["markers"]) == 2
    not_assessed = [a for a in wheel.values() if a["status"] == "not_assessed"]
    assert len(not_assessed) == 6 and all(a["value"] is None for a in not_assessed)
    assert report["parent"]["profile"] == report["clinician"]["profile"]


def test_profile_unmeasured_module_has_no_value():
    report = score_session(make_session(Child(looks_at_calibration=False)))
    social = next(a for a in report["clinician"]["profile"] if a["key"] == "social_attention")
    assert social["value"] is None and social["status"] == "insufficient"


def test_implausibly_large_yaw_gain_is_bounded():
    # Head yaw "explains" the targets at 0.2 screen widths per degree: physically impossible for a
    # screen spanning >= 20°, so the coefficient is clamped to 1/20.
    from scoring import config as C
    from scoring.gaze import _fit_x, _yaw_gain
    from scoring.models import Frame

    frames, targets = [], []
    for i in range(200):
        x = 0.15 + 0.7 * (i % 5) / 4
        yaw = -(x - 0.5) / 0.2  # 0.2 widths per degree, negative sign as in the pipeline
        frames.append(Frame(t=i, face=True, iris_x=0.5, iris_y=0.4, yaw=yaw, pitch=0, face_x=0.5, face_y=0.45, face_w=0.2))
        targets.append(x)
    model, source = _fit_x(frames, targets, yaw_spread=3.5)
    assert source == "bounded"
    assert _yaw_gain(model) == pytest.approx(-C.CALIB_YAW_GAIN_MAX)

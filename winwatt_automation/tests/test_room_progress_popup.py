from winwatt_automation.scripts.room_progress_popup import _eta_text


def test_eta_is_unknown_until_a_measurement_interval() -> None:
    assert "első 5 perc" in _eta_text(None, {"queue": 100, "complete": False}, 300)


def test_eta_uses_observed_queue_reduction() -> None:
    text = _eta_text({"queue": 100, "complete": False}, {"queue": 80, "complete": False}, 300)
    assert "20 perc" in text

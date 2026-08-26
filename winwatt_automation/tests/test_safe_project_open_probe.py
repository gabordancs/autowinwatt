from winwatt_automation.workflows import safe_project_open_probe


def test_safe_project_open_probe_records_verified_non_mutating_round_trip(monkeypatch):
    class Dialog:
        visible = True

        def exists(self):
            return self.visible

        def is_visible(self):
            return self.visible

    dialog = Dialog()

    class MainWindow:
        def is_enabled(self):
            return True

    monkeypatch.setattr(
        safe_project_open_probe,
        "prepare_and_trigger_project_open_dialog",
        lambda **_kwargs: (dialog, {"dialog_found": True, "selected_candidate": {"title": "Projekt megnyitás"}}),
    )
    monkeypatch.setattr(safe_project_open_probe, "get_cached_main_window", lambda: MainWindow())
    monkeypatch.setattr(safe_project_open_probe, "_is_visible_dialog", lambda _dialog: False)
    monkeypatch.setattr(safe_project_open_probe, "_is_detected_dialog_visible", lambda _dialog, _detection: False)
    monkeypatch.setattr(safe_project_open_probe, "_send_escape", lambda: None)

    result = safe_project_open_probe.run_safe_project_open_probe(close_timeout=0.01)

    assert result["success"] is True
    assert result["command"] == "MainForm.OpenProjekt"
    assert result["dialog_dismissed"] is True

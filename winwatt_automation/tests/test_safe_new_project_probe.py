from winwatt_automation.workflows import safe_new_project_probe


def test_safe_new_project_probe_records_verified_non_mutating_round_trip(monkeypatch):
    class MainWindow:
        def set_focus(self):
            return None

        def process_id(self):
            return 12

        def is_enabled(self):
            return True

    main_window = MainWindow()
    monkeypatch.setattr(safe_new_project_probe, "prepare_main_window_for_menu_interaction", lambda: main_window)
    monkeypatch.setattr(safe_new_project_probe, "ensure_main_window_foreground_before_click", lambda **_kwargs: main_window)
    monkeypatch.setattr(safe_new_project_probe, "get_cached_main_window", lambda: main_window)
    monkeypatch.setattr(safe_new_project_probe, "_send_new_project_menu_sequence", lambda: ["ALT+F", "ENTER"])
    monkeypatch.setattr(
        safe_new_project_probe,
        "_find_new_project_dialog",
        lambda _pid, timeout: (object(), {"dialog_found": True, "selected_candidate": {"title": "Projekt létrehozása", "handle": 44}}),
    )
    monkeypatch.setattr(safe_new_project_probe, "_send_escape", lambda: None)
    monkeypatch.setattr(safe_new_project_probe, "_dialog_is_visible", lambda _handle: False)
    monkeypatch.setattr(safe_new_project_probe, "_snapshot_visible_controls", lambda _dialog: [{"title": "Mégse", "control_id": 2}])

    result = safe_new_project_probe.run_safe_new_project_probe(close_timeout=0.01)

    assert result["success"] is True
    assert result["command"] == "MainForm.NewProjekt"
    assert result["dialog_dismissed"] is True
    assert result["dialog_controls"] == [{"title": "Mégse", "control_id": 2}]

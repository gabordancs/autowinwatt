from winwatt_automation.workflows import safe_project_options_probe


def test_safe_project_options_probe_closes_without_accepting_changes(monkeypatch):
    class MainWindow:
        def process_id(self):
            return 12

        def is_enabled(self):
            return True

    class Dialog:
        handle = 44

        def close(self):
            return None

    main_window = MainWindow()
    dialog = Dialog()
    found = iter([dialog, None, None])
    monkeypatch.setattr(safe_project_options_probe, "prepare_main_window_for_menu_interaction", lambda: main_window)
    monkeypatch.setattr(safe_project_options_probe, "ensure_main_window_foreground_before_click", lambda **_kwargs: main_window)
    monkeypatch.setattr(safe_project_options_probe, "_open_project_options", lambda _main: None)
    monkeypatch.setattr(safe_project_options_probe, "_find_project_options_dialog", lambda _pid, timeout: next(found))
    monkeypatch.setattr(safe_project_options_probe, "_snapshot_controls", lambda _dialog: [{"title": "Elvet"}])
    monkeypatch.setattr(safe_project_options_probe, "get_cached_main_window", lambda: main_window)

    result = safe_project_options_probe.run_safe_project_options_probe(close_timeout=0.01)

    assert result["success"] is True
    assert result["command"] == "MainForm.ProjektOptions"
    assert result["dialog_controls"] == [{"title": "Elvet"}]

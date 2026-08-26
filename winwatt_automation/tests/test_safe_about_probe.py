from winwatt_automation.workflows import safe_about_probe


def test_safe_about_probe_closes_identified_dialog_and_restores_main_window(monkeypatch):
    class MainWindow:
        def process_id(self):
            return 12

        def is_enabled(self):
            return True

    class Dialog:
        handle = 44

    main_window = MainWindow()
    dialog = Dialog()
    calls = []
    found = iter([dialog, None, None])
    monkeypatch.setattr(safe_about_probe, "prepare_main_window_for_menu_interaction", lambda: main_window)
    monkeypatch.setattr(safe_about_probe, "ensure_main_window_foreground_before_click", lambda **_kwargs: main_window)
    monkeypatch.setattr(safe_about_probe, "_open_about_dialog", lambda _main: calls.append("open"))
    monkeypatch.setattr(safe_about_probe, "_find_about_dialog", lambda _pid, timeout: next(found))
    monkeypatch.setattr(safe_about_probe, "_close_about_dialog", lambda _dialog: calls.append("close"))
    monkeypatch.setattr(safe_about_probe, "get_cached_main_window", lambda: main_window)

    result = safe_about_probe.run_safe_about_probe(close_timeout=0.01)

    assert calls == ["open", "close"]
    assert result["success"] is True
    assert result["command"] == "MainForm.HelpAbout"
    assert result["dialog_dismissed"] is True

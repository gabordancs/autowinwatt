from __future__ import annotations

from winwatt_automation.runtime_mapping import program_mapper


def test_explore_top_menu_stops_when_file_menu_open_failed(monkeypatch):
    monkeypatch.setattr(
        program_mapper.menu_helpers,
        "open_file_menu_and_capture_popup_state",
        lambda: {"status": "failed_system_menu", "rows": []},
    )

    monkeypatch.setattr(
        program_mapper,
        "capture_state_snapshot",
        lambda state_id: program_mapper.RuntimeStateSnapshot(
            state_id=state_id,
            process_id=1,
            main_window_title="WinWatt",
            main_window_class="TMainForm",
            visible_top_windows=[{"title": "WinWatt"}],
            discovered_top_menus=["Fájl"],
            timestamp="2026-01-01T00:00:00+00:00",
        ),
    )

    rows, actions, dialogs, windows = program_mapper.explore_top_menu(state_id="s", top_menu="Fájl", safe_mode="safe")

    assert rows == []
    assert dialogs == []
    assert windows == []
    assert len(actions) == 1
    assert actions[0].result_type == "failed_system_menu"


def test_map_runtime_state_aborts_on_focus_failure(monkeypatch):
    snapshot = program_mapper.RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[{"title": "WinWatt"}],
        discovered_top_menus=["Fájl", "Ablak"],
        timestamp="2026-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(program_mapper, "capture_state_snapshot", lambda state_id: snapshot)

    def _fail(**kwargs):
        raise RuntimeError("focus_not_restored")

    monkeypatch.setattr(program_mapper, "ensure_main_window_foreground_before_click", _fail)

    state_map = program_mapper.map_runtime_state(state_id="s", safe_mode="safe")

    assert len(state_map.actions) == 1
    assert state_map.actions[0]["result_type"] == "failed_focus"

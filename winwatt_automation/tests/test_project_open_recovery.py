from __future__ import annotations

from winwatt_automation.runtime_mapping import program_mapper
from winwatt_automation.runtime_mapping.models import RuntimeStateMap


class _FakeMainWindow:
    def __init__(self, *, visible: bool = True, enabled: bool = True, handle: int = 1):
        self._visible = visible
        self._enabled = enabled
        self._handle = handle

    def is_visible(self):
        return self._visible

    def is_enabled(self):
        return self._enabled

    def handle(self):
        return self._handle

    def window_text(self):
        return "WinWatt"

    def class_name(self):
        return "TMainForm"

    def process_id(self):
        return 42

    def rectangle(self):
        return type("R", (), {"left": 1, "top": 2, "right": 3, "bottom": 4})()


def test_recover_after_project_open_success_after_disabled(monkeypatch):
    state = {"enabled": False}

    def _cached_main_window():
        return _FakeMainWindow(visible=True, enabled=state["enabled"])

    def _attempt_close(**kwargs):
        state["enabled"] = True
        return [{"method": "key", "name": "Esc"}]

    monkeypatch.setattr(program_mapper, "get_cached_main_window", _cached_main_window)
    monkeypatch.setattr(program_mapper, "_collect_project_open_recovery_diagnostics", lambda window: {"foreground_window": {}, "dialog_candidates": [], "main_window": {"visible": True, "enabled": state["enabled"], "rect": {}}})
    monkeypatch.setattr(program_mapper, "_attempt_project_open_modal_close", _attempt_close)

    result = program_mapper.recover_after_project_open(timeout_s=1.0, poll_interval_s=0.01)

    assert result["success"] is True
    assert result["close_attempts"] == [{"method": "key", "name": "Esc"}]


def test_build_full_runtime_program_map_stops_on_recovery_failure(monkeypatch, tmp_path):
    no_project = RuntimeStateMap("no_project", {"state_id": "no_project"}, [{"text": "Fájl"}], [], [], [], [], [])

    monkeypatch.setattr(program_mapper, "ensure_output_dirs", lambda _path: {
        "base": tmp_path,
        "state_no_project": tmp_path / "state_no_project",
        "state_project_open": tmp_path / "state_project_open",
        "diff": tmp_path / "diff",
    })
    for sub in ("state_no_project", "state_project_open", "diff"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)

    def _map_runtime_state(**kwargs):
        if kwargs["state_id"] == "no_project":
            return no_project
        raise AssertionError("project_open mapping should not run when recovery fails")

    monkeypatch.setattr(program_mapper, "map_runtime_state", _map_runtime_state)
    monkeypatch.setattr(program_mapper, "open_test_project", lambda *args, **kwargs: {"success": True, "recovery": {"success": False, "diagnostics": {"x": 1}, "close_attempts": []}})

    result = program_mapper.build_full_runtime_program_map(project_path="x", output_dir=tmp_path)

    assert result["state_project_open"].snapshot["mapping_partial"] is True
    assert result["state_project_open"].snapshot["mapping_stop_reason"] == "project_open_recovery_failed"
    assert result["state_project_open"].snapshot["recovery_diagnostics"] == {"x": 1}


def test_restore_clean_menu_baseline_modal_pending_uses_recovery(monkeypatch):
    monkeypatch.setattr(program_mapper, "ensure_main_window_foreground_before_click", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("focus_not_restored")))
    monkeypatch.setattr(program_mapper, "get_cached_main_window", lambda: _FakeMainWindow(visible=True, enabled=False))
    monkeypatch.setattr(program_mapper, "recover_after_project_open", lambda **kwargs: {"success": True, "diagnostics": {}, "close_attempts": []})
    monkeypatch.setattr(program_mapper.menu_helpers, "capture_menu_popup_snapshot", lambda: [])

    assert program_mapper.restore_clean_menu_baseline(state_id="s", stage="before:Fájl") is True


def test_close_attempt_order_is_stable(monkeypatch):
    monkeypatch.setattr(program_mapper, "get_cached_main_window", lambda: _FakeMainWindow(visible=True, enabled=False))
    monkeypatch.setattr(program_mapper, "_send_recovery_key", lambda _k, **_kwargs: False)
    monkeypatch.setattr(program_mapper, "_click_recovery_button", lambda *_args, **_kwargs: False)

    attempts = program_mapper._attempt_project_open_modal_close(main_window_handle=1)

    names = [item["name"] for item in attempts]
    assert names[:3] == ["Esc", "Enter", "Alt+F4"]
    assert names[3:11] == ["OK", "Rendben", "Bezár", "Mégse", "Cancel", "Close", "No", "Nem"]


def test_recovery_diagnostics_payload_shape(monkeypatch):
    monkeypatch.setattr(program_mapper, "_list_visible_top_windows", lambda: [{"title": "WinWatt", "class_name": "TMainForm", "process_id": 42, "handle": 1}, {"title": "Open", "class_name": "#32770", "process_id": 42, "handle": 2}])
    monkeypatch.setattr(program_mapper, "_foreground_window_info", lambda: {"title": "Open", "class_name": "#32770", "process_id": 42})

    data = program_mapper._collect_project_open_recovery_diagnostics(_FakeMainWindow(visible=True, enabled=False, handle=1))

    assert set(data.keys()) == {"foreground_window", "dialog_candidates", "main_window"}
    assert set(data["main_window"].keys()) >= {"enabled", "visible", "rect"}


def test_build_full_runtime_program_map_continues_when_recovery_succeeds(monkeypatch, tmp_path):
    no_project = RuntimeStateMap("no_project", {"state_id": "no_project"}, [{"text": "Fájl"}], [], [], [], [], [])
    project_open = RuntimeStateMap("project_open", {"state_id": "project_open"}, [{"text": "Fájl"}], [], [], [], [], [])

    monkeypatch.setattr(program_mapper, "ensure_output_dirs", lambda _path: {
        "base": tmp_path,
        "state_no_project": tmp_path / "state_no_project",
        "state_project_open": tmp_path / "state_project_open",
        "diff": tmp_path / "diff",
    })
    for sub in ("state_no_project", "state_project_open", "diff"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)

    calls: list[str] = []

    def _map_runtime_state(**kwargs):
        calls.append(kwargs["state_id"])
        return no_project if kwargs["state_id"].endswith("no_project") else project_open

    monkeypatch.setattr(program_mapper, "map_runtime_state", _map_runtime_state)
    monkeypatch.setattr(program_mapper, "open_test_project", lambda *args, **kwargs: {"success": True, "recovery": {"success": True, "diagnostics": {}, "close_attempts": []}})

    result = program_mapper.build_full_runtime_program_map(project_path="x", output_dir=tmp_path)

    assert calls == ["no_project", "project_open"]
    assert result["state_project_open"].snapshot["project_open_recovery"]["success"] is True


def test_build_full_runtime_program_map_skips_known_no_project_paths(monkeypatch, tmp_path):
    no_project = RuntimeStateMap(
        "no_project",
        {"state_id": "no_project"},
        [{"text": "Fájl"}],
        [{"menu_path": ["Fájl", "Megnyitás"], "enabled_guess": True}],
        [],
        [],
        [],
        [],
    )
    project_open = RuntimeStateMap("project_open", {"state_id": "project_open"}, [{"text": "Fájl"}], [], [], [], [], [])

    monkeypatch.setattr(program_mapper, "ensure_output_dirs", lambda _path: {
        "base": tmp_path,
        "state_no_project": tmp_path / "state_no_project",
        "state_project_open": tmp_path / "state_project_open",
        "diff": tmp_path / "diff",
    })
    for sub in ("state_no_project", "state_project_open", "diff"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)

    seen_known_paths: list[set[tuple[str, ...]] | None] = []

    def _map_runtime_state(**kwargs):
        seen_known_paths.append(kwargs.get("known_paths_to_skip"))
        return no_project if kwargs["state_id"] == "no_project" else project_open

    monkeypatch.setattr(program_mapper, "map_runtime_state", _map_runtime_state)
    monkeypatch.setattr(program_mapper, "open_test_project", lambda *args, **kwargs: {"success": True, "recovery": {"success": True, "diagnostics": {}, "close_attempts": []}})

    program_mapper.build_full_runtime_program_map(project_path="x", output_dir=tmp_path)

    assert seen_known_paths[0] is None
    assert seen_known_paths[1] == {("fájl", "megnyitás")}

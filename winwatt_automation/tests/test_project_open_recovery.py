from __future__ import annotations

import json

from winwatt_automation.runtime_mapping import program_mapper
from winwatt_automation.runtime_mapping.models import RuntimeStateMap, RuntimeStateSnapshot
from winwatt_automation.runtime_mapping.config import configure_diagnostics


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
    assert result["modal_pending"] is True
    assert result["close_attempted"] is True
    assert result["main_window_reenabled"] is True


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
    monkeypatch.setattr(program_mapper.menu_helpers, "wait_for_popup_to_close", lambda **kwargs: True)

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
    no_project = RuntimeStateMap(
        "no_project",
        {"state_id": "no_project"},
        [{"text": "Fájl"}],
        [],
        [],
        [{"menu_path": ["Fájl", "Megnyitás"], "attempted": True, "event_details": {}}],
        [],
        [],
        [],
        [{"path": ["Fájl", "Megnyitás"], "action_type": "click", "action_state_classification": "executes_command", "opens_modal": False, "opens_submenu": False, "changes_menu_state": False, "opens_project_and_changes_runtime_state": False, "traversal_depth": 1}],
        [],
        {},
    )
    project_open = RuntimeStateMap(
        "project_open",
        {"state_id": "project_open"},
        [{"text": "Fájl"}],
        [],
        [],
        [{"menu_path": ["Fájl", "Recent", "Sample"], "attempted": True, "event_details": {"project_open_state_transition": True, "result_type": "project_open_state_transition", "new_runtime_state": {"main_window_title": "WinWatt - Sample"}}}],
        [],
        [],
        [],
        [{"path": ["Fájl", "Recent", "Sample"], "action_type": "click", "action_state_classification": "opens_project_and_changes_runtime_state", "opens_modal": False, "opens_submenu": False, "changes_menu_state": False, "opens_project_and_changes_runtime_state": True, "traversal_depth": 1}],
        [{"path": ["Fájl", "Recent", "Sample"], "trigger": "opens_project_and_changes_runtime_state", "result_type": "project_open_state_transition", "new_runtime_state": {"main_window_title": "WinWatt - Sample"}, "project_open_transition_reasons": {}}],
        {},
    )

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
    assert set(result["runtime_state_atlas"]["states"].keys()) == {"no_project", "project_open"}
    assert result["runtime_state_atlas"]["states"]["no_project"]["action_catalog"]
    assert result["runtime_state_atlas"]["states"]["project_open"]["state_transitions"][0]["trigger"] == "opens_project_and_changes_runtime_state"
    atlas_json = json.loads((tmp_path / "runtime_state_atlas.json").read_text(encoding="utf-8"))
    assert set(atlas_json["states"].keys()) == {"no_project", "project_open"}


def test_recent_project_probe_policy_keeps_recent_project_classification(monkeypatch):
    configure_diagnostics(recent_projects_policy="probe_recent_projects", diagnostic_fast_mode=False, placeholder_traversal_focus=False)
    snapshot = RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[],
        discovered_top_menus=["Fájl"],
        timestamp="t",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"title": "WinWatt", "class_name": "TMainForm"},
    )
    monkeypatch.setattr(program_mapper, "capture_state_snapshot", lambda _state_id: snapshot)
    monkeypatch.setattr(program_mapper, "_is_recent_projects_candidate", lambda **_kwargs: True)
    popup_rows = [{
        "text": "",
        "center_x": 15,
        "center_y": 95,
        "rectangle": {"left": 0, "top": 90, "right": 100, "bottom": 110},
        "is_separator": False,
        "source_scope": "main_window",
        "popup_candidate": True,
        "topbar_candidate": False,
        "popup_reason": "empty_text_vertical_cluster_below_topbar",
        "recent_project_entry": True,
        "recent_projects_block": True,
        "stateful_menu_block": True,
        "popup_block_classification": "recent_projects_block",
    }]

    nodes, _, actions, _, _, catalog = program_mapper.explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        popup_rows=popup_rows,
        visited_paths={("fájl",)},
    )

    assert nodes[0]["action_state_classification"] == "recent_project_entry"
    assert actions[0].event_details["action_state_classification"] == "recent_project_entry"
    assert catalog[0]["skip_reason"] == "recent_project_catalog_only"


def test_build_full_runtime_program_map_rechecks_paths_in_project_state(monkeypatch, tmp_path):
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
    assert seen_known_paths[1] is None


def test_build_full_runtime_program_map_writes_knowledge_verification(monkeypatch, tmp_path):
    no_project = RuntimeStateMap(
        "no_project",
        {"state_id": "no_project"},
        [{"text": "Fájl"}],
        [{"menu_path": ["Fájl", "Megnyitás"], "enabled_guess": True}],
        [],
        [{"menu_path": ["Fájl", "Megnyitás"], "title": "Open", "class_name": "#32770"}],
        [],
        [],
    )
    project_open = RuntimeStateMap(
        "project_open",
        {"state_id": "project_open"},
        [{"text": "Fájl"}],
        [{"menu_path": ["Fájl", "Megnyitás"], "enabled_guess": True}, {"menu_path": ["Fájl", "Mentés"], "enabled_guess": True}],
        [],
        [],
        [{"menu_path": ["Fájl", "Mentés"], "title": "Save", "class_name": "TSaveDlg"}],
        [],
    )

    monkeypatch.setattr(program_mapper, "ensure_output_dirs", lambda _path: {
        "base": tmp_path,
        "state_no_project": tmp_path / "state_no_project",
        "state_project_open": tmp_path / "state_project_open",
        "diff": tmp_path / "diff",
    })
    for sub in ("state_no_project", "state_project_open", "diff"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)

    call_idx = {"i": 0}

    def _map_runtime_state(**kwargs):
        call_idx["i"] += 1
        return no_project if call_idx["i"] == 1 else project_open

    monkeypatch.setattr(program_mapper, "map_runtime_state", _map_runtime_state)
    monkeypatch.setattr(program_mapper, "open_test_project", lambda *args, **kwargs: {"success": True, "recovery": {"success": True, "diagnostics": {}, "close_attempts": []}})

    result = program_mapper.build_full_runtime_program_map(project_path="x", output_dir=tmp_path)

    assert result["knowledge_verification"]["baseline_loaded"] is False
    assert (tmp_path / "knowledge.json").exists()
    assert (tmp_path / "knowledge_summary.md").exists()


def test_project_path_helpers_and_verdicts():
    title = r"WinWatt - C:\work\demo\testwwp.wwp"

    verification = program_mapper._build_project_path_verification(
        expected_project_path=r"C:/work/demo/testwwp.wwp",
        observed_main_window_title=title,
    )

    assert verification["observed_project_path"] == r"C:\work\demo\testwwp.wwp"
    assert verification["path_match_normalized"] is True
    assert program_mapper._project_open_verdict(
        already_open_before_mapping=True,
        path_match_normalized=True,
        open_attempt_success=True,
    ) == "already_open_before_mapping"
    assert program_mapper._project_open_verdict(
        already_open_before_mapping=False,
        path_match_normalized=True,
        open_attempt_success=True,
    ) == "opened_by_this_attempt"
    assert program_mapper._project_open_verdict(
        already_open_before_mapping=False,
        path_match_normalized=False,
        open_attempt_success=False,
    ) == "open_attempt_failed"
    assert program_mapper._project_open_verdict(
        already_open_before_mapping=False,
        path_match_normalized=False,
        open_attempt_success=True,
    ) == "unproven"


def test_build_full_runtime_program_map_records_project_open_verification(monkeypatch, tmp_path):
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

    snapshots = iter([
        RuntimeStateSnapshot("startup", 1, "WinWatt", "TMainForm", [], ["Fájl"], "t"),
        RuntimeStateSnapshot("verify", 1, r"WinWatt - C:\tmp\demo\testwwp.wwp", "TMainForm", [], ["Fájl"], "t"),
    ])
    monkeypatch.setattr(program_mapper, "capture_state_snapshot", lambda _state_id: next(snapshots))
    monkeypatch.setattr(program_mapper, "map_runtime_state", lambda **kwargs: no_project if kwargs["state_id"] == "no_project" else project_open)
    monkeypatch.setattr(program_mapper, "open_test_project", lambda *args, **kwargs: {
        "success": True,
        "dialog_found": True,
        "path_entered": True,
        "confirm_clicked": True,
        "project_open_audit": {
            "project_open_attempt_started": True,
            "project_open_menu_item_clicked": True,
            "open_file_dialog_detected": True,
            "file_dialog_path_entered": True,
            "file_dialog_confirm_clicked": True,
        },
        "recovery": {"success": True, "diagnostics": {}, "close_attempts": [], "main_window_ready_after_attempt": True},
    })

    events: list[tuple[str, dict[str, object]]] = []
    result = program_mapper.build_full_runtime_program_map(
        project_path=r"C:\tmp\demo\testwwp.wwp",
        output_dir=tmp_path,
        event_recorder=lambda event_type, payload: events.append((event_type, payload)),
    )

    assert result["project_open_result"]["project_open_verdict"] == "opened_by_this_attempt"
    assert result["project_open_result"]["path_match_normalized"] is True
    assert result["state_no_project"].snapshot["startup_project_detected"] is False
    assert result["state_project_open"].snapshot["project_open_verdict"] == "opened_by_this_attempt"
    project_open_payload = dict(next(payload for event_type, payload in events if event_type == "project_open_result"))
    assert project_open_payload["project_open_attempt_started"] is True
    assert project_open_payload["project_open_menu_item_clicked"] is True
    assert project_open_payload["path_match_normalized"] is True
    step_events = {event_type: payload for event_type, payload in events}
    assert step_events["open_file_dialog_detected"]["value"] is True
    assert step_events["file_dialog_path_entered"]["value"] is True
    assert step_events["file_dialog_confirm_clicked"]["value"] is True
    assert step_events["dialog_closed"]["value"] is False
    assert step_events["observed_main_window_title_after_open"]["value"] == r"WinWatt - C:\tmp\demo\testwwp.wwp"
    assert step_events["observed_project_path"]["value"] == r"C:\tmp\demo\testwwp.wwp"
    assert step_events["path_match_normalized"]["value"] is True


class _FakeComError(Exception):
    __module__ = "pythoncom"


class _FakeMenuParent:
    def __init__(self, control_type: str):
        self.element_info = type("Info", (), {"control_type": control_type, "name": control_type, "class_name": ""})()


class _FakeMenuItem:
    def __init__(self, name: str, rect: tuple[int, int, int, int], *, parent_mode: str = "ok"):
        self.element_info = type("Info", (), {"name": name, "control_type": "MenuItem", "class_name": "MenuItem", "process_id": 42, "handle": id(self)})()
        self._rect = rect
        self._parent_mode = parent_mode

    def is_visible(self):
        return True

    def rectangle(self):
        left, top, right, bottom = self._rect
        return type("Rect", (), {"left": left, "top": top, "right": right, "bottom": bottom})()

    def parent(self):
        if self._parent_mode == "comerror":
            raise _FakeComError("uia parent lookup failed")
        return _FakeMenuParent("MenuBar")


def test_capture_menu_popup_snapshot_recovers_from_parent_comerror(monkeypatch):
    from loguru import logger
    from winwatt_automation.live_ui import menu_helpers

    menu_helpers._TOPBAR_BAND_CACHE.update({"handle": None, "captured_at": 0.0, "band": None})
    menu_helpers._consume_topbar_parent_error_state()

    main_rows = [
        {
            "text": "Megnyitás",
            "normalized_text": "megnyitás",
            "control_type": "MenuItem",
            "class_name": "MenuItem",
            "rectangle": {"left": 5, "top": 60, "right": 140, "bottom": 82},
            "width": 135,
            "height": 22,
            "center_x": 72,
            "center_y": 71,
            "is_separator": False,
            "source_scope": "main_window",
            "process_id": 42,
            "native_handle": 1,
        }
    ]
    top_items = [
        _FakeMenuItem("Fájl", (4, 4, 70, 28), parent_mode="comerror"),
        _FakeMenuItem("Ablak", (71, 4, 150, 28), parent_mode="comerror"),
        _FakeMenuItem("Súgó", (151, 4, 220, 28), parent_mode="comerror"),
    ]
    events: list[str] = []
    sink_id = logger.add(lambda msg: events.append(msg.record["message"]), level="INFO")
    try:
        monkeypatch.setattr(menu_helpers, "_menu_like_controls_from_main_window", lambda: [dict(row) for row in main_rows])
        monkeypatch.setattr(menu_helpers, "_menu_like_controls_from_global_process_scan", lambda: [])
        monkeypatch.setattr(menu_helpers, "get_cached_main_window", lambda: type("Main", (), {"element_info": type("Info", (), {"handle": 99})(), "child_window": lambda self, **kwargs: (_ for _ in ()).throw(RuntimeError("no menubar"))})())
        monkeypatch.setattr(menu_helpers, "_query_menu_items_from_root", lambda _root, **kwargs: top_items)

        rows = menu_helpers.capture_menu_popup_snapshot()
    finally:
        logger.remove(sink_id)

    assert rows
    assert rows[0]["popup_candidate"] is True
    assert any("TOPBAR_PARENT_COMERROR_FALLBACK" in event for event in events)
    assert any("TOPBAR_GEOMETRY_FALLBACK_USED" in event for event in events)
    assert any("POPUP_SNAPSHOT_COMSAFE_RECOVERY" in event for event in events)

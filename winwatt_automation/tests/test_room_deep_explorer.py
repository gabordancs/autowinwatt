from collections import deque

from winwatt_automation.runtime_mapping.room_deep_explorer import ControlAction, _path_enters_focus_tab, _path_uses_excluded_action, _prune_queue, action_identity, canonical_states_by_signature, failure_diagnostics, logical_state_hash, resolve_edge_targets, state_diff, state_hash
from winwatt_automation.runtime_mapping import room_deep_explorer


def test_failure_diagnostics_preserves_empty_exception_details() -> None:
    class EmptyFailure(Exception):
        def __str__(self) -> str:
            return ""

    details = failure_diagnostics(EmptyFailure("hidden"))

    assert details["error_type"] == "EmptyFailure"
    assert "EmptyFailure" in details["error"]
    assert details["error_repr"] == details["error"]
from winwatt_automation.scripts.explore_rooms_deep import excluded_tabs_for_scope


def test_state_hash_is_deterministic_for_equal_structures() -> None:
    first = {"title": "x", "class_name": "y", "controls": [{"name": "a"}]}
    second = {"controls": [{"name": "a"}], "class_name": "y", "title": "x"}
    assert state_hash(first) == state_hash(second)


def test_state_hash_ignores_recreated_automation_handles() -> None:
    first = {"title": "x", "class_name": "y", "controls": [{"name": "a", "automation_id": "101"}]}
    second = {"title": "x", "class_name": "y", "controls": [{"name": "a", "automation_id": "202"}]}
    assert state_hash(first) == state_hash(second)


def test_state_hash_keeps_selected_value_distinct() -> None:
    first = {"title": "x", "class_name": "y", "controls": [{"name": "a", "value": "inside"}]}
    second = {"title": "x", "class_name": "y", "controls": [{"name": "a", "value": "outside"}]}
    assert state_hash(first) != state_hash(second)


def test_logical_state_hash_ignores_screen_coordinates() -> None:
    first = {"title": "x", "class_name": "y", "controls": [{"name": "a", "rect": (0, 0, 20, 20)}]}
    second = {"title": "x", "class_name": "y", "controls": [{"name": "a", "rect": (100, 100, 200, 200)}]}
    assert logical_state_hash(first) == logical_state_hash(second)


def test_worker_scopes_do_not_overlap() -> None:
    assert "Határoló szerkezetek" in excluded_tabs_for_scope("climate")
    assert "Általános adatok" in excluded_tabs_for_scope("boundaries")
    assert not (excluded_tabs_for_scope("climate") & {"Általános adatok", "Téli hőszükséglet", "Nyári hőterhelés"})
    assert not (excluded_tabs_for_scope("boundaries") & {"Határoló szerkezetek"})
    assert "Nyári hőterhelés" in excluded_tabs_for_scope("general-winter")
    assert "Téli hőszükséglet" in excluded_tabs_for_scope("summer")


def test_control_action_is_serializable_for_replay() -> None:
    action = ControlAction("Button", "Szerkezetek...", "id", (1, 2, 3, 4))
    assert action.operation == "activate"


def test_focus_tab_keeps_root_and_requested_subtree_only() -> None:
    general = ControlAction("TabItem", "Általános adatok", "", (1, 2, 3, 4))
    heating = ControlAction("TabItem", "Fűtés", "", (1, 2, 3, 4))
    button = ControlAction("Button", "Részletek", "", (1, 2, 3, 4))

    assert _path_enters_focus_tab([], {"fűtés"})
    assert _path_enters_focus_tab([heating, button], {"fűtés"})
    assert not _path_enters_focus_tab([general, button], {"fűtés"})
    assert not _path_enters_focus_tab([button], {"fűtés"})


def test_excluded_action_matches_exact_names_and_protected_substrings() -> None:
    close = ControlAction("Button", "Elvet", "", (1, 2, 3, 4))
    submit = ControlAction("Button", "Feltöltés az OÉNY-be", "", (1, 2, 3, 4))
    export = ControlAction("Button", "XML készítése", "", (1, 2, 3, 4))

    assert _path_uses_excluded_action([close], {"elvet"}, set())
    assert _path_uses_excluded_action([submit], set(), {"feltölt"})
    assert not _path_uses_excluded_action([export], {"elvet"}, {"feltölt"})


def test_buildings_root_reuses_verified_live_session(monkeypatch, tmp_path) -> None:
    class Main:
        def process_id(self) -> int:
            return 42

    sentinel = object()
    fresh_calls: list[str] = []
    monkeypatch.setattr(room_deep_explorer, "_project_session_is_ready", lambda _path: True)
    monkeypatch.setattr(room_deep_explorer, "get_main_window", lambda: Main())
    monkeypatch.setattr(room_deep_explorer, "_dismiss_secondary_windows", lambda _pid, attempts: None)
    monkeypatch.setattr(room_deep_explorer, "_activate_buildings_catalog_fast", lambda _main: None)
    monkeypatch.setattr(room_deep_explorer, "active_buildings_window", lambda _pid: sentinel)
    monkeypatch.setattr(
        room_deep_explorer, "prepare_fresh_winwatt_session",
        lambda **kwargs: fresh_calls.append(kwargs["project_path"]),
    )

    result = room_deep_explorer.open_sandbox_buildings(
        project_path=str(tmp_path / "sandbox.wwp"), reuse_session=True,
    )

    assert result is sentinel
    assert fresh_calls == []


def test_action_identity_ignores_recreated_automation_id() -> None:
    first = ControlAction("Button", "Módosít...", "101", (1, 2, 3, 4))
    second = ControlAction("Button", "Módosít...", "202", (1, 2, 3, 4))
    assert action_identity(first) == action_identity(second)


def test_tree_and_list_action_identity_ignores_scroll_position() -> None:
    first = ControlAction("TreeItem", "Anyagok", "", (10, 100, 140, 120))
    second = ControlAction("TreeItem", "Anyagok", "", (10, 500, 140, 520))
    list_first = ControlAction("ListItem", "víz", "", (10, 100, 140, 120))
    list_second = ControlAction("ListItem", "víz", "", (10, 500, 140, 520))
    assert action_identity(first) == action_identity(second)
    assert action_identity(list_first) == action_identity(list_second)


def test_state_diff_records_added_and_removed_controls() -> None:
    old = {"title": "x", "class_name": "Form", "controls": [{"control_type": "Button", "class_name": "TButton", "name": "A", "rect": (0, 0, 1, 1), "enabled": True, "visible": True}]}
    new = {"title": "x", "class_name": "Form", "controls": [{"control_type": "Button", "class_name": "TButton", "name": "B", "rect": (0, 0, 1, 1), "enabled": True, "visible": True}]}
    diff = state_diff(old, new)
    assert diff["changed"] is True
    assert diff["added_controls"][0]["name"] == "B"
    assert diff["removed_controls"][0]["name"] == "A"


def test_state_diff_records_value_change() -> None:
    old = {"title": "x", "class_name": "Form", "controls": [{"control_type": "ComboBox", "class_name": "TComboBox", "name": "", "rect": (0, 0, 1, 1), "enabled": True, "visible": True, "value": "A"}]}
    new = {"title": "x", "class_name": "Form", "controls": [{"control_type": "ComboBox", "class_name": "TComboBox", "name": "", "rect": (0, 0, 1, 1), "enabled": True, "visible": True, "value": "B"}]}
    diff = state_diff(old, new)
    assert diff["changed"] is True
    assert diff["value_changes"][0]["current_value"] == "B"


def test_prune_queue_removes_exhausted_path_but_keeps_other_work() -> None:
    failed = ControlAction("Button", "Hibás", "1", (1, 1, 2, 2))
    useful = ControlAction("Button", "Jó", "2", (3, 3, 4, 4))
    queue, removed = _prune_queue(
        deque([([failed], None), ([useful], None), ([useful], None)]), [], [],
        [{"path": [failed.__dict__], "error": "x", "attempt": attempt} for attempt in range(1, 4)],
    )
    assert removed == 1
    assert list(queue) == [([useful], None)]


def test_prune_queue_removes_repeated_tree_or_list_navigation_loop() -> None:
    category = ControlAction("TreeItem", "Anyagok", "", (10, 10, 100, 30))
    type_item = ControlAction("ListItem", "Fal", "", (10, 40, 100, 60))
    useful = ControlAction("Button", "Felvesz", "", (10, 70, 100, 90))
    queue, removed = _prune_queue(
        deque([([category, type_item, category], None), ([category, type_item, useful], None)]),
        [], [], [],
    )
    assert removed == 1
    assert list(queue) == [([category, type_item, useful], None)]


def test_revisited_edge_keeps_canonical_target() -> None:
    action = ControlAction("Button", "Tovább", "volatile", (1, 2, 3, 4))
    states = [
        {"state_id": "root", "signature_hash": "aaa", "path": []},
        {"state_id": "canonical", "signature_hash": "bbb", "path": [action.__dict__]},
    ]
    edges = [{"from": "root", "action": action.__dict__, "to": "canonical", "status": "revisited"}]

    assert canonical_states_by_signature(states)["bbb"] == "canonical"
    resolve_edge_targets(states, edges)

    assert edges[0]["to"] == "canonical"


def test_unresolved_edge_is_still_marked_explicitly() -> None:
    action = ControlAction("Button", "Ismeretlen", "", (1, 2, 3, 4))
    states = [{"state_id": "root", "signature_hash": "aaa", "path": []}]
    edges = [{"from": "root", "action": action.__dict__, "to": "pending", "status": "failed"}]

    resolve_edge_targets(states, edges)

    assert edges[0]["to"] == "revisited_or_blocked"

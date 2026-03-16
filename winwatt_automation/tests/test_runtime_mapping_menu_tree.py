from __future__ import annotations

from winwatt_automation.runtime_mapping.models import RuntimeStateMap, RuntimeStateSnapshot
from winwatt_automation.runtime_mapping.program_mapper import (
    _build_menu_rows_from_popup_rows,
    compare_runtime_states,
    map_runtime_state,
    explore_menu_tree,
)


def test_hierarchical_menu_tree_building(monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda name: None)

    snapshots = iter([
        [
            {"text": "Megnyitás", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"},
            {"text": "Export", "center_x": 1, "center_y": 2, "rectangle": {"left": 0, "top": 22, "right": 100, "bottom": 32}, "is_separator": False, "source_scope": "main"},
        ],
        [
            {"text": "PDF", "center_x": 150, "center_y": 22, "rectangle": {"left": 140, "top": 20, "right": 220, "bottom": 30}, "is_separator": False, "source_scope": "main"},
        ],
        [],
    ])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))

    state = map_runtime_state(state_id="no_project", top_menus=["Fájl"], max_submenu_depth=2)

    root_children = state.menu_tree[0]["children"]
    parent_with_submenu = next(node for node in root_children if node["opens_submenu"])
    assert parent_with_submenu["children"][0]["title"] == "PDF"


def test_disabled_to_enabled_diff_detected():
    state_a = RuntimeStateMap("no_project", {}, [{"text": "Fájl"}], [{"menu_path": ["Fájl", "Mentés"], "enabled_guess": False}], [], [], [], [])
    state_b = RuntimeStateMap("project_open", {}, [{"text": "Fájl"}], [{"menu_path": ["Fájl", "Mentés"], "enabled_guess": True}], [], [], [], [])

    diff = compare_runtime_states(state_a, state_b)
    assert diff.enabled_state_changes == [{"path": ["Fájl", "Mentés"], "from": False, "to": True}]


def test_skipped_by_safety_classification():
    rows = _build_menu_rows_from_popup_rows(
        "no_project",
        "Fájl",
        [{"text": "Kilépés", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"}],
    )
    assert rows[0].text == "Kilépés"


def test_best_effort_top_menu_processing(monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl", "Súgó"], timestamp="t"))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)

    def _click(menu):
        if menu == "Fájl":
            raise RuntimeError("boom")

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", _click)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: [{"text": "Névjegy", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"}])

    state = map_runtime_state(state_id="no_project", top_menus=["Fájl", "Súgó"], max_submenu_depth=1)
    assert any(action.get("result_type") == "failed_focus" for action in state.actions)
    assert any(root.get("title") == "Súgó" for root in state.menu_tree)

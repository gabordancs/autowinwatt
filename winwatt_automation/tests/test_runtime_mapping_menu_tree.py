from __future__ import annotations

from winwatt_automation.runtime_mapping.models import RuntimeStateMap, RuntimeStateSnapshot
from winwatt_automation.runtime_mapping.program_mapper import (
    _build_menu_rows_from_popup_rows,
    compare_runtime_states,
    explore_menu_tree,
    get_canonical_top_menu_names,
    is_top_menu_like_popup_row,
    map_runtime_state,
    reset_top_menu_cache,
)


def test_hierarchical_menu_tree_building(monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda name: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)

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
    assert diff.enabled_state_changes == [{"path": ["fájl", "mentés"], "from": False, "to": True}]


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
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)

    def _click(menu):
        if menu == "Fájl":
            raise RuntimeError("boom")

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", _click)
    snapshots = iter([
        [],
        [{"text": "Névjegy", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"}],
        [{"text": "Névjegy", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"}],
    ])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))

    state = map_runtime_state(state_id="no_project", top_menus=["Fájl", "Súgó"], max_submenu_depth=1)
    assert any(action.get("result_type") == "failed_focus" for action in state.actions)
    assert any(root.get("title") == "Súgó" for root in state.menu_tree)


def test_popup_top_level_name_is_filtered_from_children():
    rows = _build_menu_rows_from_popup_rows(
        "no_project",
        "Fájl",
        [
            {"text": "Beállítások", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"},
            {"text": "Megnyitás", "center_x": 1, "center_y": 2, "rectangle": {"left": 0, "top": 22, "right": 100, "bottom": 32}, "is_separator": False, "source_scope": "main"},
        ],
        canonical_top_menu_names={"beállítások", "fájl"},
    )
    assert [row.text for row in rows] == ["Megnyitás"]
    assert is_top_menu_like_popup_row({"text": "Ablak"}, {"ablak"})


def test_visited_paths_skips_duplicate_submenu_traversal(monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda _: None)

    snapshots = iter(
        [
            [
                {"text": "Megnyitás", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"},
                {"text": "Megnyitás", "center_x": 1, "center_y": 2, "rectangle": {"left": 0, "top": 22, "right": 100, "bottom": 32}, "is_separator": False, "source_scope": "main"},
            ],
            [],
            [],
        ]
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"),
    )

    nodes, rows, *_ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        visited_paths={("fájl",)},
    )
    assert len(nodes) == 1
    assert len([row for row in rows if row.text == "Megnyitás"]) == 2




def test_mapping_continues_when_focus_loss_is_recovered(monkeypatch):
    snapshot = RuntimeStateSnapshot(state_id="s", process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl", "Súgó"], timestamp="t")
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: snapshot)

    restore_calls: list[str] = []

    def _restore(*, state_id: str, stage: str) -> bool:
        restore_calls.append(stage)
        return True

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", _restore)

    def _explore_menu_tree(**kwargs):
        if kwargs["top_menu"] == "Fájl":
            raise RuntimeError("focus_not_restored: temporary")
        return ([], [], [], [], [])

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.explore_menu_tree", _explore_menu_tree)

    state = map_runtime_state(state_id="s", top_menus=["Fájl", "Súgó"])
    assert state.snapshot["mapping_partial"] is False
    assert state.snapshot["mapping_stop_reason"] is None
    assert any(root.get("title") == "Súgó" for root in state.menu_tree)
    assert "recover_after_exception:Fájl" in restore_calls
def test_mapping_stops_as_partial_when_main_window_is_lost(monkeypatch):
    snapshot = RuntimeStateSnapshot(state_id="s", process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl", "Súgó"], timestamp="t")
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: snapshot)

    restore_calls: list[str] = []

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.should_restore_clean_menu_baseline", lambda **kwargs: True)

    def _restore(*, state_id: str, stage: str) -> bool:
        restore_calls.append(stage)
        return stage != "after:Súgó"

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", _restore)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.explore_menu_tree",
        lambda **kwargs: ([], [], [], [], []),
    )

    state = map_runtime_state(state_id="s", top_menus=["Fájl", "Súgó"])
    assert state.snapshot["mapping_partial"] is True
    assert state.snapshot["mapping_stop_reason"] == "lost_main_window_after:Súgó"
    assert restore_calls == ["after:Fájl", "after:Súgó"]


def test_known_paths_are_marked_as_reused_without_reexploration(monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda _: None)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"),
    )

    snapshots = iter(
        [
            [
                {"text": "Megnyitás", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"},
            ],
        ]
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))

    nodes, _, actions, *_ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        visited_paths={("fájl",)},
        known_paths_to_skip={("fájl", "megnyitás")},
    )

    assert nodes[0]["action_classification"] == "reused_from_previous_state"
    assert nodes[0]["debug"]["reused_from_previous_state"] is True
    assert actions[0].attempted is False
    assert actions[0].notes == "reused_from_previous_state"


def test_mapper_does_not_treat_canonical_top_menu_as_child(monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda _: None)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl", "Súgó"], timestamp="t"),
    )

    snapshots = iter(
        [
            [
                {"text": "Súgó", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"},
                {"text": "Megnyitás", "center_x": 1, "center_y": 2, "rectangle": {"left": 0, "top": 22, "right": 100, "bottom": 32}, "is_separator": False, "source_scope": "main"},
            ],
        ]
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))

    nodes, _, *_ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=1,
        include_disabled=True,
        canonical_top_menu_names={"fájl", "súgó"},
        visited_paths={("fájl",)},
    )
    assert [node["title"] for node in nodes] == ["Megnyitás"]


def test_child_rows_are_not_reprocessed_as_top_level_rows(monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda _: None)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"),
    )

    snapshots = iter(
        [
            [
                {"text": "Export", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"},
            ],
            [
                {"text": "CSV", "center_x": 150, "center_y": 11, "rectangle": {"left": 140, "top": 10, "right": 220, "bottom": 20}, "is_separator": False, "source_scope": "main"},
            ],
        ]
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))

    nodes, _, actions, *_ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        visited_paths={("fájl",)},
    )

    assert len(nodes) == 1
    assert nodes[0]["title"] == "Export"
    assert [child["title"] for child in nodes[0]["children"]] == ["CSV"]
    assert sum(1 for action in actions if action.menu_path == ["Fájl", "CSV"]) == 0


def test_top_menu_cache_reused_until_main_window_handle_changes(monkeypatch):
    class _MainWindow:
        def __init__(self, handle: int):
            self._handle = handle

        def handle(self) -> int:
            return self._handle

    window = _MainWindow(handle=100)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.get_cached_main_window", lambda: window)
    reset_top_menu_cache()

    first = get_canonical_top_menu_names(["Fájl", "Súgó"])
    second = get_canonical_top_menu_names(["Rendszer"])

    assert [item["raw"] for item in first["items"]] == ["Fájl", "Súgó"]
    assert second == first

    window._handle = 200
    third = get_canonical_top_menu_names(["Rendszer"])
    assert [item["raw"] for item in third["items"]] == ["Rendszer"]

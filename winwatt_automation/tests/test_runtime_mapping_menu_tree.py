from __future__ import annotations
import pytest

from winwatt_automation.runtime_mapping.models import RuntimeStateMap, RuntimeStateSnapshot
from winwatt_automation.runtime_mapping.program_mapper import (
    _classify_popup_block,
    _build_menu_rows_from_popup_rows,
    _evaluate_action_admission,
    _run_action_evidence_probe,
    _filter_normal_popup_rows,
    _safe_depth_decision,
    compare_runtime_states,
    explore_menu_tree,
    get_canonical_top_menu_names,
    is_top_menu_like_popup_row,
    map_runtime_state,
    reset_top_menu_cache,
    run_single_row_probe,
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




def test_build_menu_rows_replaces_empty_text_popup_rows_with_geometry_placeholders():
    rows = _build_menu_rows_from_popup_rows(
        "no_project",
        "Fájl",
        [
            {
                "text": "",
                "center_x": 1,
                "center_y": 1,
                "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20},
                "is_separator": False,
                "source_scope": "main",
                "popup_reason": "empty_text_vertical_cluster_below_topbar",
                "popup_candidate": True,
                "topbar_candidate": False,
            },
            {
                "text": "Megnyitás",
                "center_x": 1,
                "center_y": 2,
                "rectangle": {"left": 0, "top": 22, "right": 100, "bottom": 32},
                "is_separator": False,
                "source_scope": "main",
            },
        ],
    )

    assert [row.text for row in rows] == ["[unlabeled row 0]", "Megnyitás"]
    assert rows[0].meta["id"] == "__geom_row_000"
    assert rows[0].meta["source"] == "geometry_placeholder"
    assert rows[0].meta["click_strategy"] == "center_point_fallback"
    assert rows[0].actionable is True
    assert rows[0].action_type == "click"
    assert rows[0].recent_project_entry is False


def test_classify_popup_block_accepts_empty_file_recent_projects_block():
    snapshot = RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[],
        discovered_top_menus=["Fájl", "Súgó"],
        timestamp="t",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"title": "WinWatt", "class_name": "TMainForm"},
    )
    rows = [
        {
            "text": "",
            "center_x": 20,
            "center_y": 50 + (idx * 18),
            "rectangle": {"left": 10, "top": 40 + (idx * 18), "right": 150, "bottom": 56 + (idx * 18)},
            "is_separator": False,
            "source_scope": "main_window",
            "popup_candidate": True,
            "topbar_candidate": False,
            "popup_reason": "empty_text_vertical_cluster_below_topbar",
        }
        for idx in range(17)
    ]

    classification, accepted_rows, meta = _classify_popup_block(top_menu="Fájl", rows=rows, snapshot=snapshot)

    assert classification == "recent_projects_block"
    assert len(accepted_rows) == 17
    assert meta["empty_popup_row_count"] == 17
    assert all(row["recent_project_entry"] is True for row in accepted_rows)
    assert all(row["stateful_menu_block"] is True for row in accepted_rows)

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
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)

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
        return ([], [], [], [], [], [])

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
        lambda **kwargs: ([], [], [], [], [], []),
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
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._reopen_parent_popup_rows",
        lambda **kwargs: [
            {"text": "Export", "center_x": 1, "center_y": 1, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"},
        ],
    )
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


def test_top_menu_cache_refreshes_when_discovered_menus_change(monkeypatch):
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
    assert [item["raw"] for item in second["items"]] == ["Rendszer"]

    window._handle = 200
    third = get_canonical_top_menu_names(["Fájl"])
    assert [item["raw"] for item in third["items"]] == ["Fájl"]


def test_explore_menu_tree_reopens_parent_popup_for_each_row(monkeypatch):
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"),
    )

    row_a = {"text": "A", "center_x": 10, "center_y": 10, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main"}
    row_b = {"text": "B", "center_x": 10, "center_y": 25, "rectangle": {"left": 0, "top": 22, "right": 100, "bottom": 32}, "is_separator": False, "source_scope": "main"}

    reopen_calls: list[list[str]] = []
    activate_calls: list[str] = []

    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._reopen_parent_popup_rows",
        lambda **kwargs: reopen_calls.append(list(kwargs["parent_path"])) or [row_a, row_b],
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._activate_row_for_exploration",
        lambda row, popup_rows: activate_calls.append(row.text),
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot",
        lambda: [row_a, row_b],
    )

    nodes, _, actions, *_ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="blocked",
        max_depth=2,
        include_disabled=True,
        popup_rows=[row_a, row_b],
        visited_paths={("fájl",)},
    )

    assert [node["title"] for node in nodes] == ["A", "B"]
    assert activate_calls == ["A", "B"]
    assert reopen_calls == [["Fájl"], ["Fájl"]]
    assert sum(1 for action in actions if action.attempted) == 2


def test_filter_normal_popup_rows_excludes_topbar_and_system_menu_overlap():
    rows = [
        {"text": "Rendszer", "topbar_candidate": True, "popup_candidate": False, "rectangle": {"left": 0, "top": 0, "right": 10, "bottom": 10}},
        {"text": "Fájl", "topbar_candidate": False, "popup_candidate": True, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}},
        {"text": "Megnyitás", "topbar_candidate": False, "popup_candidate": True, "rectangle": {"left": 0, "top": 21, "right": 100, "bottom": 31}},
    ]

    filtered = _filter_normal_popup_rows(rows, canonical_top_menu_names={"rendszer", "fájl"})

    assert [row["text"] for row in filtered] == ["Megnyitás"]


def test_explore_menu_tree_does_not_reuse_topbar_only_snapshot_for_normal_menu(monkeypatch):
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"),
    )

    click_calls: list[str] = []

    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item",
        lambda title: click_calls.append(title),
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)

    topbar_only_rows = [
        {
            "text": "Fájl",
            "center_x": 10,
            "center_y": 10,
            "rectangle": {"left": 0, "top": 0, "right": 50, "bottom": 20},
            "is_separator": False,
            "source_scope": "main",
            "topbar_candidate": True,
            "popup_candidate": False,
        }
    ]
    snapshots = iter([topbar_only_rows, topbar_only_rows, topbar_only_rows])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))

    nodes, rows, *_ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        visited_paths={("fájl",)},
        canonical_top_menu_names={"fájl"},
    )

    assert nodes == []
    assert rows == []
    assert click_calls == ["Fájl", "Fájl"]


def test_explore_menu_tree_recurses_when_real_popup_rows_exist(monkeypatch):
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"),
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda _: (_ for _ in ()).throw(AssertionError("valid popup snapshot should be reused")))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)

    root_rows = [
        {
            "text": "Export",
            "center_x": 10,
            "center_y": 10,
            "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20},
            "is_separator": False,
            "source_scope": "main",
            "topbar_candidate": False,
            "popup_candidate": True,
        }
    ]
    child_rows = [
        {
            "text": "CSV",
            "center_x": 150,
            "center_y": 10,
            "rectangle": {"left": 140, "top": 10, "right": 220, "bottom": 20},
            "is_separator": False,
            "source_scope": "main",
            "topbar_candidate": False,
            "popup_candidate": True,
        }
    ]
    snapshots = iter([child_rows, child_rows])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper._activate_row_for_exploration", lambda row, popup_rows: None)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._reopen_parent_popup_rows",
        lambda **kwargs: root_rows,
    )

    nodes, _, _, _, _, _ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        visited_paths={("fájl",)},
        popup_rows=root_rows,
        canonical_top_menu_names={"fájl"},
    )

    assert [node["title"] for node in nodes] == ["Export"]
    assert nodes[0]["opens_submenu"] is True
    assert [child["title"] for child in nodes[0]["children"]] == ["CSV"]


def test_map_runtime_state_prioritizes_normal_top_menus_by_default(monkeypatch):
    snapshot = RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="W",
        main_window_class="C",
        visible_top_windows=[],
        discovered_top_menus=["Rendszer", "Fájl", "Súgó"],
        timestamp="t",
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: snapshot)

    explored: list[str] = []

    def _explore_menu_tree(**kwargs):
        explored.append(kwargs["top_menu"])
        return ([], [], [], [], [], [])

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.explore_menu_tree", _explore_menu_tree)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.should_restore_clean_menu_baseline", lambda **kwargs: False)

    state = map_runtime_state(state_id="s")

    assert explored == ["Fájl", "Súgó"]
    assert [item["text"] for item in state.top_menus] == ["Fájl", "Súgó"]


def test_depth_one_retains_leaf_disabled_separator_and_submenu_metadata(monkeypatch):
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"),
    )

    popup_rows = [
        {"text": "Megnyitás", "center_x": 10, "center_y": 10, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 20}, "is_separator": False, "source_scope": "main", "enabled": True},
        {"text": "", "center_x": 10, "center_y": 20, "rectangle": {"left": 0, "top": 21, "right": 100, "bottom": 22}, "is_separator": True, "source_scope": "main"},
        {"text": "Mentés", "center_x": 10, "center_y": 30, "rectangle": {"left": 0, "top": 23, "right": 100, "bottom": 33}, "is_separator": False, "source_scope": "main", "enabled": False},
        {"text": "Export", "center_x": 10, "center_y": 40, "rectangle": {"left": 0, "top": 34, "right": 100, "bottom": 44}, "is_separator": False, "source_scope": "main", "enabled": True},
    ]
    child_snapshot = [
        {"text": "PDF", "center_x": 150, "center_y": 40, "rectangle": {"left": 140, "top": 34, "right": 220, "bottom": 44}, "is_separator": False, "source_scope": "main", "enabled": True},
    ]

    snapshots = iter([child_snapshot, []])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper._reopen_parent_popup_rows", lambda **kwargs: popup_rows)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper._activate_row_for_exploration", lambda row, popup_rows: None)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._detect_child_rows",
        lambda parent_row, all_rows: child_snapshot if parent_row.get("text") == "Export" else [],
    )

    nodes, _, _, _, _, _ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="off",
        max_depth=2,
        include_disabled=True,
        popup_rows=popup_rows,
        visited_paths={("fájl",)},
    )

    assert [node["action_classification"] for node in nodes] == ["leaf_action", "separator", "disabled", "opens_submenu"]
    assert nodes[3]["children"][0]["title"] == "PDF"


def test_explore_menu_tree_placeholder_fast_mode_skips_parent_reopen(monkeypatch):
    from winwatt_automation.runtime_mapping.config import configure_diagnostics

    configure_diagnostics(diagnostic_fast_mode=True, placeholder_traversal_focus=False)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"),
    )

    popup_rows = [
        {
            "text": "",
            "center_x": 15,
            "center_y": 15,
            "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
            "is_separator": False,
            "source_scope": "main_window",
            "popup_candidate": True,
            "topbar_candidate": False,
            "popup_reason": "empty_text_vertical_cluster_below_topbar",
        }
    ]

    reopen_calls = []
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._reopen_parent_popup_rows",
        lambda **kwargs: reopen_calls.append(kwargs) or (_ for _ in ()).throw(AssertionError("should not reopen")),
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._activate_row_for_exploration",
        lambda row, popup_rows: None,
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot",
        lambda: popup_rows,
    )

    explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        popup_rows=popup_rows,
        visited_paths={("fájl",)},
    )

    assert reopen_calls == []
    configure_diagnostics(diagnostic_fast_mode=False, placeholder_traversal_focus=False)




def test_explore_menu_tree_placeholder_focus_hard_fails_without_fresh_popup(monkeypatch):
    from winwatt_automation.runtime_mapping.config import configure_diagnostics

    configure_diagnostics(diagnostic_fast_mode=False, placeholder_traversal_focus=True)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(
            state_id=state_id,
            process_id=1,
            main_window_title="W",
            main_window_class="C",
            visible_top_windows=[],
            discovered_top_menus=["Fájl"],
            timestamp="t",
            main_window_enabled=True,
            main_window_visible=True,
            foreground_window={"title": "W", "class_name": "TMainForm"},
        ),
    )

    popup_rows = [
        {
            "text": "",
            "center_x": 15,
            "center_y": 15,
            "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
            "is_separator": False,
            "source_scope": "main_window",
            "popup_candidate": True,
            "topbar_candidate": False,
            "popup_reason": "empty_text_vertical_cluster_below_topbar",
        }
    ]

    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._reopen_parent_popup_rows",
        lambda **kwargs: [],
    )

    with pytest.raises(RuntimeError, match="fresh root popup reopen failed"):
        explore_menu_tree(
            state_id="s",
            top_menu="Fájl",
            safe_mode="safe",
            max_depth=2,
            include_disabled=True,
            popup_rows=popup_rows,
            visited_paths={("fájl",)},
            canonical_top_menu_names={"fájl"},
        )

    configure_diagnostics(diagnostic_fast_mode=False, placeholder_traversal_focus=False)

def test_explore_menu_tree_placeholder_focus_reopens_fresh_root_snapshot(monkeypatch):
    from winwatt_automation.runtime_mapping.config import configure_diagnostics

    configure_diagnostics(diagnostic_fast_mode=False, placeholder_traversal_focus=True)
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda state_id: RuntimeStateSnapshot(
            state_id=state_id,
            process_id=1,
            main_window_title="W",
            main_window_class="C",
            visible_top_windows=[],
            discovered_top_menus=["Fájl"],
            timestamp="t",
            main_window_enabled=True,
            main_window_visible=True,
            foreground_window={"title": "W", "class_name": "TMainForm"},
        ),
    )

    popup_rows = [
        {
            "text": "",
            "center_x": 15,
            "center_y": 15,
            "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
            "is_separator": False,
            "source_scope": "main_window",
            "popup_candidate": True,
            "topbar_candidate": False,
            "popup_reason": "empty_text_vertical_cluster_below_topbar",
        }
    ]
    refreshed_rows = [
        {
            "text": "",
            "center_x": 18,
            "center_y": 18,
            "rectangle": {"left": 1, "top": 11, "right": 101, "bottom": 31},
            "is_separator": False,
            "source_scope": "main_window",
            "popup_candidate": True,
            "topbar_candidate": False,
            "popup_reason": "empty_text_vertical_cluster_below_topbar",
        }
    ]

    reopen_calls = []
    restore_calls = []
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._reopen_parent_popup_rows",
        lambda **kwargs: reopen_calls.append(kwargs) or (popup_rows if len(reopen_calls) == 1 else refreshed_rows),
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._activate_row_for_exploration",
        lambda row, popup_rows: None,
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot",
        lambda: [],
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline",
        lambda **kwargs: restore_calls.append(kwargs) or True,
    )

    nodes, _, actions, _, _, _ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        popup_rows=popup_rows,
        visited_paths={("fájl",)},
    )

    assert len(reopen_calls) == 2
    assert restore_calls[0]["stage"] == "post_action:Fájl > [unlabeled row 0]"
    assert nodes[0]["action_state_classification"] == "changes_menu_state"
    assert actions[0].event_details["action_state_classification"] == "changes_menu_state"
    configure_diagnostics(diagnostic_fast_mode=False, placeholder_traversal_focus=False)


def test_explore_menu_tree_open_sample_recent_project_invalidates_stale_refs(monkeypatch):
    from winwatt_automation.runtime_mapping.config import configure_diagnostics
    from winwatt_automation.live_ui.ui_cache import PopupState

    configure_diagnostics(
        diagnostic_fast_mode=False,
        placeholder_traversal_focus=False,
        recent_projects_policy="open_sample_recent_project",
    )

    no_project_snapshot = RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[],
        discovered_top_menus=["Fájl", "Súgó"],
        timestamp="t0",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"title": "WinWatt", "class_name": "TMainForm"},
    )
    project_open_snapshot = RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="WinWatt - Sample Project",
        main_window_class="TMainForm",
        visible_top_windows=[],
        discovered_top_menus=["Fájl", "Eszközök", "Súgó"],
        timestamp="t1",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"title": "WinWatt - Sample Project", "class_name": "TMainForm"},
    )
    project_open_transition_snapshot = RuntimeStateSnapshot(
        state_id="s_project_open_transition",
        process_id=1,
        main_window_title="WinWatt - Sample Project",
        main_window_class="TMainForm",
        visible_top_windows=[],
        discovered_top_menus=["Fájl", "Eszközök", "Súgó"],
        timestamp="t2",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"title": "WinWatt - Sample Project", "class_name": "TMainForm"},
    )
    capture_calls = {"count": 0}

    def _capture_snapshot(state_id: str) -> RuntimeStateSnapshot:
        capture_calls["count"] += 1
        if capture_calls["count"] <= 4:
            return no_project_snapshot
        if capture_calls["count"] == 5:
            return project_open_snapshot
        if capture_calls["count"] == 6:
            return project_open_transition_snapshot
        return project_open_snapshot
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        _capture_snapshot,
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.get_cached_main_window",
        lambda: type("W", (), {"window_text": lambda self: "WinWatt - Sample Project"})(),
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot",
        lambda: [],
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._activate_row_for_exploration",
        lambda row, popup_rows: None,
    )
    popup_state = PopupState(current_menu_path=("fájl",), popup_handle=42, popup_rows=[{"text": "stale"}])
    popup_rows = [
        {
            "text": f"Elem {idx}",
            "center_x": 15,
            "center_y": 15 + idx,
            "rectangle": {"left": 0, "top": 10 + (idx * 20), "right": 100, "bottom": 30 + (idx * 20)},
            "is_separator": False,
            "source_scope": "main_window",
            "popup_candidate": True,
            "topbar_candidate": False,
            "popup_reason": "",
        }
        for idx in range(4)
    ] + [
        {
            "text": "",
            "center_x": 15,
            "center_y": 95,
            "rectangle": {"left": 0, "top": 90, "right": 100, "bottom": 110},
            "is_separator": False,
            "source_scope": "main_window",
            "popup_candidate": True,
            "topbar_candidate": False,
            "popup_reason": "empty_text_vertical_cluster_below_topbar",
        }
    ]

    nodes, _, actions, _, _, _ = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        popup_rows=popup_rows,
        visited_paths={("fájl",)},
        popup_state=popup_state,
    )

    assert nodes[-1]["action_state_classification"] == "opens_project_and_changes_runtime_state"
    assert actions[-1].event_details["action_state_classification"] == "opens_project_and_changes_runtime_state"
    assert popup_state.current_menu_path is None
    assert popup_state.popup_rows is None
    assert popup_state.runtime_state_reset_required is True
    configure_diagnostics(diagnostic_fast_mode=False, placeholder_traversal_focus=False)


def test_recent_project_entries_are_cataloged_not_unknown(monkeypatch):
    from winwatt_automation.runtime_mapping.config import configure_diagnostics

    configure_diagnostics(
        diagnostic_fast_mode=False,
        placeholder_traversal_focus=False,
        recent_projects_policy="skip_recent_projects",
    )
    snapshot = RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[],
        discovered_top_menus=["Fájl", "Súgó"],
        timestamp="t",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"title": "WinWatt", "class_name": "TMainForm"},
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda _state_id: snapshot)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper._is_recent_projects_candidate", lambda **_kwargs: True)
    popup_rows = [
        {
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
        }
    ]

    nodes, _, _actions, _dialogs, _windows, action_catalog = explore_menu_tree(
        state_id="s",
        top_menu="Fájl",
        safe_mode="safe",
        max_depth=2,
        include_disabled=True,
        popup_rows=popup_rows,
        visited_paths={("fájl",)},
    )

    assert nodes[0]["action_state_classification"] == "recent_project_entry"
    assert action_catalog[0]["action_state_classification"] == "recent_project_entry"
    assert action_catalog[0]["skip_reason"] == "recent_project_blocked_by_policy"
    configure_diagnostics(diagnostic_fast_mode=False, placeholder_traversal_focus=False)


def test_safe_depth_policy_blocks_modal_recent_and_command_branches():
    assert _safe_depth_decision(
        state_id="s",
        path=["Fájl", "Megnyitás"],
        current_depth=1,
        max_depth=2,
        action_state_classification="opens_modal",
    ) is False
    assert _safe_depth_decision(
        state_id="s",
        path=["Fájl", "Korábbi projektek", "Minta"],
        current_depth=1,
        max_depth=2,
        action_state_classification="opens_project_and_changes_runtime_state",
    ) is False
    assert _safe_depth_decision(
        state_id="s",
        path=["Súgó", "Névjegy"],
        current_depth=1,
        max_depth=2,
        action_state_classification="executes_command",
    ) is False
    assert _safe_depth_decision(
        state_id="s",
        path=["Ablak", "Nézetek"],
        current_depth=1,
        max_depth=2,
        action_state_classification="opens_submenu",
    ) is True


class _FakeComError(Exception):
    __module__ = "pythoncom"


class _FakeMenuParent:
    def __init__(self, control_type: str):
        self.element_info = type("Info", (), {"control_type": control_type, "name": control_type, "class_name": ""})()


class _FakeMenuItem:
    def __init__(self, name: str, rect: tuple[int, int, int, int], *, parent_mode: str = "ok"):
        self.element_info = type("Info", (), {"name": name, "control_type": "MenuItem", "class_name": "MenuItem", "handle": id(self)})()
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


def test_explore_menu_tree_builds_action_catalog_after_parent_comerror(monkeypatch):
    from winwatt_automation.live_ui import menu_helpers

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Ablak"], timestamp="t"))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda name: None)

    comerror_items = [
        _FakeMenuItem("Fájl", (4, 4, 70, 28), parent_mode="comerror"),
        _FakeMenuItem("Ablak", (71, 4, 150, 28), parent_mode="comerror"),
        _FakeMenuItem("Súgó", (151, 4, 220, 28), parent_mode="comerror"),
    ]
    popup_rows = [
        {"text": "Rendezés", "center_x": 40, "center_y": 70, "rectangle": {"left": 5, "top": 60, "right": 140, "bottom": 82}, "is_separator": False, "source_scope": "main_window", "popup_candidate": True, "topbar_candidate": False},
        {"text": "Mozaik", "center_x": 40, "center_y": 94, "rectangle": {"left": 5, "top": 84, "right": 140, "bottom": 106}, "is_separator": False, "source_scope": "main_window", "popup_candidate": True, "topbar_candidate": False},
    ]

    def _capture():
        menu_helpers._consume_topbar_parent_error_state()
        recovered = menu_helpers._top_level_menu_items_from_items(comerror_items)
        assert any(menu_helpers._normalize(menu_helpers._name(item)) == "ablak" for item in recovered)
        return [dict(row) for row in popup_rows]

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", _capture)

    nodes, rows, actions, dialogs, windows, catalog = explore_menu_tree(
        state_id="s",
        top_menu="Ablak",
        safe_mode="safe",
        max_depth=1,
        include_disabled=True,
    )

    assert [node["title"] for node in nodes] == ["Rendezés", "Mozaik"]
    assert [row.text for row in rows] == ["Rendezés", "Mozaik"]
    assert actions
    assert dialogs == []
    assert windows == []
    assert catalog
    assert catalog[0]["path"] == ["Ablak", "Rendezés"]


def test_build_menu_rows_recovers_text_from_popup_fragments_instead_of_placeholder():
    rows = _build_menu_rows_from_popup_rows(
        "no_project",
        "Fájl",
        [
            {
                "text": "",
                "raw_text_sources": [],
                "text_confidence": "none",
                "center_x": 50,
                "center_y": 15,
                "rectangle": {"left": 0, "top": 10, "right": 120, "bottom": 22},
                "is_separator": False,
                "source_scope": "main",
                "popup_reason": "empty_text_vertical_cluster_below_topbar",
                "popup_candidate": True,
                "topbar_candidate": False,
                "fragments": [
                    {"text": "Projekt", "rectangle": {"left": 8, "top": 10, "right": 50, "bottom": 22}, "center": (29, 16)},
                    {"text": "megnyitása", "rectangle": {"left": 54, "top": 10, "right": 116, "bottom": 22}, "center": (85, 16)},
                ],
            }
        ],
    )

    assert rows[0].text == "Projekt megnyitása"
    assert rows[0].meta.get("source") != "geometry_placeholder"
    assert rows[0].raw_text_sources == ["fragment_merge"]
    assert rows[0].text_confidence == "medium"



def test_grouped_popup_rows_preserve_usable_text_when_uia_name_is_empty():
    grouped = _build_menu_rows_from_popup_rows(
        "no_project",
        "Fájl",
        [
            {
                "text": "Mentés másként",
                "raw_text_sources": ["window_text"],
                "text_confidence": "high",
                "center_x": 50,
                "center_y": 15,
                "rectangle": {"left": 0, "top": 10, "right": 140, "bottom": 24},
                "is_separator": False,
                "source_scope": "main",
                "popup_candidate": True,
                "topbar_candidate": False,
                "fragments": [
                    {"text": "Mentés", "rectangle": {"left": 8, "top": 10, "right": 60, "bottom": 24}, "center": (34, 17)},
                    {"text": "másként", "rectangle": {"left": 64, "top": 10, "right": 132, "bottom": 24}, "center": (98, 17)},
                ],
            }
        ],
    )

    assert grouped[0].text == "Mentés másként"
    assert grouped[0].raw_text_sources == ["window_text"]
    assert grouped[0].text_confidence == "high"


def test_build_menu_rows_does_not_reuse_same_repeated_legacy_text_across_many_popup_rows():
    popup_rows = []
    for index in range(12):
        popup_rows.append(
            {
                "text": "",
                "raw_text_sources": ["legacy_text"],
                "text_confidence": "none",
                "rejected_text_recovery_reason": "repeated_legacy_text",
                "center_x": 50,
                "center_y": 20 + index * 24,
                "rectangle": {"left": 0, "top": 10 + index * 24, "right": 140, "bottom": 32 + index * 24},
                "is_separator": False,
                "source_scope": "main",
                "popup_reason": "below_topbar_band",
                "popup_candidate": True,
                "topbar_candidate": False,
                "fragments": [
                    {
                        "text": "Végrehajtás",
                        "rectangle": {"left": 8, "top": 10 + index * 24, "right": 100, "bottom": 32 + index * 24},
                        "center": (54, 20 + index * 24),
                        "source_scope": "main",
                        "raw_text_sources": ["legacy_text"],
                    }
                ],
            }
        )

    rows = _build_menu_rows_from_popup_rows("no_project", "Fájl", popup_rows)

    assert len(rows) == 12
    assert all(row.text.startswith("[unlabeled row ") for row in rows)
    assert all(row.meta.get("text_confidence") == "none" for row in rows)
    assert all(row.meta.get("raw_text_sources") == ["legacy_text"] for row in rows)


def test_build_menu_rows_prefers_row_local_fragment_merge_over_repeated_legacy_text():
    rows = _build_menu_rows_from_popup_rows(
        "no_project",
        "Fájl",
        [
            {
                "text": "",
                "raw_text_sources": ["legacy_text"],
                "text_confidence": "none",
                "rejected_text_recovery_reason": "repeated_legacy_text",
                "center_x": 50,
                "center_y": 15,
                "rectangle": {"left": 0, "top": 10, "right": 160, "bottom": 30},
                "is_separator": False,
                "source_scope": "main",
                "popup_reason": "below_topbar_band",
                "popup_candidate": True,
                "topbar_candidate": False,
                "fragments": [
                    {"text": "Projekt", "rectangle": {"left": 8, "top": 10, "right": 54, "bottom": 30}, "center": (31, 20), "source_scope": "child_text"},
                    {"text": "megnyitása", "rectangle": {"left": 58, "top": 10, "right": 148, "bottom": 30}, "center": (103, 20), "source_scope": "child_text"},
                    {"text": "Végrehajtás", "rectangle": {"left": 8, "top": 10, "right": 100, "bottom": 30}, "center": (54, 20), "source_scope": "main", "raw_text_sources": ["legacy_text"]},
                ],
            }
        ],
    )

    assert rows[0].text == "Projekt megnyitása"
    assert rows[0].raw_text_sources == ["legacy_text", "fragment_merge"]
    assert rows[0].text_confidence == "medium"


def test_map_runtime_state_retains_selected_top_menus_after_runtime_reset(monkeypatch):
    snapshots = iter([
        RuntimeStateSnapshot(state_id="s", process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl", "Jegyzékek"], timestamp="t1"),
        RuntimeStateSnapshot(state_id="s", process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=[], timestamp="t2"),
    ])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: next(snapshots))

    def _explore_menu_tree(**kwargs):
        kwargs["popup_state"].runtime_state_reset_required = True
        return ([], [], [], [], [], [])

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.explore_menu_tree", _explore_menu_tree)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)

    state = map_runtime_state(state_id="s", top_menus=["Fájl", "Jegyzékek"])

    assert [item["text"] for item in state.top_menus] == ["Fájl", "Jegyzékek"]
    assert state.state_atlas["canonical_top_menus"] == state.top_menus


def test_map_runtime_state_keeps_placeholder_rows_and_actions_in_state_atlas(monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Fájl"], timestamp="t"))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda _: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)

    snapshots = iter([
        [
            {
                "text": "",
                "center_x": 20,
                "center_y": 20,
                "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
                "is_separator": False,
                "source_scope": "global_process_scan",
                "popup_candidate": True,
                "topbar_candidate": False,
                "popup_reason": "below_topbar_band",
                "recent_project_entry": True,
                "stateful_menu_block": True,
            }
        ],
        [],
    ])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))

    state = map_runtime_state(state_id="no_project", top_menus=["Fájl"], max_submenu_depth=1)

    assert len(state.top_menus) == 1
    assert len(state.menu_rows) == 1
    assert len(state.action_catalog) == 0
    assert state.menu_rows[0]["text"] == "[unlabeled row 0]"
    assert state.menu_rows[0]["retained_as_structure_only"] is True
    assert state.menu_rows[0]["admitted_to_action_catalog"] is False
    assert state.menu_rows[0]["rejection_reason"] == "placeholder_without_state_change"
    assert state.state_atlas["canonical_top_menus"][0]["text"] == "Fájl"
    assert len(state.state_atlas["top_menu_rows"]) == 1
    assert len(state.state_atlas["action_catalog"]) == 0


def test_build_menu_rows_preserves_placeholder_rows_after_repeated_legacy_rejection():
    rows = _build_menu_rows_from_popup_rows(
        "project_open",
        "Fájl",
        [
            {
                "text": "",
                "center_x": 20,
                "center_y": 20,
                "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
                "is_separator": False,
                "source_scope": "global_process_scan",
                "popup_candidate": True,
                "topbar_candidate": False,
                "popup_reason": "below_topbar_band",
                "recent_projects_block": True,
                "recent_project_entry": True,
                "stateful_menu_block": True,
            }
        ],
    )

    assert len(rows) == 1
    assert rows[0].text == "[unlabeled row 0]"
    assert rows[0].actionable is True
    assert rows[0].recent_project_entry is True
    assert rows[0].stateful_menu_block is True


def test_placeholder_row_retained_but_not_admitted_to_action_catalog(monkeypatch):
    snapshot = RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[],
        discovered_top_menus=["Jegyzékek"],
        timestamp="t",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"title": "WinWatt", "class_name": "TMainForm"},
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda _state_id: snapshot)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: [])

    rows = [{
        "text": "",
        "center_x": 15,
        "center_y": 20,
        "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
        "is_separator": False,
        "source_scope": "main_window",
        "popup_candidate": True,
        "topbar_candidate": False,
        "popup_reason": "below_topbar_band",
    }]

    nodes, retained_rows, _actions, _dialogs, _windows, action_catalog = explore_menu_tree(
        state_id="s",
        top_menu="Jegyzékek",
        safe_mode="safe",
        max_depth=1,
        include_disabled=True,
        popup_rows=rows,
        visited_paths={("jegyzékek",)},
    )

    assert len(nodes) == 1
    assert len(retained_rows) == 1
    assert retained_rows[0].retained_as_structure_only is True
    assert retained_rows[0].admitted_to_action_catalog is False
    assert retained_rows[0].rejection_reason == "placeholder_without_state_change"
    assert action_catalog == []


def test_legacy_text_only_low_confidence_row_stays_structure_only(monkeypatch):
    snapshot = RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[],
        discovered_top_menus=["Jegyzékek"],
        timestamp="t",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"title": "WinWatt", "class_name": "TMainForm"},
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda _state_id: snapshot)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: [])

    rows = [{
        "text": "Végrehajtás",
        "center_x": 15,
        "center_y": 20,
        "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
        "is_separator": False,
        "source_scope": "main_window",
        "popup_candidate": True,
        "topbar_candidate": False,
        "raw_text_sources": ["legacy_text"],
        "text_confidence": "low",
        "enabled_guess": None,
    }]

    _nodes, retained_rows, _actions, _dialogs, _windows, action_catalog = explore_menu_tree(
        state_id="s",
        top_menu="Jegyzékek",
        safe_mode="safe",
        max_depth=1,
        include_disabled=True,
        popup_rows=rows,
        visited_paths={("jegyzékek",)},
    )

    assert retained_rows[0].retained_as_structure_only is True
    assert retained_rows[0].admitted_to_action_catalog is False
    assert retained_rows[0].rejection_reason == "text_confidence_low_without_interaction_evidence"
    assert action_catalog == []


def test_unknown_classification_is_suppressed_from_action_catalog():
    rows = _build_menu_rows_from_popup_rows(
        "s",
        "Jegyzékek",
        [{
            "text": "Végrehajtás",
            "center_x": 15,
            "center_y": 20,
            "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
            "is_separator": False,
            "source_scope": "main_window",
            "popup_candidate": True,
            "topbar_candidate": False,
            "enabled_guess": None,
        }],
    )

    admitted, admission_reason, rejection_reason = _evaluate_action_admission(
        row=rows[0],
        path=["Jegyzékek", "Végrehajtás"],
        action_state_classification="unknown",
        transition={"result_type": "suppressed_pending_validation", "attempted": True},
        opens_submenu=False,
        opens_modal=False,
        skip_reason=None,
        traversal_depth=1,
    )

    assert admitted is False
    assert admission_reason is None
    assert rejection_reason == "unknown_classification_suppressed"


def test_no_visible_change_row_is_not_admitted_action(monkeypatch):
    snapshot = RuntimeStateSnapshot(
        state_id="s",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[],
        discovered_top_menus=["Jegyzékek"],
        timestamp="t",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"title": "WinWatt", "class_name": "TMainForm"},
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda _state_id: snapshot)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: [])

    rows = [{
        "text": "Lista",
        "center_x": 15,
        "center_y": 20,
        "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
        "is_separator": False,
        "source_scope": "main_window",
        "popup_candidate": True,
        "topbar_candidate": False,
        "enabled_guess": None,
        "raw_text_sources": ["uia_name"],
        "text_confidence": "high",
    }]

    _nodes, retained_rows, _actions, _dialogs, _windows, action_catalog = explore_menu_tree(
        state_id="s",
        top_menu="Jegyzékek",
        safe_mode="safe",
        max_depth=1,
        include_disabled=True,
        popup_rows=rows,
        visited_paths={("jegyzékek",)},
    )

    assert retained_rows[0].retained_as_structure_only is True
    assert retained_rows[0].admitted_to_action_catalog is False
    assert retained_rows[0].rejection_reason == "no_visible_change_without_interaction_evidence"
    assert action_catalog == []


def test_action_count_drops_while_row_retention_remains(monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: RuntimeStateSnapshot(state_id=state_id, process_id=1, main_window_title="W", main_window_class="C", visible_top_windows=[], discovered_top_menus=["Jegyzékek"], timestamp="t", main_window_enabled=True, main_window_visible=True, foreground_window={"title": "W", "class_name": "C"}))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.click_top_menu_item", lambda _: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)
    snapshots = iter([
        [
            {
                "text": "",
                "center_x": 20,
                "center_y": 20,
                "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30},
                "is_separator": False,
                "source_scope": "global_process_scan",
                "popup_candidate": True,
                "topbar_candidate": False,
                "popup_reason": "below_topbar_band",
            },
            {
                "text": "Végrehajtás",
                "center_x": 20,
                "center_y": 40,
                "rectangle": {"left": 0, "top": 30, "right": 100, "bottom": 50},
                "is_separator": False,
                "source_scope": "global_process_scan",
                "popup_candidate": True,
                "topbar_candidate": False,
                "raw_text_sources": ["legacy_text"],
                "text_confidence": "low",
                "enabled_guess": None,
            },
        ],
        [],
    ])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: next(snapshots, []))

    state = map_runtime_state(state_id="s", top_menus=["Jegyzékek"], max_submenu_depth=1)

    assert len(state.menu_rows) == 2
    assert len(state.action_catalog) == 0
    assert all(row["retained_as_structure_only"] for row in state.menu_rows)


def test_legacy_text_only_row_probe_is_admitted_when_child_popup_opens(monkeypatch):
    before = RuntimeStateSnapshot(state_id="s", process_id=1, main_window_title="WinWatt", main_window_class="TMainForm", visible_top_windows=[], discovered_top_menus=["Jegyzékek"], timestamp="t", main_window_enabled=True, main_window_visible=True, foreground_window={"title": "WinWatt", "class_name": "TMainForm"})
    after = RuntimeStateSnapshot(state_id="s", process_id=1, main_window_title="WinWatt", main_window_class="TMainForm", visible_top_windows=[], discovered_top_menus=["Jegyzékek"], timestamp="t2", main_window_enabled=True, main_window_visible=True, foreground_window={"title": "WinWatt", "class_name": "TMainForm"})
    rows = _build_menu_rows_from_popup_rows("s", "Jegyzékek", [{"text": "Végrehajtás", "center_x": 15, "center_y": 20, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30}, "is_separator": False, "source_scope": "main_window", "popup_candidate": True, "topbar_candidate": False, "raw_text_sources": ["legacy_text"], "text_confidence": "low", "enabled_guess": None}])
    snapshots = iter([before, after])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda _state_id: next(snapshots))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper._activate_row_for_exploration", lambda row, popup_rows: None)
    before_popup = [{"text": "Végrehajtás", "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30}, "is_separator": False}]
    after_popup = before_popup + [{"text": "Almenü", "rectangle": {"left": 120, "top": 10, "right": 220, "bottom": 30}, "is_separator": False}]
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: after_popup)
    evidence = _run_action_evidence_probe(state_id="s", top_menu="Jegyzékek", path=["Jegyzékek", "Végrehajtás"], row=rows[0], popup_rows=before_popup, current_rows=before_popup)
    admitted, reason, rejected = _evaluate_action_admission(row=rows[0], path=["Jegyzékek", "Végrehajtás"], action_state_classification="unknown", transition={"result_type": evidence["result_type"], "attempted": True}, opens_submenu=False, opens_modal=False, skip_reason=None, traversal_depth=1, probe_evidence=evidence)
    assert evidence["result_type"] == "child_popup_opened"
    assert admitted is True
    assert reason == "interaction_evidence:child_popup_opened"
    assert rejected is None


def test_placeholder_row_probe_is_admitted_when_dialog_opens():
    row = _build_menu_rows_from_popup_rows("s", "Jegyzékek", [{"text": "", "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30}, "is_separator": False, "source_scope": "main_window", "popup_candidate": True, "topbar_candidate": False, "popup_reason": "empty_text_vertical_cluster_below_topbar"}])[0]
    admitted, reason, rejected = _evaluate_action_admission(row=row, path=row.menu_path, action_state_classification="unknown", transition={"result_type": "dialog_opened", "attempted": True}, opens_submenu=False, opens_modal=False, skip_reason=None, traversal_depth=1, probe_evidence={"result_type": "dialog_opened", "new_dialog_detected": True, "evidence_strength": "strong"})
    assert admitted is True
    assert reason == "interaction_evidence:dialog_opened"
    assert rejected is None


def test_placeholder_row_stays_structure_only_when_probe_has_no_observable_effect():
    row = _build_menu_rows_from_popup_rows("s", "Jegyzékek", [{"text": "", "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30}, "is_separator": False, "source_scope": "main_window", "popup_candidate": True, "topbar_candidate": False, "popup_reason": "empty_text_vertical_cluster_below_topbar"}])[0]
    admitted, reason, rejected = _evaluate_action_admission(row=row, path=row.menu_path, action_state_classification="unknown", transition={"result_type": "no_observable_effect", "attempted": True}, opens_submenu=False, opens_modal=False, skip_reason=None, traversal_depth=1, probe_evidence={"result_type": "no_observable_effect", "evidence_strength": "none"})
    assert admitted is False
    assert reason is None
    assert rejected == "placeholder_without_state_change"


def test_click_failed_focus_guard_is_not_admission_evidence():
    row = _build_menu_rows_from_popup_rows("s", "Jegyzékek", [{"text": "Lista", "center_x": 15, "center_y": 20, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30}, "is_separator": False, "source_scope": "main_window", "popup_candidate": True, "topbar_candidate": False, "enabled_guess": None, "raw_text_sources": ["uia_name"], "text_confidence": "high"}])[0]
    admitted, reason, rejected = _evaluate_action_admission(row=row, path=row.menu_path, action_state_classification="unknown", transition={"result_type": "click_failed_focus_guard", "attempted": True}, opens_submenu=False, opens_modal=False, skip_reason=None, traversal_depth=1, probe_evidence={"result_type": "click_failed_focus_guard", "click_exception": "RuntimeError: focus lost", "evidence_strength": "weak"})
    assert admitted is False
    assert reason is None
    assert rejected == "unknown_classification_suppressed"


def test_output_summary_reports_probe_counters(monkeypatch):
    snapshot = RuntimeStateSnapshot(state_id="s", process_id=1, main_window_title="WinWatt", main_window_class="TMainForm", visible_top_windows=[], discovered_top_menus=["Jegyzékek"], timestamp="t", main_window_enabled=True, main_window_visible=True, foreground_window={"title": "WinWatt", "class_name": "TMainForm"})
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda _state_id: snapshot)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper._run_action_evidence_probe", lambda **kwargs: {"result_type": "no_observable_effect", "evidence_strength": "none"})
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: [])
    messages = []
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.logger.info", lambda message, *args: messages.append(message.format(*args)))
    explore_menu_tree(state_id="s", top_menu="Jegyzékek", safe_mode="safe", max_depth=1, include_disabled=True, popup_rows=[{"text": "", "center_x": 15, "center_y": 20, "rectangle": {"left": 0, "top": 10, "right": 100, "bottom": 30}, "is_separator": False, "source_scope": "main_window", "popup_candidate": True, "topbar_candidate": False, "popup_reason": "below_topbar_band"}], visited_paths={("jegyzékek",)})
    summary = next(message for message in messages if message.startswith("ACTION_CATALOG_OUTPUT_SUMMARY"))
    assert "candidate_rows=1" in summary
    assert "probed_rows=1" in summary
    assert "admitted_after_probe=0" in summary
    assert "still_structure_only=1" in summary


def test_run_single_row_probe_detects_dialog_open(monkeypatch):
    popup_rows = [
        {
            "text": "Megnyitás",
            "center_x": 25,
            "center_y": 35,
            "rectangle": {"left": 10, "top": 20, "right": 40, "bottom": 50},
            "is_separator": False,
            "source_scope": "main",
            "popup_candidate": True,
            "topbar_candidate": False,
        }
    ]
    before_snapshot = RuntimeStateSnapshot(
        state_id="probe",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[{"handle": 1, "title": "WinWatt", "class_name": "TMainForm", "process_id": 1}],
        discovered_top_menus=["Fájl"],
        timestamp="t1",
        main_window_enabled=True,
        main_window_visible=True,
        foreground_window={"handle": 1, "title": "WinWatt", "class_name": "TMainForm", "process_id": 1},
    )
    after_snapshot = RuntimeStateSnapshot(
        state_id="probe",
        process_id=1,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=[
            {"handle": 1, "title": "WinWatt", "class_name": "TMainForm", "process_id": 1},
            {"handle": 2, "title": "Megnyitás", "class_name": "#32770", "process_id": 1},
        ],
        discovered_top_menus=["Fájl"],
        timestamp="t2",
        main_window_enabled=False,
        main_window_visible=True,
        foreground_window={"handle": 2, "title": "Megnyitás", "class_name": "#32770", "process_id": 1},
    )
    snapshots = iter([before_snapshot, before_snapshot, after_snapshot])

    class _Window:
        def children(self):
            return [object()]

        def descendants(self):
            return [object(), object()]

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: next(snapshots))
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.get_cached_main_window", lambda: _Window())
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.get_canonical_top_menu_names",
        lambda discovered: {"normalized_to_raw": {"fájl": "Fájl"}, "normalized_names": {"fájl"}, "items": [{"raw": "Fájl"}]},
    )
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._open_and_capture_root_menu",
        lambda **kwargs: (popup_rows, {"result_type": "child_popup_opened"}),
    )
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.menu_helpers.capture_menu_popup_snapshot", lambda: [])
    activated: list[str] = []
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper._activate_row_for_exploration",
        lambda row, popup_rows: activated.append(row.text),
    )

    result = run_single_row_probe(
        state_id="probe",
        top_menu="Fájl",
        probe_row_text="Megnyitás",
    )

    assert activated == ["Megnyitás"]
    assert result["final_classification"] == "dialog_opened"
    assert result["summary"]["provable_change"] is True
    assert result["summary"]["action_like"] is True

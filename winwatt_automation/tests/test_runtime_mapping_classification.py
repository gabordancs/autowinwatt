from __future__ import annotations

from winwatt_automation.runtime_mapping.models import RuntimeStateSnapshot
from winwatt_automation.runtime_mapping.program_mapper import _build_menu_rows_from_popup_rows, classify_post_click_result


def _snapshot(*, title: str = "WinWatt", windows: int = 1) -> RuntimeStateSnapshot:
    return RuntimeStateSnapshot(
        state_id="state_no_project",
        process_id=123,
        main_window_title=title,
        main_window_class="TMainForm",
        visible_top_windows=[{"title": f"win-{idx}"} for idx in range(windows)],
        discovered_top_menus=["Fájl"],
        timestamp="2026-01-01T00:00:00+00:00",
    )


def test_classify_post_click_result_dialog_opened():
    result = classify_post_click_result(
        process_id=123,
        before_snapshot=_snapshot(),
        after_snapshot=_snapshot(),
        dialog_detection={"dialog_detected": True, "dialog_title": "Megnyitás", "dialog_class": "#32770"},
        state_id="state_no_project",
        top_menu="Fájl",
        row_index=0,
        menu_path=["Fájl", "Megnyitás"],
        action_key="Fájl > Megnyitás",
        safety_level="safe",
        attempted=True,
    )
    assert result.result_type == "dialog_opened"


def test_classify_post_click_result_no_visible_change():
    result = classify_post_click_result(
        process_id=123,
        before_snapshot=_snapshot(),
        after_snapshot=_snapshot(),
        dialog_detection=None,
        state_id="state_no_project",
        top_menu="Nézet",
        row_index=2,
        menu_path=["Nézet", "Rács"],
        action_key="Nézet > Rács",
        safety_level="safe",
        attempted=True,
    )
    assert result.result_type == "no_observable_effect"


def test_classify_post_click_result_skipped_and_failed():
    skipped = classify_post_click_result(
        process_id=None,
        before_snapshot=_snapshot(),
        after_snapshot=_snapshot(),
        dialog_detection=None,
        state_id="state_no_project",
        top_menu="Fájl",
        row_index=10,
        menu_path=["Fájl", "Kilépés"],
        action_key="Fájl > Kilépés",
        safety_level="blocked",
        attempted=False,
    )
    failed = classify_post_click_result(
        process_id=None,
        before_snapshot=_snapshot(),
        after_snapshot=_snapshot(),
        dialog_detection=None,
        state_id="state_no_project",
        top_menu="Fájl",
        row_index=3,
        menu_path=["Fájl", "Nem létezik"],
        action_key="Fájl > Nem létezik",
        safety_level="safe",
        attempted=True,
        error_text="click failed",
    )
    assert skipped.result_type == "failed"
    assert failed.result_type == "failed"


def test_build_menu_rows_from_popup_rows_preserves_order_and_indices():
    rows = _build_menu_rows_from_popup_rows(
        "state_no_project",
        "Fájl",
        [
            {
                "text": "Megnyitás",
                "rectangle": {"left": 0, "top": 10, "right": 10, "bottom": 20},
                "center_x": 5,
                "center_y": 15,
                "is_separator": False,
                "source_scope": "main_window",
                "fragments": [],
            },
            {
                "text": "",
                "rectangle": {"left": 0, "top": 21, "right": 10, "bottom": 22},
                "center_x": 5,
                "center_y": 21,
                "is_separator": True,
                "source_scope": "main_window",
                "fragments": [],
            },
        ],
    )
    assert [row.row_index for row in rows] == [0, 1]
    assert rows[0].menu_path == ["Fájl", "Megnyitás"]
    assert rows[1].is_separator is True



def test_classify_post_click_result_forced_failure_types():
    result = classify_post_click_result(
        process_id=None,
        before_snapshot=_snapshot(),
        after_snapshot=_snapshot(),
        dialog_detection=None,
        state_id="state_no_project",
        top_menu="Fájl",
        row_index=0,
        menu_path=["Fájl"],
        action_key="Fájl",
        safety_level="safe",
        attempted=False,
        forced_result_type="failed_system_menu",
    )
    assert result.result_type == "failed_system_menu"


def test_build_menu_rows_geometry_placeholder_uses_rect_center_for_empty_popup_rows():
    rows = _build_menu_rows_from_popup_rows(
        "state_no_project",
        "Fájl",
        [
            {
                "text": "",
                "rectangle": {"left": 10, "top": 20, "right": 30, "bottom": 50},
                "is_separator": False,
                "source_scope": "main_window",
                "fragments": [],
                "popup_candidate": True,
                "topbar_candidate": False,
                "popup_reason": "empty_text_vertical_cluster_below_topbar",
            },
        ],
    )
    assert rows[0].text == "[unlabeled row 0]"
    assert rows[0].center_x == 20
    assert rows[0].center_y == 35
    assert rows[0].meta["click_point"] == {"x": 20, "y": 35}
    assert rows[0].menu_path == ["Fájl", "[unlabeled row 0]"]

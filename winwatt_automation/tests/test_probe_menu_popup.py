from __future__ import annotations

from winwatt_automation.scripts import probe_menu_popup


def _row(index: int, left: int, top: int, right: int, bottom: int, *, text: str = "", is_separator: bool = False):
    return {
        "index": index,
        "text": text,
        "normalized_text": text.strip().lower(),
        "control_type": "MenuItem",
        "class_name": "TMenuItem",
        "rectangle": {"left": left, "top": top, "right": right, "bottom": bottom},
        "center_x": int((left + right) / 2),
        "center_y": int((top + bottom) / 2),
        "is_separator": is_separator,
        "source_scope": "main_window",
        "popup_candidate": True,
        "topbar_candidate": False,
        "popup_reason": "below_topbar_band",
    }


def test_classify_probe_row_prefers_separator_and_empty_hover_reactive():
    separator = _row(0, 10, 10, 200, 12, is_separator=True)
    reactive_empty = _row(1, 10, 20, 200, 42, text="")

    assert probe_menu_popup.classify_probe_row(separator, {"structure_changed": False, "active_row_changed": False, "submenu_detected": False}) == "separator"
    assert (
        probe_menu_popup.classify_probe_row(
            reactive_empty,
            {"structure_changed": True, "active_row_changed": True, "submenu_detected": False},
        )
        == "empty_but_hover_reactive"
    )


def test_classify_probe_row_keeps_empty_popup_candidate_out_of_inert():
    geometry_candidate = _row(2, 10, 44, 220, 66, text="")

    assert (
        probe_menu_popup.classify_probe_row(
            geometry_candidate,
            {"structure_changed": False, "active_row_changed": False, "submenu_detected": False},
        )
        == "geometry_actionable_candidate"
    )


def test_hover_diff_detects_submenu_spawn_to_the_right(monkeypatch):
    parent = _row(0, 10, 50, 150, 72, text="Jegyzék")
    after_rows = [
        _row(0, 10, 50, 150, 72, text="Jegyzék"),
        _row(0, 170, 48, 310, 70, text="Almenü 1"),
        _row(1, 170, 70, 310, 92, text="Almenü 2"),
    ]
    monkeypatch.setattr(
        probe_menu_popup,
        "_structured_popup_rows_from_snapshots",
        lambda before, after: after[1:],
    )

    result = probe_menu_popup._hover_diff_result(parent, [parent], after_rows)

    assert result["submenu_detected"] is True
    assert result["popup_rows_changed"] is True
    assert len(result["submenu_rows"]) == 2


def test_empty_hover_reactive_row_is_retained_in_summary(monkeypatch):
    row = _row(0, 10, 50, 160, 72, text="")
    monkeypatch.setattr(probe_menu_popup, "connect_to_winwatt", lambda: None)
    monkeypatch.setattr(probe_menu_popup, "prepare_main_window_for_menu_interaction", lambda: None)
    monkeypatch.setattr(
        probe_menu_popup,
        "open_top_menu_and_capture_popup_state",
        lambda top_menu: {"rows": [row], "popup_open": True, "status": "success_popup_opened", "click_mode": "object"},
    )
    snapshots = iter([[row], [row]])
    monkeypatch.setattr(probe_menu_popup, "capture_menu_popup_snapshot", lambda: next(snapshots))
    monkeypatch.setattr(probe_menu_popup, "_hover_row", lambda hovered: None)
    monkeypatch.setattr(
        probe_menu_popup,
        "_hover_diff_result",
        lambda hovered, before, after: {
            "structure_changed": True,
            "submenu_detected": False,
            "submenu_rows": [],
            "popup_disappeared": False,
            "popup_row_count_before": 1,
            "popup_row_count_after": 1,
            "popup_rows_changed": False,
            "active_row_changed": True,
            "hovered_row_present_after": True,
        },
    )

    summary = probe_menu_popup.probe_top_menu_popup("Fájl")

    assert summary["candidate_row_count"] == 1
    assert summary["empty_hover_rows"] == [0]
    assert summary["classified_rows"][0]["raw_text"] == ""
    assert summary["classified_rows"][0]["classification"] == "empty_but_hover_reactive"


def test_probe_summary_reports_geometry_candidates_and_geometry_accepted_rows(monkeypatch):
    row = _row(0, 4, 56, 932, 84, text="")
    row["popup_reason"] = "empty_text_vertical_cluster_below_topbar"
    monkeypatch.setattr(probe_menu_popup, "connect_to_winwatt", lambda: None)
    monkeypatch.setattr(probe_menu_popup, "prepare_main_window_for_menu_interaction", lambda: None)
    monkeypatch.setattr(
        probe_menu_popup,
        "open_top_menu_and_capture_popup_state",
        lambda top_menu: {"rows": [row], "popup_open": True, "status": "success_popup_opened", "click_mode": "object"},
    )
    snapshots = iter([[row], [row]])
    monkeypatch.setattr(probe_menu_popup, "capture_menu_popup_snapshot", lambda: next(snapshots))
    monkeypatch.setattr(probe_menu_popup, "_hover_row", lambda hovered: None)
    monkeypatch.setattr(
        probe_menu_popup,
        "_hover_diff_result",
        lambda hovered, before, after: {
            "structure_changed": False,
            "submenu_detected": False,
            "submenu_rows": [],
            "popup_disappeared": False,
            "popup_row_count_before": 1,
            "popup_row_count_after": 1,
            "popup_rows_changed": False,
            "active_row_changed": False,
            "hovered_row_present_after": True,
        },
    )

    summary = probe_menu_popup.probe_top_menu_popup("Fájl")

    assert summary["geometry_candidate_rows"] == [0]
    assert summary["popup_rows_accepted_by_geometry"] == [0]
    assert summary["inert_rows"] == []
    assert summary["classified_rows"][0]["classification"] == "geometry_actionable_candidate"

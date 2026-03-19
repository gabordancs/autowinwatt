"""Diagnostic probe for WinWatt top-menu popups using geometry and hover-state diffs."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from loguru import logger

from winwatt_automation.live_ui.app_connector import connect_to_winwatt, prepare_main_window_for_menu_interaction
from winwatt_automation.live_ui.menu_helpers import (
    _structured_popup_rows_from_snapshots,
    capture_menu_popup_snapshot,
    click_structured_popup_row,
    open_top_menu_and_capture_popup_state,
    wait_for_popup_to_close,
)
from winwatt_automation.runtime_mapping.program_mapper import _hover_row
from winwatt_automation.runtime_mapping.safety import is_action_allowed
from winwatt_automation.runtime_mapping.timing import DEFAULT_UI_DELAY


def _rect_key(rect: dict[str, Any] | None) -> tuple[int, int, int, int]:
    rect = rect or {}
    return (
        int(rect.get("left", 0)),
        int(rect.get("top", 0)),
        int(rect.get("right", 0)),
        int(rect.get("bottom", 0)),
    )


def _snapshot_signature(rows: list[dict[str, Any]]) -> set[tuple[str, str, str, tuple[int, int, int, int], str]]:
    return {
        (
            str(row.get("normalized_text") or ""),
            str(row.get("control_type") or ""),
            str(row.get("class_name") or ""),
            _rect_key(row.get("rectangle")),
            str(row.get("source_scope") or ""),
        )
        for row in rows
    }


def _popup_rect(rows: list[dict[str, Any]]) -> dict[str, int] | None:
    if not rows:
        return None
    left = min(_rect_key(row.get("rectangle"))[0] for row in rows)
    top = min(_rect_key(row.get("rectangle"))[1] for row in rows)
    right = max(_rect_key(row.get("rectangle"))[2] for row in rows)
    bottom = max(_rect_key(row.get("rectangle"))[3] for row in rows)
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def _match_row_by_rect(rows: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, Any] | None:
    wanted = _rect_key(target.get("rectangle"))
    for row in rows:
        if _rect_key(row.get("rectangle")) == wanted:
            return row
    return None


def _detect_submenu_rows(parent_row: dict[str, Any], before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spawned = _structured_popup_rows_from_snapshots(before_rows, after_rows)
    if not spawned:
        return []
    parent_rect = parent_row.get("rectangle") or {}
    parent_right = int(parent_rect.get("right", 0))
    parent_top = int(parent_rect.get("top", 0))
    parent_bottom = int(parent_rect.get("bottom", 0))
    matches = []
    for row in spawned:
        rect = row.get("rectangle") or {}
        if int(rect.get("left", 0)) <= parent_right + 8:
            continue
        if int(rect.get("top", 0)) < parent_top - 120:
            continue
        if int(rect.get("top", 0)) > parent_bottom + 220:
            continue
        matches.append(row)
    return sorted(matches, key=lambda item: (_rect_key(item.get("rectangle"))[1], _rect_key(item.get("rectangle"))[0]))


def _hover_diff_result(row: dict[str, Any], before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_sig = _snapshot_signature(before_rows)
    after_sig = _snapshot_signature(after_rows)
    submenu_rows = _detect_submenu_rows(row, before_rows, after_rows)
    popup_disappeared = bool(before_rows) and not after_rows
    structure_changed = before_sig != after_sig
    hovered_row_after = _match_row_by_rect(after_rows, row)
    rows_changed = len(before_rows) != len(after_rows)
    active_changed = structure_changed or hovered_row_after is None or bool(submenu_rows)
    return {
        "structure_changed": structure_changed,
        "submenu_detected": bool(submenu_rows),
        "submenu_rows": submenu_rows,
        "popup_disappeared": popup_disappeared,
        "popup_row_count_before": len(before_rows),
        "popup_row_count_after": len(after_rows),
        "popup_rows_changed": rows_changed,
        "active_row_changed": active_changed,
        "hovered_row_present_after": hovered_row_after is not None,
    }


def classify_probe_row(row: dict[str, Any], hover_result: dict[str, Any], click_result: dict[str, Any] | None = None) -> str:
    text = str(row.get("normalized_text") or "")
    if bool(row.get("is_separator")):
        return "separator"
    if hover_result.get("submenu_detected") and not text:
        return "empty_but_submenu_spawning"
    if hover_result.get("submenu_detected"):
        return "submenu"
    if not text and (hover_result.get("structure_changed") or hover_result.get("active_row_changed")):
        return "empty_but_hover_reactive"
    if click_result and click_result.get("popup_closed"):
        return "actionable"
    if not hover_result.get("structure_changed") and not click_result:
        return "inert"
    return "unknown"


def _safe_click_probe(top_menu: str, row: dict[str, Any]) -> dict[str, Any]:
    normalized_text = str(row.get("normalized_text") or "")
    if not normalized_text:
        return {"attempted": False, "reason": "missing_text"}
    if not is_action_allowed([top_menu, str(row.get("text") or "")], mode="safe"):
        return {"attempted": False, "reason": "blocked_by_safe_mode"}

    open_state = open_top_menu_and_capture_popup_state(top_menu)
    probe_rows = list(open_state.get("rows") or [])
    if not probe_rows:
        return {"attempted": False, "reason": "reopen_failed"}

    matching_index = next((idx for idx, candidate in enumerate(probe_rows) if _rect_key(candidate.get("rectangle")) == _rect_key(row.get("rectangle"))), None)
    if matching_index is None:
        return {"attempted": False, "reason": "row_not_found_after_reopen"}

    before_click = capture_menu_popup_snapshot()
    click_structured_popup_row(probe_rows, matching_index)
    time.sleep(max(0.05, DEFAULT_UI_DELAY))
    closed = wait_for_popup_to_close(timeout=max(0.2, DEFAULT_UI_DELAY * 2), poll_interval=max(0.05, DEFAULT_UI_DELAY / 2))
    after_click = [] if closed else capture_menu_popup_snapshot()
    return {
        "attempted": True,
        "row_index": matching_index,
        "popup_closed": closed,
        "before_row_count": len(before_click),
        "after_row_count": len(after_click),
    }


def probe_top_menu_popup(top_menu: str, *, allow_safe_click: bool = False, hover_pause_s: float = 0.15) -> dict[str, Any]:
    logger.info("DBG_MENU_PROBE_START top_menu={} allow_safe_click={}", top_menu, allow_safe_click)
    connect_to_winwatt()
    prepare_main_window_for_menu_interaction()
    open_state = open_top_menu_and_capture_popup_state(top_menu)
    rows = list(open_state.get("rows") or [])
    popup_rect = _popup_rect(rows)
    logger.info(
        "DBG_MENU_PROBE_POPUP_OPENED top_menu={} popup_detected={} popup_rect={} candidate_row_count={} status={} click_mode={}",
        top_menu,
        bool(open_state.get("popup_open")),
        popup_rect,
        len(rows),
        open_state.get("status"),
        open_state.get("click_mode"),
    )

    classified_rows: list[dict[str, Any]] = []
    for row in rows:
        row_payload = {
            "row_index": int(row.get("index", len(classified_rows))),
            "rect": dict(row.get("rectangle") or {}),
            "raw_text": str(row.get("text") or ""),
            "normalized_text": str(row.get("normalized_text") or ""),
            "source_scope": row.get("source_scope"),
            "control_type": row.get("control_type"),
            "class_name": row.get("class_name"),
            "popup_reason": row.get("popup_reason"),
            "topbar_like": bool(row.get("topbar_candidate")),
            "popup_like": bool(row.get("popup_candidate")),
        }
        logger.info("DBG_MENU_PROBE_ROW top_menu={} payload={}", top_menu, row_payload)

        hover_before = capture_menu_popup_snapshot()
        logger.info("DBG_MENU_PROBE_HOVER_BEFORE top_menu={} row_index={} popup_row_count={} popup_rect={}", top_menu, row_payload["row_index"], len(hover_before), _popup_rect(hover_before))
        _hover_row(row)
        time.sleep(max(0.05, hover_pause_s))
        hover_after = capture_menu_popup_snapshot()
        logger.info("DBG_MENU_PROBE_HOVER_AFTER top_menu={} row_index={} popup_row_count={} popup_rect={}", top_menu, row_payload["row_index"], len(hover_after), _popup_rect(hover_after))
        hover_result = _hover_diff_result(row, hover_before, hover_after)
        logger.info("DBG_MENU_PROBE_HOVER_RESULT top_menu={} row_index={} result={}", top_menu, row_payload["row_index"], hover_result)
        if hover_result["submenu_detected"]:
            logger.info(
                "DBG_MENU_PROBE_SUBMENU_DETECTED top_menu={} row_index={} submenu_rows={}",
                top_menu,
                row_payload["row_index"],
                [
                    {
                        "index": item.get("index"),
                        "text": item.get("text"),
                        "rect": item.get("rectangle"),
                    }
                    for item in hover_result["submenu_rows"]
                ],
            )

        click_result = None
        if allow_safe_click:
            click_result = _safe_click_probe(top_menu, row)
            logger.info("DBG_MENU_PROBE_CLICK_RESULT top_menu={} row_index={} result={}", top_menu, row_payload["row_index"], click_result)

        classification = classify_probe_row(row, hover_result, click_result)
        logger.info(
            "DBG_MENU_PROBE_ROW_CLASSIFICATION top_menu={} row_index={} classification={} raw_text={!r} normalized_text={!r}",
            top_menu,
            row_payload["row_index"],
            classification,
            row_payload["raw_text"],
            row_payload["normalized_text"],
        )
        classified_rows.append({**row_payload, "hover_result": hover_result, "click_result": click_result, "classification": classification})

    summary = {
        "top_menu": top_menu,
        "popup_detected": bool(open_state.get("popup_open")),
        "popup_rect": popup_rect,
        "candidate_row_count": len(rows),
        "classified_rows": classified_rows,
        "submenu_rows": [row["row_index"] for row in classified_rows if row["classification"] in {"submenu", "empty_but_submenu_spawning"}],
        "actionable_rows": [row["row_index"] for row in classified_rows if row["classification"] == "actionable"],
        "empty_hover_rows": [row["row_index"] for row in classified_rows if row["classification"] == "empty_but_hover_reactive"],
        "unknown_rows": [row["row_index"] for row in classified_rows if row["classification"] == "unknown"],
    }
    logger.info("DBG_MENU_PROBE_SUMMARY {}", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-menu", required=True)
    parser.add_argument("--allow-safe-click", action="store_true")
    parser.add_argument("--hover-pause", type=float, default=0.15)
    args = parser.parse_args()

    summary = probe_top_menu_popup(args.top_menu, allow_safe_click=args.allow_safe_click, hover_pause_s=args.hover_pause)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

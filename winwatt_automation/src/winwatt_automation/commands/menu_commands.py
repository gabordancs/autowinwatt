"""Command helpers for navigating WinWatt menus."""

from __future__ import annotations

from typing import Any

from winwatt_automation.live_ui import menu_helpers, waits

FILE_MENU_TITLE = "Fájl"


def open_file_menu() -> None:
    """Open the top-level ``Fájl`` menu."""

    try:
        menu_helpers.click_top_menu_item(FILE_MENU_TITLE)
    except LookupError as exc:
        available = menu_helpers.list_top_menu_items()
        raise LookupError(f"Top menu '{FILE_MENU_TITLE}' was not found. Available menus: {available}") from exc


def click_file_submenu_item_by_index(index: int) -> dict[str, Any]:
    """Open ``Fájl`` and click a popup submenu entry by geometry index."""

    return menu_helpers.click_open_menu_item_by_index(index)


def invoke_open_project_dialog_by_index(index: int) -> dict[str, Any]:
    """Click a file-menu popup row by index and report whether dialog appeared."""

    popup_state = menu_helpers.open_file_menu_and_capture_popup_state()
    popup_rows = popup_state.get("rows", [])
    clicked = menu_helpers.click_structured_popup_row(popup_rows, index)

    process_id = popup_state.get("process_id")
    dialog_result = waits.detect_open_file_dialog_from_context(process_id=process_id, timeout=5.0)

    dialog_title = dialog_result.get("dialog_title")
    if dialog_result.get("dialog_detected") and dialog_title is None:
        try:
            dialog = waits.wait_for_dialog_from_context(process_id=process_id, timeout=1.0)
            dialog_title = dialog.window_text()
        except Exception:
            dialog_title = None

    return {
        "clicked_index": index,
        "clicked_rectangle": clicked.get("rectangle"),
        "clicked_entry": clicked,
        "dialog_detected": bool(dialog_result.get("dialog_detected")),
        "dialog_title": dialog_title,
        "dialog_class": dialog_result.get("dialog_class"),
        "dialog_candidate_count": dialog_result.get("candidate_count"),
        "process_id": process_id,
    }

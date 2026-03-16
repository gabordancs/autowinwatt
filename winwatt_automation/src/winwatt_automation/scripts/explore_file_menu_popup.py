"""Explore the geometry-based popup rows under WinWatt's Fájl menu."""

from __future__ import annotations

import argparse
import time

from winwatt_automation.live_ui.app_connector import connect_to_winwatt, prepare_main_window_for_menu_interaction
from winwatt_automation.live_ui.menu_helpers import click_structured_popup_row, open_file_menu_and_capture_popup_state
from winwatt_automation.live_ui.waits import detect_open_file_dialog, wait_for_dialog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--click-index", type=int, default=None)
    parser.add_argument("--hold-seconds", type=float, default=0.75)
    args = parser.parse_args()

    connect_to_winwatt()
    prepare_main_window_for_menu_interaction()
    popup_state = open_file_menu_and_capture_popup_state()
    entries = popup_state["rows"]
    after_rows = popup_state.get("after_snapshot", [])
    new_rows = [row for row in after_rows if row.get("appeared_after_popup_open")]

    print(f"total new rows: {len(new_rows)}")
    print(f"total structured rows: {len(entries)}")
    if len(entries) == 0 and len(new_rows) > 0:
        print("first 20 raw new rows:")
        for row in new_rows[:20]:
            rect = row.get("rectangle", {})
            print(
                f"- rect=({rect.get('left')},{rect.get('top')})-({rect.get('right')},{rect.get('bottom')}) "
                f"text={row.get('text', '')!r} scope={row.get('source_scope', '')}"
            )

    print("Popup submenu entries:")
    for entry in entries:
        rect = entry["rectangle"]
        print(
            f"[{entry['index']}] text='{entry['text']}' "
            f"rect=({rect['left']},{rect['top']})-({rect['right']},{rect['bottom']}) "
            f"separator={entry['is_separator']} source={entry['source_scope']}"
        )

    separators = [entry for entry in entries if entry.get("is_separator")]
    if separators:
        print("\nDetected separator rows:")
        for sep in separators:
            print(f"- index={sep['index']} rect={sep['rectangle']}")

    if args.click_index is None:
        time.sleep(max(0.0, args.hold_seconds))
        return

    clicked = click_structured_popup_row(entries, args.click_index)
    dialog_detected = detect_open_file_dialog(timeout=5.0)
    dialog_title = None
    if dialog_detected:
        try:
            dialog_title = wait_for_dialog(timeout=1.0).window_text()
        except Exception:
            dialog_title = None

    print("\nClick result:")
    print({
        "clicked_index": args.click_index,
        "clicked_rectangle": clicked.get("rectangle"),
        "clicked_entry": clicked,
        "dialog_detected": dialog_detected,
        "dialog_title": dialog_title,
        "top_menu_click_count": popup_state.get("top_menu_click_count"),
    })


if __name__ == "__main__":
    main()

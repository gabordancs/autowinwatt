"""Explore the geometry-based popup rows under WinWatt's Fájl menu."""

from __future__ import annotations

import argparse
import time

from winwatt_automation.commands.menu_commands import invoke_open_project_dialog_by_index, open_file_menu
from winwatt_automation.live_ui.app_connector import connect_to_winwatt, prepare_main_window_for_menu_interaction
from winwatt_automation.live_ui.menu_helpers import list_open_menu_items_structured


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--click-index", type=int, default=None)
    parser.add_argument("--hold-seconds", type=float, default=0.75)
    args = parser.parse_args()

    connect_to_winwatt()
    prepare_main_window_for_menu_interaction()
    open_file_menu()

    entries = list_open_menu_items_structured()
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

    result = invoke_open_project_dialog_by_index(args.click_index)
    print("\nClick result:")
    print(result)


if __name__ == "__main__":
    main()

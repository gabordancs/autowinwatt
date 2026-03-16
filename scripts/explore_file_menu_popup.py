"""Diagnostic explorer for WinWatt Fájl popup geometry-based submenu detection."""

from __future__ import annotations

import time

from winwatt_automation.live_ui.app_connector import (
    connect_to_winwatt,
    is_main_window_foreground,
    prepare_main_window_for_menu_interaction,
)
from winwatt_automation.live_ui.menu_helpers import click_top_menu_item, list_open_menu_items_structured


def main() -> None:
    connect_to_winwatt()
    prepare_main_window_for_menu_interaction()
    print(f"WinWatt is foreground before opening menu: {is_main_window_foreground()}")

    click_top_menu_item("Fájl")
    time.sleep(0.3)

    items = list_open_menu_items_structured()
    print("Popup submenu entries:")
    for entry in items:
        left, top, right, bottom = entry["rectangle"]
        print(
            f"[{entry['order_index']}] text={entry['text']!r} "
            f"rect=({left},{top})-({right},{bottom}) separator={entry['is_separator']}"
        )

    print("Keeping menu open for inspection...")
    time.sleep(5)


if __name__ == "__main__":
    main()

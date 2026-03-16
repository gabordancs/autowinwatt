"""Quick exploratory script for WinWatt's Fájl menu."""

from __future__ import annotations

import time

from winwatt_automation.live_ui.app_connector import (
    connect_to_winwatt,
    is_main_window_foreground,
    prepare_main_window_for_menu_interaction,
)
from winwatt_automation.live_ui.menu_helpers import (
    _menu_snapshot,
    click_top_menu_item,
    did_any_new_menu_popup_appear,
    list_open_menu_items,
    list_top_menu_items,
)


def main() -> None:
    connect_to_winwatt()

    prepare_main_window_for_menu_interaction()
    print(f"WinWatt is foreground before listing menus: {is_main_window_foreground()}")

    top_items = list_top_menu_items()
    print("Top-level menu items:")
    for item in top_items:
        print(f"- {item}")

    before_snapshot = _menu_snapshot()
    click_top_menu_item("Fájl")
    time.sleep(0.3)
    after_snapshot = _menu_snapshot()

    print(f"WinWatt is foreground after click: {is_main_window_foreground()}")
    print(f"New menu popup appeared: {did_any_new_menu_popup_appear(before_snapshot, after_snapshot)}")

    open_items = list_open_menu_items()
    print("\nVisible submenu items after opening 'Fájl':")
    for item in open_items:
        print(f"- {item}")


if __name__ == "__main__":
    main()

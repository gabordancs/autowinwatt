"""Quick exploratory script for WinWatt's Fájl menu."""

from __future__ import annotations

import time

from winwatt_automation.live_ui.app_connector import (
    connect_to_winwatt,
    describe_foreground_window,
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
    print(f"Foreground before listing menus: {describe_foreground_window()}")

    top_items = list_top_menu_items()
    print("Top-level menu items:")
    for item in top_items:
        print(f"- {item}")

    before_snapshot = _menu_snapshot()
    click_top_menu_item("Fájl")
    time.sleep(0.3)
    after_snapshot = _menu_snapshot()
    popup_opened = did_any_new_menu_popup_appear(before_snapshot, after_snapshot)
    fg_after = describe_foreground_window()

    print(f"focus ok / restored: {fg_after}")
    print("clicked target: Fájl")
    print(f"popup opened yes/no: {popup_opened}")
    print(f"system menu opened yes/no: {fg_after.get('class_name') == '#32768'}")

    open_items = list_open_menu_items()
    print("\nVisible submenu items after opening 'Fájl':")
    for item in open_items:
        print(f"- {item}")


if __name__ == "__main__":
    main()

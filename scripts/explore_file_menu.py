"""Quick exploratory script for WinWatt's Fájl menu."""

from __future__ import annotations

import time

from winwatt_automation.live_ui.app_connector import connect_to_winwatt
from winwatt_automation.live_ui.menu_helpers import click_top_menu_item, list_open_menu_items, list_top_menu_items


def main() -> None:
    connect_to_winwatt()

    top_items = list_top_menu_items()
    print("Top-level menu items:")
    for item in top_items:
        print(f"- {item}")

    click_top_menu_item("Fájl")
    time.sleep(0.3)

    open_items = list_open_menu_items()
    print("\nVisible submenu items after opening 'Fájl':")
    for item in open_items:
        print(f"- {item}")


if __name__ == "__main__":
    main()

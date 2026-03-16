"""Temporary workflow: open Fájl, click popup item by index, and log dialog appearance."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from winwatt_automation.commands.menu_commands import click_file_submenu_item_by_index
from winwatt_automation.live_ui.app_connector import connect_to_winwatt, get_cached_main_window


def _top_windows_for_main_process() -> set[int]:
    from pywinauto import Desktop

    main_window = get_cached_main_window()
    process_id = main_window.process_id()
    desktop = Desktop(backend="uia")
    handles: set[int] = set()
    for window in desktop.windows(top_level_only=True):
        try:
            if window.process_id() != process_id:
                continue
            if not window.is_visible():
                continue
            handle = window.handle()
            if handle is not None:
                handles.add(int(handle))
        except Exception:
            continue
    return handles


def run_temp_file_menu_click_by_index(index: int = 0, wait_after_click: float = 1.0) -> dict[str, Any]:
    """Run geometry-only submenu click and report whether a new dialog/window appeared."""

    connect_to_winwatt()
    before_handles = _top_windows_for_main_process()
    clicked_entry = click_file_submenu_item_by_index(index)
    time.sleep(wait_after_click)
    after_handles = _top_windows_for_main_process()

    new_handles = sorted(after_handles - before_handles)
    result = {
        "clicked_index": index,
        "clicked_entry": clicked_entry,
        "dialog_appeared": bool(new_handles),
        "new_window_handles": new_handles,
    }
    logger.info("Temporary submenu-index workflow result: {}", result)
    return result

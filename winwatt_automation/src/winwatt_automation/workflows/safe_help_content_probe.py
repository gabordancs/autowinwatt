"""A non-mutating workflow for WinWatt's CHM help contents."""

from __future__ import annotations

import time
from typing import Any

from winwatt_automation.live_ui.app_connector import ensure_main_window_foreground_before_click, get_cached_main_window, prepare_main_window_for_menu_interaction

HELP_CLASS = "HH Parent"
HELP_TITLE = "Súgó"


def _visible_help_handles() -> set[int]:
    from pywinauto.findwindows import find_windows

    return {int(handle) for handle in find_windows(class_name=HELP_CLASS, title=HELP_TITLE, visible_only=True)}


def _open_help_content(main_window: Any) -> None:
    from pywinauto.application import Application

    window = Application(backend="win32").connect(process=int(main_window.process_id())).window(handle=main_window.handle)
    help_item = next(item for item in window.menu().items() if int(item.item_id()) == 97)
    help_item.click()
    time.sleep(0.1)
    next(item for item in help_item.sub_menu().items() if int(item.item_id()) == 98).click()


def _find_new_help_window(existing_handles: set[int], *, timeout: float) -> Any | None:
    from pywinauto.application import Application

    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        for handle in _visible_help_handles() - existing_handles:
            try:
                return Application(backend="win32").connect(handle=handle).window(handle=handle)
            except Exception:
                continue
        time.sleep(0.05)
    return None


def run_safe_help_content_probe(*, window_timeout: float = 4.0, close_timeout: float = 2.0) -> dict[str, Any]:
    """Open, inspect and close only the help window launched by this probe."""
    prepare_main_window_for_menu_interaction()
    main_window = ensure_main_window_foreground_before_click(action_label="safe_help_content_probe", allow_dialog=True)
    existing_handles = _visible_help_handles()
    _open_help_content(main_window)
    help_window = _find_new_help_window(existing_handles, timeout=window_timeout)
    found = help_window is not None
    handle = int(help_window.handle) if found else None
    if found:
        help_window.close()
    deadline = time.monotonic() + max(0.1, close_timeout)
    while time.monotonic() < deadline and handle is not None and handle in _visible_help_handles():
        time.sleep(0.05)
    dismissed = found and handle not in _visible_help_handles()
    main_enabled = bool(get_cached_main_window().is_enabled())
    return {
        "workflow": "safe_help_content_probe", "command": "MainForm.HelpContent",
        "native_menu_path": [{"menu_command_id": 97}, {"command_id": 98}],
        "help_found": found, "help_title": HELP_TITLE if found else None,
        "help_class": HELP_CLASS if found else None, "help_handle": handle,
        "help_dismissed": dismissed, "main_window_enabled_after": main_enabled,
        "success": found and dismissed and main_enabled,
    }

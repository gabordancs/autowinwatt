"""A non-mutating, verified workflow for WinWatt's About dialog."""

from __future__ import annotations

import time
from typing import Any

from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    prepare_main_window_for_menu_interaction,
)

ABOUT_TITLE = "Névjegy"
ABOUT_CLASS = "TAboutForm"


def _open_about_dialog(main_window: Any) -> None:
    """Use the verified 9.60 native Help-menu position (Súgó, index 1)."""
    from pywinauto.application import Application

    window = Application(backend="win32").connect(process=int(main_window.process_id())).window(handle=main_window.handle)
    help_item = window.menu().item(5)
    help_item.click()
    time.sleep(0.1)
    help_item.sub_menu().item(1).click()


def _find_about_dialog(process_id: int, *, timeout: float) -> Any | None:
    from pywinauto import Desktop

    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        for candidate in Desktop(backend="win32").windows():
            try:
                if (
                    int(candidate.process_id()) == process_id
                    and candidate.window_text() == ABOUT_TITLE
                    and candidate.class_name() == ABOUT_CLASS
                    and candidate.is_visible()
                ):
                    return candidate
            except Exception:
                continue
        time.sleep(0.05)
    return None


def _close_about_dialog(dialog: Any) -> None:
    """Esc does not close TAboutForm; close the uniquely identified owned window."""
    dialog.close()


def run_safe_about_probe(*, dialog_timeout: float = 3.0, close_timeout: float = 2.0) -> dict[str, Any]:
    """Open, identify and close the informational About dialog safely."""
    prepare_main_window_for_menu_interaction()
    main_window = ensure_main_window_foreground_before_click(action_label="safe_about_probe", allow_dialog=True)
    _open_about_dialog(main_window)
    dialog = _find_about_dialog(int(main_window.process_id()), timeout=dialog_timeout)
    dialog_found = dialog is not None
    dialog_handle = int(dialog.handle) if dialog_found else None
    if dialog_found:
        _close_about_dialog(dialog)
    deadline = time.monotonic() + max(0.1, close_timeout)
    while time.monotonic() < deadline:
        if _find_about_dialog(int(main_window.process_id()), timeout=0.01) is None:
            break
        time.sleep(0.05)
    dismissed = dialog_found and _find_about_dialog(int(main_window.process_id()), timeout=0.01) is None
    main_enabled = bool(get_cached_main_window().is_enabled())
    return {
        "workflow": "safe_about_probe",
        "command": "MainForm.HelpAbout",
        "native_menu_path": [{"menu_command_id": 97, "index": 5}, {"command_id": 99, "index": 1}],
        "dialog_found": dialog_found,
        "dialog_title": ABOUT_TITLE if dialog_found else None,
        "dialog_class": ABOUT_CLASS if dialog_found else None,
        "dialog_handle": dialog_handle,
        "dialog_dismissed": dismissed,
        "main_window_enabled_after": main_enabled,
        "success": dialog_found and dismissed and main_enabled,
    }

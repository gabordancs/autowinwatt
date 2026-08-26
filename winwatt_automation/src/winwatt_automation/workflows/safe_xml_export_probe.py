"""Open and cancel the XML Export save dialog without writing a file."""

from __future__ import annotations

import time
from typing import Any

from winwatt_automation.live_ui.app_connector import ensure_main_window_foreground_before_click, get_cached_main_window, prepare_main_window_for_menu_interaction

DIALOG_TITLE = "Mentés másként"
DIALOG_CLASS = "#32770"


def _open_xml_export(main_window: Any) -> None:
    from pywinauto.application import Application

    window = Application(backend="win32").connect(process=int(main_window.process_id())).window(handle=main_window.handle)
    file_menu = next(item for item in window.menu().items() if int(item.item_id()) == 1)
    file_menu.click()
    time.sleep(0.1)
    next(item for item in file_menu.sub_menu().items() if int(item.item_id()) == 9).click()


def _find_save_dialog(process_id: int, *, timeout: float) -> Any | None:
    from pywinauto.application import Application
    from pywinauto.findwindows import find_windows

    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        for handle in find_windows(process=process_id, class_name=DIALOG_CLASS, title=DIALOG_TITLE, visible_only=True):
            try:
                return Application(backend="win32").connect(process=process_id).window(handle=handle)
            except Exception:
                continue
        time.sleep(0.05)
    return None


def run_safe_xml_export_probe(*, dialog_timeout: float = 3.0, close_timeout: float = 2.0) -> dict[str, Any]:
    """Verify the export dialog while explicitly forbidding file confirmation."""
    prepare_main_window_for_menu_interaction()
    main_window = ensure_main_window_foreground_before_click(action_label="safe_xml_export_probe", allow_dialog=True)
    _open_xml_export(main_window)
    dialog = _find_save_dialog(int(main_window.process_id()), timeout=dialog_timeout)
    found = dialog is not None
    handle = int(dialog.handle) if found else None
    if found:
        dialog.type_keys("{ESC}")
    deadline = time.monotonic() + max(0.1, close_timeout)
    while time.monotonic() < deadline:
        if _find_save_dialog(int(main_window.process_id()), timeout=0.01) is None:
            break
        time.sleep(0.05)
    dismissed = found and _find_save_dialog(int(main_window.process_id()), timeout=0.01) is None
    main_enabled = bool(get_cached_main_window().is_enabled())
    return {
        "workflow": "safe_xml_export_probe", "command": "MainForm.XMLExportAction",
        "native_menu_path": [{"menu_command_id": 1}, {"command_id": 9}],
        "dialog_found": found, "dialog_title": DIALOG_TITLE if found else None,
        "dialog_class": DIALOG_CLASS if found else None, "dialog_handle": handle,
        "dialog_dismissed": dismissed, "main_window_enabled_after": main_enabled,
        "forbidden_effect": "confirm_file_name_or_write_export_file",
        "success": found and dismissed and main_enabled,
    }

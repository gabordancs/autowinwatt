"""Open and cancel the custom-report template picker without creating a report."""

from __future__ import annotations

import time
from typing import Any

from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    prepare_main_window_for_menu_interaction,
)
from winwatt_automation.workflows.safe_xml_import_probe import DIALOG_CLASS, DIALOG_TITLE, _find_open_dialog


def _open_custom_reports(main_window: Any) -> None:
    from pywinauto.application import Application

    window = Application(backend="win32").connect(process=int(main_window.process_id())).window(handle=main_window.handle)
    file_menu = next(item for item in window.menu().items() if int(item.item_id()) == 1)
    file_menu.click()
    time.sleep(0.1)
    next(item for item in file_menu.sub_menu().items() if int(item.item_id()) == 19).click()


def run_safe_custom_reports_probe(*, dialog_timeout: float = 3.0, close_timeout: float = 2.0) -> dict[str, Any]:
    """Verify only the report-template picker; never select a template or create output."""
    prepare_main_window_for_menu_interaction()
    main_window = ensure_main_window_foreground_before_click(action_label="safe_custom_reports_probe", allow_dialog=True)
    _open_custom_reports(main_window)
    dialog = _find_open_dialog(int(main_window.process_id()), timeout=dialog_timeout)
    found = dialog is not None
    handle = int(dialog.handle) if found else None
    if found:
        dialog.type_keys("{ESC}")
    deadline = time.monotonic() + max(0.1, close_timeout)
    while time.monotonic() < deadline:
        if _find_open_dialog(int(main_window.process_id()), timeout=0.01) is None:
            break
        time.sleep(0.05)
    dismissed = found and _find_open_dialog(int(main_window.process_id()), timeout=0.01) is None
    main_enabled = bool(get_cached_main_window().is_enabled())
    return {
        "workflow": "safe_custom_reports_probe",
        "command": "MainForm.CreateReportAction",
        "native_menu_path": [{"menu_command_id": 1}, {"command_id": 19}],
        "dialog_found": found,
        "dialog_title": DIALOG_TITLE if found else None,
        "dialog_class": DIALOG_CLASS if found else None,
        "dialog_handle": handle,
        "dialog_dismissed": dismissed,
        "main_window_enabled_after": main_enabled,
        "forbidden_effect": "select_report_template_or_create_report",
        "success": found and dismissed and main_enabled,
    }

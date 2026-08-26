"""A non-mutating, privacy-preserving workflow for Project Data."""

from __future__ import annotations

import time
from typing import Any

from winwatt_automation.live_ui.app_connector import ensure_main_window_foreground_before_click, get_cached_main_window, prepare_main_window_for_menu_interaction

DATA_TITLE = "Projekt adatok"
DATA_CLASS = "TProjektDataForm"


def _open_project_data(main_window: Any) -> None:
    from pywinauto.application import Application

    window = Application(backend="win32").connect(process=int(main_window.process_id())).window(handle=main_window.handle)
    file_menu = next(item for item in window.menu().items() if int(item.item_id()) == 1)
    file_menu.click()
    time.sleep(0.1)
    next(item for item in file_menu.sub_menu().items() if int(item.item_id()) == 7).click()


def _find_project_data_dialog(process_id: int, *, timeout: float) -> Any | None:
    from pywinauto import Desktop

    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        for candidate in Desktop(backend="win32").windows():
            try:
                if int(candidate.process_id()) == process_id and candidate.window_text() == DATA_TITLE and candidate.class_name() == DATA_CLASS and candidate.is_visible():
                    return candidate
            except Exception:
                continue
        time.sleep(0.05)
    return None


def _control_summary(dialog: Any) -> dict[str, int]:
    summary: dict[str, int] = {}
    for control in dialog.descendants():
        try:
            class_name = control.class_name()
        except Exception:
            continue
        summary[class_name] = summary.get(class_name, 0) + 1
    return dict(sorted(summary.items()))


def run_safe_project_data_probe(*, dialog_timeout: float = 3.0, close_timeout: float = 2.0) -> dict[str, Any]:
    """Open and inspect structural metadata only, then close without accepting changes."""
    prepare_main_window_for_menu_interaction()
    main_window = ensure_main_window_foreground_before_click(action_label="safe_project_data_probe", allow_dialog=True)
    _open_project_data(main_window)
    dialog = _find_project_data_dialog(int(main_window.process_id()), timeout=dialog_timeout)
    found = dialog is not None
    handle = int(dialog.handle) if found else None
    summary = _control_summary(dialog) if found else {}
    if found:
        dialog.close()
    deadline = time.monotonic() + max(0.1, close_timeout)
    while time.monotonic() < deadline:
        if _find_project_data_dialog(int(main_window.process_id()), timeout=0.01) is None:
            break
        time.sleep(0.05)
    dismissed = found and _find_project_data_dialog(int(main_window.process_id()), timeout=0.01) is None
    main_enabled = bool(get_cached_main_window().is_enabled())
    return {
        "workflow": "safe_project_data_probe", "command": "MainForm.ProjektData",
        "native_menu_path": [{"menu_command_id": 1}, {"command_id": 7}],
        "dialog_found": found, "dialog_title": DATA_TITLE if found else None,
        "dialog_class": DATA_CLASS if found else None, "dialog_handle": handle,
        "dialog_dismissed": dismissed, "main_window_enabled_after": main_enabled,
        "control_class_summary": summary,
        "privacy_policy": "Field values are intentionally excluded from the workflow result.",
        "success": found and dismissed and main_enabled,
    }

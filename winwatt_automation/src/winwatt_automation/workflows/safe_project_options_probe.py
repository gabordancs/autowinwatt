"""A non-mutating, verified workflow for the Project Options dialog."""

from __future__ import annotations

import time
from typing import Any

from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    prepare_main_window_for_menu_interaction,
)


OPTIONS_CLASS = "TProjektOptionsForm"


def _open_project_options(main_window: Any) -> None:
    """Invoke the native Settings > Project Options IDs, independent of MDI menu layout."""
    from pywinauto.application import Application

    window = Application(backend="win32").connect(process=int(main_window.process_id())).window(handle=main_window.handle)
    settings = next(item for item in window.menu().items() if int(item.item_id()) == 88)
    settings.click()
    time.sleep(0.1)
    project_options = next(item for item in settings.sub_menu().items() if int(item.item_id()) == 90)
    project_options.click()


def _find_project_options_dialog(process_id: int, *, timeout: float) -> Any | None:
    from pywinauto import Desktop

    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        for candidate in Desktop(backend="win32").windows():
            try:
                if int(candidate.process_id()) == process_id and candidate.class_name() == OPTIONS_CLASS:
                    return candidate
            except Exception:
                continue
        time.sleep(0.05)
    return None


def _snapshot_controls(dialog: Any) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for control in dialog.descendants():
        try:
            controls.append(
                {
                    "title": control.window_text(),
                    "class_name": control.class_name(),
                    "control_id": control.control_id(),
                    "enabled": bool(control.is_enabled()),
                }
            )
        except Exception:
            continue
    return controls


def run_safe_project_options_probe(*, dialog_timeout: float = 3.0, close_timeout: float = 2.0) -> dict[str, Any]:
    """Open, inspect and close Project Options without changing or accepting values."""
    prepare_main_window_for_menu_interaction()
    main_window = ensure_main_window_foreground_before_click(action_label="safe_project_options_probe", allow_dialog=True)
    _open_project_options(main_window)
    dialog = _find_project_options_dialog(int(main_window.process_id()), timeout=dialog_timeout)
    dialog_found = dialog is not None
    dialog_handle = int(dialog.handle) if dialog_found else None
    controls = _snapshot_controls(dialog) if dialog_found else []
    if dialog_found:
        dialog.close()
    deadline = time.monotonic() + max(0.1, close_timeout)
    while time.monotonic() < deadline:
        if _find_project_options_dialog(int(main_window.process_id()), timeout=0.01) is None:
            break
        time.sleep(0.05)
    dismissed = dialog_found and _find_project_options_dialog(int(main_window.process_id()), timeout=0.01) is None
    main_enabled = bool(get_cached_main_window().is_enabled())
    return {
        "workflow": "safe_project_options_probe",
        "command": "MainForm.ProjektOptions",
        "native_menu_path": [{"menu_command_id": 88}, {"command_id": 90}],
        "dialog_found": dialog_found,
        "dialog_class": OPTIONS_CLASS if dialog_found else None,
        "dialog_handle": dialog_handle,
        "dialog_dismissed": dismissed,
        "main_window_enabled_after": main_enabled,
        "dialog_controls": controls,
        "success": dialog_found and dismissed and main_enabled,
    }

"""A non-mutating, verified workflow for the New Project dialog."""

from __future__ import annotations

import time
from typing import Any

from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    prepare_main_window_for_menu_interaction,
)

NEW_PROJECT_DIALOG_TITLE = "Projekt létrehozása"


def _send_new_project_menu_sequence() -> list[str]:
    """Open File and invoke its verified first command without confirming it."""

    from pywinauto import keyboard

    sequence = ["ALT+F", "ENTER"]
    keyboard.send_keys("%f")
    time.sleep(0.1)
    keyboard.send_keys("{ENTER}")
    return sequence


def _find_new_project_dialog(process_id: int, *, timeout: float) -> tuple[Any | None, dict[str, Any]]:
    from pywinauto import Desktop

    deadline = time.monotonic() + max(0.1, timeout)
    while time.monotonic() < deadline:
        for candidate in Desktop(backend="win32").windows():
            try:
                if int(candidate.process_id()) != process_id:
                    continue
                if candidate.window_text() != NEW_PROJECT_DIALOG_TITLE or candidate.class_name() != "#32770":
                    continue
                if not candidate.is_visible():
                    continue
                return candidate, {
                    "dialog_found": True,
                    "selected_candidate": {
                        "title": candidate.window_text(),
                        "class_name": candidate.class_name(),
                        "process_id": process_id,
                        "handle": int(candidate.handle),
                    },
                }
            except Exception:
                continue
        time.sleep(0.05)
    return None, {"dialog_found": False}


def _send_escape() -> None:
    from pywinauto import keyboard

    keyboard.send_keys("{ESC}")


def _snapshot_visible_controls(dialog: Any) -> list[dict[str, Any]]:
    """Capture inspectable dialog controls before cancelling the dialog."""

    controls: list[dict[str, Any]] = []
    for control in dialog.descendants():
        try:
            if not bool(control.is_visible()):
                continue
            rectangle = control.rectangle()
            controls.append(
                {
                    "title": control.window_text(),
                    "class_name": control.class_name(),
                    "friendly_class_name": control.friendly_class_name(),
                    "control_id": control.control_id(),
                    "enabled": bool(control.is_enabled()),
                    "rectangle": {
                        "left": rectangle.left,
                        "top": rectangle.top,
                        "right": rectangle.right,
                        "bottom": rectangle.bottom,
                    },
                }
            )
        except Exception:
            continue
    return controls


def _dialog_is_visible(handle: int | None) -> bool:
    if not isinstance(handle, int):
        return False
    from pywinauto import Desktop

    for candidate in Desktop(backend="win32").windows():
        try:
            if int(candidate.handle) == handle:
                return bool(candidate.is_visible())
        except Exception:
            continue
    return False


def run_safe_new_project_probe(*, dialog_timeout: float = 3.0, close_timeout: float = 2.0) -> dict[str, Any]:
    """Open and cancel the New Project dialog; no project is created or saved."""

    prepare_main_window_for_menu_interaction()
    main_window = ensure_main_window_foreground_before_click(
        action_label="safe_new_project_probe",
        allow_dialog=True,
    )
    main_window.set_focus()
    process_id = int(main_window.process_id())
    sequence = _send_new_project_menu_sequence()
    dialog, detection = _find_new_project_dialog(process_id, timeout=dialog_timeout)
    dialog_found = dialog is not None and bool(detection.get("dialog_found"))
    controls = _snapshot_visible_controls(dialog) if dialog_found else []
    handle = (detection.get("selected_candidate") or {}).get("handle")
    dismissed = False
    if dialog_found:
        _send_escape()
        deadline = time.monotonic() + max(0.1, close_timeout)
        while time.monotonic() < deadline:
            if not _dialog_is_visible(handle):
                dismissed = True
                break
            time.sleep(0.05)
    main_window = get_cached_main_window()
    main_window_enabled = bool(main_window.is_enabled())
    return {
        "workflow": "safe_new_project_probe",
        "command": "MainForm.NewProjekt",
        "command_id": 2,
        "dialog_found": dialog_found,
        "dialog_title": (detection.get("selected_candidate") or {}).get("title"),
        "dialog_dismissed": dismissed,
        "main_window_enabled_after": main_window_enabled,
        "success": dialog_found and dismissed and main_window_enabled,
        "dialog_controls": controls,
        "detection": {**detection, "method": "file_menu_mnemonic", "sequence": sequence},
    }

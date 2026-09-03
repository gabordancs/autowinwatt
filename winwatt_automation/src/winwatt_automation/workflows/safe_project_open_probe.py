"""A non-mutating, verified workflow for the Project Open dialog."""

from __future__ import annotations

import time
from typing import Any

from winwatt_automation.live_ui.app_connector import FocusGuardError, get_cached_main_window
from winwatt_automation.live_ui.file_dialog import find_open_file_dialog, prepare_and_trigger_project_open_dialog
from winwatt_automation.live_ui.project_open_accelerator import send_project_open_accelerator


def _is_visible_dialog(dialog: Any) -> bool:
    for method_name in ("exists", "is_visible"):
        method = getattr(dialog, method_name, None)
        if callable(method):
            try:
                if not bool(method()):
                    return False
            except Exception:
                return False
    return True


def _send_escape() -> None:
    from pywinauto import keyboard

    keyboard.send_keys("{ESC}")


def _is_detected_dialog_visible(dialog: Any, detection: dict[str, Any]) -> bool:
    handle = (detection.get("selected_candidate") or {}).get("handle")
    if isinstance(handle, int):
        from pywinauto import Desktop

        for candidate in Desktop(backend="uia").windows(top_level_only=True):
            try:
                if int(candidate.handle) == handle:
                    return bool(candidate.is_visible())
            except Exception:
                continue
        return False
    return _is_visible_dialog(dialog)


def _trigger_with_focus_guard_fallback(dialog_timeout: float) -> tuple[Any | None, dict[str, Any]]:
    """Use Ctrl+O only if the generic UIA focus guard rejects a live main window."""

    try:
        return prepare_and_trigger_project_open_dialog(
            action_label="safe_project_open_probe",
            dialog_timeout=dialog_timeout,
        )
    except FocusGuardError as error:
        main_window = get_cached_main_window()
        main_window.set_focus()
        process_id = int(main_window.process_id())
        accelerator = send_project_open_accelerator()
        dialog, detection = find_open_file_dialog(process_id=process_id, timeout=dialog_timeout)
        return dialog, {
            **detection,
            "method": "ctrl_o_focus_guard_fallback",
            "fallback_reason": str(error),
            "project_open_method": accelerator.get("project_open_method"),
            "sequence": accelerator.get("sequence"),
        }


def run_safe_project_open_probe(*, dialog_timeout: float = 3.0, close_timeout: float = 2.0) -> dict[str, Any]:
    """Open and cancel the Project Open dialog, proving the command path safely."""

    dialog, detection = _trigger_with_focus_guard_fallback(dialog_timeout)
    dialog_found = bool(detection.get("dialog_found")) and dialog is not None
    dismissed = False

    if dialog_found:
        _send_escape()
        deadline = time.monotonic() + max(0.1, close_timeout)
        while time.monotonic() < deadline:
            if not _is_detected_dialog_visible(dialog, detection):
                dismissed = True
                break
            time.sleep(0.05)
        dismissed = dismissed or not _is_detected_dialog_visible(dialog, detection)

    main_window = get_cached_main_window()
    main_window_enabled = bool(main_window.is_enabled())
    return {
        "workflow": "safe_project_open_probe",
        "command": "MainForm.OpenProjekt",
        "command_id": 3,
        "dialog_found": dialog_found,
        "dialog_title": detection.get("selected_candidate", {}).get("title"),
        "dialog_dismissed": dismissed,
        "main_window_enabled_after": main_window_enabled,
        "success": dialog_found and dismissed and main_window_enabled,
        "detection": detection,
    }

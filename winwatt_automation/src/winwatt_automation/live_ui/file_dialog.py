from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from loguru import logger

from winwatt_automation.live_ui import menu_helpers

DIALOG_CLASS_NAME = "#32770"
DIALOG_TITLE_HINTS = ("projekt megnyitás", "megnyitás", "open")
CONFIRM_BUTTON_HINTS = ("megnyitás", "&megnyitás", "open", "&open")
FILENAME_EDIT_HINTS = ("fájlnév", "fajlnev", "file name", "filename", "name")


@dataclass(slots=True)
class OpenProjectDialogResult:
    success: bool
    path: str
    dialog_found: bool
    path_entered: bool
    confirm_clicked: bool
    dialog_closed: bool
    project_state_changed: bool
    detected_changes: list[str]
    error: str | None = None


def _safe_call(obj: Any, method: str, default: Any = None) -> Any:
    attr = getattr(obj, method, None)
    if not callable(attr):
        return default
    try:
        return attr()
    except Exception:
        return default


def _window_snapshot(window: Any) -> dict[str, Any]:
    title = str(_safe_call(window, "window_text", "") or "").strip()
    class_name = str(_safe_call(window, "class_name", "") or "").strip()
    process_id = _safe_call(window, "process_id", None)
    handle = _safe_call(window, "handle", None)
    return {
        "title": title,
        "title_lower": title.lower(),
        "class_name": class_name,
        "class_lower": class_name.lower(),
        "process_id": process_id,
        "handle": handle,
    }


def _is_open_dialog_title(title: str) -> bool:
    lowered = (title or "").strip().lower()
    return any(hint in lowered for hint in DIALOG_TITLE_HINTS)


def _candidate_score(candidate: dict[str, Any], process_id: int | None, previous_handles: set[int] | None) -> tuple[int, int, int, int]:
    pid_match = int(process_id is not None and candidate.get("process_id") == process_id)
    class_match = int(candidate.get("class_name") == DIALOG_CLASS_NAME)
    title_match = int(_is_open_dialog_title(str(candidate.get("title") or "")))
    handle = candidate.get("handle")
    newly_appeared = int(previous_handles is not None and handle is not None and handle not in previous_handles)
    return (pid_match, newly_appeared, class_match, title_match)


def select_best_dialog_candidate(
    candidates: list[dict[str, Any]],
    *,
    process_id: int | None,
    previous_handles: set[int] | None,
) -> dict[str, Any] | None:
    eligible = [item for item in candidates if item.get("class_name") == DIALOG_CLASS_NAME and _is_open_dialog_title(str(item.get("title") or ""))]
    if not eligible:
        return None
    ranked = sorted(
        eligible,
        key=lambda item: _candidate_score(item, process_id, previous_handles),
        reverse=True,
    )
    return ranked[0]


def find_open_file_dialog(
    *,
    process_id: int | None,
    timeout: float = 6.0,
    poll_interval: float = 0.1,
    previous_handles: set[int] | None = None,
) -> tuple[Any | None, dict[str, Any]]:
    from pywinauto import Desktop

    start = time.monotonic()
    deadline = start + timeout
    desktop = Desktop(backend="uia")

    while time.monotonic() < deadline:
        wrappers: dict[int, Any] = {}
        snapshots: list[dict[str, Any]] = []
        for window in desktop.windows(top_level_only=True):
            if not bool(_safe_call(window, "is_visible", False)):
                continue
            snap = _window_snapshot(window)
            handle = snap.get("handle")
            if isinstance(handle, int):
                wrappers[handle] = window
            snapshots.append(snap)

        best = select_best_dialog_candidate(snapshots, process_id=process_id, previous_handles=previous_handles)
        logger.info("find_open_file_dialog candidates={} selected={}", snapshots, best)
        if best is not None:
            selected_wrapper = wrappers.get(best.get("handle"))
            result = {
                "dialog_found": True,
                "selected_candidate": best,
                "candidate_count": len(snapshots),
                "elapsed_seconds": round(time.monotonic() - start, 3),
            }
            return selected_wrapper, result
        time.sleep(poll_interval)

    return None, {
        "dialog_found": False,
        "selected_candidate": None,
        "candidate_count": 0,
        "elapsed_seconds": round(time.monotonic() - start, 3),
    }


def _control_name(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return str(getattr(info, "name", "") or "").strip()


def _control_type(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return str(getattr(info, "control_type", "") or "").strip().lower()


def _find_filename_edit_control(dialog: Any) -> Any | None:
    descendants = getattr(dialog, "descendants", None)
    if not callable(descendants):
        return None

    edits = [item for item in descendants() if _control_type(item) == "edit"]
    if not edits:
        return None

    def score(edit: Any) -> tuple[int, int]:
        name = _control_name(edit).lower()
        name_hint = int(any(hint in name for hint in FILENAME_EDIT_HINTS))
        enabled = int(bool(_safe_call(edit, "is_enabled", False)))
        return (name_hint, enabled)

    return sorted(edits, key=score, reverse=True)[0]


def _read_edit_value(edit: Any) -> str:
    text = str(_safe_call(edit, "window_text", "") or "")
    if text:
        return text
    iface_value = getattr(edit, "iface_value", None)
    if iface_value is not None:
        try:
            return str(getattr(iface_value, "CurrentValue", "") or "")
        except Exception:
            return ""
    return ""


def _write_to_edit(edit: Any, project_path: str) -> bool:
    for method in ("set_edit_text", "set_text"):
        setter = getattr(edit, method, None)
        if not callable(setter):
            continue
        try:
            setter(project_path)
            if project_path.lower() in _read_edit_value(edit).lower():
                return True
        except Exception:
            continue

    type_keys = getattr(edit, "type_keys", None)
    if callable(type_keys):
        try:
            edit.set_focus()
        except Exception:
            pass
        try:
            type_keys("^a{BACKSPACE}", set_foreground=True)
            type_keys(project_path, with_spaces=True, set_foreground=True)
            if project_path.lower() in _read_edit_value(edit).lower():
                return True
        except Exception:
            pass

    return False


def set_file_dialog_path(dialog: Any, project_path: str) -> tuple[bool, dict[str, Any]]:
    from pywinauto import keyboard

    edit = _find_filename_edit_control(dialog)
    if edit is not None and _write_to_edit(edit, project_path):
        logger.info("set_file_dialog_path direct-edit success edit_name={}", _control_name(edit))
        return True, {"method": "direct_edit", "edit_name": _control_name(edit)}

    try:
        dialog.set_focus()
    except Exception:
        pass

    for hotkey in ("^l", "%d"):
        try:
            keyboard.send_keys(hotkey)
            time.sleep(0.05)
            keyboard.send_keys("^a{BACKSPACE}")
            keyboard.send_keys(project_path, with_spaces=True)
            keyboard.send_keys("{TAB}")
            refreshed_edit = _find_filename_edit_control(dialog)
            if refreshed_edit is not None and project_path.lower() in _read_edit_value(refreshed_edit).lower():
                logger.info("set_file_dialog_path hotkey success hotkey={}", hotkey)
                return True, {"method": "hotkey", "hotkey": hotkey, "edit_name": _control_name(refreshed_edit)}
        except Exception:
            continue

    if edit is not None:
        try:
            edit.set_focus()
            keyboard.send_keys("^a{BACKSPACE}")
            keyboard.send_keys(project_path, with_spaces=True)
            if project_path.lower() in _read_edit_value(edit).lower():
                logger.info("set_file_dialog_path final edit fallback success")
                return True, {"method": "final_edit_fallback", "edit_name": _control_name(edit)}
        except Exception:
            pass

    return False, {"method": "failed"}


def find_confirm_open_button(dialog: Any) -> Any | None:
    descendants = getattr(dialog, "descendants", None)
    if not callable(descendants):
        return None

    buttons = [item for item in descendants() if _control_type(item) == "button"]
    if not buttons:
        return None

    def score(button: Any) -> tuple[int, int]:
        text = _control_name(button).lower()
        label = int(any(hint == text or hint in text for hint in CONFIRM_BUTTON_HINTS))
        enabled = int(bool(_safe_call(button, "is_enabled", False)))
        return (label, enabled)

    best = sorted(buttons, key=score, reverse=True)[0]
    if score(best)[0] == 0:
        return None
    return best


def confirm_file_dialog_open(dialog: Any) -> tuple[bool, dict[str, Any]]:
    from pywinauto import keyboard

    button = find_confirm_open_button(dialog)
    if button is not None:
        try:
            button.click_input()
            logger.info("confirm_file_dialog_open clicked button={}", _control_name(button))
            return True, {"method": "button", "button": _control_name(button)}
        except Exception:
            invoke = getattr(button, "invoke", None)
            if callable(invoke):
                try:
                    invoke()
                    logger.info("confirm_file_dialog_open invoked button={}", _control_name(button))
                    return True, {"method": "button_invoke", "button": _control_name(button)}
                except Exception:
                    pass

    try:
        dialog.set_focus()
    except Exception:
        pass
    try:
        keyboard.send_keys("{ENTER}")
        logger.info("confirm_file_dialog_open used ENTER fallback")
        return True, {"method": "enter_fallback"}
    except Exception as exc:
        return False, {"method": "failed", "error": str(exc)}


def detect_project_state_changed(before_snapshot: dict[str, Any], after_snapshot: dict[str, Any]) -> tuple[bool, list[str]]:
    changes: list[str] = []
    before_menus = list(before_snapshot.get("discovered_top_menus") or [])
    after_menus = list(after_snapshot.get("discovered_top_menus") or [])
    if before_menus != after_menus:
        changes.append("top_menus_changed")
    if len(before_menus) != len(after_menus):
        changes.append("top_menu_count_changed")

    before_windows = list(before_snapshot.get("visible_top_windows") or [])
    after_windows = list(after_snapshot.get("visible_top_windows") or [])
    if len(before_windows) != len(after_windows):
        changes.append("visible_window_count_changed")

    if before_snapshot.get("main_window_title") != after_snapshot.get("main_window_title"):
        changes.append("main_window_title_changed")

    return bool(changes), changes


def _top_level_handles() -> set[int]:
    from pywinauto import Desktop

    handles: set[int] = set()
    for window in Desktop(backend="uia").windows(top_level_only=True):
        handle = _safe_call(window, "handle", None)
        if isinstance(handle, int):
            handles.add(handle)
    return handles


def trigger_open_project_dialog_from_default_state(*, process_id: int | None, dialog_timeout: float = 3.0) -> tuple[Any | None, dict[str, Any]]:
    from pywinauto import keyboard

    handles_before_shortcut = _top_level_handles()
    steps: list[str] = []
    try:
        keyboard.send_keys("%")
        steps.append("ALT")
        time.sleep(0.05)
        keyboard.send_keys("f")
        steps.append("F")
        time.sleep(0.05)
        keyboard.send_keys("m")
        steps.append("M")
    except Exception as exc:
        return None, {
            "dialog_found": False,
            "method": "accelerator",
            "steps": steps,
            "error": str(exc),
        }

    dialog, detect_info = find_open_file_dialog(
        process_id=process_id,
        timeout=dialog_timeout,
        previous_handles=handles_before_shortcut,
    )
    detect_info = {
        **detect_info,
        "method": "accelerator",
        "steps": steps,
    }
    return dialog, detect_info


def _project_open_menu_row_index(rows: list[dict[str, Any]]) -> int | None:
    for index, row in enumerate(rows):
        text = str(row.get("text") or "").strip().lower()
        if "projekt" in text and "megnyit" in text:
            return index
    for index, row in enumerate(rows):
        text = str(row.get("text") or "").strip().lower()
        if "megnyit" in text or "open" in text:
            return index
    return None


def open_project_file_via_dialog(
    project_path: str,
    *,
    before_snapshot: dict[str, Any],
    after_snapshot_provider: Any,
    dialog_timeout: float = 8.0,
) -> OpenProjectDialogResult:
    start = time.monotonic()
    dialog_found = False
    path_entered = False
    confirm_clicked = False
    dialog_closed = False
    project_state_changed = False
    detected_changes: list[str] = []

    try:
        process_id = None
        dialog = None
        detect_info: dict[str, Any] = {}
        accelerator_error: str | None = None

        dialog, detect_info = trigger_open_project_dialog_from_default_state(
            process_id=process_id,
            dialog_timeout=min(dialog_timeout, 3.0),
        )
        dialog_found = bool(detect_info.get("dialog_found"))
        if dialog_found:
            logger.info("open_project_file_via_dialog accelerator success detect_info={}", detect_info)
        else:
            accelerator_error = detect_info.get("error")
            logger.info("open_project_file_via_dialog accelerator fallback detect_info={}", detect_info)

            popup_state = menu_helpers.open_file_menu_and_capture_popup_state()
            rows = popup_state.get("rows", [])
            row_index = _project_open_menu_row_index(rows)
            if row_index is None:
                return OpenProjectDialogResult(
                    success=False,
                    path=project_path,
                    dialog_found=False,
                    path_entered=False,
                    confirm_clicked=False,
                    dialog_closed=False,
                    project_state_changed=False,
                    detected_changes=[],
                    error="Could not locate 'Projekt megnyitás' row in Fájl popup.",
                )

            process_id = popup_state.get("process_id")
            handles_before_click = _top_level_handles()
            clicked = menu_helpers.click_structured_popup_row(rows, row_index)
            logger.info("open_project_file_via_dialog clicked popup_row={} text={}", row_index, clicked.get("text"))

            dialog, detect_info = find_open_file_dialog(
                process_id=process_id,
                timeout=dialog_timeout,
                previous_handles=handles_before_click,
            )
            dialog_found = bool(detect_info.get("dialog_found"))
        if dialog is None:
            return OpenProjectDialogResult(
                success=False,
                path=project_path,
                dialog_found=dialog_found,
                path_entered=False,
                confirm_clicked=False,
                dialog_closed=False,
                project_state_changed=False,
                detected_changes=[],
                error=accelerator_error or "Open-file dialog not detected after menu click.",
            )

        path_entered, path_info = set_file_dialog_path(dialog, project_path)
        logger.info("open_project_file_via_dialog path set result={}", path_info)
        if not path_entered:
            return OpenProjectDialogResult(
                success=False,
                path=project_path,
                dialog_found=True,
                path_entered=False,
                confirm_clicked=False,
                dialog_closed=False,
                project_state_changed=False,
                detected_changes=[],
                error="Failed to enter project path into dialog.",
            )

        confirm_clicked, confirm_info = confirm_file_dialog_open(dialog)
        logger.info("open_project_file_via_dialog confirm result={}", confirm_info)
        if not confirm_clicked:
            return OpenProjectDialogResult(
                success=False,
                path=project_path,
                dialog_found=True,
                path_entered=True,
                confirm_clicked=False,
                dialog_closed=False,
                project_state_changed=False,
                detected_changes=[],
                error="Failed to trigger dialog confirmation action.",
            )

        close_deadline = time.monotonic() + max(1.0, dialog_timeout)
        while time.monotonic() < close_deadline:
            if not bool(_safe_call(dialog, "exists", True)) or not bool(_safe_call(dialog, "is_visible", True)):
                dialog_closed = True
                break
            time.sleep(0.1)

        after_snapshot = after_snapshot_provider()
        project_state_changed, detected_changes = detect_project_state_changed(before_snapshot, after_snapshot)

        success = dialog_closed and project_state_changed
        elapsed = round(time.monotonic() - start, 3)
        logger.info(
            "open_project_file_via_dialog completed success={} dialog_found={} path_entered={} confirm_clicked={} dialog_closed={} state_changed={} changes={} elapsed_s={}",
            success,
            dialog_found,
            path_entered,
            confirm_clicked,
            dialog_closed,
            project_state_changed,
            detected_changes,
            elapsed,
        )
        error = None
        if not dialog_closed:
            error = "Dialog did not close after confirmation."
        elif not project_state_changed:
            error = "Dialog closed but runtime state did not change."

        return OpenProjectDialogResult(
            success=success,
            path=project_path,
            dialog_found=dialog_found,
            path_entered=path_entered,
            confirm_clicked=confirm_clicked,
            dialog_closed=dialog_closed,
            project_state_changed=project_state_changed,
            detected_changes=detected_changes,
            error=error,
        )
    except Exception as exc:
        logger.exception("open_project_file_via_dialog failed")
        return OpenProjectDialogResult(
            success=False,
            path=project_path,
            dialog_found=dialog_found,
            path_entered=path_entered,
            confirm_clicked=confirm_clicked,
            dialog_closed=dialog_closed,
            project_state_changed=project_state_changed,
            detected_changes=detected_changes,
            error=str(exc),
        )


def open_project_file_via_dialog_dict(
    project_path: str,
    *,
    before_snapshot: dict[str, Any],
    after_snapshot_provider: Any,
    dialog_timeout: float = 8.0,
) -> dict[str, Any]:
    return asdict(
        open_project_file_via_dialog(
            project_path,
            before_snapshot=before_snapshot,
            after_snapshot_provider=after_snapshot_provider,
            dialog_timeout=dialog_timeout,
        )
    )

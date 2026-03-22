from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from loguru import logger

from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    prepare_main_window_for_menu_interaction,
)
from winwatt_automation.live_ui import menu_helpers
from winwatt_automation.live_ui.project_open_accelerator import (
    PROJECT_OPEN_ACCELERATOR_MODE,
    project_open_accelerator_sequence,
    send_project_open_accelerator,
)

DIALOG_CLASS_NAME = "#32770"
DIALOG_TITLE_HINTS = ("projekt megnyitás", "megnyitás", "open")
CONFIRM_BUTTON_HINTS = ("megnyitás", "&megnyitás", "open", "&open")
FILENAME_EDIT_HINTS = ("fájlnév", "fajlnev", "file name", "filename", "name")


@dataclass(slots=True)
class OpenProjectDialogResult:
    success: bool
    path: str
    dialog_found: bool
    path_entry_attempted: bool
    path_entered: bool
    confirm_attempted: bool
    confirm_clicked: bool
    dialog_closed: bool
    project_state_changed: bool
    detected_changes: list[str]
    project_open_method: str = PROJECT_OPEN_ACCELERATOR_MODE
    project_open_sequence: list[str] | None = None
    detected_dialog_snapshot: dict[str, Any] | None = None
    helper_received_dialog_context: dict[str, Any] | None = None
    helper_dialog_revalidated: bool = False
    helper_dialog_ready_for_interaction: bool = False
    observed_main_window_title_after_open: str | None = None
    observed_project_path: str | None = None
    path_match_normalized: bool = False
    error: str | None = None


def _safe_call(obj: Any, method: str, default: Any = None) -> Any:
    attr = getattr(obj, method, None)
    if not callable(attr):
        return default
    try:
        return attr()
    except Exception:
        return default


def _extract_project_path_from_title(title: str | None) -> str | None:
    import re

    value = str(title or "").strip()
    if not value:
        return None
    match = re.search(r'([A-Za-z]:\\[^"\r\n\t]*\.[Ww][Ww][Pp])', value)
    if match:
        return match.group(1)
    return None


def _normalize_project_path(project_path: str | None) -> str | None:
    value = str(project_path or "").strip()
    if not value:
        return None
    return value.replace("/", "\\").lower()


def _build_project_path_verification(*, expected_project_path: str | None, observed_main_window_title: str | None) -> dict[str, Any]:
    observed_project_path = _extract_project_path_from_title(observed_main_window_title)
    normalized_expected = _normalize_project_path(expected_project_path)
    normalized_observed = _normalize_project_path(observed_project_path)
    return {
        "expected_project_path": expected_project_path,
        "observed_main_window_title": str(observed_main_window_title or ""),
        "observed_project_path": observed_project_path,
        "path_match_normalized": bool(normalized_expected and normalized_expected == normalized_observed),
    }


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


def trigger_open_project_dialog_from_default_state(
    *,
    process_id: int | None,
    dialog_timeout: float = 3.0,
    accelerator_mode: str = PROJECT_OPEN_ACCELERATOR_MODE,
    step_delay_s: float = 0.05,
) -> tuple[Any | None, dict[str, Any]]:
    handles_before_shortcut = _top_level_handles()
    send_info = {
        "project_open_method": accelerator_mode,
        "sequence": [],
    }
    try:
        send_info = send_project_open_accelerator(mode=accelerator_mode, step_delay_s=step_delay_s)
    except Exception as exc:
        return None, {
            "dialog_found": False,
            "method": "accelerator",
            "steps": list(send_info.get("sequence") or []),
            "project_open_method": accelerator_mode,
            "sequence": list(send_info.get("sequence") or []),
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
        "steps": list(send_info.get("sequence") or []),
        "project_open_method": send_info.get("project_open_method", accelerator_mode),
        "sequence": list(send_info.get("sequence") or []),
    }
    return dialog, detect_info


def interact_with_open_file_dialog(
    dialog: Any,
    project_path: str,
    *,
    before_snapshot: dict[str, Any],
    after_snapshot_provider: Any,
    dialog_timeout: float = 8.0,
    project_open_method: str = PROJECT_OPEN_ACCELERATOR_MODE,
    project_open_sequence: list[str] | None = None,
    detected_dialog_snapshot: dict[str, Any] | None = None,
    dialog_context: dict[str, Any] | None = None,
) -> OpenProjectDialogResult:
    start = time.monotonic()
    path_entry_attempted = False
    path_entered = False
    confirm_attempted = False
    confirm_clicked = False
    dialog_closed = False
    project_state_changed = False
    detected_changes: list[str] = []
    observed_main_window_title_after_open = ""
    observed_project_path = None
    path_match_normalized = False
    helper_dialog_revalidated = False
    helper_dialog_ready_for_interaction = False
    received_context = {
        "dialog_already_verified": bool((dialog_context or {}).get("dialog_already_verified")),
        "dialog_handle": (dialog_context or {}).get("dialog_handle"),
        "dialog_title": (dialog_context or {}).get("dialog_title"),
        "dialog_class": (dialog_context or {}).get("dialog_class"),
        "dialog_process_id": (dialog_context or {}).get("dialog_process_id"),
    }

    try:
        logger.info("interact_with_open_file_dialog detected_dialog_snapshot={}", detected_dialog_snapshot)
        logger.info("interact_with_open_file_dialog helper_received_dialog_context={}", received_context)

        helper_dialog_revalidated = bool(
            dialog is not None
            and bool(_safe_call(dialog, "exists", True))
            and bool(_safe_call(dialog, "is_visible", True))
        )
        logger.info("interact_with_open_file_dialog helper_dialog_revalidated={}", helper_dialog_revalidated)
        helper_dialog_ready_for_interaction = helper_dialog_revalidated and bool(received_context.get("dialog_already_verified"))
        logger.info("interact_with_open_file_dialog helper_dialog_ready_for_interaction={}", helper_dialog_ready_for_interaction)
        if not helper_dialog_revalidated:
            return OpenProjectDialogResult(
                success=False,
                path=project_path,
                dialog_found=bool(received_context.get("dialog_already_verified")),
                path_entry_attempted=False,
                path_entered=False,
                confirm_attempted=False,
                confirm_clicked=False,
                dialog_closed=False,
                project_state_changed=False,
                detected_changes=[],
                project_open_method=project_open_method,
                project_open_sequence=project_open_sequence,
                detected_dialog_snapshot=detected_dialog_snapshot,
                helper_received_dialog_context=received_context,
                helper_dialog_revalidated=False,
                helper_dialog_ready_for_interaction=False,
                error="dialog_revalidation_failed",
            )

        path_entry_attempted = True
        path_entered, path_info = set_file_dialog_path(dialog, project_path)
        logger.info("interact_with_open_file_dialog path set result={}", path_info)
        logger.info("project_open_step step=file_dialog_path_entered value={} details={}", path_entered, path_info)
        if not path_entered:
            return OpenProjectDialogResult(
                success=False,
                path=project_path,
                dialog_found=True,
                path_entry_attempted=path_entry_attempted,
                path_entered=False,
                confirm_attempted=False,
                confirm_clicked=False,
                dialog_closed=False,
                project_state_changed=False,
                detected_changes=[],
                project_open_method=project_open_method,
                project_open_sequence=project_open_sequence,
                error="file_name_control_not_found" if str(path_info.get("method") or "") == "failed" else "path_entry_failed",
                detected_dialog_snapshot=detected_dialog_snapshot,
                helper_received_dialog_context=received_context,
                helper_dialog_revalidated=helper_dialog_revalidated,
                helper_dialog_ready_for_interaction=helper_dialog_ready_for_interaction,
            )

        confirm_attempted = True
        confirm_clicked, confirm_info = confirm_file_dialog_open(dialog)
        logger.info("interact_with_open_file_dialog confirm result={}", confirm_info)
        logger.info("project_open_step step=file_dialog_confirm_clicked value={} details={}", confirm_clicked, confirm_info)
        if not confirm_clicked:
            return OpenProjectDialogResult(
                success=False,
                path=project_path,
                dialog_found=True,
                path_entry_attempted=path_entry_attempted,
                path_entered=True,
                confirm_attempted=confirm_attempted,
                confirm_clicked=False,
                dialog_closed=False,
                project_state_changed=False,
                detected_changes=[],
                project_open_method=project_open_method,
                project_open_sequence=project_open_sequence,
                error="confirm_action_failed",
                detected_dialog_snapshot=detected_dialog_snapshot,
                helper_received_dialog_context=received_context,
                helper_dialog_revalidated=helper_dialog_revalidated,
                helper_dialog_ready_for_interaction=helper_dialog_ready_for_interaction,
            )

        close_deadline = time.monotonic() + max(1.0, dialog_timeout)
        while time.monotonic() < close_deadline:
            if not bool(_safe_call(dialog, "exists", True)) or not bool(_safe_call(dialog, "is_visible", True)):
                dialog_closed = True
                break
            time.sleep(0.1)
        logger.info("project_open_step step=dialog_closed value={}", dialog_closed)

        after_snapshot = after_snapshot_provider()
        project_state_changed, detected_changes = detect_project_state_changed(before_snapshot, after_snapshot)
        observed_main_window_title_after_open = str(after_snapshot.get("main_window_title") or "")
        verification = _build_project_path_verification(
            expected_project_path=project_path,
            observed_main_window_title=observed_main_window_title_after_open,
        )
        observed_project_path = verification.get("observed_project_path")
        path_match_normalized = bool(verification.get("path_match_normalized"))

        success = dialog_closed and project_state_changed and path_match_normalized
        elapsed = round(time.monotonic() - start, 3)
        logger.info(
            "interact_with_open_file_dialog completed success={} dialog_found={} path_entered={} confirm_clicked={} dialog_closed={} state_changed={} path_match_normalized={} changes={} elapsed_s={}",
            success,
            True,
            path_entered,
            confirm_clicked,
            dialog_closed,
            project_state_changed,
            path_match_normalized,
            detected_changes,
            elapsed,
        )
        error = None
        if not dialog_closed:
            error = "Dialog did not close after confirmation."
        elif not project_state_changed:
            error = "Dialog closed but runtime state did not change."
        elif not path_match_normalized:
            error = "Dialog closed and state changed, but the observed project path did not match the expected path."

        return OpenProjectDialogResult(
            success=success,
            path=project_path,
            dialog_found=True,
            path_entry_attempted=path_entry_attempted,
            path_entered=path_entered,
            confirm_attempted=confirm_attempted,
            confirm_clicked=confirm_clicked,
            dialog_closed=dialog_closed,
            project_state_changed=project_state_changed,
            detected_changes=detected_changes,
            project_open_method=project_open_method,
            project_open_sequence=project_open_sequence,
            detected_dialog_snapshot=detected_dialog_snapshot,
            helper_received_dialog_context=received_context,
            helper_dialog_revalidated=helper_dialog_revalidated,
            helper_dialog_ready_for_interaction=helper_dialog_ready_for_interaction,
            observed_main_window_title_after_open=observed_main_window_title_after_open,
            observed_project_path=observed_project_path,
            path_match_normalized=path_match_normalized,
            error=error,
        )
    except Exception as exc:
        logger.exception("interact_with_open_file_dialog failed")
        return OpenProjectDialogResult(
            success=False,
            path=project_path,
            dialog_found=True,
            path_entry_attempted=path_entry_attempted,
            path_entered=path_entered,
            confirm_attempted=confirm_attempted,
            confirm_clicked=confirm_clicked,
            dialog_closed=dialog_closed,
            project_state_changed=project_state_changed,
            detected_changes=detected_changes,
            project_open_method=project_open_method,
            project_open_sequence=project_open_sequence,
            detected_dialog_snapshot=detected_dialog_snapshot,
            helper_received_dialog_context=received_context,
            helper_dialog_revalidated=helper_dialog_revalidated,
            helper_dialog_ready_for_interaction=helper_dialog_ready_for_interaction,
            observed_main_window_title_after_open=observed_main_window_title_after_open,
            observed_project_path=observed_project_path,
            path_match_normalized=path_match_normalized,
            error=str(exc),
        )


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
    project_open_method = PROJECT_OPEN_ACCELERATOR_MODE
    project_open_sequence = project_open_accelerator_sequence()

    try:
        main_window = prepare_main_window_for_menu_interaction()
        ensure_main_window_foreground_before_click(
            action_label="open_project_file_via_dialog",
            allow_dialog=True,
            allow_stale_wrapper_refresh=True,
        )
        main_window = get_cached_main_window() if main_window is None else main_window
        process_id = _safe_call(main_window, "process_id", None)
        dialog = None
        detect_info: dict[str, Any] = {}
        accelerator_error: str | None = None

        dialog, detect_info = trigger_open_project_dialog_from_default_state(
            process_id=process_id,
            dialog_timeout=min(dialog_timeout, 3.0),
        )
        dialog_found = bool(detect_info.get("dialog_found"))
        project_open_method = str(detect_info.get("project_open_method") or project_open_method)
        project_open_sequence = list(detect_info.get("sequence") or project_open_sequence)
        logger.info(
            "project_open_step step=open_file_dialog_detected value={} detect_info={}",
            dialog_found,
            detect_info,
        )
        if dialog_found:
            logger.info("open_project_file_via_dialog accelerator success detect_info={}", detect_info)
        else:
            accelerator_error = detect_info.get("error")
            logger.info("open_project_file_via_dialog accelerator did not open dialog detect_info={}", detect_info)
        if dialog is None:
            return OpenProjectDialogResult(
                success=False,
                path=project_path,
                dialog_found=dialog_found,
                path_entry_attempted=False,
                path_entered=False,
                confirm_attempted=False,
                confirm_clicked=False,
                dialog_closed=False,
                project_state_changed=False,
                detected_changes=[],
                project_open_method=project_open_method,
                project_open_sequence=project_open_sequence,
                error=accelerator_error or f"Open-file dialog not detected after {'+'.join(project_open_sequence)} accelerator.",
            )
        detected_dialog_snapshot = detect_info.get("selected_candidate")
        result = interact_with_open_file_dialog(
            dialog,
            project_path,
            before_snapshot=before_snapshot,
            after_snapshot_provider=after_snapshot_provider,
            dialog_timeout=dialog_timeout,
            project_open_method=project_open_method,
            project_open_sequence=project_open_sequence,
            detected_dialog_snapshot=detected_dialog_snapshot,
            dialog_context={
                "dialog_already_verified": dialog_found,
                "dialog_handle": (detected_dialog_snapshot or {}).get("handle"),
                "dialog_title": (detected_dialog_snapshot or {}).get("title"),
                "dialog_class": (detected_dialog_snapshot or {}).get("class_name"),
                "dialog_process_id": (detected_dialog_snapshot or {}).get("process_id"),
            },
        )
        logger.info(
            "open_project_file_via_dialog completed success={} dialog_found={} path_entered={} confirm_clicked={} dialog_closed={} path_match_normalized={} elapsed_s={}",
            result.success,
            result.dialog_found,
            result.path_entered,
            result.confirm_clicked,
            result.dialog_closed,
            result.path_match_normalized,
            round(time.monotonic() - start, 3),
        )
        return result
    except Exception as exc:
        logger.exception("open_project_file_via_dialog failed")
        return OpenProjectDialogResult(
            success=False,
            path=project_path,
            dialog_found=dialog_found,
            path_entry_attempted=False,
            path_entered=False,
            confirm_attempted=False,
            confirm_clicked=False,
            dialog_closed=False,
            project_state_changed=False,
            detected_changes=[],
            project_open_method=project_open_method,
            project_open_sequence=project_open_sequence,
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

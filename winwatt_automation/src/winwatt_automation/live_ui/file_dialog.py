from __future__ import annotations

import time
from dataclasses import asdict, dataclass
import os
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
    binding_strategy_used: str | None = None
    dialog_handle_available: bool = False
    dialog_binding_candidates_count: int = 0
    binding_failed_reason: str | None = None
    observed_main_window_title_after_open: str | None = None
    observed_project_path: str | None = None
    path_match_normalized: bool = False
    path_entry_diagnostics: dict[str, Any] | None = None
    error: str | None = None


def _safe_member(obj: Any, name: str, default: Any = None) -> Any:
    attr = getattr(obj, name, None)
    if attr is None:
        return default
    if callable(attr):
        try:
            return attr()
        except Exception:
            return default
    return attr


def _safe_call(obj: Any, method: str, default: Any = None) -> Any:
    value = _safe_member(obj, method, default)
    return default if callable(value) else value


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
    title = str(_safe_member(window, "window_text", "") or "").strip()
    class_name = str(_safe_member(window, "class_name", "") or "").strip()
    process_id = _safe_member(window, "process_id", None)
    handle = _safe_member(window, "handle", None)
    rectangle = _safe_member(window, "rectangle", None)
    rect_payload = None
    if rectangle is not None:
        try:
            rect_payload = {
                "left": int(rectangle.left),
                "top": int(rectangle.top),
                "right": int(rectangle.right),
                "bottom": int(rectangle.bottom),
            }
        except Exception:
            rect_payload = None
    return {
        "title": title,
        "title_lower": title.lower(),
        "class_name": class_name,
        "class_lower": class_name.lower(),
        "process_id": int(process_id) if process_id is not None else None,
        "handle": int(handle) if handle is not None else None,
        "rectangle": rect_payload,
    }




def _rectangles_roughly_match(first: dict[str, Any] | None, second: dict[str, Any] | None, *, tolerance: int = 25) -> bool:
    if not first or not second:
        return False
    for key in ("left", "top", "right", "bottom"):
        if key not in first or key not in second:
            return False
        if abs(int(first[key]) - int(second[key])) > tolerance:
            return False
    return True


def _dialog_snapshot_matches_context(candidate: dict[str, Any], expected: dict[str, Any] | None, context: dict[str, Any]) -> bool:
    expected = expected or {}
    expected_pid = context.get("dialog_process_id") or expected.get("process_id")
    expected_title = context.get("dialog_title") or expected.get("title")
    expected_class = context.get("dialog_class") or expected.get("class_name")
    expected_rect = expected.get("rectangle")
    if expected_pid is not None and candidate.get("process_id") != expected_pid:
        return False
    if expected_title and str(candidate.get("title") or "").strip() != str(expected_title).strip():
        return False
    if expected_class and str(candidate.get("class_name") or "").strip() != str(expected_class).strip():
        return False
    if expected_rect and not _rectangles_roughly_match(candidate.get("rectangle"), expected_rect):
        return False
    return True


def _resolve_dialog_wrapper_for_interaction(dialog: Any, *, detected_dialog_snapshot: dict[str, Any] | None, dialog_context: dict[str, Any] | None) -> tuple[Any | None, dict[str, Any]]:
    context = dialog_context or {}
    handle = context.get("dialog_handle") or (detected_dialog_snapshot or {}).get("handle")
    diagnostics = {
        "binding_strategy_used": None,
        "dialog_handle_available": handle is not None,
        "dialog_binding_candidates_count": 0,
        "binding_failed_reason": None,
        "wrapper_ready": False,
    }

    if dialog is not None and bool(_safe_call(dialog, "exists", True)) and bool(_safe_call(dialog, "is_visible", True)):
        diagnostics["binding_strategy_used"] = "provided_wrapper"
        diagnostics["wrapper_ready"] = True
        return dialog, diagnostics

    try:
        from pywinauto import Desktop
    except Exception:
        diagnostics["binding_failed_reason"] = "desktop_api_unavailable"
        return None, diagnostics

    windows = [window for window in Desktop(backend="uia").windows(top_level_only=True) if bool(_safe_call(window, "is_visible", False))]
    snapshots = [(window, _window_snapshot(window)) for window in windows]

    if handle is not None:
        for window, snapshot in snapshots:
            if snapshot.get("handle") == handle:
                diagnostics["binding_strategy_used"] = "handle"
                diagnostics["dialog_binding_candidates_count"] = 1
                diagnostics["wrapper_ready"] = True
                return window, diagnostics

    locator_matches = [(window, snapshot) for window, snapshot in snapshots if _dialog_snapshot_matches_context(snapshot, detected_dialog_snapshot, context)]
    diagnostics["dialog_binding_candidates_count"] = len(locator_matches)
    if locator_matches:
        diagnostics["binding_strategy_used"] = "pid_class_title_rect"
        diagnostics["wrapper_ready"] = True
        return locator_matches[0][0], diagnostics

    try:
        foreground = Desktop(backend="uia").get_active()
    except Exception:
        foreground = None
    if foreground is not None:
        foreground_snapshot = _window_snapshot(foreground)
        if _dialog_snapshot_matches_context(foreground_snapshot, detected_dialog_snapshot, context):
            diagnostics["binding_strategy_used"] = "foreground_top_level_dialog"
            diagnostics["dialog_binding_candidates_count"] = max(diagnostics["dialog_binding_candidates_count"], 1)
            diagnostics["wrapper_ready"] = True
            return foreground, diagnostics

    diagnostics["binding_failed_reason"] = "no_matching_dialog_wrapper_found"
    return None, diagnostics

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


def _control_class_name(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return str(getattr(info, "class_name", "") or "").strip()


def _normalized_label_text(value: str | None) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    return " ".join(text.replace(":", " ").split())


def _is_label_like_text(value: str | None) -> bool:
    normalized = _normalized_label_text(value)
    return normalized in {"fájlnév", "fajlnev", "file name", "filename"}


def _is_control_editable(control: Any) -> bool:
    control_type = _control_type(control)
    if control_type not in {"edit", "combobox"}:
        return False
    if not bool(_safe_call(control, "is_enabled", False)):
        return False
    if bool(_safe_call(control, "is_read_only", False)):
        return False
    for attr in ("is_editable", "is_keyboard_focusable", "has_keyboard_focus", "is_focusable"):
        value = _safe_call(control, attr, None)
        if value is not None:
            return bool(value)
    iface_value = getattr(control, "iface_value", None)
    if iface_value is not None:
        return True
    legacy_props = getattr(control, "legacy_properties", None)
    if callable(legacy_props):
        try:
            props = legacy_props()
        except Exception:
            props = None
        if isinstance(props, dict):
            state = str(props.get("State") or "").lower()
            if "readonly" in state:
                return False
            if state:
                return True
    class_name = _control_class_name(control).lower()
    return control_type == "edit" and class_name != "static"


def _describe_filename_control(control: Any, reason: str | None) -> dict[str, Any]:
    return {
        "file_name_control_class_name": _control_class_name(control) if control is not None else "",
        "file_name_control_control_type": _control_type(control) if control is not None else "",
        "file_name_control_is_editable": _is_control_editable(control) if control is not None else False,
        "file_name_control_is_label_like": _is_label_like_text(_control_name(control) if control is not None else ""),
        "file_name_control_locator_reason": reason,
    }


def _rectangle_payload(control: Any) -> dict[str, int] | None:
    rectangle = _safe_call(control, "rectangle", None)
    if rectangle is None:
        return None
    try:
        return {
            "left": int(rectangle.left),
            "top": int(rectangle.top),
            "right": int(rectangle.right),
            "bottom": int(rectangle.bottom),
        }
    except Exception:
        return None


def _control_summary(control: Any) -> dict[str, Any] | None:
    if control is None:
        return None
    info = getattr(control, "element_info", control)
    return {
        "control_type": _control_type(control),
        "class_name": _control_class_name(control),
        "friendly_class_name": str(_safe_member(control, "friendly_class_name", "") or "").strip(),
        "automation_id": str(getattr(info, "automation_id", "") or "").strip(),
        "name": _control_name(control),
        "handle": _safe_call(control, "handle", None),
        "rectangle": _rectangle_payload(control),
    }


def _selected_control_telemetry(control: Any) -> dict[str, Any]:
    summary = _control_summary(control) or {}
    parent = _safe_call(control, "parent", None) if control is not None else None
    parent_summary = _control_summary(parent)
    sibling_summaries: list[dict[str, Any]] = []
    if parent is not None:
        children = getattr(parent, "children", None)
        if callable(children):
            for sibling in children():
                if sibling is control:
                    continue
                sibling_summary = _control_summary(sibling) or {}
                if not any(sibling_summary.get(key) for key in ("name", "automation_id", "class_name", "control_type")):
                    continue
                sibling_summaries.append(sibling_summary)
                if len(sibling_summaries) >= 5:
                    break
    return {
        "selected_control_control_type": summary.get("control_type", ""),
        "selected_control_class_name": summary.get("class_name", ""),
        "selected_control_friendly_class_name": summary.get("friendly_class_name", ""),
        "selected_control_automation_id": summary.get("automation_id", ""),
        "selected_control_name": summary.get("name", ""),
        "selected_control_handle": summary.get("handle"),
        "selected_control_rectangle": summary.get("rectangle"),
        "selected_control_parent_summary": parent_summary,
        "selected_control_sibling_summaries": sibling_summaries,
    }


def _iter_candidate_edits(control: Any) -> list[Any]:
    candidates: list[Any] = []
    if _control_type(control) == "edit":
        candidates.append(control)
    if _control_type(control) == "combobox":
        children = getattr(control, "children", None)
        if callable(children):
            candidates.extend(item for item in children() if _control_type(item) == "edit")
    return candidates


def _pick_viable_filename_control(candidates: list[tuple[Any, str]]) -> tuple[Any | None, str | None]:
    for control, reason in candidates:
        if control is None:
            continue
        if _is_label_like_text(_control_name(control)) or _is_label_like_text(_read_edit_value(control)):
            continue
        if not _is_control_editable(control):
            continue
        return control, reason
    return None, None


def _find_filename_edit_control(dialog: Any) -> tuple[Any | None, str | None]:
    descendants = getattr(dialog, "descendants", None)
    if not callable(descendants):
        return None, None

    controls = list(descendants())
    edits = [item for item in controls if _control_type(item) == "edit"]
    if not edits:
        edits = []

    filename_rows: list[tuple[Any, str]] = []
    for item in controls:
        item_name = _control_name(item)
        if not any(hint in item_name.lower() for hint in FILENAME_EDIT_HINTS):
            continue
        if _control_type(item) in {"edit", "combobox"}:
            reason = "combo_named_like_file_name_child_edit" if _control_type(item) == "combobox" else "edit_named_like_file_name"
            for candidate in _iter_candidate_edits(item):
                filename_rows.append((candidate, reason))
            continue
        if _is_label_like_text(item_name):
            parent = _safe_call(item, "parent", None)
            siblings: list[Any] = []
            if parent is not None:
                children = getattr(parent, "children", None)
                if callable(children):
                    siblings = list(children())
            for sibling in siblings:
                if sibling is item:
                    continue
                for candidate in _iter_candidate_edits(sibling):
                    filename_rows.append((candidate, "label_neighbor_edit"))

    chosen, strategy = _pick_viable_filename_control(filename_rows)
    if chosen is not None:
        return chosen, strategy

    named_edits = [
        item for item in edits
        if any(hint in _control_name(item).lower() for hint in FILENAME_EDIT_HINTS)
    ]
    chosen, strategy = _pick_viable_filename_control([(item, "edit_named_like_file_name") for item in named_edits])
    if chosen is not None:
        return chosen, strategy

    combo_named = [
        item for item in controls
        if _control_type(item) == "combobox"
        and any(hint in _control_name(item).lower() for hint in FILENAME_EDIT_HINTS)
    ]
    chosen, strategy = _pick_viable_filename_control(
        [(candidate, "combo_named_like_file_name_child_edit") for combo in combo_named for candidate in _iter_candidate_edits(combo)]
    )
    if chosen is not None:
        return chosen, strategy

    chosen, strategy = _pick_viable_filename_control([(item, "last_enabled_edit_fallback") for item in edits])
    if chosen is not None:
        return chosen, strategy
    return None, None


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


def _read_edit_value_variants(edit: Any) -> dict[str, str]:
    info = getattr(edit, "element_info", edit)
    window_text = str(_safe_call(edit, "window_text", "") or "")

    value_pattern = ""
    iface_value = getattr(edit, "iface_value", None)
    if iface_value is not None:
        try:
            value_pattern = str(getattr(iface_value, "CurrentValue", "") or "")
        except Exception:
            value_pattern = ""

    legacy_text = ""
    legacy_value = _safe_call(edit, "legacy_properties", None)
    if isinstance(legacy_value, dict):
        legacy_text = str(legacy_value.get("Value") or legacy_value.get("Name") or "")
    elif callable(getattr(edit, "legacy_properties", None)):
        try:
            legacy_props = edit.legacy_properties()
        except Exception:
            legacy_props = None
        if isinstance(legacy_props, dict):
            legacy_text = str(legacy_props.get("Value") or legacy_props.get("Name") or "")

    if not legacy_text:
        legacy_text = str(getattr(info, "rich_text", "") or "")

    return {
        "window_text": window_text,
        "get_value": value_pattern,
        "legacy": legacy_text,
    }


def _preferred_actual_path(value_variants: dict[str, str]) -> str:
    for key in ("get_value", "window_text", "legacy"):
        value = str(value_variants.get(key) or "")
        if value:
            return value
    return ""


def _classify_path_mismatch(*, expected_raw: str, actual_raw: str, actual_variants: dict[str, str], path_match_normalized: bool) -> str:
    if path_match_normalized:
        return ""
    normalized_expected = _normalize_project_path(expected_raw) or ""
    normalized_actual = _normalize_project_path(actual_raw) or ""
    if not normalized_actual:
        return "empty_after_write"
    if _is_label_like_text(actual_raw):
        return "label_text_detected"
    expected_ext = os.path.splitext(normalized_expected)[1]
    actual_ext = os.path.splitext(normalized_actual)[1]
    if expected_ext and not actual_ext:
        if normalized_actual.endswith("\\") or "\\" in normalized_actual:
            return "directory_only"
        return "extension_missing"
    if expected_ext and actual_ext != expected_ext:
        return "extension_missing"
    if normalized_expected and normalized_actual and normalized_actual in normalized_expected and normalized_actual != normalized_expected:
        return "partial_path_only"
    if any((_normalize_project_path(value) or "") != normalized_actual for value in actual_variants.values() if str(value or "").strip()):
        return "value_changed_after_delay"
    return "unknown"


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


def _set_clipboard_text(value: str) -> bool:
    if os.name != "nt":
        return False

    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        GMEM_MOVEABLE = 0x0002
        CF_UNICODETEXT = 13

        if not user32.OpenClipboard(None):
            return False
        try:
            if not user32.EmptyClipboard():
                return False

            text = str(value)
            buffer = ctypes.create_unicode_buffer(text)
            size_bytes = ctypes.sizeof(buffer)
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size_bytes)
            if not handle:
                return False

            locked = kernel32.GlobalLock(handle)
            if not locked:
                kernel32.GlobalFree(handle)
                return False
            try:
                ctypes.memmove(locked, ctypes.addressof(buffer), size_bytes)
            finally:
                kernel32.GlobalUnlock(handle)

            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return False


def _paste_path_with_hotkey(dialog: Any, project_path: str, *, hotkey: str) -> tuple[bool, dict[str, Any]]:
    from pywinauto import keyboard

    clipboard_ready = _set_clipboard_text(project_path)

    try:
        keyboard.send_keys(hotkey)
        time.sleep(0.05)
        keyboard.send_keys("^a{BACKSPACE}")
        if clipboard_ready:
            keyboard.send_keys("^v")
        else:
            keyboard.send_keys(project_path, with_spaces=True)
        time.sleep(0.05)
        refreshed_edit, refreshed_strategy = _find_filename_edit_control(dialog)
        if refreshed_edit is not None and project_path.lower() in _read_edit_value(refreshed_edit).lower():
            logger.info(
                "set_file_dialog_path hotkey success hotkey={} entry_method={}",
                hotkey,
                "clipboard_paste" if clipboard_ready else "typed_fallback",
            )
            return True, {
                "method": "hotkey",
                "hotkey": hotkey,
                "entry_method": "clipboard_paste" if clipboard_ready else "typed_fallback",
                "edit_name": _control_name(refreshed_edit),
                "file_name_control_strategy": refreshed_strategy,
            }
    except Exception:
        pass

    return False, {
        "method": "hotkey_failed",
        "hotkey": hotkey,
        "entry_method": "clipboard_paste" if clipboard_ready else "typed_fallback",
    }


def set_file_dialog_path(dialog: Any, project_path: str) -> tuple[bool, dict[str, Any]]:
    try:
        dialog.set_focus()
    except Exception:
        pass

    edit, strategy = _find_filename_edit_control(dialog)
    info: dict[str, Any] = {
        "method": "failed",
        "file_name_control_strategy": strategy,
        "file_name_control_found": edit is not None,
        "file_name_control_value_before": _read_edit_value(edit) if edit is not None else "",
        "file_name_control_value_after": "",
        "file_name_value_matches_expected": False,
        "location_bar_touched": False,
        "confirm_skipped_reason": None,
        "expected_path_raw": project_path,
        "expected_path_normalized": _normalize_project_path(project_path),
        "actual_path_raw": "",
        "actual_path_normalized": None,
        "path_match_normalized": False,
        "mismatch_reason": "unknown",
        "path_entry_strategy_selected": "direct_edit_then_type_keys_fallback",
        "path_entry_strategy_attempted": [],
        "path_entry_strategy_succeeded": None,
        "paste_attempted": False,
        "paste_sent": False,
        "typed_attempted": False,
        "typed_sent": False,
        "direct_edit_attempted": False,
        "direct_edit_sent": False,
        "typed_fallback_skipped_reason": None,
        "direct_edit_fallback_skipped_reason": None,
        "raw_value_before": {},
        "raw_value_after_immediate": {},
        "raw_value_after_300ms": {},
        "raw_value_after_1000ms": {},
    }
    info.update(_describe_filename_control(edit, strategy))
    info.update(_selected_control_telemetry(edit))

    if edit is None:
        info["confirm_skipped_reason"] = "file_name_control_not_found"
        logger.info("set_file_dialog_path file_name_control_found=false strategy={} confirm_skipped_reason={}", strategy, info["confirm_skipped_reason"])
        return False, info

    info["raw_value_before"] = _read_edit_value_variants(edit)

    def refresh_validation(*, delay_s: float, target_key: str) -> None:
        if delay_s > 0:
            time.sleep(delay_s)
        variants = _read_edit_value_variants(edit)
        info[target_key] = variants
        if target_key == "raw_value_after_immediate":
            info["file_name_control_value_after"] = _preferred_actual_path(variants)
            info["actual_path_raw"] = info["file_name_control_value_after"]
            info["actual_path_normalized"] = _normalize_project_path(info["actual_path_raw"])
            info["path_match_normalized"] = bool(
                info["expected_path_normalized"] and info["expected_path_normalized"] == info["actual_path_normalized"]
            )
            info["file_name_value_matches_expected"] = info["path_match_normalized"]
        elif target_key == "raw_value_after_1000ms":
            final_actual = _preferred_actual_path(variants)
            info["actual_path_raw"] = final_actual
            info["actual_path_normalized"] = _normalize_project_path(final_actual)
            info["path_match_normalized"] = bool(
                info["expected_path_normalized"] and info["expected_path_normalized"] == info["actual_path_normalized"]
            )
            info["file_name_value_matches_expected"] = info["path_match_normalized"]
            info["mismatch_reason"] = _classify_path_mismatch(
                expected_raw=project_path,
                actual_raw=final_actual,
                actual_variants={
                    "immediate": _preferred_actual_path(info["raw_value_after_immediate"]),
                    "after_300ms": _preferred_actual_path(info["raw_value_after_300ms"]),
                    "after_1000ms": final_actual,
                },
                path_match_normalized=info["path_match_normalized"],
            )

    try:
        edit.set_focus()
    except Exception:
        pass

    info["direct_edit_attempted"] = True
    info["path_entry_strategy_attempted"].append("direct_edit")
    if _write_to_edit(edit, project_path):
        info["method"] = "direct_edit"
        info["direct_edit_sent"] = True
        info["path_entry_strategy_succeeded"] = "direct_edit"
        refresh_validation(delay_s=0.0, target_key="raw_value_after_immediate")
        refresh_validation(delay_s=0.3, target_key="raw_value_after_300ms")
        refresh_validation(delay_s=0.7, target_key="raw_value_after_1000ms")
        if info["file_name_value_matches_expected"]:
            logger.info(
                "set_file_dialog_path telemetry={}",
                info,
            )
            return True, info
    else:
        info["direct_edit_fallback_skipped_reason"] = "direct_edit_write_failed"

    from pywinauto import keyboard
    try:
        edit.set_focus()
    except Exception:
        pass
    info["typed_attempted"] = True
    info["path_entry_strategy_attempted"].append("typed_edit_fallback")
    try:
        keyboard.send_keys("^a{BACKSPACE}")
        keyboard.send_keys(project_path, with_spaces=True)
        info["typed_sent"] = True
    except Exception:
        info["confirm_skipped_reason"] = "file_name_write_failed"
        return False, info

    info["method"] = "typed_edit_fallback"
    if info["path_entry_strategy_succeeded"] is None:
        info["path_entry_strategy_succeeded"] = "typed_edit_fallback"
    refresh_validation(delay_s=0.0, target_key="raw_value_after_immediate")
    refresh_validation(delay_s=0.3, target_key="raw_value_after_300ms")
    refresh_validation(delay_s=0.7, target_key="raw_value_after_1000ms")
    if not info["file_name_value_matches_expected"]:
        info["confirm_skipped_reason"] = "file_name_value_mismatch"
    if info["direct_edit_sent"]:
        info["mismatch_reason"] = "value_changed_after_delay" if not info["path_match_normalized"] else info["mismatch_reason"]
    logger.info(
        "set_file_dialog_path telemetry={}",
        info,
    )
    return bool(info["file_name_value_matches_expected"]), info


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


def confirm_file_dialog_open(dialog: Any, *, prefer_enter: bool = False) -> tuple[bool, dict[str, Any]]:
    from pywinauto import keyboard

    try:
        dialog.set_focus()
    except Exception:
        pass

    if prefer_enter:
        try:
            keyboard.send_keys("{ENTER}")
            logger.info("confirm_file_dialog_open used ENTER preferred path")
            return True, {"method": "enter_preferred"}
        except Exception as exc:
            logger.info("confirm_file_dialog_open ENTER preferred path failed error={}", exc)

    try:
        keyboard.send_keys("{ENTER}")
        logger.info("confirm_file_dialog_open used ENTER default path")
        return True, {"method": "enter_default"}
    except Exception as exc:
        logger.info("confirm_file_dialog_open ENTER default path failed error={}", exc)

    button = find_confirm_open_button(dialog)
    if button is not None:
        try:
            invoke = getattr(button, "invoke", None)
            if callable(invoke):
                invoke()
                logger.info("confirm_file_dialog_open invoked button after ENTER failures button={}", _control_name(button))
                return True, {"method": "button_invoke_fallback", "button": _control_name(button)}
            button.click_input()
            logger.info("confirm_file_dialog_open clicked button after ENTER failures button={}", _control_name(button))
            return True, {"method": "button_fallback", "button": _control_name(button)}
        except Exception as button_exc:
            return False, {"method": "failed", "error": str(button_exc)}

    return False, {"method": "failed", "error": "enter_and_button_confirm_failed"}


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
    binding_strategy_used = None
    dialog_handle_available = False
    dialog_binding_candidates_count = 0
    binding_failed_reason = None
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

        dialog, binding_diagnostics = _resolve_dialog_wrapper_for_interaction(
            dialog,
            detected_dialog_snapshot=detected_dialog_snapshot,
            dialog_context=received_context,
        )
        binding_strategy_used = binding_diagnostics.get("binding_strategy_used")
        dialog_handle_available = bool(binding_diagnostics.get("dialog_handle_available"))
        dialog_binding_candidates_count = int(binding_diagnostics.get("dialog_binding_candidates_count") or 0)
        binding_failed_reason = binding_diagnostics.get("binding_failed_reason")
        logger.info("interact_with_open_file_dialog binding_strategy_used={}", binding_strategy_used)
        logger.info("interact_with_open_file_dialog dialog_handle_available={}", dialog_handle_available)
        logger.info("interact_with_open_file_dialog dialog_binding_candidates_count={}", dialog_binding_candidates_count)
        logger.info("interact_with_open_file_dialog binding_failed_reason={}", binding_failed_reason)

        helper_dialog_revalidated = bool(
            binding_diagnostics.get("wrapper_ready")
            or (
                dialog is not None
                and bool(_safe_call(dialog, "exists", True))
                and bool(_safe_call(dialog, "is_visible", True))
            )
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
                binding_strategy_used=binding_strategy_used,
                dialog_handle_available=dialog_handle_available,
                dialog_binding_candidates_count=dialog_binding_candidates_count,
                binding_failed_reason=binding_failed_reason,
                path_entry_diagnostics=None,
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
                binding_strategy_used=binding_strategy_used,
                dialog_handle_available=dialog_handle_available,
                dialog_binding_candidates_count=dialog_binding_candidates_count,
                binding_failed_reason=binding_failed_reason,
                path_entry_diagnostics=path_info,
            )

        if not bool(path_info.get("file_name_value_matches_expected", path_entered)):
            confirm_info = {"method": "skipped", "reason": path_info.get("confirm_skipped_reason") or "file_name_value_not_validated"}
            logger.info("interact_with_open_file_dialog confirm skipped reason={}", confirm_info["reason"])
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
                error="path_entry_validation_failed",
                detected_dialog_snapshot=detected_dialog_snapshot,
                helper_received_dialog_context=received_context,
                helper_dialog_revalidated=helper_dialog_revalidated,
                helper_dialog_ready_for_interaction=helper_dialog_ready_for_interaction,
                binding_strategy_used=binding_strategy_used,
                dialog_handle_available=dialog_handle_available,
                dialog_binding_candidates_count=dialog_binding_candidates_count,
                binding_failed_reason=binding_failed_reason,
                path_entry_diagnostics=path_info,
            )

        confirm_attempted = True
        confirm_clicked, confirm_info = confirm_file_dialog_open(dialog, prefer_enter=True)
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
                binding_strategy_used=binding_strategy_used,
                dialog_handle_available=dialog_handle_available,
                dialog_binding_candidates_count=dialog_binding_candidates_count,
                binding_failed_reason=binding_failed_reason,
                path_entry_diagnostics=path_info,
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
            binding_strategy_used=binding_strategy_used,
            dialog_handle_available=dialog_handle_available,
            dialog_binding_candidates_count=dialog_binding_candidates_count,
            binding_failed_reason=binding_failed_reason,
            observed_main_window_title_after_open=observed_main_window_title_after_open,
            observed_project_path=observed_project_path,
            path_match_normalized=path_match_normalized,
            path_entry_diagnostics=path_info,
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
            binding_strategy_used=binding_strategy_used,
            dialog_handle_available=dialog_handle_available,
            dialog_binding_candidates_count=dialog_binding_candidates_count,
            binding_failed_reason=binding_failed_reason,
            observed_main_window_title_after_open=observed_main_window_title_after_open,
            observed_project_path=observed_project_path,
            path_match_normalized=path_match_normalized,
            path_entry_diagnostics=path_info if 'path_info' in locals() else None,
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

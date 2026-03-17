from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Callable

from loguru import logger

from winwatt_automation.live_ui import menu_helpers
from winwatt_automation.dialog_explorer.dialog_explorer import explore_dialog
from winwatt_automation.live_ui.app_connector import (
    ensure_main_window_foreground_before_click,
    get_cached_main_window,
    is_winwatt_foreground_context,
)
from winwatt_automation.live_ui.file_dialog import open_project_file_via_dialog_dict
from winwatt_automation.runtime_mapping.models import (
    RuntimeActionResult,
    RuntimeDialogRecord,
    RuntimeMenuNode,
    RuntimeMenuRow,
    RuntimeStateDiff,
    RuntimeStateMap,
    RuntimeStateSnapshot,
    RuntimeWindowRecord,
)
from winwatt_automation.runtime_mapping.menu_text import clean_menu_title, normalize_menu_title
from winwatt_automation.runtime_mapping.safety import classify_safety, is_action_allowed
from winwatt_automation.runtime_mapping.serializers import ensure_output_dirs, write_json
from winwatt_automation.runtime_mapping.timing import BASELINE_DELAY
from winwatt_automation.runtime_mapping.config import is_fast_mode
from winwatt_automation.live_ui.ui_cache import PopupState


DEFAULT_TOP_MENUS = ["Rendszer", "Fájl", "Jegyzékek", "Adatbázis...", "Beállítások", "Ablak", "Súgó"]
DEFAULT_TEST_PROJECT_PATH = str(Path(__file__).resolve().parents[2] / "tests" / "testwwp.wwp")

_TOP_MENU_CACHE: dict[str, Any] | None = None
_TOP_MENU_CACHE_MAIN_WINDOW_HANDLE: int | None = None



class UnrecoverableMainWindowError(RuntimeError):
    """Raised when the mapper loses WinWatt main window context and cannot recover."""


def _safe_call(obj: Any, method: str, default: Any = None) -> Any:
    attr = getattr(obj, method, None)
    if not callable(attr):
        return default
    try:
        return attr()
    except Exception:
        return default


def _list_visible_top_windows() -> list[dict[str, Any]]:
    try:
        from pywinauto import Desktop
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for window in Desktop(backend="uia").windows(top_level_only=True):
        if not bool(_safe_call(window, "is_visible", False)):
            continue
        rows.append({
            "title": _safe_call(window, "window_text", "") or "",
            "class_name": _safe_call(window, "class_name", "") or "",
            "process_id": _safe_call(window, "process_id", None),
            "handle": _safe_call(window, "handle", None),
        })
    return rows


def _close_secondary_windows(main_title: str) -> None:
    try:
        from pywinauto import Desktop, keyboard
    except Exception:
        return
    for window in Desktop(backend="uia").windows(top_level_only=True):
        if not bool(_safe_call(window, "is_visible", False)):
            continue
        title = _safe_call(window, "window_text", "") or ""
        if title == main_title:
            continue
        try:
            window.set_focus()
            keyboard.send_keys("{ESC}")
        except Exception:
            continue


def _extract_shortcut(text: str) -> tuple[str, str | None]:
    parts = [part.strip() for part in text.split("\t")]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return text, None


def _guess_enabled(row: dict[str, Any]) -> bool | None:
    if row.get("is_separator"):
        return None
    if "enabled" in row:
        value = row.get("enabled")
        return bool(value) if value is not None else None
    return True


def _row_to_node(
    state_id: str,
    top_menu: str,
    row: dict[str, Any],
    *,
    level: int,
    index: int,
    path: list[str],
    children: list[dict[str, Any]],
    opens_submenu: bool,
    opens_dialog: bool = False,
    skipped_by_safety: bool = False,
    reused_from_previous_state: bool = False,
) -> RuntimeMenuNode:
    title_raw = str(row.get("text") or "")
    title, shortcut = _extract_shortcut(title_raw)
    title_clean = clean_menu_title(title)
    normalized = normalize_menu_title(title)
    logger.debug('RAW_MENU_TITLE="{}" NORMALIZED_MENU_TITLE="{}"', title, normalized)
    normalized_path = [clean_menu_title(part) for part in path]
    safety = classify_safety(normalized_path)
    likely_destructive = safety == "blocked"
    likely_state_changing = safety in {"caution", "blocked"}
    enabled = _guess_enabled(row)
    if row.get("is_separator"):
        action_classification = "separator"
    elif reused_from_previous_state:
        action_classification = "reused_from_previous_state"
    elif skipped_by_safety:
        action_classification = "skipped_by_safety"
    elif opens_submenu:
        action_classification = "opens_submenu"
    elif opens_dialog:
        action_classification = "opens_dialog"
    elif enabled is False:
        action_classification = "disabled"
    elif enabled is True:
        action_classification = "enabled"
    else:
        action_classification = "unknown"

    return RuntimeMenuNode(
        state_id=state_id,
        title_raw=title,
        title=title_clean,
        normalized_title=normalized,
        path=normalized_path,
        level=level,
        index=index,
        enabled=enabled,
        separator=bool(row.get("is_separator")),
        shortcut=shortcut,
        opens_submenu=opens_submenu,
        opens_dialog=opens_dialog,
        likely_destructive=likely_destructive,
        likely_state_changing=likely_state_changing,
        action_classification=action_classification,
        skipped_by_safety=skipped_by_safety,
        children=children,
        debug={
            "geometry": dict(row.get("rectangle") or {}),
            "source_scope": str(row.get("source_scope") or ""),
            "fragments": list(row.get("fragments") or []),
            "top_menu": top_menu,
            "reused_from_previous_state": reused_from_previous_state,
        },
    )


def reset_top_menu_cache() -> None:
    global _TOP_MENU_CACHE, _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE
    _TOP_MENU_CACHE = None
    _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE = None


def get_canonical_top_menu_names(discovered_top_menus: list[str]) -> dict[str, Any]:
    global _TOP_MENU_CACHE, _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE

    try:
        main_window = get_cached_main_window()
    except Exception:
        main_window = None
    current_handle = _safe_call(main_window, "handle", None)
    if current_handle is not None and _TOP_MENU_CACHE is not None and _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE == current_handle:
        return _TOP_MENU_CACHE

    items: list[dict[str, str]] = []
    normalized_to_raw: dict[str, str] = {}

    for raw_name in discovered_top_menus:
        normalized = normalize_menu_title(raw_name)
        if not normalized or normalized in normalized_to_raw:
            continue
        clean_name = clean_menu_title(raw_name)
        normalized_to_raw[normalized] = raw_name
        items.append({"raw": raw_name, "clean": clean_name, "normalized": normalized})

    canonical = {
        "items": items,
        "normalized_to_raw": normalized_to_raw,
        "normalized_names": set(normalized_to_raw),
    }
    if current_handle is not None:
        _TOP_MENU_CACHE = canonical
        _TOP_MENU_CACHE_MAIN_WINDOW_HANDLE = current_handle
    logger.info("Canonical top-level menus [{}]: {}", len(items), [item["raw"] for item in items])
    return canonical


def is_top_menu_like_popup_row(row: dict[str, Any], canonical_top_menu_names: set[str]) -> bool:
    text = str(row.get("text") or "")
    normalized = normalize_menu_title(text)
    return bool(normalized and normalized in canonical_top_menu_names)


def should_restore_clean_menu_baseline(*, state_id: str, stage: str, popup_rows: list[dict[str, Any]] | None = None) -> bool:
    try:
        main_window = get_cached_main_window()
    except Exception:
        return False
    if not bool(_safe_call(main_window, "is_visible", False)):
        logger.warning("baseline_restore_needed state={} stage={} reason=main_window_hidden", state_id, stage)
        return True
    if not bool(_safe_call(main_window, "is_enabled", True)):
        logger.warning("baseline_restore_needed state={} stage={} reason=main_window_disabled", state_id, stage)
        return True
    if not is_winwatt_foreground_context(main_window, allow_dialog=True):
        logger.warning("baseline_restore_needed state={} stage={} reason=focus_lost", state_id, stage)
        return True
    if popup_rows is not None:
        try:
            current_rows = menu_helpers.capture_menu_popup_snapshot()
        except Exception:
            current_rows = []
        if bool(current_rows) != bool(popup_rows):
            logger.warning("baseline_restore_needed state={} stage={} reason=popup_snapshot_mismatch", state_id, stage)
            return True
    return False


def restore_clean_menu_baseline(*, state_id: str, stage: str) -> bool:
    logger.debug("baseline_restore start state={} stage={}", state_id, stage)
    try:
        ensure_main_window_foreground_before_click(action_label=f"baseline_restore:{state_id}:{stage}")
    except Exception as exc:
        main_window = get_cached_main_window()
        if bool(_safe_call(main_window, "is_visible", False)) and not bool(_safe_call(main_window, "is_enabled", True)):
            logger.warning("baseline_restore modal_pending state={} stage={} error={}", state_id, stage, exc)
            recovery = recover_after_project_open()
            if recovery.get("success"):
                logger.info("baseline_restore modal_pending_recovered state={} stage={}", state_id, stage)
            else:
                logger.error("baseline_restore failed state={} stage={} error={}", state_id, stage, exc)
                return False
        else:
            logger.error("baseline_restore failed state={} stage={} error={}", state_id, stage, exc)
            return False

    for _ in range(2):
        try:
            from pywinauto import keyboard

            keyboard.send_keys("{ESC}")
            time.sleep(BASELINE_DELAY)
        except Exception:
            pass

    try:
        menu_helpers.capture_menu_popup_snapshot()
    except Exception:
        pass

    logger.debug("baseline_restore success state={} stage={}", state_id, stage)
    return True


def capture_state_snapshot(state_id: str) -> RuntimeStateSnapshot:
    main_window = get_cached_main_window()
    return RuntimeStateSnapshot(
        state_id=state_id,
        process_id=_safe_call(main_window, "process_id", None),
        main_window_title=_safe_call(main_window, "window_text", "") or "",
        main_window_class=_safe_call(main_window, "class_name", "") or "",
        visible_top_windows=_list_visible_top_windows(),
        discovered_top_menus=menu_helpers.list_top_menu_items(),
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        main_window_enabled=bool(_safe_call(main_window, "is_enabled", False)),
        main_window_visible=bool(_safe_call(main_window, "is_visible", False)),
        foreground_window=_foreground_window_info(),
    )


def _build_menu_rows_from_popup_rows(
    state_id: str,
    top_menu: str,
    rows: list[dict[str, Any]],
    *,
    canonical_top_menu_names: set[str] | None = None,
) -> list[RuntimeMenuRow]:
    mapped: list[RuntimeMenuRow] = []
    for index, row in enumerate(rows):
        if canonical_top_menu_names and is_top_menu_like_popup_row(row, canonical_top_menu_names):
            logger.debug("popup row filtered as top-level overlap top_menu={} row_text={}", top_menu, row.get("text"))
            continue
        text = str(row.get("text") or "")
        title, _ = _extract_shortcut(text)
        title_clean = clean_menu_title(title)
        normalized_title = normalize_menu_title(title)
        logger.debug('RAW_MENU_TITLE="{}" NORMALIZED_MENU_TITLE="{}"', title, normalized_title)
        mapped.append(
            RuntimeMenuRow(
                state_id=state_id,
                top_menu=top_menu,
                row_index=index,
                menu_path=[clean_menu_title(top_menu), title_clean],
                text=title_clean,
                normalized_text=normalized_title,
                rectangle=dict(row.get("rectangle") or {}),
                center_x=int(row.get("center_x") or 0),
                center_y=int(row.get("center_y") or 0),
                is_separator=bool(row.get("is_separator")),
                source_scope=str(row.get("source_scope") or ""),
                fragments=list(row.get("fragments") or []),
                enabled_guess=_guess_enabled(row),
                discovered_in_state=state_id,
            )
        )
    return mapped


def _hover_row(row: dict[str, Any]) -> None:
    try:
        from pywinauto import mouse

        mouse.move(coords=(int(row.get("center_x") or 0), int(row.get("center_y") or 0)))
    except Exception:
        return


def _activate_row_for_exploration(row: RuntimeMenuRow, popup_rows: list[dict[str, Any]]) -> None:
    try:
        menu_helpers.click_structured_popup_row(popup_rows, row.row_index)
        return
    except Exception as exc:
        logger.debug("structured row click failed; fallback to hover path={} error={}", row.menu_path, exc)
    _hover_row(asdict(row))


def _detect_child_rows(parent_row: dict[str, Any], all_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rect = parent_row.get("rectangle") or {}
    p_left, p_top, p_right, p_bottom = int(rect.get("left", 0)), int(rect.get("top", 0)), int(rect.get("right", 0)), int(rect.get("bottom", 0))
    children: list[dict[str, Any]] = []
    for row in all_rows:
        r = row.get("rectangle") or {}
        left, top = int(r.get("left", 0)), int(r.get("top", 0))
        if left <= p_right + 8:
            continue
        if top < p_top - 120 or top > p_bottom + 220:
            continue
        children.append(row)
    children.sort(key=lambda item: int((item.get("rectangle") or {}).get("top", 0)))
    return children




def _foreground_window_info() -> dict[str, Any]:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {}
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title_buf = ctypes.create_unicode_buffer(512)
        class_buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title_buf, 511)
        user32.GetClassNameW(hwnd, class_buf, 255)
        return {"handle": int(hwnd), "title": title_buf.value or "", "class_name": class_buf.value or "", "process_id": int(pid.value)}
    except Exception:
        return {}


def _window_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("handle"),
        row.get("title") or "",
        row.get("class_name") or "",
        row.get("process_id"),
    )


def _list_process_visible_windows(process_id: int | None) -> list[dict[str, Any]]:
    if process_id is None:
        return []
    return [w for w in _list_visible_top_windows() if w.get("process_id") == process_id]


def _describe_controls(window: Any, limit: int = 20) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    try:
        descendants = _safe_call(window, "descendants", []) or []
    except Exception:
        return controls
    for child in descendants[:limit]:
        controls.append({
            "control_type": getattr(getattr(child, "element_info", None), "control_type", None),
            "name": _safe_call(child, "window_text", "") or "",
            "automation_id": getattr(getattr(child, "element_info", None), "automation_id", None),
        })
    return controls


def _window_snapshot(window: Any) -> dict[str, Any]:
    rect = _safe_call(window, "rectangle", None)
    rectangle = {}
    if rect is not None:
        rectangle = {
            "left": int(getattr(rect, "left", 0)),
            "top": int(getattr(rect, "top", 0)),
            "right": int(getattr(rect, "right", 0)),
            "bottom": int(getattr(rect, "bottom", 0)),
        }
    return {
        "title": _safe_call(window, "window_text", "") or "",
        "class_name": _safe_call(window, "class_name", "") or "",
        "process_id": _safe_call(window, "process_id", None),
        "handle": _safe_call(window, "handle", None),
        "rectangle": rectangle,
        "enabled": bool(_safe_call(window, "is_enabled", False)),
        "visible": bool(_safe_call(window, "is_visible", False)),
        "controls": _describe_controls(window),
    }


def _resolve_window_wrapper(candidate: dict[str, Any]) -> Any | None:
    handle = candidate.get("handle")
    if handle is None:
        return None
    try:
        from pywinauto import Desktop

        return Desktop(backend="uia").window(handle=handle)
    except Exception:
        return None


def _explore_dialog_candidate(candidate: dict[str, Any], *, safe_mode: str) -> dict[str, Any]:
    dialog = _resolve_window_wrapper(candidate)
    if dialog is None:
        return {"controls": [], "interactions": [], "states": [], "exploration_depth": 0}
    try:
        return explore_dialog(dialog, safe_mode=safe_mode == "safe")
    except Exception as exc:
        logger.warning("dialog_explorer_failed title={} error={}", candidate.get("title"), exc)
        return {"controls": [], "interactions": [], "states": [], "exploration_depth": 0}


def detect_dialog_or_window_transition(
    before_snapshot: RuntimeStateSnapshot,
    after_snapshot: RuntimeStateSnapshot,
    *,
    child_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    child_rows = child_rows or []
    before_ids = {_window_identity(w) for w in before_snapshot.visible_top_windows}
    new_windows = [w for w in after_snapshot.visible_top_windows if _window_identity(w) not in before_ids]
    main_disabled = before_snapshot.main_window_enabled is not False and after_snapshot.main_window_enabled is False

    if child_rows:
        return {"result_type": "submenu_opened", "new_windows": new_windows}

    if new_windows:
        candidate = new_windows[0]
        title = str(candidate.get("title") or "")
        class_name = str(candidate.get("class_name") or "")
        result_type = "dialog_opened" if class_name == "#32770" or "dialog" in class_name.lower() else "window_opened"
        logger.info("dialog_detected result_type={} title={} class_name={}", result_type, title, class_name)
        return {"result_type": result_type, "dialog_detected": result_type == "dialog_opened", "window_snapshot": candidate}

    if main_disabled:
        logger.warning("modal_likely_main_disabled title={}", after_snapshot.main_window_title)
        return {"result_type": "main_window_disabled_modal_likely", "dialog_detected": True}

    if after_snapshot.foreground_window != before_snapshot.foreground_window:
        return {"result_type": "popup_changed", "dialog_detected": False}

    return {"result_type": "no_visible_change", "dialog_detected": False}


def close_transient_dialog_or_window(window: Any | None, *, action_label: str = "") -> dict[str, Any]:
    logger.info("dialog_close_attempt action_label={}", action_label)
    if window is None:
        try:
            from pywinauto import keyboard
            keyboard.send_keys('{ESC}')
            logger.info('dialog_close_success method=esc_global')
            return {'closed': True, 'method': 'esc_global'}
        except Exception:
            return {"closed": False, "method": None, "error": "missing_window"}
    try:
        from pywinauto import keyboard
    except Exception:
        keyboard = None

    if keyboard is not None:
        for key, method in [('{ESC}', 'esc'), ('%{F4}', 'alt_f4')]:
            try:
                window.set_focus()
                keyboard.send_keys(key)
                if not bool(_safe_call(window, 'is_visible', False)):
                    logger.info('dialog_close_success method={}', method)
                    return {'closed': True, 'method': method}
            except Exception:
                continue

    labels = ["Mégse", "Cancel", "Bezár", "Bezárás", "Close", "OK"]
    for label in labels:
        for meth in ("child_window", "window"):
            try:
                btn = getattr(window, meth)(title_re=f".*{label}.*", control_type="Button")
                btn.click_input()
                if not bool(_safe_call(window, 'is_visible', False)):
                    logger.info('dialog_close_success method=button:{}', label)
                    return {'closed': True, 'method': f'button:{label}'}
            except Exception:
                continue

    try:
        window.close()
        if not bool(_safe_call(window, 'is_visible', False)):
            logger.info('dialog_close_success method=close')
            return {'closed': True, 'method': 'close'}
    except Exception:
        pass

    logger.error("dialog_close_failed action_label={}", action_label)
    return {"closed": False, "method": None, "error": "close_failed"}


def verify_main_window_recovery(main_window: Any) -> bool:
    visible = bool(_safe_call(main_window, "is_visible", False))
    enabled = bool(_safe_call(main_window, "is_enabled", False))
    ok = visible and enabled
    if ok:
        logger.info("recovery_success")
    else:
        logger.error("recovery_failed visible={} enabled={}", visible, enabled)
    return ok


def _main_window_recovery_state(main_window: Any) -> dict[str, Any]:
    rect = _safe_call(main_window, "rectangle", None)
    rectangle = {}
    if rect is not None:
        rectangle = {
            "left": int(getattr(rect, "left", 0)),
            "top": int(getattr(rect, "top", 0)),
            "right": int(getattr(rect, "right", 0)),
            "bottom": int(getattr(rect, "bottom", 0)),
        }
    return {
        "exists": main_window is not None,
        "title": _safe_call(main_window, "window_text", "") or "",
        "class_name": _safe_call(main_window, "class_name", "") or "",
        "process_id": _safe_call(main_window, "process_id", None),
        "handle": _safe_call(main_window, "handle", None),
        "visible": bool(_safe_call(main_window, "is_visible", False)),
        "enabled": bool(_safe_call(main_window, "is_enabled", False)),
        "rect": rectangle,
    }


def _list_recovery_target_windows(*, main_window_handle: Any | None = None, main_process_id: int | None = None) -> list[Any]:
    try:
        from pywinauto import Desktop
    except Exception:
        return []

    targets: list[tuple[int, Any]] = []
    for window in Desktop(backend="uia").windows(top_level_only=True):
        if not bool(_safe_call(window, "is_visible", False)):
            continue
        handle = _safe_call(window, "handle", None)
        if main_window_handle is not None and handle == main_window_handle:
            continue
        score = 0
        if main_process_id is not None and _safe_call(window, "process_id", None) == main_process_id:
            score += 10
        title = (_safe_call(window, "window_text", "") or "").strip()
        if title:
            score += 1
        targets.append((score, window))

    targets.sort(key=lambda item: item[0], reverse=True)
    return [window for _, window in targets]


def _send_recovery_key(
    key_sequence: str,
    *,
    main_window_handle: Any | None = None,
    main_process_id: int | None = None,
) -> bool:
    try:
        from pywinauto import keyboard
    except Exception:
        return False

    targets = _list_recovery_target_windows(main_window_handle=main_window_handle, main_process_id=main_process_id)
    if not targets:
        try:
            keyboard.send_keys(key_sequence)
            return True
        except Exception:
            return False

    for target in targets:
        try:
            target.set_focus()
            keyboard.send_keys(key_sequence)
            return True
        except Exception:
            continue
    return False


def _click_recovery_button(label: str, *, main_window_handle: Any | None = None) -> bool:
    try:
        from pywinauto import Desktop
    except Exception:
        return False

    for window in Desktop(backend="uia").windows(top_level_only=True):
        if not bool(_safe_call(window, "is_visible", False)):
            continue
        if main_window_handle is not None and _safe_call(window, "handle", None) == main_window_handle:
            continue
        for method_name in ("child_window", "window"):
            try:
                button = getattr(window, method_name)(title_re=fr".*{label}.*", control_type="Button")
                button.click_input()
                return True
            except Exception:
                continue
    return False


def _collect_project_open_recovery_diagnostics(main_window: Any) -> dict[str, Any]:
    main_state = _main_window_recovery_state(main_window)
    dialog_candidates = [
        window
        for window in _list_visible_top_windows()
        if window.get("handle") != main_state.get("handle")
    ]
    return {
        "foreground_window": _foreground_window_info(),
        "dialog_candidates": dialog_candidates,
        "main_window": {
            "enabled": main_state.get("enabled"),
            "visible": main_state.get("visible"),
            "rect": main_state.get("rect"),
            "title": main_state.get("title"),
            "class_name": main_state.get("class_name"),
            "process_id": main_state.get("process_id"),
            "handle": main_state.get("handle"),
            "exists": main_state.get("exists"),
        },
    }


def _is_main_window_interactive(main_window: Any) -> bool:
    state = _main_window_recovery_state(main_window)
    return bool(state["exists"] and state["visible"] and state["enabled"])


def _attempt_project_open_modal_close(
    *,
    main_window_handle: Any | None = None,
    main_process_id: int | None = None,
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for key_sequence, name in (("{ESC}", "Esc"), ("{ENTER}", "Enter"), ("%{F4}", "Alt+F4")):
        attempt = {"method": "key", "name": name, "key_sequence": key_sequence}
        logger.info("project_open_recovery_close_attempt method={} name={}", attempt["method"], attempt["name"])
        attempt["sent"] = _send_recovery_key(
            key_sequence,
            main_window_handle=main_window_handle,
            main_process_id=main_process_id,
        )
        attempts.append(attempt)
        if _is_main_window_interactive(get_cached_main_window()):
            logger.info("project_open_recovery_close_success method={} name={}", attempt["method"], attempt["name"])
            return attempts

    for label in ["OK", "Rendben", "Bezár", "Mégse", "Cancel", "Close", "No", "Nem"]:
        attempt = {"method": "button", "name": label}
        logger.info("project_open_recovery_close_attempt method={} name={}", attempt["method"], attempt["name"])
        attempt["clicked"] = _click_recovery_button(label, main_window_handle=main_window_handle)
        attempts.append(attempt)
        if _is_main_window_interactive(get_cached_main_window()):
            logger.info("project_open_recovery_close_success method={} name={}", attempt["method"], attempt["name"])
            return attempts
    return attempts


def recover_after_project_open(*, timeout_s: float = 15.0, poll_interval_s: float = 0.25) -> dict[str, Any]:
    logger.info("project_open_recovery_start timeout_s={} poll_interval_s={}", timeout_s, poll_interval_s)
    deadline = time.monotonic() + timeout_s
    diagnostics: dict[str, Any] = {}
    close_attempts: list[dict[str, Any]] = []
    modal_logged = False

    while time.monotonic() <= deadline:
        main_window = get_cached_main_window()
        main_state = _main_window_recovery_state(main_window)
        if main_state["exists"] and main_state["visible"] and main_state["enabled"]:
            logger.info("project_open_recovery_success")
            diagnostics = _collect_project_open_recovery_diagnostics(main_window)
            return {"success": True, "diagnostics": diagnostics, "close_attempts": close_attempts}

        if main_state["visible"] and not main_state["enabled"]:
            diagnostics = _collect_project_open_recovery_diagnostics(main_window)
            if not modal_logged:
                logger.warning("project_open_recovery_modal_detected diagnostics={}", diagnostics)
                modal_logged = True
            close_attempts.extend(
                _attempt_project_open_modal_close(
                    main_window_handle=main_state.get("handle"),
                    main_process_id=main_state.get("process_id"),
                )
            )

        time.sleep(poll_interval_s)

    diagnostics = _collect_project_open_recovery_diagnostics(get_cached_main_window())
    logger.error("project_open_recovery_failed diagnostics={}", diagnostics)
    return {"success": False, "diagnostics": diagnostics, "close_attempts": close_attempts}


def classify_post_click_result(
    process_id: int | None,
    before_snapshot: RuntimeStateSnapshot,
    after_snapshot: RuntimeStateSnapshot,
    dialog_detection: dict[str, Any] | None,
    *,
    state_id: str,
    top_menu: str,
    row_index: int,
    menu_path: list[str],
    action_key: str,
    safety_level: str,
    attempted: bool,
    error_text: str | None = None,
    notes: str | None = None,
    top_menu_click_count: int | None = None,
    forced_result_type: str | None = None,
) -> RuntimeActionResult:
    details = dict(dialog_detection or {})
    if forced_result_type:
        result_type = forced_result_type
    elif not attempted:
        result_type = "failed"
    elif error_text:
        result_type = "failed"
    else:
        result_type = str(details.get("result_type") or ("dialog_opened" if details.get("dialog_detected") else "no_visible_change"))

    return RuntimeActionResult(
        state_id=state_id,
        top_menu=top_menu,
        row_index=row_index,
        menu_path=menu_path,
        action_key=action_key,
        safety_level=safety_level,
        attempted=attempted,
        result_type=result_type,
        dialog_title=details.get("dialog_title") or ((details.get("window_snapshot") or {}).get("title")),
        dialog_class=details.get("dialog_class") or ((details.get("window_snapshot") or {}).get("class_name")),
        window_title=(details.get("window_snapshot") or {}).get("title"),
        window_class=(details.get("window_snapshot") or {}).get("class_name"),
        error_text=error_text,
        notes=notes,
        process_id=process_id,
        top_menu_click_count=top_menu_click_count,
        event_details=details,
    )


def explore_menu_tree(
    *,
    state_id: str,
    top_menu: str,
    safe_mode: str,
    max_depth: int,
    include_disabled: bool,
    depth: int = 1,
    parent_path: list[str] | None = None,
    popup_rows: list[dict[str, Any]] | None = None,
    canonical_top_menu_names: set[str] | None = None,
    visited_paths: set[tuple[str, ...]] | None = None,
    visited_path_hashes: set[int] | None = None,
    known_paths_to_skip: set[tuple[str, ...]] | None = None,
    popup_state: PopupState | None = None,
) -> tuple[list[dict[str, Any]], list[RuntimeMenuRow], list[RuntimeActionResult], list[RuntimeDialogRecord], list[RuntimeWindowRecord]]:
    parent_path = list(parent_path or [clean_menu_title(top_menu)])
    dialogs: list[RuntimeDialogRecord] = []
    windows: list[RuntimeWindowRecord] = []
    top_transition: dict[str, Any] = {"result_type": "no_visible_change"}

    if popup_rows is None:
        normalized_parent = tuple(normalize_menu_title(part) for part in parent_path)
        if popup_state is not None and popup_state.current_menu_path == normalized_parent and popup_state.popup_rows:
            popup_rows = list(popup_state.popup_rows)
        else:
            popup_rows = menu_helpers.capture_menu_popup_snapshot()
        if popup_rows:
            logger.debug("reusing_open_popup_snapshot state={} top_menu={} row_count={}", state_id, top_menu, len(popup_rows))
        else:
            before_click = capture_state_snapshot(state_id)
            menu_helpers.click_top_menu_item(top_menu)
            popup_rows = menu_helpers.capture_menu_popup_snapshot()
            after_click = capture_state_snapshot(state_id)
            top_transition = detect_dialog_or_window_transition(before_click, after_click, child_rows=popup_rows)
        if top_transition.get("result_type") in {"dialog_opened", "window_opened", "main_window_disabled_modal_likely"}:
            candidate = top_transition.get("window_snapshot") or {}
            if top_transition.get("result_type") == "dialog_opened" or top_transition.get("result_type") == "main_window_disabled_modal_likely":
                exploration = _explore_dialog_candidate(candidate, safe_mode=safe_mode)
                dialogs.append(RuntimeDialogRecord(
                    state_id=state_id,
                    top_menu=top_menu,
                    row_index=-1,
                    menu_path=[clean_menu_title(top_menu)],
                    title=str(candidate.get("title") or ""),
                    class_name=str(candidate.get("class_name") or ""),
                    process_id=candidate.get("process_id"),
                    rectangle=dict(candidate.get("rectangle") or {}),
                    enabled=candidate.get("enabled"),
                    visible=candidate.get("visible"),
                    controls=list(candidate.get("controls") or []),
                    explored_controls=list(exploration.get("controls") or []),
                    interactions_attempted=list(exploration.get("interactions") or []),
                    resulting_states=list(exploration.get("states") or []),
                    exploration_depth=int(exploration.get("exploration_depth") or 0),
                ))
            else:
                windows.append(RuntimeWindowRecord(
                    state_id=state_id,
                    top_menu=top_menu,
                    row_index=-1,
                    menu_path=[clean_menu_title(top_menu)],
                    title=str(candidate.get("title") or ""),
                    class_name=str(candidate.get("class_name") or ""),
                    process_id=candidate.get("process_id"),
                    rectangle=dict(candidate.get("rectangle") or {}),
                    enabled=candidate.get("enabled"),
                    visible=candidate.get("visible"),
                    controls=list(candidate.get("controls") or []),
                ))
            close_result = close_transient_dialog_or_window(None, action_label=f"top_menu:{top_menu}")
            if not close_result.get("closed"):
                logger.error("dialog_close_failed top_menu={}", top_menu)
        if popup_state is not None:
            popup_state.current_menu_path = normalized_parent
            popup_state.popup_rows = list(popup_rows)

    if visited_paths is None:
        visited_paths = set()
    if visited_path_hashes is None:
        visited_path_hashes = set()
    known_paths_to_skip = set(known_paths_to_skip or set())

    current_level_rows = _build_menu_rows_from_popup_rows(
        state_id,
        top_menu,
        popup_rows,
        canonical_top_menu_names=canonical_top_menu_names,
    )
    collected_rows: list[RuntimeMenuRow] = list(current_level_rows)
    nodes: list[dict[str, Any]] = []
    actions: list[RuntimeActionResult] = []

    for row in current_level_rows:
        if not include_disabled and row.enabled_guess is False:
            continue
        path = parent_path + [row.text]
        normalized_path = tuple(normalize_menu_title(part) for part in path)
        visit_key = normalized_path
        if not row.normalized_text:
            visit_key = (*normalized_path, f"#idx:{row.row_index}")

        path_key = hash(visit_key)
        if path_key in visited_path_hashes:
            logger.debug("visited path skip state={} path={}", state_id, normalized_path)
            continue
        visited_path_hashes.add(path_key)
        visited_paths.add(visit_key)

        skipped = row.is_separator or (not is_action_allowed(path, mode=safe_mode))
        reused_from_previous_state = normalized_path in known_paths_to_skip
        opens_submenu = False
        children_nodes: list[dict[str, Any]] = []
        before_action = capture_state_snapshot(state_id) if not is_fast_mode() else RuntimeStateSnapshot(
            state_id=state_id,
            process_id=None,
            main_window_title="",
            main_window_class="",
            visible_top_windows=[],
            discovered_top_menus=[],
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
        )
        transition: dict[str, Any] = {"result_type": "no_visible_change"}

        if depth < max_depth and not row.is_separator and row.enabled_guess is not False and not reused_from_previous_state:
            _activate_row_for_exploration(row, popup_rows)
            current_rows = menu_helpers.capture_menu_popup_snapshot()
            child_rows = _detect_child_rows(asdict(row), current_rows)
            if canonical_top_menu_names:
                child_rows = [
                    child_row
                    for child_row in child_rows
                    if not is_top_menu_like_popup_row(child_row, canonical_top_menu_names)
                ]
            after_action = capture_state_snapshot(state_id) if not is_fast_mode() else before_action
            if child_rows or not is_fast_mode():
                transition = detect_dialog_or_window_transition(before_action, after_action, child_rows=child_rows)
            if child_rows:
                opens_submenu = True
                if popup_state is not None:
                    popup_state.current_menu_path = tuple(normalize_menu_title(part) for part in path)
                    popup_state.popup_rows = list(child_rows)
                child_nodes, child_menu_rows, child_actions, child_dialogs, child_windows = explore_menu_tree(
                    state_id=state_id,
                    top_menu=top_menu,
                    safe_mode=safe_mode,
                    max_depth=max_depth,
                    include_disabled=include_disabled,
                    depth=depth + 1,
                    parent_path=path,
                    popup_rows=child_rows,
                    canonical_top_menu_names=canonical_top_menu_names,
                    visited_paths=visited_paths,
                    visited_path_hashes=visited_path_hashes,
                    known_paths_to_skip=known_paths_to_skip,
                    popup_state=popup_state,
                )
                children_nodes = child_nodes
                collected_rows.extend(child_menu_rows)
                actions.extend(child_actions)
                dialogs.extend(child_dialogs)
                windows.extend(child_windows)
            elif transition.get("result_type") in {"dialog_opened", "window_opened", "main_window_disabled_modal_likely"}:
                candidate = transition.get("window_snapshot") or {}
                if transition.get("result_type") in {"dialog_opened", "main_window_disabled_modal_likely"}:
                    exploration = _explore_dialog_candidate(candidate, safe_mode=safe_mode)
                    dialogs.append(RuntimeDialogRecord(
                        state_id=state_id,
                        top_menu=top_menu,
                        row_index=row.row_index,
                        menu_path=path,
                        title=str(candidate.get("title") or ""),
                        class_name=str(candidate.get("class_name") or ""),
                        process_id=candidate.get("process_id"),
                        rectangle=dict(candidate.get("rectangle") or {}),
                        enabled=candidate.get("enabled"),
                        visible=candidate.get("visible"),
                        controls=list(candidate.get("controls") or []),
                        explored_controls=list(exploration.get("controls") or []),
                        interactions_attempted=list(exploration.get("interactions") or []),
                        resulting_states=list(exploration.get("states") or []),
                        exploration_depth=int(exploration.get("exploration_depth") or 0),
                    ))
                else:
                    windows.append(RuntimeWindowRecord(
                        state_id=state_id,
                        top_menu=top_menu,
                        row_index=row.row_index,
                        menu_path=path,
                        title=str(candidate.get("title") or ""),
                        class_name=str(candidate.get("class_name") or ""),
                        process_id=candidate.get("process_id"),
                        rectangle=dict(candidate.get("rectangle") or {}),
                        enabled=candidate.get("enabled"),
                        visible=candidate.get("visible"),
                        controls=list(candidate.get("controls") or []),
                    ))

        node = _row_to_node(
            state_id,
            top_menu,
            asdict(row),
            level=depth,
            index=row.row_index,
            path=path,
            children=children_nodes,
            opens_submenu=opens_submenu,
            opens_dialog=transition.get("result_type") in {"dialog_opened", "main_window_disabled_modal_likely", "window_opened"},
            skipped_by_safety=skipped,
            reused_from_previous_state=reused_from_previous_state,
        )
        nodes.append(asdict(node))
        actions.append(
            classify_post_click_result(
                process_id=None,
                before_snapshot=before_action,
                after_snapshot=capture_state_snapshot(state_id),
                dialog_detection=transition,
                state_id=state_id,
                top_menu=top_menu,
                row_index=row.row_index,
                menu_path=path,
                action_key=" > ".join(path),
                safety_level=classify_safety([clean_menu_title(part) for part in path]),
                attempted=not skipped and not reused_from_previous_state,
                notes="reused_from_previous_state" if reused_from_previous_state else "mapped_only",
            )
        )

    return nodes, collected_rows, actions, dialogs, windows


def _state_summary_markdown(state_map: RuntimeStateMap) -> str:
    enabled = sum(1 for item in state_map.menu_rows if item.get("enabled_guess") is True)
    disabled = sum(1 for item in state_map.menu_rows if item.get("enabled_guess") is False)
    submenu_count = sum(1 for item in state_map.actions if item.get("result_type") == "success_popup_opened")
    dialog_candidates = len(state_map.dialogs)
    return "\n".join(
        [
            f"# Runtime summary ({state_map.state_id})",
            "",
            f"- top menük száma: {len(state_map.top_menus)}",
            f"- összes menüpont: {len(state_map.menu_rows)}",
            f"- enabled: {enabled}",
            f"- disabled: {disabled}",
            f"- submenu count: {submenu_count}",
            f"- dialog candidates: {dialog_candidates}",
            "",
        ]
    )


def _diff_summary_markdown(diff: RuntimeStateDiff) -> str:
    return "\n".join(
        [
            "# Runtime állapot diff",
            "",
            f"- shared top-level menük: {len(diff.top_menu_diff.get('shared', []))}",
            f"- csak projekt után látható elemek: {len(diff.project_only_paths)}",
            f"- enabled változások: {len(diff.enabled_state_changes)}",
            "",
        ]
    )


def map_runtime_state(
    *,
    state_id: str,
    safe_mode: str = "safe",
    top_menus: list[str] | None = None,
    max_submenu_depth: int = 3,
    include_disabled: bool = True,
    known_paths_to_skip: set[tuple[str, ...]] | None = None,
) -> RuntimeStateMap:
    snapshot = capture_state_snapshot(state_id)
    discovered = snapshot.discovered_top_menus
    canonical_top_menus = get_canonical_top_menu_names(discovered)
    target_menus = top_menus or DEFAULT_TOP_MENUS
    target_menu_map = {normalize_menu_title(item): item for item in target_menus}

    all_rows: list[RuntimeMenuRow] = []
    all_tree: list[dict[str, Any]] = []
    all_actions: list[RuntimeActionResult] = []
    all_dialogs: list[RuntimeDialogRecord] = []
    all_windows: list[RuntimeWindowRecord] = []

    partial_mapping = False
    stop_reason: str | None = None
    popup_state = PopupState()

    for top_menu_normalized, _ in target_menu_map.items():
        discovered_top_menu = canonical_top_menus["normalized_to_raw"].get(top_menu_normalized)
        if not discovered_top_menu:
            continue

        rows: list[RuntimeMenuRow] = []
        try:
            tree, rows, actions, dialogs, windows = explore_menu_tree(
                state_id=state_id,
                top_menu=discovered_top_menu,
                safe_mode=safe_mode,
                max_depth=max_submenu_depth,
                include_disabled=include_disabled,
                canonical_top_menu_names=canonical_top_menus["normalized_names"],
                visited_paths={(normalize_menu_title(discovered_top_menu),)},
                visited_path_hashes={hash((normalize_menu_title(discovered_top_menu),))},
                known_paths_to_skip=known_paths_to_skip,
                popup_state=popup_state,
            )
            clean_top_menu = clean_menu_title(discovered_top_menu)
            normalized_top_menu = normalize_menu_title(discovered_top_menu)
            logger.debug('RAW_MENU_TITLE="{}" NORMALIZED_MENU_TITLE="{}"', discovered_top_menu, normalized_top_menu)
            all_tree.append({"state_id": state_id, "title_raw": discovered_top_menu, "title_normalized": normalized_top_menu, "title": clean_top_menu, "path": [clean_top_menu], "children": tree})
            all_rows.extend(rows)
            all_actions.extend(actions)
            all_dialogs.extend(dialogs)
            all_windows.extend(windows)
        except Exception as exc:
            logger.exception("Top menu mapping failed: {}", discovered_top_menu)
            all_actions.append(
                asdict(
                    classify_post_click_result(
                        process_id=None,
                        before_snapshot=snapshot,
                        after_snapshot=snapshot,
                        dialog_detection=None,
                        state_id=state_id,
                        top_menu=clean_menu_title(discovered_top_menu),
                        row_index=-1,
                        menu_path=[clean_menu_title(discovered_top_menu)],
                        action_key=clean_menu_title(discovered_top_menu),
                        safety_level="caution",
                        attempted=False,
                        error_text=str(exc),
                        forced_result_type="failed_focus",
                    )
                )
            )
            if "WinWatt" in type(exc).__name__ or "focus_not_restored" in str(exc):
                recovered = restore_clean_menu_baseline(state_id=state_id, stage=f"recover_after_exception:{discovered_top_menu}")
                if recovered:
                    logger.warning(
                        "recovered from focus loss, continuing mapping state={} top_menu={}",
                        state_id,
                        discovered_top_menu,
                    )
                else:
                    partial_mapping = True
                    stop_reason = f"unrecoverable:{discovered_top_menu}"
                    logger.error("unrecoverable main window loss during top menu state={} top_menu={}", state_id, discovered_top_menu)
                    break

        if should_restore_clean_menu_baseline(state_id=state_id, stage=f"after:{discovered_top_menu}"):
            if not restore_clean_menu_baseline(state_id=state_id, stage=f"after:{discovered_top_menu}"):
                partial_mapping = True
                stop_reason = f"lost_main_window_after:{discovered_top_menu}"
                logger.error("unrecoverable main window loss after top menu state={} top_menu={}", state_id, discovered_top_menu)
                break

    snapshot_payload = asdict(snapshot)
    snapshot_payload["mapping_partial"] = partial_mapping
    snapshot_payload["mapping_stop_reason"] = stop_reason

    return RuntimeStateMap(
        state_id=state_id,
        snapshot=snapshot_payload,
        top_menus=[
            {"state_id": state_id, "text": item["clean"], "text_raw": item["raw"], "text_normalized": item["normalized"]}
            for item in canonical_top_menus["items"]
            if item["normalized"] in set(target_menu_map)
        ],
        menu_rows=[asdict(item) for item in all_rows],
        menu_tree=all_tree,
        actions=[item if isinstance(item, dict) else asdict(item) for item in all_actions],
        dialogs=[asdict(item) for item in all_dialogs],
        windows=[asdict(item) for item in all_windows],
        skipped_actions=[item if isinstance(item, dict) else asdict(item) for item in all_actions if (item.get("attempted") if isinstance(item, dict) else item.attempted) is False],
    )


def _normalized_path(path: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalize_menu_title(part) for part in path)


def _enabled_map(state: RuntimeStateMap) -> dict[tuple[str, ...], bool | None]:
    result: dict[tuple[str, ...], bool | None] = {}
    for row in state.menu_rows:
        path = _normalized_path(tuple(row.get("menu_path", [])))
        result[path] = row.get("enabled_guess")
    return result


def compare_runtime_states(state_a: RuntimeStateMap, state_b: RuntimeStateMap) -> RuntimeStateDiff:
    menus_a = {normalize_menu_title(item["text"]) for item in state_a.top_menus}
    menus_b = {normalize_menu_title(item["text"]) for item in state_b.top_menus}
    actions_a = {_normalized_path(tuple(item.get("menu_path", []))) for item in state_a.actions}
    actions_b = {_normalized_path(tuple(item.get("menu_path", []))) for item in state_b.actions}

    enabled_a = _enabled_map(state_a)
    enabled_b = _enabled_map(state_b)
    shared_paths = set(enabled_a) & set(enabled_b)
    enabled_changes = [
        {"path": list(path), "from": enabled_a[path], "to": enabled_b[path]}
        for path in sorted(shared_paths)
        if enabled_a[path] != enabled_b[path]
    ]

    project_only_paths = [list(path) for path in sorted(set(enabled_b) - set(enabled_a))]

    return RuntimeStateDiff(
        state_a=state_a.state_id,
        state_b=state_b.state_id,
        top_menu_diff={"only_in_a": sorted(menus_a - menus_b), "only_in_b": sorted(menus_b - menus_a), "shared": sorted(menus_a & menus_b)},
        menu_action_diff={"only_in_a": [list(x) for x in sorted(actions_a - actions_b)], "only_in_b": [list(x) for x in sorted(actions_b - actions_a)], "shared": [list(x) for x in sorted(actions_a & actions_b)]},
        dialog_diff={"only_in_a": [], "only_in_b": [], "shared": []},
        window_diff={"only_in_a": [], "only_in_b": [], "shared": []},
        summary={
            "shared_top_menus": len(menus_a & menus_b),
            "actions_only_in_a": len(actions_a - actions_b),
            "actions_only_in_b": len(actions_b - actions_a),
            "enabled_changes": len(enabled_changes),
            "project_only_paths": len(project_only_paths),
        },
        enabled_state_changes=enabled_changes,
        project_only_paths=project_only_paths,
    )


def _is_safe_mode_project_path_allowed(project_path: str) -> bool:
    normalized = str(project_path or "").replace("/", "\\").strip().lower()
    return normalized.endswith("\\winwatt_automation\\tests\\testwwp.wwp")


def open_test_project(project_path: str, *, safe_mode: str = "safe") -> dict[str, Any]:
    if safe_mode == "safe" and not _is_safe_mode_project_path_allowed(project_path):
        return {
            "success": False,
            "path": project_path,
            "dialog_found": False,
            "path_entered": False,
            "confirm_clicked": False,
            "dialog_closed": False,
            "project_state_changed": False,
            "detected_changes": [],
            "error": "Safe mode only allows explicitly approved test project path.",
        }

    before = asdict(capture_state_snapshot("project_open_before"))
    result = open_project_file_via_dialog_dict(
        project_path,
        before_snapshot=before,
        after_snapshot_provider=lambda: asdict(capture_state_snapshot("project_open_after")),
    )
    result["recovery"] = recover_after_project_open()
    return result


def _write_state_outputs(state_dir: Path, state_map: RuntimeStateMap) -> None:
    write_json(state_dir / "snapshot.json", state_map.snapshot)
    write_json(state_dir / "menu_tree.json", state_map.menu_tree)
    write_json(state_dir / "dialogs.json", state_map.dialogs)
    write_json(state_dir / "windows.json", state_map.windows)
    (state_dir / "summary.md").write_text(_state_summary_markdown(state_map), encoding="utf-8")


def _collect_known_menu_paths(state_map: RuntimeStateMap) -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()
    for row in state_map.menu_rows:
        normalized = _normalized_path(tuple(row.get("menu_path", [])))
        if normalized:
            paths.add(normalized)
    return paths


def _collect_state_knowledge(state_map: RuntimeStateMap) -> dict[str, list[list[str]]]:
    menu_paths = [
        list(item)
        for item in sorted({_normalized_path(tuple(row.get("menu_path", []))) for row in state_map.menu_rows if row.get("menu_path")})
    ]
    dialog_signatures = sorted(
        {
            (
                normalize_menu_title(" > ".join(dialog.get("menu_path", []))),
                normalize_menu_title(dialog.get("title", "")),
                normalize_menu_title(dialog.get("class_name", "")),
            )
            for dialog in state_map.dialogs
        }
    )
    window_signatures = sorted(
        {
            (
                normalize_menu_title(" > ".join(window.get("menu_path", []))),
                normalize_menu_title(window.get("title", "")),
                normalize_menu_title(window.get("class_name", "")),
            )
            for window in state_map.windows
        }
    )
    return {
        "menu_paths": menu_paths,
        "dialog_signatures": [list(item) for item in dialog_signatures],
        "window_signatures": [list(item) for item in window_signatures],
    }


def _compute_knowledge_verification(current: dict[str, Any], baseline: dict[str, Any] | None) -> dict[str, Any]:
    baseline = baseline or {}

    def _to_set(values: list[Any] | None) -> set[tuple[Any, ...]]:
        return {tuple(item) if isinstance(item, list) else tuple([item]) for item in (values or [])}

    current_menus = _to_set(current.get("menu_paths"))
    baseline_menus = _to_set(baseline.get("menu_paths"))
    current_dialogs = _to_set(current.get("dialog_signatures"))
    baseline_dialogs = _to_set(baseline.get("dialog_signatures"))
    current_windows = _to_set(current.get("window_signatures"))
    baseline_windows = _to_set(baseline.get("window_signatures"))

    missing_menu_paths = [list(item) for item in sorted(baseline_menus - current_menus)]
    new_menu_paths = [list(item) for item in sorted(current_menus - baseline_menus)]
    missing_dialogs = [list(item) for item in sorted(baseline_dialogs - current_dialogs)]
    new_dialogs = [list(item) for item in sorted(current_dialogs - baseline_dialogs)]
    missing_windows = [list(item) for item in sorted(baseline_windows - current_windows)]
    new_windows = [list(item) for item in sorted(current_windows - baseline_windows)]

    baseline_total = len(baseline_menus)
    covered = baseline_total - len(missing_menu_paths)
    coverage_pct = 100.0 if baseline_total == 0 else round((covered / baseline_total) * 100, 2)

    return {
        "baseline_loaded": bool(baseline),
        "missing_menu_paths": missing_menu_paths,
        "new_menu_paths": new_menu_paths,
        "missing_dialogs": missing_dialogs,
        "new_dialogs": new_dialogs,
        "missing_windows": missing_windows,
        "new_windows": new_windows,
        "known_menu_paths": baseline_total,
        "current_menu_paths": len(current_menus),
        "covered_known_menu_paths": covered,
        "coverage_pct": coverage_pct,
    }


def _load_previous_knowledge(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("current") if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("knowledge_load_failed path={} error={}", path, exc)
        return None


def _knowledge_markdown(verification: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Runtime tudás verifikáció",
            "",
            f"- baseline loaded: {verification.get('baseline_loaded')}",
            f"- known menu paths: {verification.get('known_menu_paths')}",
            f"- covered known paths: {verification.get('covered_known_menu_paths')}",
            f"- missing menu paths: {len(verification.get('missing_menu_paths', []))}",
            f"- new menu paths: {len(verification.get('new_menu_paths', []))}",
            f"- missing dialogs: {len(verification.get('missing_dialogs', []))}",
            f"- missing windows: {len(verification.get('missing_windows', []))}",
            f"- coverage: {verification.get('coverage_pct')}%",
            "",
        ]
    )


def build_full_runtime_program_map(
    project_path: str | None = None,
    safe_mode: str = "safe",
    output_dir: str | Path = "data/runtime_maps",
    state_id_prefix: str = "state",
    top_menus: list[str] | None = None,
    max_submenu_depth: int = 3,
    include_disabled: bool = True,
    event_recorder: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    paths = ensure_output_dirs(Path(output_dir))
    knowledge_path = paths["base"] / "knowledge.json"
    previous_knowledge = _load_previous_knowledge(knowledge_path)
    no_project_id = "no_project" if state_id_prefix == "state" else f"{state_id_prefix}_no_project"
    project_id = "project_open" if state_id_prefix == "state" else f"{state_id_prefix}_project_open"

    state_no_project = map_runtime_state(
        state_id=no_project_id,
        safe_mode=safe_mode,
        top_menus=top_menus,
        max_submenu_depth=max_submenu_depth,
        include_disabled=include_disabled,
    )
    if event_recorder:
        event_recorder(
            "state_mapped",
            {
                "state_id": state_no_project.state_id,
                "top_menus": len(state_no_project.top_menus),
                "actions": len(state_no_project.actions),
                "dialogs": len(state_no_project.dialogs),
            },
        )
    _write_state_outputs(paths["state_no_project"], state_no_project)

    effective_project_path = project_path or DEFAULT_TEST_PROJECT_PATH
    project_open_result = open_test_project(effective_project_path, safe_mode=safe_mode)
    recovery = (project_open_result or {}).get("recovery") if project_open_result else None
    if event_recorder and project_open_result:
        event_recorder(
            "project_open_result",
            {
                "success": bool(project_open_result.get("success")),
                "error": project_open_result.get("error"),
                "dialog_found": bool(project_open_result.get("dialog_found")),
            },
        )
    if event_recorder and recovery:
        event_recorder(
            "project_open_recovery",
            {
                "success": bool(recovery.get("success")),
                "reason": recovery.get("reason"),
                "modal_detected": bool(recovery.get("modal_pending")),
            },
        )

    if recovery and not recovery.get("success"):
        state_project_open = RuntimeStateMap(
            state_id=project_id,
            snapshot={
                "state_id": project_id,
                "mapping_partial": True,
                "mapping_stop_reason": "project_open_recovery_failed",
                "project_open_recovery": recovery,
                "recovery_diagnostics": recovery.get("diagnostics", {}),
            },
            top_menus=[],
            menu_rows=[],
            menu_tree=[],
            actions=[],
            dialogs=[],
            windows=[],
            skipped_actions=[],
        )
    else:
        state_project_open = map_runtime_state(
            state_id=project_id,
            safe_mode=safe_mode,
            top_menus=top_menus,
            max_submenu_depth=max_submenu_depth,
            include_disabled=include_disabled,
        )
        if recovery:
            state_project_open.snapshot["project_open_recovery"] = recovery
    if event_recorder:
        event_recorder(
            "state_mapped",
            {
                "state_id": state_project_open.state_id,
                "top_menus": len(state_project_open.top_menus),
                "actions": len(state_project_open.actions),
                "dialogs": len(state_project_open.dialogs),
            },
        )
    _write_state_outputs(paths["state_project_open"], state_project_open)

    diff = compare_runtime_states(state_no_project, state_project_open)
    if event_recorder:
        event_recorder(
            "runtime_diff",
            {
                "summary": dict(diff.summary),
                "enabled_changes": len(diff.enabled_state_changes),
                "project_only_paths": len(diff.project_only_paths),
            },
        )
    write_json(paths["diff"] / "state_diff.json", asdict(diff))
    (paths["diff"] / "summary.md").write_text(_diff_summary_markdown(diff), encoding="utf-8")

    current_knowledge = {
        "state_no_project": _collect_state_knowledge(state_no_project),
        "state_project_open": _collect_state_knowledge(state_project_open),
    }
    merged_current_knowledge = {
        "menu_paths": sorted({tuple(item) for item in current_knowledge["state_no_project"]["menu_paths"] + current_knowledge["state_project_open"]["menu_paths"]}),
        "dialog_signatures": sorted({tuple(item) for item in current_knowledge["state_no_project"]["dialog_signatures"] + current_knowledge["state_project_open"]["dialog_signatures"]}),
        "window_signatures": sorted({tuple(item) for item in current_knowledge["state_no_project"]["window_signatures"] + current_knowledge["state_project_open"]["window_signatures"]}),
    }
    merged_current_knowledge = {key: [list(item) for item in values] for key, values in merged_current_knowledge.items()}
    knowledge_verification = _compute_knowledge_verification(merged_current_knowledge, previous_knowledge)
    knowledge_payload = {
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        "current": merged_current_knowledge,
        "states": current_knowledge,
        "verification": knowledge_verification,
    }
    write_json(knowledge_path, knowledge_payload)
    (paths["base"] / "knowledge_summary.md").write_text(_knowledge_markdown(knowledge_verification), encoding="utf-8")
    if event_recorder:
        event_recorder("knowledge_verification", dict(knowledge_verification))

    skipped = sum(1 for action in state_no_project.actions + state_project_open.actions if not action.get("attempted", False))
    print(f"no_project menük száma: {len(state_no_project.top_menus)}")
    print(f"project_open menük száma: {len(state_project_open.top_menus)}")
    print(f"diff változások: {len(diff.enabled_state_changes) + len(diff.project_only_paths)}")
    print(f"skipped_by_safety: {skipped}")
    print(
        "knowledge verification: "
        f"missing={len(knowledge_verification['missing_menu_paths'])}, "
        f"new={len(knowledge_verification['new_menu_paths'])}, "
        f"coverage={knowledge_verification['coverage_pct']}%"
    )
    print(f"output: {paths['base']}")

    return {
        "state_no_project": state_no_project,
        "state_project_open": state_project_open,
        "diff": diff,
        "project_open_result": project_open_result,
        "knowledge_verification": knowledge_verification,
        "output_dir": str(paths["base"]),
    }

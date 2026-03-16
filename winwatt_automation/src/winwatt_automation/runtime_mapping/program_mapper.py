from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from winwatt_automation.live_ui import menu_helpers, waits
from winwatt_automation.live_ui.app_connector import get_main_window
from winwatt_automation.live_ui.file_dialog import open_project_file_via_dialog_dict
from winwatt_automation.runtime_mapping.models import (
    RuntimeActionResult,
    RuntimeDialogRecord,
    RuntimeMenuRow,
    RuntimeStateDiff,
    RuntimeStateMap,
    RuntimeStateSnapshot,
    RuntimeWindowRecord,
)
from winwatt_automation.runtime_mapping.safety import classify_safety, is_action_allowed, normalize_menu_text
from winwatt_automation.runtime_mapping.serializers import ensure_output_dirs, write_json, write_markdown_summary


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
        rows.append(
            {
                "title": _safe_call(window, "window_text", "") or "",
                "class_name": _safe_call(window, "class_name", "") or "",
                "process_id": _safe_call(window, "process_id", None),
                "handle": _safe_call(window, "handle", None),
            }
        )
    return rows


def _close_secondary_windows(main_title: str) -> None:
    try:
        from pywinauto import Desktop, keyboard
    except Exception:
        return
    for window in Desktop(backend="uia").windows(top_level_only=True):
        title = _safe_call(window, "window_text", "") or ""
        if not bool(_safe_call(window, "is_visible", False)):
            continue
        if title == main_title:
            continue
        try:
            window.set_focus()
            keyboard.send_keys("{ESC}")
        except Exception:
            continue


def capture_state_snapshot(state_id: str) -> RuntimeStateSnapshot:
    logger.info("state snapshot start state_id={}", state_id)
    main_window = get_main_window()
    process_id = _safe_call(main_window, "process_id", None)
    snapshot = RuntimeStateSnapshot(
        state_id=state_id,
        process_id=process_id,
        main_window_title=_safe_call(main_window, "window_text", "") or "",
        main_window_class=_safe_call(main_window, "class_name", "") or "",
        visible_top_windows=_list_visible_top_windows(),
        discovered_top_menus=list_top_menus(),
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )
    logger.info("state snapshot done state_id={} top_menus={}", state_id, len(snapshot.discovered_top_menus))
    return snapshot


def list_top_menus() -> list[str]:
    menus = menu_helpers.list_top_menu_items()
    logger.info("listed top menus count={}", len(menus))
    return menus


def _build_menu_rows_from_popup_rows(state_id: str, top_menu: str, rows: list[dict[str, Any]]) -> list[RuntimeMenuRow]:
    result: list[RuntimeMenuRow] = []
    for index, row in enumerate(rows):
        result.append(
            RuntimeMenuRow(
                state_id=state_id,
                top_menu=top_menu,
                row_index=index,
                menu_path=[top_menu, str(row.get("text") or "")],
                text=str(row.get("text") or ""),
                normalized_text=normalize_menu_text(str(row.get("text") or "")),
                rectangle=dict(row.get("rectangle") or {}),
                center_x=int(row.get("center_x") or 0),
                center_y=int(row.get("center_y") or 0),
                is_separator=bool(row.get("is_separator")),
                source_scope=str(row.get("source_scope") or ""),
                fragments=list(row.get("fragments") or []),
                enabled_guess=None if row.get("is_separator") else True,
                discovered_in_state=state_id,
            )
        )
    return result


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
) -> RuntimeActionResult:
    if not attempted:
        result_type = "skipped_unsafe"
    elif error_text:
        result_type = "failed"
    elif dialog_detection and dialog_detection.get("dialog_detected"):
        title = str(dialog_detection.get("dialog_title") or "").lower()
        result_type = "error_dialog" if "hiba" in title or "error" in title else "dialog_opened"
    elif len(after_snapshot.visible_top_windows) > len(before_snapshot.visible_top_windows):
        result_type = "window_opened"
    elif before_snapshot.main_window_title != after_snapshot.main_window_title:
        result_type = "state_changed"
    else:
        result_type = "no_visible_change"

    return RuntimeActionResult(
        state_id=state_id,
        top_menu=top_menu,
        row_index=row_index,
        menu_path=menu_path,
        action_key=action_key,
        safety_level=safety_level,
        attempted=attempted,
        result_type=result_type,
        dialog_title=(dialog_detection or {}).get("dialog_title"),
        dialog_class=(dialog_detection or {}).get("dialog_class"),
        window_title=None,
        window_class=None,
        error_text=error_text,
        notes=notes,
        process_id=process_id,
        top_menu_click_count=top_menu_click_count,
    )


def explore_top_menu(
    state_id: str,
    top_menu: str,
    safe_mode: str = "safe",
) -> tuple[list[RuntimeMenuRow], list[RuntimeActionResult], list[RuntimeDialogRecord], list[RuntimeWindowRecord]]:
    logger.info("explore top menu start state_id={} top_menu={}", state_id, top_menu)
    popup = menu_helpers.open_file_menu_and_capture_popup_state() if top_menu == "Fájl" else None
    if popup is None:
        menu_helpers.click_top_menu_item(top_menu)
        popup_rows_raw = menu_helpers.capture_menu_popup_snapshot()
    else:
        popup_rows_raw = popup.get("rows", [])

    menu_rows = _build_menu_rows_from_popup_rows(state_id, top_menu, popup_rows_raw)
    actions: list[RuntimeActionResult] = []
    dialogs: list[RuntimeDialogRecord] = []
    windows: list[RuntimeWindowRecord] = []

    for row in menu_rows:
        safety_level = classify_safety(row.menu_path)
        action_key = " > ".join(row.menu_path)
        logger.info(
            "row safety state_id={} top_menu={} row_index={} safety={}",
            state_id,
            top_menu,
            row.row_index,
            safety_level,
        )
        if row.is_separator or not is_action_allowed(row.menu_path, mode=safe_mode):
            actions.append(
                classify_post_click_result(
                    process_id=None,
                    before_snapshot=capture_state_snapshot(state_id),
                    after_snapshot=capture_state_snapshot(state_id),
                    dialog_detection=None,
                    state_id=state_id,
                    top_menu=top_menu,
                    row_index=row.row_index,
                    menu_path=row.menu_path,
                    action_key=action_key,
                    safety_level=safety_level,
                    attempted=False,
                    notes="separator_or_unsafe",
                )
            )
            continue

        before = capture_state_snapshot(state_id)
        dialog_detection: dict[str, Any] | None = None
        error_text: str | None = None
        try:
            popup_state = menu_helpers.open_file_menu_and_capture_popup_state() if top_menu == "Fájl" else None
            if popup_state:
                clicked = menu_helpers.click_structured_popup_row(popup_state.get("rows", []), row.row_index)
                process_id = popup_state.get("process_id")
                dialog_detection = waits.detect_open_file_dialog_from_context(process_id=process_id, timeout=1.5)
            else:
                process_id = None
                clicked = None
            logger.info("click attempted top_menu={} row_index={} clicked={}", top_menu, row.row_index, bool(clicked))
        except Exception as exc:
            process_id = None
            error_text = str(exc)

        after = capture_state_snapshot(state_id)
        result = classify_post_click_result(
            process_id=process_id,
            before_snapshot=before,
            after_snapshot=after,
            dialog_detection=dialog_detection,
            state_id=state_id,
            top_menu=top_menu,
            row_index=row.row_index,
            menu_path=row.menu_path,
            action_key=action_key,
            safety_level=safety_level,
            attempted=error_text is None,
            error_text=error_text,
            top_menu_click_count=popup.get("top_menu_click_count") if popup else None,
        )
        actions.append(result)

        if result.result_type in {"dialog_opened", "error_dialog"}:
            dialogs.append(
                RuntimeDialogRecord(
                    state_id=state_id,
                    top_menu=top_menu,
                    row_index=row.row_index,
                    menu_path=row.menu_path,
                    title=result.dialog_title or "",
                    class_name=result.dialog_class or "",
                    process_id=process_id,
                )
            )
        if result.result_type == "window_opened":
            new_windows = [w for w in after.visible_top_windows if w not in before.visible_top_windows]
            for win in new_windows:
                windows.append(
                    RuntimeWindowRecord(
                        state_id=state_id,
                        top_menu=top_menu,
                        row_index=row.row_index,
                        menu_path=row.menu_path,
                        title=str(win.get("title") or ""),
                        class_name=str(win.get("class_name") or ""),
                        process_id=win.get("process_id"),
                    )
                )

        _close_secondary_windows(before.main_window_title)

    logger.info("explore top menu done state_id={} top_menu={} rows={}", state_id, top_menu, len(menu_rows))
    return menu_rows, actions, dialogs, windows


def map_runtime_state(state_id: str, safe_mode: str = "safe") -> RuntimeStateMap:
    logger.info("runtime map start state_id={} safe_mode={}", state_id, safe_mode)
    snapshot = capture_state_snapshot(state_id)
    all_rows: list[RuntimeMenuRow] = []
    all_actions: list[RuntimeActionResult] = []
    all_dialogs: list[RuntimeDialogRecord] = []
    all_windows: list[RuntimeWindowRecord] = []

    for top_menu in snapshot.discovered_top_menus:
        rows, actions, dialogs, windows = explore_top_menu(state_id=state_id, top_menu=top_menu, safe_mode=safe_mode)
        all_rows.extend(rows)
        all_actions.extend(actions)
        all_dialogs.extend(dialogs)
        all_windows.extend(windows)

    state_map = RuntimeStateMap(
        state_id=state_id,
        snapshot=asdict(snapshot),
        top_menus=[{"state_id": state_id, "text": item} for item in snapshot.discovered_top_menus],
        menu_rows=[asdict(item) for item in all_rows],
        actions=[asdict(item) for item in all_actions],
        dialogs=[asdict(item) for item in all_dialogs],
        windows=[asdict(item) for item in all_windows],
        skipped_actions=[asdict(item) for item in all_actions if not item.attempted],
    )
    logger.info("runtime map done state_id={} rows={} actions={}", state_id, len(all_rows), len(all_actions))
    return state_map


def compare_runtime_states(state_a: RuntimeStateMap, state_b: RuntimeStateMap) -> RuntimeStateDiff:
    menus_a = {item["text"] for item in state_a.top_menus}
    menus_b = {item["text"] for item in state_b.top_menus}

    action_keys_a = {tuple(action.get("menu_path", [])) for action in state_a.actions}
    action_keys_b = {tuple(action.get("menu_path", [])) for action in state_b.actions}

    dialogs_a = {(item.get("title"), item.get("class_name")) for item in state_a.dialogs}
    dialogs_b = {(item.get("title"), item.get("class_name")) for item in state_b.dialogs}

    windows_a = {(item.get("title"), item.get("class_name")) for item in state_a.windows}
    windows_b = {(item.get("title"), item.get("class_name")) for item in state_b.windows}

    diff = RuntimeStateDiff(
        state_a=state_a.state_id,
        state_b=state_b.state_id,
        top_menu_diff={
            "only_in_a": sorted(menus_a - menus_b),
            "only_in_b": sorted(menus_b - menus_a),
            "shared": sorted(menus_a & menus_b),
        },
        menu_action_diff={
            "only_in_a": [list(item) for item in sorted(action_keys_a - action_keys_b)],
            "only_in_b": [list(item) for item in sorted(action_keys_b - action_keys_a)],
            "shared": [list(item) for item in sorted(action_keys_a & action_keys_b)],
        },
        dialog_diff={
            "only_in_a": sorted(dialogs_a - dialogs_b),
            "only_in_b": sorted(dialogs_b - dialogs_a),
            "shared": sorted(dialogs_a & dialogs_b),
        },
        window_diff={
            "only_in_a": sorted(windows_a - windows_b),
            "only_in_b": sorted(windows_b - windows_a),
            "shared": sorted(windows_a & windows_b),
        },
        summary={
            "shared_top_menus": len(menus_a & menus_b),
            "actions_only_in_a": len(action_keys_a - action_keys_b),
            "actions_only_in_b": len(action_keys_b - action_keys_a),
            "dialogs_only_in_a": len(dialogs_a - dialogs_b),
            "dialogs_only_in_b": len(dialogs_b - dialogs_a),
            "windows_only_in_a": len(windows_a - windows_b),
            "windows_only_in_b": len(windows_b - windows_a),
        },
    )
    logger.info("diff built {} vs {}", state_a.state_id, state_b.state_id)
    return diff


def _is_safe_mode_project_path_allowed(project_path: str) -> bool:
    normalized = str(project_path or "").replace("/", "\\").strip().lower()
    return normalized.endswith("\\winwatt_automation\\tests\\testwwp.wwp")


def open_test_project(project_path: str, *, safe_mode: str = "safe") -> dict[str, Any]:
    logger.info("open test project start path={}", project_path)
    if safe_mode == "safe" and not _is_safe_mode_project_path_allowed(project_path):
        error = "Safe mode only allows explicitly approved test project path."
        logger.warning("open test project blocked safe_mode path={} reason={}", project_path, error)
        return {
            "success": False,
            "path": project_path,
            "dialog_found": False,
            "path_entered": False,
            "confirm_clicked": False,
            "dialog_closed": False,
            "project_state_changed": False,
            "detected_changes": [],
            "error": error,
        }

    before = asdict(capture_state_snapshot("project_open_before"))
    result = open_project_file_via_dialog_dict(
        project_path,
        before_snapshot=before,
        after_snapshot_provider=lambda: asdict(capture_state_snapshot("project_open_after")),
    )
    logger.info("open test project result={}", result)
    return result


def _write_state_outputs(state_dir: Path, state_map: RuntimeStateMap) -> None:
    write_json(state_dir / "state_snapshot.json", state_map.snapshot)
    write_json(state_dir / "top_menus.json", state_map.top_menus)
    write_json(state_dir / "menu_rows.json", state_map.menu_rows)
    write_json(state_dir / "actions.json", state_map.actions)
    write_json(state_dir / "dialogs.json", state_map.dialogs)
    write_json(state_dir / "windows.json", state_map.windows)
    write_json(state_dir / "skipped_actions.json", state_map.skipped_actions)


def build_full_runtime_program_map(
    project_path: str | None = None,
    safe_mode: str = "safe",
    output_dir: str | Path = "data/runtime_maps",
    state_id_prefix: str = "state",
) -> dict[str, Any]:
    paths = ensure_output_dirs(Path(output_dir))

    state_no_project_id = f"{state_id_prefix}_no_project"
    state_project_open_id = f"{state_id_prefix}_project_open"

    state_no_project = map_runtime_state(state_id=state_no_project_id, safe_mode=safe_mode)
    _write_state_outputs(paths["state_no_project"], state_no_project)

    project_open_result = None
    if project_path:
        project_open_result = open_test_project(project_path, safe_mode=safe_mode)

    state_project_open = map_runtime_state(state_id=state_project_open_id, safe_mode=safe_mode)
    _write_state_outputs(paths["state_project_open"], state_project_open)

    diff = compare_runtime_states(state_no_project, state_project_open)
    write_json(paths["diff"] / "menu_diff.json", diff.top_menu_diff)
    write_json(paths["diff"] / "dialogs_diff.json", diff.dialog_diff)
    write_json(paths["diff"] / "windows_diff.json", diff.window_diff)
    write_json(paths["diff"] / "actions_diff.json", diff.menu_action_diff)
    write_json(paths["diff"] / "state_comparison.json", asdict(diff))
    write_markdown_summary(paths["diff"] / "state_comparison.md", diff)

    return {
        "state_no_project": state_no_project,
        "state_project_open": state_project_open,
        "diff": diff,
        "project_open_result": project_open_result,
        "output_dir": str(paths["base"]),
    }

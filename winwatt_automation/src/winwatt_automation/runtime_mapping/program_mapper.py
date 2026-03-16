from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from winwatt_automation.live_ui import menu_helpers
from winwatt_automation.live_ui.app_connector import ensure_main_window_foreground_before_click, get_cached_main_window
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


DEFAULT_TOP_MENUS = ["Fájl", "Jegyzékek", "Adatbázisok", "Beállítások", "Ablak", "Súgó"]



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
        },
    )


def get_canonical_top_menu_names(discovered_top_menus: list[str]) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    normalized_to_raw: dict[str, str] = {}

    for raw_name in discovered_top_menus:
        normalized = normalize_menu_title(raw_name)
        if not normalized or normalized in normalized_to_raw:
            continue
        clean_name = clean_menu_title(raw_name)
        normalized_to_raw[normalized] = raw_name
        items.append({"raw": raw_name, "clean": clean_name, "normalized": normalized})

    logger.info("Canonical top-level menus [{}]: {}", len(items), [item["raw"] for item in items])
    return {
        "items": items,
        "normalized_to_raw": normalized_to_raw,
        "normalized_names": set(normalized_to_raw),
    }


def is_top_menu_like_popup_row(row: dict[str, Any], canonical_top_menu_names: set[str]) -> bool:
    text = str(row.get("text") or "")
    normalized = normalize_menu_title(text)
    return bool(normalized and normalized in canonical_top_menu_names)


def restore_clean_menu_baseline(*, state_id: str, stage: str) -> bool:
    logger.debug("baseline_restore start state={} stage={}", state_id, stage)
    try:
        ensure_main_window_foreground_before_click(action_label=f"baseline_restore:{state_id}:{stage}")
    except Exception as exc:
        logger.error("baseline_restore failed state={} stage={} error={}", state_id, stage, exc)
        return False

    for _ in range(2):
        try:
            from pywinauto import keyboard

            keyboard.send_keys("{ESC}")
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
    if forced_result_type:
        result_type = forced_result_type
    elif not attempted:
        result_type = "skipped_unsafe"
    elif error_text:
        result_type = "failed"
    elif dialog_detection and dialog_detection.get("dialog_detected"):
        result_type = "success_dialog_opened"
    elif len(after_snapshot.visible_top_windows) > len(before_snapshot.visible_top_windows):
        result_type = "success_popup_opened"
    elif before_snapshot.main_window_title != after_snapshot.main_window_title:
        result_type = "state_changed"
    else:
        result_type = "failed_no_visible_change"

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
) -> tuple[list[dict[str, Any]], list[RuntimeMenuRow], list[RuntimeActionResult], list[RuntimeDialogRecord], list[RuntimeWindowRecord]]:
    parent_path = list(parent_path or [clean_menu_title(top_menu)])
    if popup_rows is None:
        menu_helpers.click_top_menu_item(top_menu)
        popup_rows = menu_helpers.capture_menu_popup_snapshot()

    if visited_paths is None:
        visited_paths = set()

    menu_rows = _build_menu_rows_from_popup_rows(
        state_id,
        top_menu,
        popup_rows,
        canonical_top_menu_names=canonical_top_menu_names,
    )
    nodes: list[dict[str, Any]] = []
    actions: list[RuntimeActionResult] = []
    dialogs: list[RuntimeDialogRecord] = []
    windows: list[RuntimeWindowRecord] = []

    for row in menu_rows:
        if not include_disabled and row.enabled_guess is False:
            continue
        path = parent_path + [row.text]
        normalized_path = tuple(normalize_menu_title(part) for part in path)
        if normalized_path in visited_paths:
            logger.debug("visited path skip state={} path={}", state_id, normalized_path)
            continue
        visited_paths.add(normalized_path)

        skipped = row.is_separator or (not is_action_allowed(path, mode=safe_mode))
        opens_submenu = False
        children_nodes: list[dict[str, Any]] = []

        if depth < max_depth and not row.is_separator and row.enabled_guess is not False:
            _hover_row(asdict(row))
            current_rows = menu_helpers.capture_menu_popup_snapshot()
            child_rows = _detect_child_rows(asdict(row), current_rows)
            if canonical_top_menu_names:
                child_rows = [
                    child_row
                    for child_row in child_rows
                    if not is_top_menu_like_popup_row(child_row, canonical_top_menu_names)
                ]
            if child_rows:
                opens_submenu = True
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
                )
                children_nodes = child_nodes
                menu_rows.extend(child_menu_rows)
                actions.extend(child_actions)
                dialogs.extend(child_dialogs)
                windows.extend(child_windows)

        node = _row_to_node(
            state_id,
            top_menu,
            asdict(row),
            level=depth,
            index=row.row_index,
            path=path,
            children=children_nodes,
            opens_submenu=opens_submenu,
            skipped_by_safety=skipped,
        )
        nodes.append(asdict(node))
        actions.append(
            classify_post_click_result(
                process_id=None,
                before_snapshot=capture_state_snapshot(state_id),
                after_snapshot=capture_state_snapshot(state_id),
                dialog_detection=None,
                state_id=state_id,
                top_menu=top_menu,
                row_index=row.row_index,
                menu_path=path,
                action_key=" > ".join(path),
                safety_level=classify_safety([clean_menu_title(part) for part in path]),
                attempted=not skipped,
                notes="mapped_only",
            )
        )

    return nodes, menu_rows, actions, dialogs, windows


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

    for top_menu_normalized, _ in target_menu_map.items():
        discovered_top_menu = canonical_top_menus["normalized_to_raw"].get(top_menu_normalized)
        if not discovered_top_menu:
            continue

        if not restore_clean_menu_baseline(state_id=state_id, stage=f"before:{discovered_top_menu}"):
            partial_mapping = True
            stop_reason = f"lost_main_window_before:{discovered_top_menu}"
            logger.error("unrecoverable main window loss before top menu state={} top_menu={}", state_id, discovered_top_menu)
            break

        try:
            tree, rows, actions, dialogs, windows = explore_menu_tree(
                state_id=state_id,
                top_menu=discovered_top_menu,
                safe_mode=safe_mode,
                max_depth=max_submenu_depth,
                include_disabled=include_disabled,
                canonical_top_menu_names=canonical_top_menus["normalized_names"],
                visited_paths={(normalize_menu_title(discovered_top_menu),)},
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
                partial_mapping = True
                stop_reason = f"unrecoverable:{discovered_top_menu}"
                logger.error("unrecoverable main window loss during top menu state={} top_menu={}", state_id, discovered_top_menu)
                break

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
    return open_project_file_via_dialog_dict(
        project_path,
        before_snapshot=before,
        after_snapshot_provider=lambda: asdict(capture_state_snapshot("project_open_after")),
    )


def _write_state_outputs(state_dir: Path, state_map: RuntimeStateMap) -> None:
    write_json(state_dir / "snapshot.json", state_map.snapshot)
    write_json(state_dir / "menu_tree.json", state_map.menu_tree)
    write_json(state_dir / "dialogs.json", state_map.dialogs)
    write_json(state_dir / "windows.json", state_map.windows)
    (state_dir / "summary.md").write_text(_state_summary_markdown(state_map), encoding="utf-8")


def build_full_runtime_program_map(
    project_path: str | None = None,
    safe_mode: str = "safe",
    output_dir: str | Path = "data/runtime_maps",
    state_id_prefix: str = "state",
    top_menus: list[str] | None = None,
    max_submenu_depth: int = 3,
    include_disabled: bool = True,
) -> dict[str, Any]:
    paths = ensure_output_dirs(Path(output_dir))
    no_project_id = "no_project" if state_id_prefix == "state" else f"{state_id_prefix}_no_project"
    project_id = "project_open" if state_id_prefix == "state" else f"{state_id_prefix}_project_open"

    state_no_project = map_runtime_state(
        state_id=no_project_id,
        safe_mode=safe_mode,
        top_menus=top_menus,
        max_submenu_depth=max_submenu_depth,
        include_disabled=include_disabled,
    )
    _write_state_outputs(paths["state_no_project"], state_no_project)

    project_open_result = open_test_project(project_path, safe_mode=safe_mode) if project_path else None

    state_project_open = map_runtime_state(
        state_id=project_id,
        safe_mode=safe_mode,
        top_menus=top_menus,
        max_submenu_depth=max_submenu_depth,
        include_disabled=include_disabled,
    )
    _write_state_outputs(paths["state_project_open"], state_project_open)

    diff = compare_runtime_states(state_no_project, state_project_open)
    write_json(paths["diff"] / "state_diff.json", asdict(diff))
    (paths["diff"] / "summary.md").write_text(_diff_summary_markdown(diff), encoding="utf-8")

    skipped = sum(1 for action in state_no_project.actions + state_project_open.actions if not action.get("attempted", False))
    print(f"no_project menük száma: {len(state_no_project.top_menus)}")
    print(f"project_open menük száma: {len(state_project_open.top_menus)}")
    print(f"diff változások: {len(diff.enabled_state_changes) + len(diff.project_only_paths)}")
    print(f"skipped_by_safety: {skipped}")
    print(f"output: {paths['base']}")

    return {
        "state_no_project": state_no_project,
        "state_project_open": state_project_open,
        "diff": diff,
        "project_open_result": project_open_result,
        "output_dir": str(paths["base"]),
    }

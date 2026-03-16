"""Helpers for interacting with WinWatt menu items via UI Automation."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger
from winwatt_automation.live_ui.app_connector import (
    get_main_window,
    is_main_window_foreground,
    prepare_main_window_for_menu_interaction,
)

def _mouse_click(coords: tuple[int, int]) -> None:
    from pywinauto import mouse

    mouse.click(button="left", coords=coords)


_LAST_MENU_SNAPSHOT_BEFORE_OPEN: set[tuple[str, str, str, str, str]] | None = None


def _normalize(text: str | None) -> str:
    return (text or "").strip().lower()


def _name(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return (getattr(info, "name", None) or "").strip()


def _is_visible(wrapper: Any) -> bool:
    is_visible = getattr(wrapper, "is_visible", None)
    if callable(is_visible):
        try:
            return bool(is_visible())
        except Exception:
            return False
    return False


def _control_type(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return _normalize(getattr(info, "control_type", None))


def _class_name(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return (getattr(info, "class_name", None) or "").strip()


def _rectangle_data(wrapper: Any) -> dict[str, int] | None:
    rectangle = getattr(wrapper, "rectangle", None)
    if not callable(rectangle):
        return None
    try:
        rect = rectangle()
    except Exception:
        return None

    left = getattr(rect, "left", None)
    top = getattr(rect, "top", None)
    right = getattr(rect, "right", None)
    bottom = getattr(rect, "bottom", None)
    if None in (left, top, right, bottom):
        return None

    left_i = int(left)
    top_i = int(top)
    right_i = int(right)
    bottom_i = int(bottom)
    width = max(0, right_i - left_i)
    height = max(0, bottom_i - top_i)
    return {
        "left": left_i,
        "top": top_i,
        "right": right_i,
        "bottom": bottom_i,
        "width": width,
        "height": height,
        "center_x": int((left_i + right_i) / 2),
        "center_y": int((top_i + bottom_i) / 2),
    }


def _parent_wrapper(wrapper: Any) -> Any | None:
    parent = getattr(wrapper, "parent", None)
    return parent() if callable(parent) else None


def _has_menuitem_ancestor(wrapper: Any) -> bool:
    seen: set[int] = set()
    current = _parent_wrapper(wrapper)
    while current is not None:
        marker = id(current)
        if marker in seen:
            break
        seen.add(marker)

        if _control_type(current) == "menuitem":
            return True
        current = _parent_wrapper(current)
    return False


def _menu_items() -> list[Any]:
    root = get_main_window()
    descendants = getattr(root, "descendants", None)
    if not callable(descendants):
        return []

    items = [item for item in descendants() if _control_type(item) == "menuitem"]
    logger.info("Discovered {} MenuItem controls", len(items))
    return items


def _top_level_menu_items_raw() -> list[Any]:
    items: list[Any] = []
    for item in _menu_items():
        parent_type = _control_type(_parent_wrapper(item))
        if parent_type not in {"menu", "menubar"}:
            continue
        if _has_menuitem_ancestor(item):
            continue
        items.append(item)
    return items


def list_top_menu_items() -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    for item in _top_level_menu_items_raw():
        text = _name(item)
        if not text:
            continue
        key = _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        names.append(text)

    logger.info("Top-level menu items (raw): {}", names)
    return names


def list_open_menu_items() -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    for item in _menu_items():
        if not _is_visible(item):
            continue
        text = _name(item)
        if not text:
            continue

        parent_wrapper = _parent_wrapper(item)
        parent_type = _control_type(parent_wrapper)
        if parent_type not in {"menu", "menuitem"}:
            continue

        key = _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        names.append(text)

    logger.info("Open/visible menu entries: {}", names)
    return names


def _is_separator_by_geometry(rect: dict[str, int]) -> bool:
    width = rect["width"]
    height = rect["height"]
    return height <= 3 or width <= 6 or (height <= 5 and width >= 40)


def _menu_like_controls_from_main_window() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _menu_items():
        if not _is_visible(item):
            continue

        rect = _rectangle_data(item)
        if rect is None:
            continue

        rows.append(
            {
                "text": _name(item),
                "normalized_text": _normalize(_name(item)),
                "control_type": getattr(getattr(item, "element_info", item), "control_type", None),
                "class_name": _class_name(item),
                "rectangle": {
                    "left": rect["left"],
                    "top": rect["top"],
                    "right": rect["right"],
                    "bottom": rect["bottom"],
                },
                "width": rect["width"],
                "height": rect["height"],
                "center_x": rect["center_x"],
                "center_y": rect["center_y"],
                "is_separator": _is_separator_by_geometry(rect),
                "source_scope": "main_window",
            }
        )
    return rows


def _menu_like_controls_from_global_process_scan() -> list[dict[str, Any]]:
    try:
        from pywinauto import Desktop
    except Exception:
        return []

    main_window = get_main_window()
    process_id = main_window.process_id()
    desktop = Desktop(backend="uia")

    rows: list[dict[str, Any]] = []
    for window in desktop.windows(top_level_only=True):
        try:
            if window.process_id() != process_id:
                continue
            descendants = getattr(window, "descendants", None)
            if not callable(descendants):
                continue
            for item in descendants(control_type="MenuItem"):
                if not _is_visible(item):
                    continue
                rect = _rectangle_data(item)
                if rect is None:
                    continue
                rows.append(
                    {
                        "text": _name(item),
                        "normalized_text": _normalize(_name(item)),
                        "control_type": getattr(getattr(item, "element_info", item), "control_type", None),
                        "class_name": _class_name(item),
                        "rectangle": {
                            "left": rect["left"],
                            "top": rect["top"],
                            "right": rect["right"],
                            "bottom": rect["bottom"],
                        },
                        "width": rect["width"],
                        "height": rect["height"],
                        "center_x": rect["center_x"],
                        "center_y": rect["center_y"],
                        "is_separator": _is_separator_by_geometry(rect),
                        "source_scope": "global_process_scan",
                    }
                )
        except Exception:
            continue
    return rows


def _snapshot_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str, str, str, str]]:
    keys: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        rect = row.get("rectangle") or {}
        rect_key = f"({rect.get('left')},{rect.get('top')})-({rect.get('right')},{rect.get('bottom')})"
        keys.add(
            (
                row.get("normalized_text", ""),
                _normalize(str(row.get("control_type", ""))),
                _normalize(str(row.get("class_name", ""))),
                rect_key,
                row.get("source_scope", ""),
            )
        )
    return keys


def capture_menu_popup_snapshot() -> list[dict[str, Any]]:
    """Capture current menu-like controls from main window and global process scans."""

    merged = _menu_like_controls_from_main_window() + _menu_like_controls_from_global_process_scan()
    seen: set[tuple[int, int, int, int, str, str, str]] = set()
    unique_rows: list[dict[str, Any]] = []

    for row in merged:
        rect = row["rectangle"]
        key = (
            rect["left"],
            rect["top"],
            rect["right"],
            rect["bottom"],
            row["normalized_text"],
            _normalize(str(row["class_name"])),
            row["source_scope"],
        )
        if key in seen:
            continue
        seen.add(key)
        row["appeared_after_popup_open"] = False
        unique_rows.append(row)

    logger.info("Captured menu snapshot rows={}", len(unique_rows))
    return unique_rows


def _reject_popup_candidate_reason(
    entry: dict[str, Any],
    top_level_rects: set[tuple[int, int, int, int]],
    top_level_texts: set[str],
    *,
    permissive: bool = False,
) -> str | None:
    rect = entry.get("rectangle") or {}
    left = int(rect.get("left", 0))
    top = int(rect.get("top", 0))
    right = int(rect.get("right", 0))
    bottom = int(rect.get("bottom", 0))
    width = int(entry.get("width") or (right - left))
    height = int(entry.get("height") or (bottom - top))

    if right <= left or bottom <= top:
        return "non-positive rectangle dimensions"
    if width <= 0 or height <= 0:
        return "zero-sized row"
    if width < 2:
        return "width below minimum threshold"
    if height < 1:
        return "height below minimum threshold"

    rect_key = (left, top, right, bottom)
    normalized_text = _normalize(str(entry.get("text", "")))
    if rect_key in top_level_rects and normalized_text in top_level_texts and normalized_text:
        return "identical to top menu bar item"

    if not permissive:
        return None
    return None


def _structured_popup_rows_from_snapshots(
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract structured popup rows by diffing two menu snapshots."""

    before_keys = _snapshot_keys(before_rows)
    after_keys = _snapshot_keys(after_rows)
    new_keys = after_keys - before_keys

    top_level_rects = {
        (rect["left"], rect["top"], rect["right"], rect["bottom"])
        for item in _top_level_menu_items_raw()
        for rect in [_rectangle_data(item)]
        if rect is not None
    }

    top_level_texts = {_normalize(_name(item)) for item in _top_level_menu_items_raw() if _normalize(_name(item))}

    popup_candidates: list[dict[str, Any]] = []
    for row in after_rows:
        rect = row["rectangle"]
        row_key = (
            row["normalized_text"],
            _normalize(str(row.get("control_type", ""))),
            _normalize(str(row.get("class_name", ""))),
            f"({rect['left']},{rect['top']})-({rect['right']},{rect['bottom']})",
            row["source_scope"],
        )
        row["appeared_after_popup_open"] = row_key in new_keys
        if not row["appeared_after_popup_open"]:
            continue
        rejection_reason = _reject_popup_candidate_reason(row, top_level_rects, top_level_texts)
        if rejection_reason is not None:
            logger.info(
                "Rejected popup row: rect={} text={!r} scope={} control_type={} reason={}",
                row.get("rectangle"),
                row.get("text", ""),
                row.get("source_scope", ""),
                row.get("control_type", ""),
                rejection_reason,
            )
            continue
        popup_candidates.append(row)

    if not popup_candidates and new_keys:
        logger.info("Strict popup filtering returned 0 rows; entering permissive fallback mode")
        seen_fallback: set[tuple[tuple[int, int, int, int], str, str]] = set()
        for row in after_rows:
            rect = row["rectangle"]
            row_key = (
                row["normalized_text"],
                _normalize(str(row.get("control_type", ""))),
                _normalize(str(row.get("class_name", ""))),
                f"({rect['left']},{rect['top']})-({rect['right']},{rect['bottom']})",
                row["source_scope"],
            )
            if row_key not in new_keys:
                continue

            rejection_reason = _reject_popup_candidate_reason(row, top_level_rects, top_level_texts, permissive=True)
            if rejection_reason is not None:
                logger.info(
                    "Rejected popup row: rect={} text={!r} scope={} control_type={} reason={}",
                    row.get("rectangle"),
                    row.get("text", ""),
                    row.get("source_scope", ""),
                    row.get("control_type", ""),
                    rejection_reason,
                )
                continue

            rect = row["rectangle"]
            dedupe_key = (
                (rect["left"], rect["top"], rect["right"], rect["bottom"]),
                str(row.get("text", "")),
                str(row.get("source_scope", "")),
            )
            if dedupe_key in seen_fallback:
                logger.info(
                    "Rejected popup row: rect={} text={!r} scope={} control_type={} reason={}",
                    row.get("rectangle"),
                    row.get("text", ""),
                    row.get("source_scope", ""),
                    row.get("control_type", ""),
                    "exact duplicate in permissive fallback",
                )
                continue
            seen_fallback.add(dedupe_key)
            popup_candidates.append(row)

    if not popup_candidates:
        logger.info(
            "Structured popup rows: before snapshot row count={} after snapshot row count={} structured row count=0",
            len(before_rows),
            len(after_rows),
        )
        return []

    popup_candidates.sort(key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"]))

    source_preference = {"main_window": 0, "global_process_scan": 1}
    deduped_by_visual_identity: dict[tuple[tuple[int, int, int, int], str, str], dict[str, Any]] = {}
    for candidate in popup_candidates:
        rect = candidate["rectangle"]
        identity_key = (
            (rect["left"], rect["top"], rect["right"], rect["bottom"]),
            _normalize(str(candidate.get("text", ""))),
            _normalize(str(candidate.get("control_type", ""))),
        )

        existing = deduped_by_visual_identity.get(identity_key)
        if existing is None:
            deduped_by_visual_identity[identity_key] = candidate
            logger.info(
                "Popup row dedupe: rect={} text={!r} control_type={} chosen preferred source={}",
                candidate.get("rectangle"),
                candidate.get("text", ""),
                candidate.get("control_type", ""),
                candidate.get("source_scope", ""),
            )
            continue

        existing_rank = source_preference.get(str(existing.get("source_scope", "")), 999)
        candidate_rank = source_preference.get(str(candidate.get("source_scope", "")), 999)
        if candidate_rank < existing_rank:
            deduped_by_visual_identity[identity_key] = candidate

        preferred = deduped_by_visual_identity[identity_key]
        logger.info(
            "Popup row dedupe: rect={} text={!r} control_type={} chosen preferred source={} dropped source={}",
            preferred.get("rectangle"),
            preferred.get("text", ""),
            preferred.get("control_type", ""),
            preferred.get("source_scope", ""),
            candidate.get("source_scope", "") if preferred is existing else existing.get("source_scope", ""),
        )

    filtered = sorted(
        deduped_by_visual_identity.values(),
        key=lambda item: (item["rectangle"]["top"], item["rectangle"]["left"]),
    )
    for idx, entry in enumerate(filtered):
        entry["index"] = idx

    logger.info(
        "Structured popup rows: before snapshot row count={} after snapshot row count={} structured row count={} deduped row count={}",
        len(before_rows),
        len(after_rows),
        len(popup_candidates),
        len(filtered),
    )
    return filtered


def open_file_menu_and_capture_popup_state() -> dict[str, Any]:
    """Open ``Fájl`` once and return popup snapshots plus structured rows."""

    main_window = prepare_main_window_for_menu_interaction()
    item = find_top_menu_item("Fájl")

    before_rows = capture_menu_popup_snapshot()
    process_id = None
    process_id_getter = getattr(main_window, "process_id", None)
    if callable(process_id_getter):
        try:
            process_id = int(process_id_getter())
        except Exception:
            process_id = None
    top_menu_click_count = 0
    try:
        item.click_input()
        top_menu_click_count += 1
    except Exception as exc:
        logger.warning("Top menu item 'Fájl' click_input() failed: {}", exc)
        _click_by_relative_rect_center(item, main_window)
        top_menu_click_count += 1

    time.sleep(0.2)
    after_rows = capture_menu_popup_snapshot()
    popup_open = did_any_new_menu_popup_appear(_snapshot_keys(before_rows), _snapshot_keys(after_rows))
    structured_rows = _structured_popup_rows_from_snapshots(before_rows, after_rows)

    logger.info(
        "Menu open transitions: before snapshot row count={} after snapshot row count={} structured row count={} top menu clicked more than once={}",
        len(before_rows),
        len(after_rows),
        len(structured_rows),
        top_menu_click_count > 1,
    )

    global _LAST_MENU_SNAPSHOT_BEFORE_OPEN
    _LAST_MENU_SNAPSHOT_BEFORE_OPEN = _snapshot_keys(before_rows)
    return {
        "before_snapshot": before_rows,
        "after_snapshot": after_rows,
        "rows": structured_rows,
        "popup_open": popup_open,
        "top_menu_click_count": top_menu_click_count,
        "process_id": process_id,
    }


def click_structured_popup_row(rows: list[dict[str, Any]], index: int) -> dict[str, Any]:
    """Click one already-discovered popup row without reopening the top menu."""

    if index < 0:
        raise ValueError("index must be >= 0")
    if not rows:
        raise ValueError("popup rows are empty; cannot click submenu row")
    if index >= len(rows):
        raise IndexError(f"Requested popup index {index}, but only {len(rows)} entries exist")

    selected = rows[index]
    if selected.get("is_separator"):
        raise ValueError(f"Requested popup index {index} is a separator and cannot be clicked")

    x = int(selected["center_x"])
    y = int(selected["center_y"])
    _mouse_click((x, y))
    logger.info(
        "Popup row click: selected row index={} selected row rectangle={} top menu clicked more than once={}",
        index,
        selected.get("rectangle"),
        False,
    )
    return selected


def list_open_menu_items_structured() -> list[dict[str, Any]]:
    """Return popup submenu entries in deterministic visual order using snapshot diff."""

    state = open_file_menu_and_capture_popup_state()
    return state["rows"]


def find_top_menu_item(title: str) -> Any:
    wanted = _normalize(title)
    matches = [item for item in _top_level_menu_items_raw() if _normalize(_name(item)) == wanted]
    if matches:
        return next((match for match in matches if _is_visible(match)), matches[0])
    raise LookupError(f"Top menu item '{title}' was not found")


def _menu_snapshot() -> set[tuple[str, str, str, str, str]]:
    rows = capture_menu_popup_snapshot()
    return _snapshot_keys(rows)


def did_any_new_menu_popup_appear(
    before_snapshot: set[tuple[str, str, str, str, str]],
    after_snapshot: set[tuple[str, str, str, str, str]],
) -> bool:
    new_items = after_snapshot - before_snapshot
    logger.info(
        "Menu popup snapshot diff: before={} after={} new={}",
        len(before_snapshot),
        len(after_snapshot),
        len(new_items),
    )
    return bool(new_items)


def _click_by_relative_rect_center(item: Any, main_window: Any) -> None:
    rect = item.rectangle()
    x = int((int(rect.left) + int(rect.right)) / 2)
    y = int((int(rect.top) + int(rect.bottom)) / 2)

    window_rect = main_window.rectangle()
    rel_x = int(x - int(window_rect.left))
    rel_y = int(y - int(window_rect.top))

    if callable(getattr(main_window, "click_input", None)):
        main_window.click_input(coords=(rel_x, rel_y))
        logger.info("Fallback menu click used rel coords rel_x={} rel_y={}", rel_x, rel_y)
        return

    _mouse_click((x, y))
    logger.info("Fallback menu click used absolute coords x={} y={}", x, y)


def click_top_menu_item(title: str) -> None:
    main_window = prepare_main_window_for_menu_interaction()
    logger.info("click_top_menu_item('{}'): foreground_before_click={}", title, is_main_window_foreground())

    item = find_top_menu_item(title)
    global _LAST_MENU_SNAPSHOT_BEFORE_OPEN
    before_snapshot = _menu_snapshot()
    _LAST_MENU_SNAPSHOT_BEFORE_OPEN = before_snapshot

    try:
        item.click_input()
    except Exception as exc:
        logger.warning("Top menu item '{}' click_input() failed: {}", title, exc)

    time.sleep(0.2)
    after_snapshot = _menu_snapshot()
    if did_any_new_menu_popup_appear(before_snapshot, after_snapshot):
        return

    _click_by_relative_rect_center(item, main_window)
    time.sleep(0.2)
    fallback_snapshot = _menu_snapshot()
    if did_any_new_menu_popup_appear(before_snapshot, fallback_snapshot):
        return

    raise RuntimeError(f"Top menu item '{title}' click attempts did not open a menu popup")


def click_open_menu_item_by_index(index: int) -> dict[str, Any]:
    if index < 0:
        raise ValueError("index must be >= 0")

    prepare_main_window_for_menu_interaction()
    popup_state = open_file_menu_and_capture_popup_state()
    popup_rows = popup_state["rows"]
    if popup_rows:
        return click_structured_popup_row(popup_rows, index)

    logger.info("Popup rows empty after open; retrying open/capture for index={}", index)
    retry_rows = open_file_menu_and_capture_popup_state()["rows"]
    return click_structured_popup_row(retry_rows, index)

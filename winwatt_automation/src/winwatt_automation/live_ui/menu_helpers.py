"""Helpers for interacting with WinWatt top-menu items via UI Automation."""

from __future__ import annotations

import time

from typing import Any

from loguru import logger
from pywinauto import mouse

_LAST_MENU_SNAPSHOT_BEFORE_OPEN: set[tuple[str, str, str, str]] | None = None

from winwatt_automation.live_ui.app_connector import (
    get_main_window,
    is_main_window_foreground,
    prepare_main_window_for_menu_interaction,
)


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


def _menu_items() -> list[Any]:
    root = get_main_window()
    descendants = getattr(root, "descendants", None)
    if not callable(descendants):
        return []

    items = [item for item in descendants() if _normalize(getattr(item.element_info, "control_type", None)) == "menuitem"]
    logger.info("Discovered {} MenuItem controls", len(items))
    for item in items:
        logger.info("MenuItem discovered: text='{}' visible={}", _name(item), _is_visible(item))
    return items


def _parent_wrapper(wrapper: Any) -> Any | None:
    parent = getattr(wrapper, "parent", None)
    return parent() if callable(parent) else None


def _control_type(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return _normalize(getattr(info, "control_type", None))


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


def _top_level_menu_items_raw() -> list[Any]:
    """Return top-level menu items under the main menu bar without visibility filtering."""

    items: list[Any] = []
    for item in _menu_items():
        parent_type = _control_type(_parent_wrapper(item))
        if parent_type not in {"menu", "menubar"}:
            continue
        if _has_menuitem_ancestor(item):
            continue
        items.append(item)

    logger.info("Discovered {} top-level MenuItem controls (raw)", len(items))
    return items


def _rectangle_repr(wrapper: Any) -> str | None:
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
    if None in {left, top, right, bottom}:
        return str(rect)
    return f"({left},{top})-({right},{bottom})"


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


def _class_name(wrapper: Any) -> str:
    info = getattr(wrapper, "element_info", wrapper)
    return (getattr(info, "class_name", None) or "").strip()


def list_top_menu_items() -> list[str]:
    """Return top-level menu item captions from the main menu bar."""

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
    """Return visible submenu/menu-popup item captions."""

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


def list_open_menu_items_structured() -> list[dict[str, Any]]:
    """Return popup submenu items sorted by geometry, even if their caption text is empty."""

    top_level_rects = {
        (rect["left"], rect["top"], rect["right"], rect["bottom"])
        for item in _top_level_menu_items_raw()
        for rect in [_rectangle_data(item)]
        if rect is not None
    }

    raw_candidates: list[dict[str, Any]] = []
    seen_rectangles: set[tuple[int, int, int, int, str, str]] = set()

    for item in _menu_items():
        if not _is_visible(item):
            continue

        rect = _rectangle_data(item)
        if rect is None:
            continue
        if rect["width"] <= 0 or rect["height"] <= 0:
            continue

        parent_type = _control_type(_parent_wrapper(item))
        control_type = _control_type(item)
        if parent_type not in {"menu", "menuitem"} and control_type != "menuitem":
            continue

        rect_key = (rect["left"], rect["top"], rect["right"], rect["bottom"])
        if rect_key in top_level_rects:
            continue

        dedupe_key = (*rect_key, _normalize(_name(item)), _class_name(item).lower())
        if dedupe_key in seen_rectangles:
            continue
        seen_rectangles.add(dedupe_key)

        raw_candidates.append(
            {
                "wrapper": item,
                "text": _name(item),
                "control_type": getattr(item.element_info, "control_type", None),
                "class_name": _class_name(item),
                "rectangle": rect_key,
                "width": rect["width"],
                "height": rect["height"],
                "center": (rect["center_x"], rect["center_y"]),
                "is_separator": rect["height"] <= 2 and rect["width"] >= 40,
            }
        )

    if _LAST_MENU_SNAPSHOT_BEFORE_OPEN is not None:
        baseline_rects = {entry[3] for entry in _LAST_MENU_SNAPSHOT_BEFORE_OPEN if len(entry) >= 4}
        raw_candidates = [item for item in raw_candidates if _rectangle_repr(item.get("wrapper")) not in baseline_rects]

    if not raw_candidates:
        return []

    popup_left = min(item["rectangle"][0] for item in raw_candidates)
    popup_right = max(item["rectangle"][2] for item in raw_candidates)
    popup_top = min(item["rectangle"][1] for item in raw_candidates)
    popup_bottom = max(item["rectangle"][3] for item in raw_candidates)

    filtered = [
        item
        for item in raw_candidates
        if item["rectangle"][0] >= popup_left
        and item["rectangle"][2] <= popup_right
        and item["rectangle"][1] >= popup_top
        and item["rectangle"][3] <= popup_bottom
    ]

    filtered.sort(key=lambda item: (item["rectangle"][1], item["rectangle"][0]))
    for index, item in enumerate(filtered):
        item["order_index"] = index
        item.pop("wrapper", None)

    logger.info("Structured popup submenu entries: {}", filtered)
    return filtered


def find_top_menu_item(title: str) -> Any:
    """Find a top-level menu item by caption, preferring visible matches."""

    wanted = _normalize(title)
    matches = [item for item in _top_level_menu_items_raw() if _normalize(_name(item)) == wanted]
    if matches:
        item = next((match for match in matches if _is_visible(match)), matches[0])
        visible = _is_visible(item)
        rect = _rectangle_repr(item)
        logger.info(
            "Resolved top menu item '{}' -> title='{}' visible={} rectangle={} selected_despite_invisible={}",
            title,
            _name(item),
            visible,
            rect,
            not visible,
        )
        return item

    raise LookupError(f"Top menu item '{title}' was not found")


def _menu_snapshot() -> set[tuple[str, str, str, str]]:
    snapshot: set[tuple[str, str, str, str]] = set()
    for item in _menu_items():
        if not _is_visible(item):
            continue
        parent_type = _control_type(_parent_wrapper(item))
        if parent_type not in {"menu", "menubar", "menuitem"}:
            continue
        text = _normalize(_name(item))
        rect = _rectangle_repr(item) or ""
        control_type = _control_type(item)
        snapshot.add((text, parent_type, control_type, rect))
    return snapshot


def did_any_new_menu_popup_appear(
    before_snapshot: set[tuple[str, str, str, str]],
    after_snapshot: set[tuple[str, str, str, str]],
) -> bool:
    """Detect whether new visible menu-like controls appeared after a click."""

    new_items = after_snapshot - before_snapshot
    logger.info(
        "Menu popup snapshot diff: before={} after={} new={} new_items={}",
        len(before_snapshot),
        len(after_snapshot),
        len(new_items),
        sorted(new_items),
    )
    return bool(new_items)


def _click_by_relative_rect_center(item: Any, main_window: Any) -> None:
    rect_callable = getattr(item, "rectangle", None)
    if not callable(rect_callable):
        raise RuntimeError("rectangle() is unavailable for relative-center click")

    rect = rect_callable()
    left = getattr(rect, "left", None)
    top = getattr(rect, "top", None)
    right = getattr(rect, "right", None)
    bottom = getattr(rect, "bottom", None)
    if None in (left, top, right, bottom):
        raise RuntimeError("rectangle() did not provide complete coordinates")

    x = int((int(left) + int(right)) / 2)
    y = int((int(top) + int(bottom)) / 2)

    window_rect_callable = getattr(main_window, "rectangle", None)
    if not callable(window_rect_callable):
        raise RuntimeError("main_window.rectangle() is unavailable for relative click")

    window_rect = window_rect_callable()
    window_left = getattr(window_rect, "left", None)
    window_top = getattr(window_rect, "top", None)
    if None in (window_left, window_top):
        raise RuntimeError("main_window.rectangle() did not provide origin coordinates")

    rel_x = int(x - int(window_left))
    rel_y = int(y - int(window_top))

    window_click_input = getattr(main_window, "click_input", None)
    if callable(window_click_input):
        window_click_input(coords=(rel_x, rel_y))
        logger.info(
            "Fallback menu click used relative window coordinates rel_x={} rel_y={} (absolute x={} y={})",
            rel_x,
            rel_y,
            x,
            y,
        )
        return

    mouse.click(button="left", coords=(x, y))
    logger.info("Fallback menu click used absolute coordinates x={} y={} because window click_input unavailable", x, y)


def click_top_menu_item(title: str) -> None:
    """Click a top-level menu item by caption and verify menu popup actually opens."""

    main_window = prepare_main_window_for_menu_interaction()
    foreground = is_main_window_foreground()
    logger.info("click_top_menu_item('{}'): foreground_before_click={}", title, foreground)

    item = find_top_menu_item(title)
    global _LAST_MENU_SNAPSHOT_BEFORE_OPEN
    before_snapshot = _menu_snapshot()
    _LAST_MENU_SNAPSHOT_BEFORE_OPEN = before_snapshot

    try:
        item.click_input()
        logger.info("Top menu item '{}' clicked via click_input", title)
    except Exception as exc:
        logger.warning("Top menu item '{}' click_input() failed: {}", title, exc)

    time.sleep(0.2)
    after_snapshot = _menu_snapshot()
    if did_any_new_menu_popup_appear(before_snapshot, after_snapshot):
        return

    logger.info("Top menu item '{}' did not open menu via click_input; trying relative-coordinate fallback", title)
    _click_by_relative_rect_center(item, main_window)

    time.sleep(0.2)
    fallback_snapshot = _menu_snapshot()
    if did_any_new_menu_popup_appear(before_snapshot, fallback_snapshot):
        return

    raise RuntimeError(f"Top menu item '{title}' click attempts did not open a menu popup")


def click_open_menu_item_by_index(index: int) -> dict[str, Any]:
    """Open ``Fájl`` and click one visible popup entry by geometry order index."""

    if index < 0:
        raise ValueError("index must be >= 0")

    click_top_menu_item("Fájl")
    entries = list_open_menu_items_structured()
    clickable_entries = [entry for entry in entries if not entry.get("is_separator", False)]
    if index >= len(clickable_entries):
        raise IndexError(f"Requested popup index {index}, but only {len(clickable_entries)} clickable entries exist")

    selected = clickable_entries[index]
    center = selected["center"]
    mouse.click(button="left", coords=(int(center[0]), int(center[1])))
    logger.info("Clicked popup submenu entry by index={} at center={} entry={}", index, center, selected)
    return selected

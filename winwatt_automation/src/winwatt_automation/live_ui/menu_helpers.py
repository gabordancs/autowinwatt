"""Helpers for interacting with WinWatt top-menu items via UI Automation."""

from __future__ import annotations

import time

from typing import Any

from loguru import logger
from pywinauto import mouse

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
    before_snapshot = _menu_snapshot()

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

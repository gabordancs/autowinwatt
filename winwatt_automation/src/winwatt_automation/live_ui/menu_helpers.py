"""Helpers for interacting with WinWatt top-menu items via UI Automation."""

from __future__ import annotations

from typing import Any

from loguru import logger

from winwatt_automation.live_ui.app_connector import get_main_window


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


def click_top_menu_item(title: str) -> None:
    """Click a top-level menu item by caption."""

    item = find_top_menu_item(title)
    for strategy in ("click_input", "invoke", "select"):
        method = getattr(item, strategy, None)
        if not callable(method):
            continue
        try:
            method()
        except Exception as exc:
            logger.warning("Top menu item '{}' {}() failed: {}", title, strategy, exc)
            continue
        logger.info("Clicked top menu item '{}' via {}", title, strategy)
        return

    raise RuntimeError(f"Top menu item '{title}' was found but no click action is supported")

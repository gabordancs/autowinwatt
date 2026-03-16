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


def list_top_menu_items() -> list[str]:
    """Return visible top-level menu item captions from the main menu bar."""

    names: list[str] = []
    seen: set[str] = set()

    for item in _menu_items():
        if not _is_visible(item):
            continue
        text = _name(item)
        if not text:
            continue
        key = _normalize(text)
        if key in seen:
            continue
        seen.add(key)
        names.append(text)

    logger.info("Top-level visible menu items: {}", names)
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

        parent = getattr(item, "parent", None)
        parent_wrapper = parent() if callable(parent) else None
        parent_type = _normalize(getattr(getattr(parent_wrapper, "element_info", parent_wrapper), "control_type", None))
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
    """Find a visible top-level menu item by caption."""

    wanted = _normalize(title)
    for item in _menu_items():
        if not _is_visible(item):
            continue
        if _normalize(_name(item)) == wanted:
            logger.info("Resolved top menu item '{}'", title)
            return item

    raise LookupError(f"Top menu item '{title}' was not found")


def click_top_menu_item(title: str) -> None:
    """Click a top-level menu item by caption."""

    item = find_top_menu_item(title)
    click_input = getattr(item, "click_input", None)
    if callable(click_input):
        click_input()
        logger.info("Clicked top menu item '{}' via click_input", title)
        return

    click = getattr(item, "click", None)
    if callable(click):
        click()
        logger.info("Clicked top menu item '{}' via click", title)
        return

    invoke = getattr(item, "invoke", None)
    if callable(invoke):
        invoke()
        logger.info("Clicked top menu item '{}' via invoke", title)
        return

    raise RuntimeError(f"Top menu item '{title}' was found but no click action is supported")

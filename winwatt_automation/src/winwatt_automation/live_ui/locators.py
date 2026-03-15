"""Locator utilities for live WinWatt controls."""

from __future__ import annotations

from typing import Any

from loguru import logger

from winwatt_automation.live_ui.app_connector import get_main_window


class LocatorError(LookupError):
    """Raised when a form/control cannot be resolved."""


def _get_name(wrapper: Any) -> str | None:
    info = getattr(wrapper, "element_info", wrapper)
    return getattr(info, "name", None)


def _get_automation_id(wrapper: Any) -> str | None:
    info = getattr(wrapper, "element_info", wrapper)
    return getattr(info, "automation_id", None)


def _get_control_type(wrapper: Any) -> str | None:
    info = getattr(wrapper, "element_info", wrapper)
    return getattr(info, "control_type", None)


def _all_descendants(root: Any) -> list[Any]:
    descendants = getattr(root, "descendants", None)
    if callable(descendants):
        return list(descendants())

    items: list[Any] = []
    for child in root.children():
        items.append(child)
        items.extend(_all_descendants(child))
    return items


def _normalize(text: str | None) -> str:
    return (text or "").strip().lower()


def _parse_query(query: str) -> tuple[str, str | None]:
    if ":" in query:
        left, right = query.split(":", 1)
        return left.strip(), right.strip() or None
    return query.strip(), None


def find_form(form_name: str) -> Any:
    """Find a form window by automation-id/name/title with fallback ordering."""

    root = get_main_window()
    query = _normalize(form_name)

    candidates = [root] + _all_descendants(root)

    for candidate in candidates:
        if _normalize(_get_automation_id(candidate)) == query:
            logger.info("Resolved form '{}' by automation_id", form_name)
            return candidate

    for candidate in candidates:
        if _normalize(_get_name(candidate)) == query:
            logger.info("Resolved form '{}' by exact name", form_name)
            return candidate

    for candidate in candidates:
        name = _normalize(_get_name(candidate))
        if query and query in name:
            logger.info("Resolved form '{}' by title/caption match", form_name)
            return candidate

    raise LocatorError(f"Form '{form_name}' was not found")


def find_control(form_name: str, control_name: str) -> Any:
    """Resolve a control inside a parent form using prioritized locator rules."""

    form = find_form(form_name)
    token, expected_type = _parse_query(control_name)
    token_n = _normalize(token)

    candidates = _all_descendants(form)

    for candidate in candidates:
        if _normalize(_get_automation_id(candidate)) == token_n:
            logger.info("Resolved control '{}' by automation_id", control_name)
            return candidate

    for candidate in candidates:
        if _normalize(_get_name(candidate)) == token_n:
            logger.info("Resolved control '{}' by exact name", control_name)
            return candidate

    for candidate in candidates:
        name = _normalize(_get_name(candidate))
        if token_n and token_n in name:
            logger.info("Resolved control '{}' by caption/title", control_name)
            return candidate

    if expected_type:
        expected_type_n = _normalize(expected_type)
        for candidate in candidates:
            if _normalize(_get_control_type(candidate)) == expected_type_n:
                logger.info("Resolved control '{}' by control type", control_name)
                return candidate

    if candidates:
        logger.warning(
            "Using index fallback for control '{}' in form '{}': first candidate",
            control_name,
            form_name,
        )
        return candidates[0]

    raise LocatorError(
        f"Control '{control_name}' was not found within form '{form_name}'"
    )

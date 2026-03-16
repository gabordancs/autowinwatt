"""Command helpers for navigating WinWatt menus."""

from __future__ import annotations

from winwatt_automation.live_ui import menu_helpers

FILE_MENU_TITLE = "Fájl"
OPEN_PROJECT_CANDIDATES = (
    "Projekt megnyitása",
    "Megnyitás",
    "Projekt megnyit",
)


def open_file_menu() -> None:
    """Open the top-level ``Fájl`` menu."""

    try:
        menu_helpers.click_top_menu_item(FILE_MENU_TITLE)
    except LookupError as exc:
        available = menu_helpers.list_top_menu_items()
        raise LookupError(f"Top menu '{FILE_MENU_TITLE}' was not found. Available menus: {available}") from exc


def click_file_submenu_item_by_index(index: int) -> dict:
    """Open ``Fájl`` and click a popup submenu entry by geometry index."""

    return menu_helpers.click_open_menu_item_by_index(index)


def invoke_open_project_dialog() -> str:
    """Invoke the project-open entry from the currently open ``Fájl`` menu."""

    visible_items = menu_helpers.list_open_menu_items()
    lowered = {item.lower(): item for item in visible_items}

    for candidate in OPEN_PROJECT_CANDIDATES:
        found = lowered.get(candidate.lower())
        if found is None:
            continue

        item = menu_helpers.find_top_menu_item(found)
        invoke = getattr(item, "invoke", None)
        if callable(invoke):
            invoke()
            return found
        click_input = getattr(item, "click_input", None)
        if callable(click_input):
            click_input()
            return found
        click = getattr(item, "click", None)
        if callable(click):
            click()
            return found

        raise RuntimeError(f"Menu item '{found}' does not support invoke/click")

    raise LookupError(
        "Project-open menu entry was not found under 'Fájl'. "
        f"Visible submenu entries: {visible_items}. Tried: {list(OPEN_PROJECT_CANDIDATES)}"
    )

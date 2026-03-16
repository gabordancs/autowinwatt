from __future__ import annotations

import types

import pytest

from winwatt_automation.commands import menu_commands
from winwatt_automation.live_ui import menu_helpers, waits


class FakeElementInfo:
    def __init__(self, name: str, control_type: str = "MenuItem"):
        self.name = name
        self.control_type = control_type


class FakeMenuItem:
    def __init__(self, name: str, *, visible: bool = True, parent=None):
        self.element_info = FakeElementInfo(name)
        self._visible = visible
        self._parent = parent
        self.clicked = False

    def is_visible(self):
        return self._visible

    def parent(self):
        return self._parent

    def click_input(self):
        self.clicked = True


class FakeContainer:
    def __init__(self, items):
        self._items = items

    def descendants(self):
        return list(self._items)


def test_menu_helpers_list_and_click(monkeypatch):
    menu_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="Menu"))
    file_item = FakeMenuItem("Fájl", parent=menu_parent)
    edit_item = FakeMenuItem("Szerkesztés", parent=menu_parent)
    submenu = FakeMenuItem("Projekt megnyitása", parent=menu_parent)

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([file_item, edit_item, submenu]))

    assert "Fájl" in menu_helpers.list_top_menu_items()
    assert "Projekt megnyitása" in menu_helpers.list_open_menu_items()

    menu_helpers.click_top_menu_item("Fájl")
    assert file_item.clicked is True


def test_open_file_menu_raises_with_available_items(monkeypatch):
    monkeypatch.setattr(menu_helpers, "click_top_menu_item", lambda title: (_ for _ in ()).throw(LookupError("nope")))
    monkeypatch.setattr(menu_helpers, "list_top_menu_items", lambda: ["Szerkesztés"])

    with pytest.raises(LookupError, match="Available menus"):
        menu_commands.open_file_menu()


def test_wait_for_any_window_title_contains(monkeypatch):
    class FakeWindow:
        def __init__(self, title):
            self._title = title

        def window_text(self):
            return self._title

    class FakeDesktop:
        def __init__(self, backend):
            self.backend = backend

        def windows(self, top_level_only=True):
            return [FakeWindow("Other"), FakeWindow("Open project")]

    monkeypatch.setitem(__import__("sys").modules, "pywinauto", types.SimpleNamespace(Desktop=FakeDesktop))

    resolved = waits.wait_for_any_window_title_contains("project", timeout=0.3)
    assert resolved.window_text() == "Open project"

from __future__ import annotations

import types

import pytest

from winwatt_automation.commands import menu_commands
from winwatt_automation.live_ui import menu_helpers, waits


class FakeElementInfo:
    def __init__(self, name: str, control_type: str = "MenuItem", class_name: str = ""):
        self.name = name
        self.control_type = control_type
        self.class_name = class_name


class FakeRect:
    def __init__(self, left: int, top: int, right: int, bottom: int):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeMenuItem:
    def __init__(self, name: str, *, visible: bool = True, parent=None, rect: FakeRect | None = None):
        self.element_info = FakeElementInfo(name)
        self._visible = visible
        self._parent = parent
        self._rect = rect or FakeRect(0, 0, 100, 20)
        self.clicked = False
        self.invoked = False
        self.selected = False

    def is_visible(self):
        return self._visible

    def parent(self):
        return self._parent

    def rectangle(self):
        return self._rect

    def click_input(self):
        self.clicked = True

    def invoke(self):
        self.invoked = True

    def select(self):
        self.selected = True


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


def test_find_top_menu_item_returns_invisible_when_only_match(monkeypatch):
    menu_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="MenuBar"))
    file_item = FakeMenuItem("Fájl", visible=False, parent=menu_parent)
    edit_item = FakeMenuItem("Szerkesztés", visible=True, parent=menu_parent)

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([file_item, edit_item]))

    resolved = menu_helpers.find_top_menu_item("Fájl")
    assert resolved is file_item


def test_find_top_menu_item_prefers_visible_duplicate(monkeypatch):
    menu_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="MenuBar"))
    file_hidden = FakeMenuItem("Fájl", visible=False, parent=menu_parent)
    file_visible = FakeMenuItem("Fájl", visible=True, parent=menu_parent)

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([file_hidden, file_visible]))

    resolved = menu_helpers.find_top_menu_item("Fájl")
    assert resolved is file_visible


def test_click_top_menu_item_fallback_to_relative_click(monkeypatch):
    menu_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="MenuBar"))

    class ClickInputFailsItem(FakeMenuItem):
        def click_input(self):
            raise RuntimeError("not clickable")

    file_item = ClickInputFailsItem("Fájl", visible=False, parent=menu_parent)

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([file_item]))
    monkeypatch.setattr(menu_helpers, "prepare_main_window_for_menu_interaction", lambda: types.SimpleNamespace())
    monkeypatch.setattr(menu_helpers, "is_main_window_foreground", lambda: True)
    popup_checks = iter([False, True])
    monkeypatch.setattr(menu_helpers, "did_any_new_menu_popup_appear", lambda before, after: next(popup_checks))

    relative_clicks = []
    monkeypatch.setattr(menu_helpers, "_click_by_relative_rect_center", lambda item, main: relative_clicks.append(item))

    menu_helpers.click_top_menu_item("Fájl")
    assert relative_clicks == [file_item]


def test_list_open_menu_items_structured_sorts_and_marks_separator(monkeypatch):
    menubar_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="MenuBar"))
    popup_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="Menu"))

    top_level = FakeMenuItem("Fájl", parent=menubar_parent, rect=FakeRect(5, 5, 60, 30))
    entry_2 = FakeMenuItem("", parent=popup_parent, rect=FakeRect(3, 89, 703, 111))
    separator = FakeMenuItem("", parent=popup_parent, rect=FakeRect(3, 111, 703, 112))
    entry_1 = FakeMenuItem("", parent=popup_parent, rect=FakeRect(3, 67, 703, 89))

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([top_level, entry_2, separator, entry_1]))

    structured = menu_helpers.list_open_menu_items_structured()

    assert [item["order_index"] for item in structured] == [0, 1, 2]
    assert structured[0]["rectangle"] == (3, 67, 703, 89)
    assert structured[2]["is_separator"] is True


def test_click_open_menu_item_by_index_clicks_center(monkeypatch):
    monkeypatch.setattr(menu_helpers, "click_top_menu_item", lambda _: None)
    monkeypatch.setattr(
        menu_helpers,
        "list_open_menu_items_structured",
        lambda: [
            {"center": (10, 10), "is_separator": True, "order_index": 0, "rectangle": (0, 0, 20, 20)},
            {"center": (30, 30), "is_separator": False, "order_index": 1, "rectangle": (20, 20, 40, 40)},
        ],
    )

    clicks = []
    monkeypatch.setattr(menu_helpers.mouse, "click", lambda button, coords: clicks.append((button, coords)))

    selected = menu_helpers.click_open_menu_item_by_index(0)

    assert selected["center"] == (30, 30)
    assert clicks == [("left", (30, 30))]


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

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

    def is_visible(self):
        return self._visible

    def parent(self):
        return self._parent

    def rectangle(self):
        return self._rect

    def click_input(self):
        self.clicked = True


class FakeContainer:
    def __init__(self, items):
        self._items = items

    def descendants(self):
        return list(self._items)


class FakeDialog:
    def __init__(self, title: str):
        self._title = title

    def window_text(self):
        return self._title


def test_menu_helpers_list_and_click(monkeypatch):
    menu_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="Menu"))
    file_item = FakeMenuItem("Fájl", parent=menu_parent)
    edit_item = FakeMenuItem("Szerkesztés", parent=menu_parent)
    submenu = FakeMenuItem("Projekt megnyitása", parent=menu_parent)

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([file_item, edit_item, submenu]))

    assert "Fájl" in menu_helpers.list_top_menu_items()
    assert "Projekt megnyitása" in menu_helpers.list_open_menu_items()

    monkeypatch.setattr(menu_helpers, "prepare_main_window_for_menu_interaction", lambda: types.SimpleNamespace())
    monkeypatch.setattr(menu_helpers, "is_main_window_foreground", lambda: True)
    monkeypatch.setattr(menu_helpers, "did_any_new_menu_popup_appear", lambda before, after: True)
    menu_helpers.click_top_menu_item("Fájl")
    assert file_item.clicked is True


def test_find_top_menu_item_returns_invisible_when_only_match(monkeypatch):
    menu_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="MenuBar"))
    file_item = FakeMenuItem("Fájl", visible=False, parent=menu_parent)
    edit_item = FakeMenuItem("Szerkesztés", visible=True, parent=menu_parent)

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([file_item, edit_item]))

    resolved = menu_helpers.find_top_menu_item("Fájl")
    assert resolved is file_item


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


def test_structured_popup_rows_from_snapshots_sorts_filters_and_marks_separator(monkeypatch):
    menu_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="MenuBar"))
    top_level = FakeMenuItem("Fájl", parent=menu_parent, rect=FakeRect(5, 5, 60, 30))

    before = [
        {
            "text": "Fájl",
            "normalized_text": "fájl",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 5, "top": 5, "right": 60, "bottom": 30},
            "width": 55,
            "height": 25,
            "center_x": 32,
            "center_y": 17,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": False,
        }
    ]
    after = before + [
        {
            "text": "",
            "normalized_text": "",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 3, "top": 89, "right": 703, "bottom": 111},
            "width": 700,
            "height": 22,
            "center_x": 353,
            "center_y": 100,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": False,
        },
        {
            "text": "",
            "normalized_text": "",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 3, "top": 111, "right": 703, "bottom": 112},
            "width": 700,
            "height": 1,
            "center_x": 353,
            "center_y": 111,
            "is_separator": True,
            "source_scope": "main_window",
            "appeared_after_popup_open": False,
        },
        {
            "text": "",
            "normalized_text": "",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 3, "top": 67, "right": 703, "bottom": 89},
            "width": 700,
            "height": 22,
            "center_x": 353,
            "center_y": 78,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": False,
        },
    ]

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([top_level]))

    structured = menu_helpers._structured_popup_rows_from_snapshots(before, after)

    assert [item["index"] for item in structured] == [0, 1, 2]
    assert structured[0]["rectangle"]["top"] == 67
    assert structured[2]["is_separator"] is True


def test_click_structured_popup_row_clicks_center(monkeypatch):
    clicks = []
    monkeypatch.setattr(menu_helpers, "_mouse_click", lambda coords: clicks.append(("left", coords)))

    selected = menu_helpers.click_structured_popup_row(
        [{"index": 0, "center_x": 30, "center_y": 30, "is_separator": False, "rectangle": {"left": 20}}],
        0,
    )

    assert selected["center_x"] == 30
    assert clicks == [("left", (30, 30))]


def test_click_open_menu_item_by_index_rejects_separator(monkeypatch):
    monkeypatch.setattr(menu_helpers, "prepare_main_window_for_menu_interaction", lambda: None)
    monkeypatch.setattr(
        menu_helpers,
        "open_file_menu_and_capture_popup_state",
        lambda: {"rows": [{"index": 0, "center_x": 10, "center_y": 10, "is_separator": True}]},
    )

    with pytest.raises(ValueError, match="separator"):
        menu_helpers.click_open_menu_item_by_index(0)


def test_click_open_menu_item_by_index_uses_existing_popup_rows_once(monkeypatch):
    monkeypatch.setattr(menu_helpers, "prepare_main_window_for_menu_interaction", lambda: None)

    call_count = {"open": 0}

    def fake_open_state():
        call_count["open"] += 1
        return {"rows": [{"index": 0, "center_x": 50, "center_y": 60, "is_separator": False, "rectangle": {"left": 20}}]}

    monkeypatch.setattr(menu_helpers, "open_file_menu_and_capture_popup_state", fake_open_state)

    clicked = []
    monkeypatch.setattr(menu_helpers, "_mouse_click", lambda coords: clicked.append(coords))

    selected = menu_helpers.click_open_menu_item_by_index(0)

    assert call_count["open"] == 1
    assert clicked == [(50, 60)]
    assert selected["center_x"] == 50


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


def test_invoke_open_project_dialog_by_index_plumbs_dialog_result(monkeypatch):
    popup_rows = [{"index": 2, "center_x": 25, "center_y": 40, "is_separator": False, "rectangle": {"left": 1}}]
    monkeypatch.setattr(
        menu_helpers,
        "open_file_menu_and_capture_popup_state",
        lambda: {"rows": popup_rows, "process_id": 1234},
    )
    monkeypatch.setattr(menu_helpers, "click_structured_popup_row", lambda rows, idx: rows[idx])
    monkeypatch.setattr(
        waits,
        "detect_open_file_dialog_from_context",
        lambda process_id, timeout=5.0: {
            "dialog_detected": True,
            "dialog_title": "Open",
            "dialog_class": "#32770",
            "candidate_count": 1,
        },
    )

    result = menu_commands.invoke_open_project_dialog_by_index(0)

    assert result["clicked_index"] == 0
    assert result["dialog_detected"] is True
    assert result["dialog_title"] == "Open"
    assert result["process_id"] == 1234
    assert result["dialog_candidate_count"] == 1


def test_structured_popup_rows_dedupes_by_visual_identity_prefers_main_window(monkeypatch):
    menu_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="MenuBar"))
    top_level = FakeMenuItem("Fájl", parent=menu_parent, rect=FakeRect(5, 5, 60, 30))

    before = []
    after = [
        {
            "text": "Projekt megnyitása",
            "normalized_text": "projekt megnyitása",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 3, "top": 45, "right": 703, "bottom": 67},
            "width": 700,
            "height": 22,
            "center_x": 353,
            "center_y": 56,
            "is_separator": False,
            "source_scope": "global_process_scan",
            "appeared_after_popup_open": False,
        },
        {
            "text": "Projekt megnyitása",
            "normalized_text": "projekt megnyitása",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 3, "top": 45, "right": 703, "bottom": 67},
            "width": 700,
            "height": 22,
            "center_x": 353,
            "center_y": 56,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": False,
        },
    ]

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([top_level]))

    structured = menu_helpers._structured_popup_rows_from_snapshots(before, after)

    assert len(structured) == 1
    assert structured[0]["index"] == 0
    assert structured[0]["source_scope"] == "main_window"


def test_detect_open_file_dialog_from_context_without_process_id(monkeypatch):
    class FakeWindow:
        def __init__(self, handle, title, class_name):
            self._handle = handle
            self._title = title
            self._class_name = class_name

        def is_visible(self):
            return True

        def window_text(self):
            return self._title

        def class_name(self):
            return self._class_name

        def process_id(self):
            return 999

        def handle(self):
            return self._handle

    class FakeDesktop:
        def __init__(self, backend):
            self.backend = backend
            self._calls = 0

        def windows(self, top_level_only=True):
            self._calls += 1
            if self._calls == 1:
                return [FakeWindow(1, "WinWatt", "TMainForm")]
            return [FakeWindow(1, "WinWatt", "TMainForm"), FakeWindow(2, "Open", "#32770")]

    monkeypatch.setitem(__import__("sys").modules, "pywinauto", types.SimpleNamespace(Desktop=FakeDesktop))

    result = waits.detect_open_file_dialog_from_context(process_id=None, timeout=0.3)

    assert result["dialog_detected"] is True
    assert result["dialog_title"] == "Open"
    assert result["dialog_class"] == "#32770"

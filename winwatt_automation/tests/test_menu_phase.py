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
    file_item = FakeMenuItem("Fájl", parent=menu_parent, rect=FakeRect(80, 50, 180, 80))
    edit_item = FakeMenuItem("Szerkesztés", parent=menu_parent)
    submenu = FakeMenuItem("Projekt megnyitása", parent=menu_parent)

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([file_item, edit_item, submenu]))

    assert "Fájl" in menu_helpers.list_top_menu_items()
    assert "Projekt megnyitása" in menu_helpers.list_open_menu_items()

    monkeypatch.setattr(menu_helpers, "prepare_main_window_for_menu_interaction", lambda: types.SimpleNamespace())
    monkeypatch.setattr(menu_helpers, "ensure_main_window_foreground_before_click", lambda **kwargs: types.SimpleNamespace(rectangle=lambda: types.SimpleNamespace(left=0, top=0, right=500, bottom=300)))
    monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "WinWatt", "class_name": "TMainForm", "process_id": 1})
    monkeypatch.setattr(menu_helpers, "is_winwatt_foreground_context", lambda *args, **kwargs: True)
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
    monkeypatch.setattr(menu_helpers, "ensure_main_window_foreground_before_click", lambda **kwargs: types.SimpleNamespace(rectangle=lambda: types.SimpleNamespace(left=0, top=0, right=500, bottom=300)))
    monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "WinWatt", "class_name": "TMainForm", "process_id": 1})
    monkeypatch.setattr(menu_helpers, "is_winwatt_foreground_context", lambda *args, **kwargs: True)
    snapshots = iter([set(), {("popup", "", "", "", "")}])
    monkeypatch.setattr(menu_helpers, "wait_for_new_menu_popup", lambda before_snapshot, **kwargs: next(snapshots))

    relative_clicks = []
    monkeypatch.setattr(menu_helpers, "_click_by_relative_rect_center", lambda item, main: relative_clicks.append(item))

    menu_helpers.click_top_menu_item("Fájl")
    assert relative_clicks == [file_item]


def test_click_top_menu_item_adjusts_point_outside_forbidden_zone_without_leaving_target_rect(monkeypatch):
    menu_parent = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="MenuBar"))
    file_item = FakeMenuItem("Fájl", parent=menu_parent, rect=FakeRect(0, 23, 32, 42))

    class MainWindow:
        def rectangle(self):
            return types.SimpleNamespace(left=0, top=0, right=500, bottom=300)

        def click_input(self, coords):
            clicks.append(coords)

    clicks = []
    main_window = MainWindow()

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: FakeContainer([file_item]))
    monkeypatch.setattr(menu_helpers, "prepare_main_window_for_menu_interaction", lambda: main_window)
    monkeypatch.setattr(menu_helpers, "ensure_main_window_foreground_before_click", lambda **kwargs: main_window)
    monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "WinWatt", "class_name": "TMainForm", "process_id": 1})
    monkeypatch.setattr(menu_helpers, "is_winwatt_foreground_context", lambda *args, **kwargs: True)
    monkeypatch.setattr(menu_helpers, "wait_for_new_menu_popup", lambda before_snapshot, **kwargs: {("popup", "", "", "", "")})
    monkeypatch.setattr(menu_helpers, "_menu_snapshot", lambda: set())

    menu_helpers.click_top_menu_item("Fájl")

    assert clicks
    rel_x, rel_y = clicks[0]
    assert 0 <= rel_x < 32
    assert 23 <= rel_y < 42
    assert rel_y > menu_helpers.TITLEBAR_ICON_GUARD_HEIGHT


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




def test_group_popup_fragments_into_logical_rows_merges_overlapping_rows():
    fragments = [
        {
            "text": "Projekt létrehozása",
            "normalized_text": "projekt létrehozása",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 12, "top": 56, "right": 280, "bottom": 84},
            "width": 268,
            "height": 28,
            "center_x": 146,
            "center_y": 70,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": True,
        },
        {
            "text": "",
            "normalized_text": "",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 10, "top": 67, "right": 300, "bottom": 89},
            "width": 290,
            "height": 22,
            "center_x": 155,
            "center_y": 78,
            "is_separator": False,
            "source_scope": "global_process_scan",
            "appeared_after_popup_open": True,
        },
        {
            "text": "Projekt megnyitása",
            "normalized_text": "projekt megnyitása",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 11, "top": 92, "right": 280, "bottom": 114},
            "width": 269,
            "height": 22,
            "center_x": 145,
            "center_y": 103,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": True,
        },
    ]

    logical_rows = menu_helpers._group_popup_fragments_into_logical_rows(fragments)

    assert len(logical_rows) == 2
    assert logical_rows[0]["rectangle"] == {"left": 10, "top": 56, "right": 300, "bottom": 89}
    assert logical_rows[0]["text"] == "Projekt létrehozása"
    assert len(logical_rows[0]["fragments"]) == 2
    assert logical_rows[1]["text"] == "Projekt megnyitása"


def test_group_popup_fragments_marks_empty_vertical_cluster_as_popup_by_geometry(monkeypatch):
    fragments = []
    for index in range(4):
        top = 56 + index * 24
        fragments.append(
            {
                "text": "",
                "normalized_text": "",
                "control_type": "MenuItem",
                "class_name": "",
                "rectangle": {"left": 4, "top": top, "right": 932, "bottom": top + 22},
                "width": 928,
                "height": 22,
                "center_x": 468,
                "center_y": top + 11,
                "is_separator": False,
                "source_scope": "main_window",
                "appeared_after_popup_open": True,
            }
        )
    fragments.append(
        {
            "text": "Fájl",
            "normalized_text": "fájl",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 0, "top": 0, "right": 48, "bottom": 24},
            "width": 48,
            "height": 24,
            "center_x": 24,
            "center_y": 12,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": False,
        }
    )
    monkeypatch.setattr(
        menu_helpers,
        "_main_window_topbar_band",
        lambda: {"left": 0, "top": 0, "right": 327, "bottom": 42, "width": 327, "height": 42, "center_x": 163, "center_y": 21},
    )

    logical_rows = menu_helpers._group_popup_fragments_into_logical_rows(fragments)
    popup_rows = [row for row in logical_rows if row["rectangle"]["top"] >= 56]

    assert len(popup_rows) == 4
    assert all(row["popup_candidate"] is True for row in popup_rows)
    assert all(row["topbar_candidate"] is False for row in popup_rows)
    assert all(row["popup_reason"] == "empty_text_vertical_cluster_below_topbar" for row in popup_rows)

def test_click_structured_popup_row_clicks_center(monkeypatch):
    clicks = []
    monkeypatch.setattr(menu_helpers, "_mouse_click", lambda coords: clicks.append(("left", coords)))
    monkeypatch.setattr(menu_helpers, "ensure_main_window_foreground_before_click", lambda **kwargs: None)

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
    monkeypatch.setattr(menu_helpers, "ensure_main_window_foreground_before_click", lambda **kwargs: None)

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


def test_forbidden_zone_blocks_click(monkeypatch):
    class MainWindow:
        def rectangle(self):
            return types.SimpleNamespace(left=0, top=0, right=400, bottom=300)

    with pytest.raises(RuntimeError, match="click_blocked_forbidden_zone"):
        menu_helpers._validate_not_in_forbidden_top_left_zone(MainWindow(), (5, 5))


def test_wrong_foreground_blocks_post_validation(monkeypatch):
    monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "VS Code", "class_name": "Chrome_WidgetWin_1", "process_id": 999})
    monkeypatch.setattr(menu_helpers, "_is_system_menu_foreground", lambda: False)
    monkeypatch.setattr(menu_helpers, "is_winwatt_foreground_context", lambda *args, **kwargs: False)

    with pytest.raises(RuntimeError, match="failed_wrong_window"):
        menu_helpers._validate_post_menu_open_foreground(types.SimpleNamespace(), title="Fájl")


def test_system_menu_detected_and_failed(monkeypatch):
    monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "System", "class_name": "#32768", "process_id": 1})
    monkeypatch.setattr(menu_helpers, "_is_system_menu_foreground", lambda: True)

    with pytest.raises(RuntimeError, match="failed_system_menu"):
        menu_helpers._validate_post_menu_open_foreground(types.SimpleNamespace(), title="Fájl")




def test_main_window_topbar_band_uses_low_level_query_without_menu_items(monkeypatch):
    class MenuItem:
        def __init__(self, left, top, right, bottom, *, parent=None):
            self._rect = types.SimpleNamespace(left=left, top=top, right=right, bottom=bottom)
            self._parent = parent
            self.element_info = types.SimpleNamespace(control_type="MenuItem", handle=100, process_id=1, class_name="")

        def rectangle(self):
            return self._rect

        def parent(self):
            return self._parent

    menubar = types.SimpleNamespace(element_info=types.SimpleNamespace(control_type="MenuBar"))
    items = [MenuItem(10, 5, 80, 30, parent=menubar), MenuItem(90, 6, 150, 31, parent=menubar)]

    class MainWindow:
        element_info = types.SimpleNamespace(handle=555)

        def descendants(self):
            return list(items)

    monkeypatch.setattr(menu_helpers, "get_cached_main_window", lambda: MainWindow())
    monkeypatch.setattr(menu_helpers, "_menu_items", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("_menu_items should not be called")))

    band = menu_helpers._main_window_topbar_band(force_refresh=True)

    assert band == {"left": 10, "top": 5, "right": 150, "bottom": 31, "width": 140, "height": 26, "center_x": 80, "center_y": 18}


def test_menu_items_reentrancy_guard_falls_back_to_direct_query(monkeypatch):
    class MenuItem:
        def __init__(self):
            self.element_info = types.SimpleNamespace(control_type="MenuItem", handle=100, process_id=1, class_name="")

    items = [MenuItem(), MenuItem()]

    class MainWindow:
        element_info = types.SimpleNamespace(handle=777)

        def descendants(self):
            return list(items)

    state = {"reentered": False}

    def recursive_topbar(*, force_refresh=False):
        if not state["reentered"]:
            state["reentered"] = True
            nested = menu_helpers._menu_items(force_refresh=force_refresh)
            assert nested == items
        return None

    monkeypatch.setattr(menu_helpers, "get_main_window", lambda: MainWindow())
    monkeypatch.setattr(menu_helpers, "_main_window_topbar_band", recursive_topbar)

    result = menu_helpers._menu_items(force_refresh=True)

    assert result == items
    assert state["reentered"] is True

def test_capture_system_menu_popup_falls_back_to_popup_region_rows(monkeypatch):
    popup_candidates = [
        {
            "text": "Előző méret",
            "normalized_text": "előző méret",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 4, "top": 55, "right": 220, "bottom": 80},
            "width": 216,
            "height": 25,
            "center_x": 112,
            "center_y": 67,
            "is_separator": False,
            "source_scope": "system_menu_fallback_main_window",
            "topbar_candidate": False,
            "popup_candidate": True,
        },
        {
            "text": "Bezárás",
            "normalized_text": "bezárás",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 4, "top": 82, "right": 220, "bottom": 107},
            "width": 216,
            "height": 25,
            "center_x": 112,
            "center_y": 94,
            "is_separator": False,
            "source_scope": "system_menu_fallback_main_window",
            "topbar_candidate": False,
            "popup_candidate": True,
        },
    ]

    monkeypatch.setattr(menu_helpers, "_system_menu_windows", lambda: [])
    monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "WinWatt", "class_name": "TMainForm", "process_id": 1})
    monkeypatch.setattr(
        menu_helpers,
        "_capture_popup_region_rows_for_system_menu",
        lambda: (popup_candidates, [], {"left": 0, "top": 0, "right": 500, "bottom": 40, "width": 500, "height": 40, "center_x": 250, "center_y": 20}),
    )

    rows = menu_helpers.capture_system_menu_popup()

    assert [row["text"] for row in rows] == ["Előző méret", "Bezárás"]
    assert all(row["source_scope"] == "system_menu_fallback" for row in rows)
    assert all(row["popup_candidate"] is True for row in rows)




def test_system_menu_fallback_retries_snapshot_when_off_foreground(monkeypatch):
    class MainWindow:
        element_info = types.SimpleNamespace(handle=777)

    query_calls = {"count": 0}

    def fake_query(root, *, force_refresh=False):
        query_calls["count"] += 1
        if query_calls["count"] == 1:
            return []
        return [
            {
                "dummy": True,
            }
        ]

    candidate_row = {
        "text": "Bezárás",
        "normalized_text": "bezárás",
        "control_type": "MenuItem",
        "class_name": "",
        "rectangle": {"left": 4, "top": 82, "right": 220, "bottom": 107},
        "width": 216,
        "height": 25,
        "center_x": 112,
        "center_y": 94,
        "is_separator": False,
        "source_scope": "system_menu_fallback_main_window",
        "topbar_candidate": False,
        "popup_candidate": True,
    }

    monkeypatch.setattr(menu_helpers, "get_cached_main_window_snapshot", lambda: MainWindow())
    monkeypatch.setattr(menu_helpers, "is_winwatt_foreground_context", lambda *args, **kwargs: False)
    monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "VS Code", "class_name": "Chrome_WidgetWin_1", "process_id": 9})
    monkeypatch.setattr(menu_helpers.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(menu_helpers, "_query_menu_items_from_root", fake_query)
    monkeypatch.setattr(menu_helpers, "_menu_row_from_wrapper", lambda item, **kwargs: candidate_row)
    monkeypatch.setattr(menu_helpers, "_compute_topbar_band_from_items", lambda items: None)
    monkeypatch.setattr(menu_helpers, "_compute_topbar_band_from_rows", lambda rows: {"left": 0, "top": 0, "right": 50, "bottom": 30, "width": 50, "height": 30, "center_x": 25, "center_y": 15})

    popup_candidates, excluded_topbar, topbar_band = menu_helpers._capture_popup_region_rows_for_system_menu()

    assert query_calls["count"] == 2
    assert popup_candidates == [candidate_row]
    assert excluded_topbar == []
    assert topbar_band["bottom"] == 30

def test_capture_system_menu_popup_falls_back_to_popup_region_rows_without_system_menu_window(monkeypatch):
    popup_candidates = [
        {
            "text": "Előző méret",
            "normalized_text": "előző méret",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 4, "top": 55, "right": 220, "bottom": 80},
            "width": 216,
            "height": 25,
            "center_x": 112,
            "center_y": 67,
            "is_separator": False,
            "source_scope": "system_menu_fallback_main_window",
            "topbar_candidate": False,
            "popup_candidate": True,
        },
        {
            "text": "Bezárás",
            "normalized_text": "bezárás",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 4, "top": 82, "right": 220, "bottom": 107},
            "width": 216,
            "height": 25,
            "center_x": 112,
            "center_y": 94,
            "is_separator": False,
            "source_scope": "system_menu_fallback_main_window",
            "topbar_candidate": False,
            "popup_candidate": True,
        },
    ]

    monkeypatch.setattr(menu_helpers, "_system_menu_windows", lambda: [])
    monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "WinWatt", "class_name": "TMainForm", "process_id": 1})
    monkeypatch.setattr(
        menu_helpers,
        "_capture_popup_region_rows_for_system_menu",
        lambda: (popup_candidates, [], {"left": 0, "top": 0, "right": 500, "bottom": 40, "width": 500, "height": 40, "center_x": 250, "center_y": 20}),
    )

    rows = menu_helpers.capture_system_menu_popup()

    assert [row["text"] for row in rows] == ["Előző méret", "Bezárás"]
    assert all(row["source_scope"] == "system_menu_fallback" for row in rows)
    assert all(row["popup_candidate"] is True for row in rows)


def test_capture_system_menu_popup_prefers_real_system_menu_windows(monkeypatch):
    monkeypatch.setattr(menu_helpers, "_system_menu_windows", lambda: [object()])
    fallback_calls: list[str] = []
    monkeypatch.setattr(menu_helpers, "_system_menu_fragment_candidates", lambda window: [])
    monkeypatch.setattr(menu_helpers, "_system_menu_fallback_rows_from_popup_region", lambda: fallback_calls.append("fallback") or [])
    monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "System", "class_name": "#32768", "process_id": 1})

    rows = menu_helpers.capture_system_menu_popup()

    assert rows == []
    assert fallback_calls == []




def test_capture_menu_popup_snapshot_accepts_empty_text_vertical_cluster_as_popup(monkeypatch):
    rows = []
    for index in range(6):
        top = 45 + index * 24
        rows.append(
            {
                "text": "",
                "normalized_text": "",
                "control_type": "MenuItem",
                "class_name": "",
                "rectangle": {"left": 40, "top": top, "right": 280, "bottom": top + 22},
                "width": 240,
                "height": 22,
                "center_x": 160,
                "center_y": top + 11,
                "source_scope": "main_window",
            }
        )
    topbar_rows = [
        {
            "text": "Fájl",
            "normalized_text": "fájl",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 0, "top": 0, "right": 50, "bottom": 24},
            "width": 50,
            "height": 24,
            "center_x": 25,
            "center_y": 12,
            "source_scope": "main_window",
        },
        {
            "text": "Jegyzékek",
            "normalized_text": "jegyzékek",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 55, "top": 0, "right": 140, "bottom": 24},
            "width": 85,
            "height": 24,
            "center_x": 97,
            "center_y": 12,
            "source_scope": "main_window",
        },
    ]
    monkeypatch.setattr(menu_helpers, '_menu_like_controls_from_main_window', lambda: topbar_rows + rows)
    monkeypatch.setattr(menu_helpers, '_menu_like_controls_from_global_process_scan', lambda: [])
    monkeypatch.setattr(menu_helpers, '_main_window_topbar_band', lambda: {"left": 0, "top": 0, "right": 327, "bottom": 464, "width": 327, "height": 464, "center_x": 163, "center_y": 232})

    snapshot = menu_helpers.capture_menu_popup_snapshot()

    popup_rows = [row for row in snapshot if row['rectangle']['top'] >= 45]
    assert len(popup_rows) == 6
    assert all(row['popup_candidate'] is True for row in popup_rows)
    assert all(row['topbar_candidate'] is False for row in popup_rows)
    assert all(row['popup_reason'] == 'empty_text_vertical_cluster_below_topbar' for row in popup_rows)


def test_capture_menu_popup_snapshot_keeps_topbar_only_snapshot_non_popup(monkeypatch):
    topbar_rows = [
        {
            "text": "Fájl",
            "normalized_text": "fájl",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 0, "top": 0, "right": 50, "bottom": 24},
            "width": 50,
            "height": 24,
            "center_x": 25,
            "center_y": 12,
            "source_scope": "main_window",
        },
        {
            "text": "Jegyzékek",
            "normalized_text": "jegyzékek",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 55, "top": 0, "right": 140, "bottom": 24},
            "width": 85,
            "height": 24,
            "center_x": 97,
            "center_y": 12,
            "source_scope": "main_window",
        },
    ]
    monkeypatch.setattr(menu_helpers, '_menu_like_controls_from_main_window', lambda: topbar_rows)
    monkeypatch.setattr(menu_helpers, '_menu_like_controls_from_global_process_scan', lambda: [])
    monkeypatch.setattr(menu_helpers, '_main_window_topbar_band', lambda: {"left": 0, "top": 0, "right": 327, "bottom": 24, "width": 327, "height": 24, "center_x": 163, "center_y": 12})

    snapshot = menu_helpers.capture_menu_popup_snapshot()

    assert all(row['topbar_candidate'] is True for row in snapshot)
    assert all(row['popup_candidate'] is False for row in snapshot)
    assert all(row['popup_reason'] is None for row in snapshot)


def test_click_top_menu_item_focus_guard_failure(monkeypatch):
    monkeypatch.setattr(menu_helpers, "prepare_main_window_for_menu_interaction", lambda: types.SimpleNamespace())

    def _fail(**kwargs):
        raise RuntimeError("focus_not_restored")

    monkeypatch.setattr(menu_helpers, "ensure_main_window_foreground_before_click", _fail)

    with pytest.raises(RuntimeError, match="focus_not_restored"):
        menu_helpers.click_top_menu_item("Fájl")


def test_capture_menu_popup_snapshot_diagnostic_fast_mode_uses_only_main_window(monkeypatch):
    from winwatt_automation.runtime_mapping.config import configure_diagnostics

    configure_diagnostics(diagnostic_fast_mode=True, placeholder_traversal_focus=False)
    topbar_rows = [
        {
            "text": "Fájl",
            "normalized_text": "fájl",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 0, "top": 0, "right": 50, "bottom": 24},
            "width": 50,
            "height": 24,
            "center_x": 25,
            "center_y": 12,
            "source_scope": "main_window",
        }
    ]
    popup_rows = [
        {
            "text": "Megnyitás",
            "normalized_text": "megnyitás",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 0, "top": 30, "right": 120, "bottom": 54},
            "width": 120,
            "height": 24,
            "center_x": 60,
            "center_y": 42,
            "source_scope": "main_window",
        }
    ]
    monkeypatch.setattr(menu_helpers, '_menu_like_controls_from_main_window', lambda: topbar_rows + popup_rows)
    monkeypatch.setattr(menu_helpers, '_menu_like_controls_from_global_process_scan', lambda: (_ for _ in ()).throw(AssertionError('global scan disabled')))
    monkeypatch.setattr(menu_helpers, '_main_window_topbar_band', lambda: {"left": 0, "top": 0, "right": 120, "bottom": 24, "width": 120, "height": 24, "center_x": 60, "center_y": 12})

    snapshot = menu_helpers.capture_menu_popup_snapshot()

    assert [row['text'] for row in snapshot] == ['Fájl', 'Megnyitás']
    configure_diagnostics(diagnostic_fast_mode=False, placeholder_traversal_focus=False)


def test_group_popup_fragments_rejects_repeated_legacy_text_for_popup_rows():
    fragments = []
    for index in range(4):
        top = 56 + index * 24
        fragments.append(
            {
                "text": "Végrehajtás",
                "normalized_text": "végrehajtás",
                "raw_text_sources": ["legacy_text"],
                "text_confidence": "medium",
                "control_type": "MenuItem",
                "class_name": "",
                "rectangle": {"left": 8, "top": top, "right": 220, "bottom": top + 22},
                "width": 212,
                "height": 22,
                "center_x": 114,
                "center_y": top + 11,
                "is_separator": False,
                "source_scope": "main_window",
                "appeared_after_popup_open": True,
                "popup_candidate": True,
                "topbar_candidate": False,
            }
        )

    logical_rows = menu_helpers._group_popup_fragments_into_logical_rows(fragments)

    assert len(logical_rows) == 4
    assert all(row["text"] == "" for row in logical_rows)
    assert all(row["rejected_text_recovery_reason"] == "repeated_legacy_text" for row in logical_rows)


def test_group_popup_fragments_prefers_child_text_over_repeated_legacy_text():
    fragments = [
        {
            "text": "Végrehajtás",
            "normalized_text": "végrehajtás",
            "raw_text_sources": ["legacy_text"],
            "text_confidence": "medium",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 8, "top": 56, "right": 220, "bottom": 78},
            "width": 212,
            "height": 22,
            "center_x": 114,
            "center_y": 67,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": True,
            "popup_candidate": True,
            "topbar_candidate": False,
            "child_fragments": [
                {
                    "text": "Projekt megnyitása",
                    "rectangle": {"left": 18, "top": 58, "right": 170, "bottom": 76},
                    "center": (94, 67),
                    "source_scope": "child_text",
                }
            ],
        },
        {
            "text": "Végrehajtás",
            "normalized_text": "végrehajtás",
            "raw_text_sources": ["legacy_text"],
            "text_confidence": "medium",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 8, "top": 82, "right": 220, "bottom": 104},
            "width": 212,
            "height": 22,
            "center_x": 114,
            "center_y": 93,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": True,
            "popup_candidate": True,
            "topbar_candidate": False,
        },
        {
            "text": "Végrehajtás",
            "normalized_text": "végrehajtás",
            "raw_text_sources": ["legacy_text"],
            "text_confidence": "medium",
            "control_type": "MenuItem",
            "class_name": "",
            "rectangle": {"left": 8, "top": 108, "right": 220, "bottom": 130},
            "width": 212,
            "height": 22,
            "center_x": 114,
            "center_y": 119,
            "is_separator": False,
            "source_scope": "main_window",
            "appeared_after_popup_open": True,
            "popup_candidate": True,
            "topbar_candidate": False,
        },
    ]

    logical_rows = menu_helpers._group_popup_fragments_into_logical_rows(fragments)

    assert logical_rows[0]["text"] == "Projekt megnyitása"
    assert logical_rows[0]["raw_text_sources"] == ["fragment_merge"]
    assert logical_rows[1]["text"] == ""
    assert logical_rows[2]["text"] == ""

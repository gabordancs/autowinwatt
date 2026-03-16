from __future__ import annotations

import types

import pytest

from winwatt_automation.live_ui import app_connector, locators, window_tree


class FakeElementInfo:
    def __init__(self, name=None, control_type=None, class_name=None, automation_id=None):
        self.name = name
        self.control_type = control_type
        self.class_name = class_name
        self.automation_id = automation_id


class FakeRect:
    def __init__(self, left: int, top: int, right: int, bottom: int):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeWindow:
    def __init__(
        self,
        *,
        title: str,
        class_name: str,
        control_type: str = "Window",
        process_id: int = 123,
        handle: int | None = 10,
        visible: bool = True,
        enabled: bool = True,
        rect: FakeRect | None = None,
    ):
        self._title = title
        self._class_name = class_name
        self._process_id = process_id
        self._handle = handle
        self._visible = visible
        self._enabled = enabled
        self._rect = rect or FakeRect(0, 0, 100, 100)
        self.element_info = FakeElementInfo(name=title, control_type=control_type, class_name=class_name)

    def window_text(self):
        return self._title

    def class_name(self):
        return self._class_name

    def process_id(self):
        return self._process_id

    def handle(self):
        return self._handle

    def is_visible(self):
        return self._visible

    def is_enabled(self):
        return self._enabled

    def rectangle(self):
        return self._rect


class FakeControl:
    def __init__(self, name=None, control_type=None, class_name=None, automation_id=None, children=None):
        self.element_info = FakeElementInfo(
            name=name,
            control_type=control_type,
            class_name=class_name,
            automation_id=automation_id,
        )
        self._children = children or []

    def children(self):
        return list(self._children)

    def descendants(self):
        result = []
        for child in self._children:
            result.append(child)
            result.extend(child.descendants())
        return result


def test_connect_to_winwatt_raises_if_all_backends_fail(monkeypatch):
    class FakeDesktop:
        def __init__(self, backend: str):
            self.backend = backend

        def windows(self, top_level_only=True):
            return []

    monkeypatch.setitem(
        __import__("sys").modules,
        "pywinauto",
        types.SimpleNamespace(Application=lambda backend: None, Desktop=FakeDesktop),
    )

    with pytest.raises(app_connector.WinWattNotRunningError):
        app_connector.connect_to_winwatt()


def test_list_candidate_windows_collects_expected_fields(monkeypatch):
    class FakeDesktop:
        def __init__(self, backend: str):
            self.backend = backend

        def windows(self, top_level_only=True):
            return [
                FakeWindow(
                    title="WinWatt - Project",
                    class_name="TMainForm",
                    handle=101,
                    rect=FakeRect(0, 0, 1200, 900),
                ),
                FakeWindow(title="WinWatt - Dialog", class_name="TDialog", handle=200),
                FakeWindow(title="Other app", class_name="TMainForm", handle=102),
            ]

    monkeypatch.setitem(
        __import__("sys").modules,
        "pywinauto",
        types.SimpleNamespace(Desktop=FakeDesktop),
    )

    candidates = app_connector.list_candidate_windows(backend="win32")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["title"] == "WinWatt - Project"
    assert candidate["window_text"] == "WinWatt - Project"
    assert candidate["class_name"] == "TMainForm"
    assert candidate["control_type"] is None
    assert candidate["process_id"] == 123
    assert candidate["handle"] == 101
    assert candidate["is_visible"] is True
    assert candidate["is_enabled"] is True
    assert candidate["rectangle"]["width"] == 1200
    assert candidate["size"]["height"] == 900


def test_list_candidate_windows_win32_skips_control_type_access_error(monkeypatch):
    class RaisingElementInfo:
        def __init__(self, class_name: str):
            self.class_name = class_name

        @property
        def control_type(self):
            raise RuntimeError("AccessDenied")

    class FakeWindowWithDeniedControlType(FakeWindow):
        def __init__(self):
            super().__init__(title="WinWatt - Project", class_name="TMainForm", handle=101)
            self.element_info = RaisingElementInfo("TMainForm")

    class FakeDesktop:
        def __init__(self, backend: str):
            self.backend = backend

        def windows(self, top_level_only=True):
            return [FakeWindowWithDeniedControlType()]

    monkeypatch.setitem(
        __import__("sys").modules,
        "pywinauto",
        types.SimpleNamespace(Desktop=FakeDesktop),
    )

    candidates = app_connector.list_candidate_windows(backend="win32")

    assert len(candidates) == 1
    assert candidates[0]["control_type"] is None


def test_select_main_window_prefers_visible_enabled_and_largest_area():
    candidates = [
        {
            "title": "WinWatt - Splash",
            "class_name": "SplashDialog",
            "is_visible": True,
            "is_enabled": True,
            "rectangle": {"width": 300, "height": 180},
            "handle": 1,
            "process_id": 1,
        },
        {
            "title": "WinWatt - Main",
            "class_name": "MainFrame",
            "is_visible": True,
            "is_enabled": True,
            "rectangle": {"width": 1600, "height": 900},
            "handle": 2,
            "process_id": 2,
        },
        {
            "title": "WinWatt - Disabled",
            "class_name": "MainFrame",
            "is_visible": True,
            "is_enabled": False,
            "rectangle": {"width": 1800, "height": 900},
            "handle": 3,
            "process_id": 3,
        },
    ]

    selected = app_connector.select_main_window(candidates)

    assert selected["handle"] == 2


def test_select_main_window_allows_candidates_without_handle():
    candidates = [
        {
            "title": "WinWatt",
            "class_name": "MainFrame",
            "is_visible": False,
            "is_enabled": True,
            "rectangle": {"width": 1200, "height": 900},
            "handle": None,
            "process_id": 555,
        },
        {
            "title": "WinWatt",
            "class_name": "MainFrame",
            "is_visible": False,
            "is_enabled": True,
            "rectangle": {"width": 1000, "height": 800},
            "handle": 12,
            "process_id": 556,
        },
    ]

    selected = app_connector.select_main_window(candidates, backend="win32")
    assert selected["process_id"] == 555


def test_select_main_window_raises_on_tie():
    candidates = [
        {
            "title": "WinWatt",
            "class_name": "MainFrame",
            "is_visible": True,
            "is_enabled": True,
            "rectangle": {"width": 1200, "height": 900},
            "handle": 11,
            "process_id": 11,
        },
        {
            "title": "WinWatt",
            "class_name": "MainFrame",
            "is_visible": True,
            "is_enabled": True,
            "rectangle": {"width": 1200, "height": 900},
            "handle": 12,
            "process_id": 12,
        },
    ]

    with pytest.raises(app_connector.WinWattMultipleWindowsError):
        app_connector.select_main_window(candidates, backend="win32")


def test_get_main_window_uses_uia_by_process_after_win32_selection(monkeypatch):
    class FakeDesktop:
        def __init__(self, backend: str):
            self.backend = backend

        def windows(self, top_level_only=True):
            return [
                FakeWindow(
                    title="WinWatt - Project",
                    class_name="TMainForm",
                    process_id=999,
                    handle=444,
                    rect=FakeRect(0, 0, 1200, 900),
                )
            ]

    class FakeConnectedApp:
        def __init__(self, backend):
            self.backend = types.SimpleNamespace(name=backend)

        def window(self, **kwargs):
            return {"backend": self.backend.name, **kwargs}

    class FakeApplicationFactory:
        def __init__(self):
            self.calls = []

        def __call__(self, backend):
            self.calls.append(("init", backend))
            factory = self

            class Instance:
                def connect(self, **kwargs):
                    factory.calls.append(("connect", backend, kwargs))
                    return FakeConnectedApp(backend)

            return Instance()

    fake_factory = FakeApplicationFactory()

    monkeypatch.setitem(
        __import__("sys").modules,
        "pywinauto",
        types.SimpleNamespace(Application=fake_factory, Desktop=FakeDesktop),
    )

    main_window = app_connector.get_main_window()

    assert main_window == {"backend": "uia", "class_name": "TMainForm", "title_re": ".*WinWatt.*", "process": 999}
    assert ("connect", "win32", {"handle": 444}) in fake_factory.calls
    assert ("connect", "uia", {"process": 999}) in fake_factory.calls


def test_connect_with_win32_handle_falls_back_to_process_when_handle_missing(monkeypatch):
    class FakeDesktop:
        def __init__(self, backend: str):
            self.backend = backend

        def windows(self, top_level_only=True):
            return [
                FakeWindow(
                    title="WinWatt - Project",
                    class_name="TMainForm",
                    process_id=321,
                    handle=None,
                    rect=FakeRect(0, 0, 1200, 900),
                )
            ]

    class FakeConnectedApp:
        def window(self, **kwargs):
            return FakeWindow(title="WinWatt - Project", class_name="TMainForm", process_id=321, handle=777)

    class FakeApplicationFactory:
        def __init__(self):
            self.calls = []

        def __call__(self, backend):
            factory = self

            class Instance:
                def connect(self, **kwargs):
                    factory.calls.append((backend, kwargs))
                    return FakeConnectedApp()

            return Instance()

    fake_factory = FakeApplicationFactory()

    monkeypatch.setitem(
        __import__("sys").modules,
        "pywinauto",
        types.SimpleNamespace(Application=fake_factory, Desktop=FakeDesktop),
    )

    _app, selected = app_connector._connect_with_win32_handle()

    assert ("win32", {"process": 321}) in fake_factory.calls
    assert selected["handle"] == 777


def test_dump_window_tree_includes_required_fields():
    tree = FakeControl(
        name="Main",
        control_type="Window",
        class_name="MainClass",
        automation_id="main",
        children=[
            FakeControl(name="Button A", control_type="Button", class_name="Button", automation_id="btn_a")
        ],
    )

    dumped = window_tree.dump_window_tree(tree, max_depth=3)

    assert dumped["name"] == "Main"
    assert dumped["control_type"] == "Window"
    assert dumped["class_name"] == "MainClass"
    assert dumped["automation_id"] == "main"
    assert dumped["children"][0]["name"] == "Button A"


def test_locator_prefers_automation_id_then_type_then_index(monkeypatch):
    control_by_id = FakeControl(name="Save", control_type="Button", automation_id="save_button")
    control_by_name = FakeControl(name="Save", control_type="Edit", automation_id="")
    control_by_type = FakeControl(name="Other", control_type="ListItem", automation_id="")
    fallback = FakeControl(name="Fallback", control_type="Pane", automation_id="")

    form = FakeControl(name="ProjectForm", children=[fallback, control_by_name, control_by_id, control_by_type])
    root = FakeControl(name="Root", children=[form])

    monkeypatch.setattr(locators, "get_main_window", lambda: root)

    assert locators.find_form("ProjectForm") is form
    assert locators.find_control("ProjectForm", "save_button") is control_by_id
    assert locators.find_control("ProjectForm", "save:listitem") is control_by_name
    assert locators.find_control("ProjectForm", "missing:listitem") is control_by_type
    assert locators.find_control("ProjectForm", "missing") is fallback

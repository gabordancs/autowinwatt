from __future__ import annotations

import types

import pytest

from winwatt_automation.live_ui import app_connector, locators, window_tree




@pytest.fixture(autouse=True)
def _reset_app_connector_sessions():
    original_winwatt_state = (
        app_connector.WinWattSession.app,
        app_connector.WinWattSession.main_window,
        app_connector.WinWattSession.process_id,
        app_connector.WinWattSession.handle,
    )
    original_main_window_state = (
        app_connector.MainWindowSession.window,
        app_connector.MainWindowSession.process_id,
        app_connector.MainWindowSession.last_validation_monotonic,
        app_connector.MainWindowSession.validation_interval_s,
        app_connector.MainWindowSession.foreground_failure_count,
        app_connector.MainWindowSession.last_foreground_failure_monotonic,
        app_connector.MainWindowSession.last_resolve_attempt_monotonic,
    )
    app_connector.WinWattSession.app = None
    app_connector.WinWattSession.main_window = None
    app_connector.WinWattSession.process_id = None
    app_connector.WinWattSession.handle = None
    app_connector.MainWindowSession.window = None
    app_connector.MainWindowSession.process_id = None
    app_connector.MainWindowSession.last_validation_monotonic = 0.0
    app_connector.MainWindowSession.validation_interval_s = 4.0
    app_connector.MainWindowSession.foreground_failure_count = 0
    app_connector.MainWindowSession.last_foreground_failure_monotonic = 0.0
    app_connector.MainWindowSession.last_resolve_attempt_monotonic = 0.0
    yield
    (
        app_connector.WinWattSession.app,
        app_connector.WinWattSession.main_window,
        app_connector.WinWattSession.process_id,
        app_connector.WinWattSession.handle,
    ) = original_winwatt_state
    (
        app_connector.MainWindowSession.window,
        app_connector.MainWindowSession.process_id,
        app_connector.MainWindowSession.last_validation_monotonic,
        app_connector.MainWindowSession.validation_interval_s,
        app_connector.MainWindowSession.foreground_failure_count,
        app_connector.MainWindowSession.last_foreground_failure_monotonic,
        app_connector.MainWindowSession.last_resolve_attempt_monotonic,
    ) = original_main_window_state


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
        exists: bool = True,
        rect: FakeRect | None = None,
    ):
        self._title = title
        self._class_name = class_name
        self._process_id = process_id
        self._handle = handle
        self._visible = visible
        self._enabled = enabled
        self._exists = exists
        self._rect = rect or FakeRect(0, 0, 100, 100)
        self.focus_calls = 0
        self.restore_calls = 0
        self.keyboard_focus_calls = 0
        self.element_info = FakeElementInfo(name=title, control_type=control_type, class_name=class_name)
        self.element_info.handle = handle
        self.element_info.process_id = process_id

    def window_text(self):
        return self._title

    def class_name(self):
        return self._class_name

    def process_id(self):
        return self._process_id

    def handle(self):
        return self._handle

    def exists(self, *args, **kwargs):
        return self._exists

    def is_visible(self):
        return self._visible

    def is_enabled(self):
        return self._enabled

    def rectangle(self):
        return self._rect

    def set_focus(self):
        self.focus_calls += 1

    def restore(self):
        self.restore_calls += 1

    def set_keyboard_focus(self):
        self.keyboard_focus_calls += 1


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


def test_pywinauto_application_class_falls_back_to_application_module(monkeypatch):
    class SentinelApplication:
        pass

    monkeypatch.setitem(
        __import__("sys").modules,
        "pywinauto",
        types.SimpleNamespace(Desktop=object()),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "pywinauto.application",
        types.SimpleNamespace(Application=SentinelApplication),
    )

    assert app_connector._pywinauto_application_class() is SentinelApplication


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

    class FakeMainWindow(dict):
        def exists(self, timeout=0):
            return True

    class FakeConnectedApp:
        def __init__(self, backend):
            self.backend = types.SimpleNamespace(name=backend)

        def window(self, **kwargs):
            return FakeMainWindow({"backend": self.backend.name, **kwargs})

        def windows(self, top_level_only=True):
            return []

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

    assert main_window == {"backend": "uia", "class_name": "TMainForm", "title_re": ".*WinWatt.*"}
    assert ("connect", "win32", {"handle": 444}) in fake_factory.calls
    assert ("connect", "uia", {"process": 999}) in fake_factory.calls


def test_get_main_window_falls_back_to_best_uia_top_level_window(monkeypatch):
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

    class MissingMainWindow(dict):
        def exists(self, timeout=0):
            return False

    class FakeConnectedApp:
        def __init__(self, backend):
            self.backend = types.SimpleNamespace(name=backend)

        def window(self, **kwargs):
            if kwargs == {"class_name": "TMainForm", "title_re": ".*WinWatt.*"}:
                return MissingMainWindow({"backend": self.backend.name, **kwargs})
            return {"backend": self.backend.name, **kwargs}

        def windows(self, top_level_only=True):
            return [
                FakeWindow(
                    title="WinWatt - Dialog",
                    class_name="TDialog",
                    process_id=999,
                    handle=111,
                    visible=True,
                    rect=FakeRect(0, 0, 300, 200),
                ),
                FakeWindow(
                    title="WinWatt - Main",
                    class_name="TMainForm",
                    process_id=999,
                    handle=777,
                    visible=True,
                    rect=FakeRect(0, 0, 1600, 900),
                ),
                FakeWindow(
                    title="Other App",
                    class_name="TMainForm",
                    process_id=999,
                    handle=999,
                    visible=True,
                    rect=FakeRect(0, 0, 2000, 1200),
                ),
            ]

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

    assert main_window == {"backend": "uia", "handle": 777}


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

    monkeypatch.setattr(locators, "get_cached_main_window", lambda: root)

    assert locators.find_form("ProjectForm") is form
    assert locators.find_control("ProjectForm", "save_button") is control_by_id
    assert locators.find_control("ProjectForm", "save:listitem") is control_by_name
    assert locators.find_control("ProjectForm", "missing:listitem") is control_by_type
    assert locators.find_control("ProjectForm", "missing") is fallback


def test_get_cached_main_window_throttles_foreground_resolve_loop(monkeypatch):
    original_winwatt_state = (
        app_connector.WinWattSession.main_window,
        app_connector.WinWattSession.process_id,
        app_connector.WinWattSession.handle,
    )
    original_main_window_state = (
        app_connector.MainWindowSession.last_validation_monotonic,
        app_connector.MainWindowSession.validation_interval_s,
        app_connector.MainWindowSession.foreground_failure_count,
        app_connector.MainWindowSession.last_foreground_failure_monotonic,
        app_connector.MainWindowSession.last_resolve_attempt_monotonic,
    )

    try:
        cached_window = FakeWindow(title="WinWatt - Project", class_name="TMainForm", process_id=999, handle=444)
        app_connector.WinWattSession.main_window = cached_window
        app_connector.WinWattSession.process_id = 999
        app_connector.WinWattSession.handle = 444
        app_connector.MainWindowSession.last_validation_monotonic = 0.0
        app_connector.MainWindowSession.validation_interval_s = 0.0
        app_connector.MainWindowSession.foreground_failure_count = 2
        app_connector.MainWindowSession.last_foreground_failure_monotonic = 96.0
        app_connector.MainWindowSession.last_resolve_attempt_monotonic = 95.0

        monkeypatch.setattr(app_connector.time, "monotonic", lambda: 100.0)
        monkeypatch.setattr(app_connector, "_cached_window_health_status", lambda window: (False, "foreground_context_failed"))
        monkeypatch.setattr(app_connector, "describe_foreground_window", lambda: {"title": "VS Code", "process_id": 1})
        monkeypatch.setattr(app_connector, "_resolve_uia_main_window", lambda: (_ for _ in ()).throw(AssertionError("resolve should be throttled")))

        result = app_connector.get_cached_main_window()

        assert result is cached_window
        assert app_connector.MainWindowSession.last_validation_monotonic == 100.0
        assert app_connector.MainWindowSession.foreground_failure_count == 3
    finally:
        app_connector.WinWattSession.main_window, app_connector.WinWattSession.process_id, app_connector.WinWattSession.handle = original_winwatt_state
        (
            app_connector.MainWindowSession.last_validation_monotonic,
            app_connector.MainWindowSession.validation_interval_s,
            app_connector.MainWindowSession.foreground_failure_count,
            app_connector.MainWindowSession.last_foreground_failure_monotonic,
            app_connector.MainWindowSession.last_resolve_attempt_monotonic,
        ) = original_main_window_state


def test_focus_guard_soft_continues_for_open_system_menu_when_exists_false_but_identity_strong(monkeypatch):
    main_window = FakeWindow(
        title="WinWatt gólya",
        class_name="TMainForm",
        process_id=1048,
        handle=4328702,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(171, 96, 1170, 1151),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.WinWattSession.process_id = 1048
    app_connector.WinWattSession.handle = 4328702
    app_connector.MainWindowSession.window = main_window
    app_connector.MainWindowSession.process_id = 1048
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)
    monkeypatch.setattr(app_connector, "is_winwatt_foreground_context", lambda window, allow_dialog=False: window is main_window)
    monkeypatch.setattr(
        app_connector,
        "describe_foreground_window",
        lambda: {"handle": 4328702, "title": "WinWatt gólya", "class_name": "TMainForm", "process_id": 1048},
    )

    resolved = app_connector.ensure_main_window_foreground_before_click(action_label="open_system_menu", timeout=0.01)

    assert resolved is main_window
    assert main_window.focus_calls == 0
    assert main_window.restore_calls == 0


def test_focus_guard_allows_normal_top_menu_click_when_exists_false_but_identity_strong(monkeypatch):
    main_window = FakeWindow(
        title="WinWatt gólya",
        class_name="TMainForm",
        process_id=1048,
        handle=4328702,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(171, 96, 1170, 1151),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.WinWattSession.process_id = 1048
    app_connector.WinWattSession.handle = 4328702
    app_connector.MainWindowSession.window = main_window
    app_connector.MainWindowSession.process_id = 1048
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)
    monkeypatch.setattr(app_connector, "is_winwatt_foreground_context", lambda window, allow_dialog=False: window is main_window)
    monkeypatch.setattr(
        app_connector,
        "describe_foreground_window",
        lambda: {"handle": 4328702, "title": "WinWatt gólya", "class_name": "TMainForm", "process_id": 1048},
    )

    resolved = app_connector.ensure_main_window_foreground_before_click(action_label="click_top_menu_item:Fájl", timeout=0.01)

    assert resolved is main_window
    assert main_window.focus_calls == 0
    assert main_window.restore_calls == 0




def test_focus_guard_allows_open_top_menu_when_exists_false_but_identity_strong(monkeypatch):
    main_window = FakeWindow(
        title="WinWatt gólya",
        class_name="TMainForm",
        process_id=1048,
        handle=4328702,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(171, 96, 1170, 1151),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.WinWattSession.process_id = 1048
    app_connector.WinWattSession.handle = 4328702
    app_connector.MainWindowSession.window = main_window
    app_connector.MainWindowSession.process_id = 1048
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)
    monkeypatch.setattr(app_connector, "is_winwatt_foreground_context", lambda window, allow_dialog=False: window is main_window)
    monkeypatch.setattr(
        app_connector,
        "describe_foreground_window",
        lambda: {"handle": 4328702, "title": "WinWatt gólya", "class_name": "TMainForm", "process_id": 1048},
    )

    resolved = app_connector.ensure_main_window_foreground_before_click(action_label="open_top_menu:Fájl", timeout=0.01)

    assert resolved is main_window
    assert main_window.focus_calls == 0
    assert main_window.restore_calls == 0


def test_focus_guard_allows_relative_menu_click_when_exists_false_but_identity_strong(monkeypatch):
    main_window = FakeWindow(
        title="WinWatt gólya",
        class_name="TMainForm",
        process_id=1048,
        handle=4328702,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(171, 96, 1170, 1151),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.WinWattSession.process_id = 1048
    app_connector.WinWattSession.handle = 4328702
    app_connector.MainWindowSession.window = main_window
    app_connector.MainWindowSession.process_id = 1048
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)
    monkeypatch.setattr(app_connector, "is_winwatt_foreground_context", lambda window, allow_dialog=False: window is main_window)
    monkeypatch.setattr(
        app_connector,
        "describe_foreground_window",
        lambda: {"handle": 4328702, "title": "WinWatt gólya", "class_name": "TMainForm", "process_id": 1048},
    )

    resolved = app_connector.ensure_main_window_foreground_before_click(action_label="relative_menu_click", timeout=0.01)

    assert resolved is main_window
    assert main_window.focus_calls == 0
    assert main_window.restore_calls == 0


def test_focus_guard_allows_single_row_probe_click_when_exists_false_but_identity_strong(monkeypatch):
    main_window = FakeWindow(
        title="WinWatt gólya",
        class_name="TMainForm",
        process_id=1048,
        handle=4328702,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(171, 96, 1170, 1151),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.WinWattSession.process_id = 1048
    app_connector.WinWattSession.handle = 4328702
    app_connector.MainWindowSession.window = main_window
    app_connector.MainWindowSession.process_id = 1048
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)
    monkeypatch.setattr(app_connector, "is_winwatt_foreground_context", lambda window, allow_dialog=False: window is main_window)
    monkeypatch.setattr(
        app_connector,
        "describe_foreground_window",
        lambda: {"handle": 4328702, "title": "WinWatt gólya", "class_name": "TMainForm", "process_id": 1048},
    )

    resolved = app_connector.ensure_main_window_foreground_before_click(action_label="single_row_probe_click[0]", timeout=0.01, allow_dialog=True)

    assert resolved is main_window
    assert main_window.focus_calls == 0
    assert main_window.restore_calls == 0


def test_focus_guard_still_fails_for_open_top_menu_when_identity_drifts(monkeypatch):
    main_window = FakeWindow(
        title="WinWatt gólya",
        class_name="TMainForm",
        process_id=1048,
        handle=4328702,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(171, 96, 1170, 1151),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.WinWattSession.process_id = 1048
    app_connector.WinWattSession.handle = 4328702
    app_connector.MainWindowSession.window = main_window
    app_connector.MainWindowSession.process_id = 1048
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)
    monkeypatch.setattr(app_connector, "is_winwatt_foreground_context", lambda window, allow_dialog=False: False)
    monkeypatch.setattr(
        app_connector,
        "describe_foreground_window",
        lambda: {"handle": 999, "title": "Másik ablak", "class_name": "OtherWindow", "process_id": 9999},
    )
    monkeypatch.setattr(app_connector.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="could not bring WinWatt to foreground for action=open_top_menu:Fájl"):
        app_connector.ensure_main_window_foreground_before_click(
            action_label="open_top_menu:Fájl",
            timeout=0.02,
            poll_interval=0.01,
        )

    assert main_window.focus_calls >= 1
    assert main_window.restore_calls >= 1
    assert main_window.keyboard_focus_calls >= 1


def test_focus_guard_still_fails_for_relative_menu_click_when_identity_drifts(monkeypatch):
    main_window = FakeWindow(
        title="WinWatt gólya",
        class_name="TMainForm",
        process_id=1048,
        handle=4328702,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(171, 96, 1170, 1151),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.WinWattSession.process_id = 1048
    app_connector.WinWattSession.handle = 4328702
    app_connector.MainWindowSession.window = main_window
    app_connector.MainWindowSession.process_id = 1048
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)
    monkeypatch.setattr(app_connector, "is_winwatt_foreground_context", lambda window, allow_dialog=False: False)
    monkeypatch.setattr(
        app_connector,
        "describe_foreground_window",
        lambda: {"handle": 999, "title": "Másik ablak", "class_name": "OtherWindow", "process_id": 9999},
    )
    monkeypatch.setattr(app_connector.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="could not bring WinWatt to foreground for action=relative_menu_click"):
        app_connector.ensure_main_window_foreground_before_click(
            action_label="relative_menu_click",
            timeout=0.02,
            poll_interval=0.01,
        )

    assert main_window.focus_calls >= 1
    assert main_window.restore_calls >= 1
    assert main_window.keyboard_focus_calls >= 1


def test_focus_guard_soft_continues_for_baseline_restore_before_refocus(monkeypatch):
    main_window = FakeWindow(
        title="WinWatt gólya",
        class_name="TMainForm",
        process_id=1048,
        handle=4328702,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(171, 96, 1170, 1151),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.WinWattSession.process_id = 1048
    app_connector.WinWattSession.handle = 4328702
    app_connector.MainWindowSession.window = main_window
    app_connector.MainWindowSession.process_id = 1048
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)

    state = {"calls": 0}

    def _foreground(window, allow_dialog=False):
        state["calls"] += 1
        return state["calls"] >= 2

    monkeypatch.setattr(app_connector, "is_winwatt_foreground_context", _foreground)
    monkeypatch.setattr(
        app_connector,
        "describe_foreground_window",
        lambda: {"handle": 4328702, "title": "WinWatt gólya", "class_name": "TMainForm", "process_id": 1048},
    )
    monkeypatch.setattr(app_connector.time, "sleep", lambda _: None)

    resolved = app_connector.ensure_main_window_foreground_before_click(
        action_label="baseline_restore:project_open:before:Rendszer",
        timeout=0.2,
        poll_interval=0.01,
        allow_dialog=True,
    )

    assert resolved is main_window
    assert main_window.focus_calls >= 1
    assert main_window.restore_calls >= 1
    assert main_window.keyboard_focus_calls >= 1


def test_focus_guard_still_fails_for_top_menu_click_when_identity_drifts(monkeypatch):
    main_window = FakeWindow(
        title="WinWatt gólya",
        class_name="TMainForm",
        process_id=1048,
        handle=4328702,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(171, 96, 1170, 1151),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.WinWattSession.process_id = 1048
    app_connector.WinWattSession.handle = 4328702
    app_connector.MainWindowSession.window = main_window
    app_connector.MainWindowSession.process_id = 1048
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)
    monkeypatch.setattr(app_connector, "is_winwatt_foreground_context", lambda window, allow_dialog=False: False)
    monkeypatch.setattr(
        app_connector,
        "describe_foreground_window",
        lambda: {"handle": 999, "title": "Másik ablak", "class_name": "OtherWindow", "process_id": 9999},
    )
    monkeypatch.setattr(app_connector.time, "sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="could not bring WinWatt to foreground for action=click_top_menu_item:Fájl"):
        app_connector.ensure_main_window_foreground_before_click(
            action_label="click_top_menu_item:Fájl",
            timeout=0.02,
            poll_interval=0.01,
        )

    assert main_window.focus_calls >= 1
    assert main_window.restore_calls >= 1
    assert main_window.keyboard_focus_calls >= 1


def test_focus_guard_still_fails_for_real_window_loss_when_exists_false_and_identity_weak(monkeypatch):
    main_window = FakeWindow(
        title="",
        class_name="",
        process_id=None,
        handle=None,
        exists=False,
        visible=True,
        enabled=True,
        rect=FakeRect(0, 0, 0, 0),
    )
    app_connector.WinWattSession.main_window = main_window
    app_connector.MainWindowSession.window = main_window
    monkeypatch.setattr(app_connector, "get_cached_main_window", lambda: main_window)

    with pytest.raises(RuntimeError, match="main window no longer exists before action=open_system_menu"):
        app_connector.ensure_main_window_foreground_before_click(action_label="open_system_menu", timeout=0.01)

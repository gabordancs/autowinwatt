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


class FakeApplication:
    def __init__(self, backend: str):
        self.backend = backend

    def connect(self, title_re: str):
        if self.backend == "uia":
            raise RuntimeError("uia fail")
        return self


def test_connect_to_winwatt_raises_if_all_backends_fail(monkeypatch):
    class AlwaysFailApplication:
        def __init__(self, backend: str):
            self.backend = backend

        def connect(self, title_re: str):
            raise RuntimeError(f"{self.backend} fail")

    monkeypatch.setitem(
        __import__("sys").modules,
        "pywinauto",
        types.SimpleNamespace(Application=AlwaysFailApplication),
    )

    with pytest.raises(app_connector.WinWattNotRunningError):
        app_connector.connect_to_winwatt()


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

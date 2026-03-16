from __future__ import annotations

from winwatt_automation.dialog_explorer.dialog_explorer import (
    classify_control,
    compute_dialog_state_hash,
    enumerate_dialog_controls,
    explore_dialog,
    try_control_interaction,
)


class Rect:
    def __init__(self, left=0, top=0, right=10, bottom=10):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeControl:
    def __init__(self, *, ctype="Button", cls="Button", text="OK", aid="", enabled=True, visible=True, selected=False, items=None):
        self._ctype = ctype
        self._cls = cls
        self._text = text
        self._enabled = enabled
        self._visible = visible
        self._selected = selected
        self._items = items or []
        self.element_info = type("EI", (), {"automation_id": aid, "control_type": ctype})()

    def control_type(self):
        return self._ctype

    def friendly_class_name(self):
        return self._cls

    def window_text(self):
        return self._text

    def is_enabled(self):
        return self._enabled

    def is_visible(self):
        return self._visible

    def rectangle(self):
        return Rect()

    def click_input(self):
        self._selected = True

    def toggle(self):
        self._selected = not self._selected

    def select(self, arg=None):
        self._selected = True

    def is_selected(self):
        return self._selected

    def expand(self):
        return None

    def item_texts(self):
        return list(self._items)

    def tab_count(self):
        return len(self._items)

    def get_selected_tab(self):
        return 0

    def get_toggle_state(self):
        return int(self._selected)


class FakeDialog:
    def __init__(self, controls, title="Dialog"):
        self._controls = controls
        self._title = title

    def descendants(self):
        return list(self._controls)

    def window_text(self):
        return self._title


def test_control_enumeration_filters_irrelevant():
    d = FakeDialog([
        FakeControl(ctype="Static", cls="Static", text="Label"),
        FakeControl(ctype="Button", cls="Button", text="OK", aid="ok"),
    ])
    rows = enumerate_dialog_controls(d)
    assert len(rows) == 1
    assert rows[0]["name"] == "OK"


def test_control_classification():
    assert classify_control({"control_type": "Button", "friendly_class_name": "Button"}) == "button"
    assert classify_control({"control_type": "CheckBox", "friendly_class_name": "CheckBox"}) == "checkbox"
    assert classify_control({"control_type": "ComboBox", "friendly_class_name": "ComboBox"}) == "combobox"


def test_interaction_mapping_checkbox():
    ctrl = FakeControl(ctype="CheckBox", cls="CheckBox", text="X")
    result = try_control_interaction(ctrl)
    assert result["classification"] == "checkbox"
    assert result["attempted"] is True


def test_state_hash_stable():
    d1 = FakeDialog([FakeControl(ctype="Button", cls="Button", text="OK", aid="ok")])
    d2 = FakeDialog([FakeControl(ctype="Button", cls="Button", text="OK", aid="ok")])
    assert compute_dialog_state_hash(d1) == compute_dialog_state_hash(d2)


def test_visited_state_skip():
    d = FakeDialog([FakeControl(ctype="Button", cls="Button", text="OK", aid="ok")])
    visited = set()
    first = explore_dialog(d, visited_states=visited)
    second = explore_dialog(d, visited_states=visited)
    assert first["states"]
    assert second["controls"] == []


def test_depth_limit():
    d = FakeDialog([FakeControl(ctype="Button", cls="Button", text="OK")])
    result = explore_dialog(d, depth=3, max_depth=3)
    assert result["controls"] == []


def test_destructive_button_filter():
    ctrl = FakeControl(ctype="Button", cls="Button", text="Delete")
    result = try_control_interaction(ctrl, safe_mode=True)
    assert result["attempted"] is False
    assert result["skipped_reason"] == "destructive_filtered"

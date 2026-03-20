from __future__ import annotations

import sys
import types

from loguru import logger

from winwatt_automation.runtime_mapping.config import configure_diagnostics
from winwatt_automation.runtime_mapping.models import RuntimeDialogRecord, RuntimeMenuRow, RuntimeStateSnapshot
from winwatt_automation.runtime_mapping.program_mapper import (
    _action_state_classification,
    _classify_placeholder_action_outcome,
    _verify_modal_close_outcome,
    close_transient_dialog_or_window,
    detect_dialog_or_window_transition,
    map_runtime_state,
    verify_main_window_recovery,
)


def _snapshot(*, enabled: bool = True, windows: list[dict] | None = None, foreground: dict | None = None) -> RuntimeStateSnapshot:
    return RuntimeStateSnapshot(
        state_id="s",
        process_id=123,
        main_window_title="WinWatt",
        main_window_class="TMainForm",
        visible_top_windows=windows or [{"title": "WinWatt", "class_name": "TMainForm", "process_id": 123, "handle": 1}],
        discovered_top_menus=["Fájl", "Súgó"],
        timestamp="t",
        main_window_enabled=enabled,
        main_window_visible=True,
        foreground_window=foreground or {"title": "WinWatt", "class_name": "TMainForm", "process_id": 123},
    )


def test_modal_likely_when_main_window_disabled():
    before = _snapshot(enabled=True)
    after = _snapshot(enabled=False)
    result = detect_dialog_or_window_transition(before, after, child_rows=[])
    assert result["result_type"] == "main_window_disabled_modal_likely"


def test_dialog_opened_when_new_window_candidate_appears():
    before = _snapshot()
    after = _snapshot(windows=[
        {"title": "WinWatt", "class_name": "TMainForm", "process_id": 123, "handle": 1},
        {"title": "Megnyitás", "class_name": "#32770", "process_id": 123, "handle": 2},
    ])
    result = detect_dialog_or_window_transition(before, after, child_rows=[])
    assert result["result_type"] == "dialog_opened"


def test_placeholder_outcome_treats_32770_without_popup_as_modal():
    configure_diagnostics(placeholder_modal_policy="submenu_only")
    before = _snapshot(enabled=True)
    after = _snapshot(
        enabled=False,
        windows=[
            {"title": "WinWatt", "class_name": "TMainForm", "process_id": 123, "handle": 1},
            {"title": "Projekt létrehozása", "class_name": "#32770", "process_id": 123, "handle": 2},
        ],
        foreground={"title": "Projekt létrehozása", "class_name": "#32770", "process_id": 123},
    )
    row = RuntimeMenuRow(
        state_id="s",
        top_menu="Fájl",
        row_index=2,
        menu_path=["Fájl", "Projekt létrehozása"],
        text="Projekt létrehozása",
        normalized_text="projekt letrehozasa",
        rectangle={},
        center_x=1,
        center_y=1,
        is_separator=False,
        source_scope="popup",
        fragments=[],
        enabled_guess=True,
        discovered_in_state="s",
        meta={"source": "geometry_placeholder"},
    )
    outcome = _classify_placeholder_action_outcome(
        state_id="s",
        path=row.menu_path,
        row=row,
        before_action=before,
        after_action=after,
        current_rows=[],
        child_rows=[],
    )
    assert outcome["outcome"] == "modal_opened"


def test_close_helper_esc_success(monkeypatch):
    calls: list[str] = []

    class W:
        visible = False

        def set_focus(self):
            calls.append("focus")

        def is_visible(self):
            return self.visible

    keyboard = types.SimpleNamespace(send_keys=lambda key: calls.append(key))
    pywinauto = types.SimpleNamespace(keyboard=keyboard)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)

    result = close_transient_dialog_or_window(W(), action_label="x")
    assert result["closed"] is True
    assert result["method"] == "esc"


def test_close_helper_cancel_button_success(monkeypatch):
    class Btn:
        def click_input(self):
            pass

    class W:
        _visible = True

        def set_focus(self):
            pass

        def is_visible(self):
            v = self._visible
            self._visible = False
            return v

        def child_window(self, **kwargs):
            return Btn()

    keyboard = types.SimpleNamespace(send_keys=lambda key: None)
    pywinauto = types.SimpleNamespace(keyboard=keyboard)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto)
    result = close_transient_dialog_or_window(W(), action_label="x")
    assert result["closed"] is True


def test_recovery_verification_main_window_ok():
    class W:
        def is_visible(self):
            return True

        def is_enabled(self):
            return True

    assert verify_main_window_recovery(W()) is True


def test_mapper_documents_dialog_and_continues(monkeypatch):
    snapshots = {
        "s": _snapshot(),
    }
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot", lambda state_id: snapshots["s"])
    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.restore_clean_menu_baseline", lambda **kwargs: True)

    top_iter = iter(["Fájl", "Súgó"])

    def _explore_menu_tree(**kwargs):
        tm = kwargs["top_menu"]
        if tm == "Fájl":
            return ([], [], [], [RuntimeDialogRecord(state_id="s", top_menu=tm, row_index=0, menu_path=[tm], title="D", class_name="#32770", process_id=1)], [], [])
        return ([{"title": "Névjegy"}], [], [], [], [], [])

    monkeypatch.setattr("winwatt_automation.runtime_mapping.program_mapper.explore_menu_tree", _explore_menu_tree)
    state = map_runtime_state(state_id="s", top_menus=["Fájl", "Súgó"])
    assert any(root.get("title") == "Súgó" for root in state.menu_tree)
    assert len(state.dialogs) == 1


def test_verify_modal_close_outcome_hard_fail_when_main_window_stays_disabled(monkeypatch):
    monkeypatch.setattr(
        "winwatt_automation.runtime_mapping.program_mapper.capture_state_snapshot",
        lambda _state_id: _snapshot(enabled=False, foreground={"title": "Megnyitás", "class_name": "#32770", "process_id": 123}),
    )

    result = _verify_modal_close_outcome(state_id="s", top_menu="Fájl", path=["Fájl", "Megnyitás"], row_index=1)

    assert result["ok"] is False
    assert result["main_window_enabled"] is False
    assert result["root_menu_reopenable"] is False


def test_recent_project_open_transition_classification_preferred_over_leaf_classification():
    classification = _action_state_classification(
        transition={"recent_project_candidate": True, "project_open_state_transition": True, "attempted": True},
        opens_submenu=False,
        opens_modal=False,
    )

    assert classification == "opens_project_and_changes_runtime_state"


class _FakeComError(Exception):
    __module__ = "pythoncom"


class _FakeMenuParent:
    def __init__(self, control_type: str):
        self.element_info = type("Info", (), {"control_type": control_type, "name": control_type, "class_name": ""})()


class _FakeClickableMenuItem:
    def __init__(self, name: str, rect: tuple[int, int, int, int], *, parent_mode: str = "ok"):
        self.element_info = type("Info", (), {"name": name, "control_type": "MenuItem", "class_name": "MenuItem", "handle": id(self)})()
        self._rect = rect
        self._parent_mode = parent_mode
        self.clicked = 0

    def is_visible(self):
        return True

    def rectangle(self):
        left, top, right, bottom = self._rect
        return type("Rect", (), {"left": left, "top": top, "right": right, "bottom": bottom})()

    def parent(self):
        if self._parent_mode == "comerror":
            raise _FakeComError("parent lookup failed")
        return _FakeMenuParent("MenuBar")

    def click_input(self):
        self.clicked += 1


def test_click_top_menu_item_uses_geometry_fallback_when_parent_comerror(monkeypatch):
    from winwatt_automation.live_ui import menu_helpers

    items = [
        _FakeClickableMenuItem("Fájl", (4, 4, 70, 28), parent_mode="comerror"),
        _FakeClickableMenuItem("Ablak", (71, 4, 150, 28), parent_mode="comerror"),
        _FakeClickableMenuItem("Súgó", (151, 4, 220, 28), parent_mode="comerror"),
    ]
    target = items[1]
    events: list[str] = []
    sink_id = logger.add(lambda msg: events.append(msg.record["message"]), level="INFO")
    try:
        menu_helpers._TOPBAR_BAND_CACHE.update({"handle": None, "captured_at": 0.0, "band": None})
        menu_helpers._consume_topbar_parent_error_state()
        monkeypatch.setattr(menu_helpers, "get_cached_main_window", lambda: type("Main", (), {"element_info": type("Info", (), {"handle": 99})(), "child_window": lambda self, **kwargs: (_ for _ in ()).throw(RuntimeError("no menubar")), "rectangle": lambda self: type("Rect", (), {"left": 0, "top": 0, "right": 400, "bottom": 300})()})())
        monkeypatch.setattr(menu_helpers, "prepare_main_window_for_menu_interaction", lambda: type("Main", (), {"rectangle": lambda self: type("Rect", (), {"left": 0, "top": 0, "right": 400, "bottom": 300})()})())
        monkeypatch.setattr(menu_helpers, "ensure_main_window_foreground_before_click", lambda **kwargs: type("Main", (), {"rectangle": lambda self: type("Rect", (), {"left": 0, "top": 0, "right": 400, "bottom": 300})(), "click_input": lambda self, coords=None: None})())
        monkeypatch.setattr(menu_helpers, "describe_foreground_window", lambda: {"title": "WinWatt"})
        monkeypatch.setattr(menu_helpers, "is_winwatt_foreground_context", lambda *args, **kwargs: True)
        monkeypatch.setattr(menu_helpers, "_is_system_menu_foreground", lambda: False)
        monkeypatch.setattr(menu_helpers, "_query_menu_items_from_root", lambda _root, **kwargs: items)
        monkeypatch.setattr(menu_helpers, "wait_for_new_menu_popup", lambda before_snapshot, **kwargs: before_snapshot | {("x", "y", "z", "w", "scope")})
        monkeypatch.setattr(menu_helpers, "_menu_snapshot", lambda: set())
        monkeypatch.setattr(menu_helpers, "_log_top_menu_popup_diagnostics", lambda *args, **kwargs: None)

        menu_helpers.click_top_menu_item("Ablak")
    finally:
        logger.remove(sink_id)

    assert target.clicked == 1
    assert any("TOPBAR_PARENT_COMERROR_FALLBACK" in event for event in events)
    assert any("TOPBAR_GEOMETRY_FALLBACK_USED context=click_top_menu_item" in event for event in events)

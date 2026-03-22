from __future__ import annotations

from winwatt_automation.live_ui import file_dialog
from winwatt_automation.runtime_mapping import program_mapper


class _FakeElementInfo:
    def __init__(self, name: str = "", control_type: str = "", class_name: str = ""):
        self.name = name
        self.control_type = control_type
        self.class_name = class_name


class _FakeControl:
    def __init__(self, name: str, control_type: str = "", enabled: bool = True):
        self.element_info = _FakeElementInfo(name=name, control_type=control_type)
        self._enabled = enabled

    def is_enabled(self):
        return self._enabled


def test_trigger_open_project_dialog_from_default_state_sends_ctrl_o(monkeypatch):
    sent: list[str] = []
    import sys
    import types

    class _FakeKeyboard:
        @staticmethod
        def send_keys(keys, **_kwargs):
            sent.append(keys)

    monkeypatch.setattr(file_dialog, "_top_level_handles", lambda: {1})
    monkeypatch.setattr(file_dialog, "find_open_file_dialog", lambda **kwargs: ("dialog", {"dialog_found": True, "process_id": kwargs["process_id"]}))
    pywinauto_module = types.SimpleNamespace(keyboard=_FakeKeyboard)
    monkeypatch.setitem(sys.modules, "pywinauto", pywinauto_module)

    dialog, info = file_dialog.trigger_open_project_dialog_from_default_state(process_id=None)

    assert dialog == "dialog"
    assert sent == ["^o"]
    assert info["dialog_found"] is True
    assert info["steps"] == ["CTRL+O"]
    assert info["project_open_method"] == "ctrl_o"
    assert info["sequence"] == ["CTRL+O"]


def test_open_project_file_via_dialog_prefers_accelerator_before_popup(monkeypatch):
    calls: list[str] = []
    focus_calls: list[str] = []

    monkeypatch.setattr(
        file_dialog,
        "trigger_open_project_dialog_from_default_state",
        lambda **kwargs: (
            calls.append("accelerator") or "dialog",
            {"dialog_found": True, "method": "accelerator", "steps": ["CTRL+O"], "project_open_method": "ctrl_o", "sequence": ["CTRL+O"]},
        ),
    )
    monkeypatch.setattr(file_dialog, "prepare_main_window_for_menu_interaction", lambda: type("MainWindow", (), {"process_id": lambda self: 22})())
    monkeypatch.setattr(file_dialog, "get_cached_main_window", lambda: type("MainWindow", (), {"process_id": lambda self: 22})())
    monkeypatch.setattr(
        file_dialog,
        "ensure_main_window_foreground_before_click",
        lambda **kwargs: focus_calls.append(kwargs["action_label"]),
    )
    monkeypatch.setattr(file_dialog, "set_file_dialog_path", lambda dialog, path: (True, {"method": "direct"}))
    monkeypatch.setattr(file_dialog, "confirm_file_dialog_open", lambda dialog: (True, {"method": "enter"}))
    state = {"visible": True}

    def fake_safe_call(obj, method, default=None):
        if method == "exists":
            return True
        if method == "is_visible":
            current = state["visible"]
            state["visible"] = False
            return current
        return default

    monkeypatch.setattr(file_dialog, "_safe_call", fake_safe_call)
    monkeypatch.setattr(file_dialog.menu_helpers, "open_file_menu_and_capture_popup_state", lambda: (_ for _ in ()).throw(AssertionError("popup fallback should not run")))

    result = file_dialog.open_project_file_via_dialog(
        r"C:\tmp\testwwp.wwp",
        before_snapshot={"discovered_top_menus": ["Fájl"], "visible_top_windows": [], "main_window_title": "WinWatt"},
        after_snapshot_provider=lambda: {"discovered_top_menus": ["Fájl", "Projekt"], "visible_top_windows": [], "main_window_title": r"WinWatt - C:\tmp\testwwp.wwp"},
    )

    assert calls == ["accelerator"]
    assert focus_calls == ["open_project_file_via_dialog"]
    assert result.success is True
    assert result.project_open_method == "ctrl_o"
    assert result.project_open_sequence == ["CTRL+O"]


def test_select_best_dialog_candidate_prefers_pid_and_new_handle():
    candidates = [
        {"title": "Megnyitás", "class_name": "#32770", "process_id": 11, "handle": 100},
        {"title": "Projekt megnyitás", "class_name": "#32770", "process_id": 22, "handle": 101},
    ]

    best = file_dialog.select_best_dialog_candidate(
        candidates,
        process_id=22,
        previous_handles={100},
    )

    assert best is not None
    assert best["process_id"] == 22
    assert best["handle"] == 101


def test_find_filename_edit_control_prefers_filename_hint():
    dialog = type("FakeDialog", (), {})()
    controls = [
        _FakeControl(name="Search", control_type="Edit"),
        _FakeControl(name="Fájlnév:", control_type="Edit"),
    ]
    dialog.descendants = lambda: controls

    selected = file_dialog._find_filename_edit_control(dialog)

    assert selected is controls[1]


def test_find_confirm_open_button_by_hungarian_or_english_label():
    dialog = type("FakeDialog", (), {})()
    controls = [
        _FakeControl(name="Mégse", control_type="Button"),
        _FakeControl(name="&Megnyitás", control_type="Button"),
    ]
    dialog.descendants = lambda: controls

    button = file_dialog.find_confirm_open_button(dialog)

    assert button is controls[1]


def test_detect_project_state_changed_logic_reports_reasons():
    before = {
        "discovered_top_menus": ["Fájl", "Nézet"],
        "visible_top_windows": [{"title": "WinWatt"}],
        "main_window_title": "WinWatt - üres",
    }
    after = {
        "discovered_top_menus": ["Fájl", "Projekt", "Nézet"],
        "visible_top_windows": [{"title": "WinWatt"}, {"title": "Projekt"}],
        "main_window_title": "WinWatt - testwwp.wwp",
    }

    changed, reasons = file_dialog.detect_project_state_changed(before, after)

    assert changed is True
    assert "top_menu_count_changed" in reasons
    assert "visible_window_count_changed" in reasons
    assert "main_window_title_changed" in reasons


def test_open_test_project_returns_structured_result_shape(monkeypatch):
    expected = {
        "success": True,
        "path": r"C:\Users\dancsg\OneDrive - Futureal\Documents\GitHub\autowinwatt\winwatt_automation\tests\testwwp.wwp",
        "dialog_found": True,
        "path_entered": True,
        "confirm_clicked": True,
        "dialog_closed": True,
        "project_state_changed": True,
        "detected_changes": ["top_menus_changed"],
        "project_open_method": "ctrl_o",
        "project_open_sequence": ["CTRL+O"],
        "error": None,
    }

    monkeypatch.setattr(program_mapper, "capture_state_snapshot", lambda _state_id: type("S", (), {"__dict__": {}})())
    monkeypatch.setattr(program_mapper, "asdict", lambda _obj: {"discovered_top_menus": ["Fájl"]})
    monkeypatch.setattr(program_mapper, "open_project_file_via_dialog_dict", lambda *args, **kwargs: expected.copy())
    monkeypatch.setattr(program_mapper, "recover_after_project_open", lambda **kwargs: {"success": True, "diagnostics": {}, "close_attempts": []})

    result = program_mapper.open_test_project(expected["path"], safe_mode="safe")

    assert set(result.keys()) == {
        "success",
        "path",
        "dialog_found",
        "path_entered",
        "confirm_clicked",
        "dialog_closed",
        "project_state_changed",
        "detected_changes",
        "project_open_method",
        "project_open_sequence",
        "error",
        "project_open_audit",
        "recovery",
    }
    assert result["success"] is True
    assert result["project_open_audit"]["project_open_attempt_started"] is True
    assert result["project_open_audit"]["project_open_method"] == "ctrl_o"
    assert result["project_open_audit"]["project_open_sequence"] == ["CTRL+O"]
    assert result["recovery"]["success"] is True
    assert result["recovery"]["main_window_ready_after_attempt"] is True


def test_open_test_project_safe_mode_blocks_non_test_path():
    result = program_mapper.open_test_project(r"C:\tmp\random.wwp", safe_mode="safe")

    assert result["success"] is False
    assert result["dialog_found"] is False
    assert result["project_open_audit"]["project_open_attempt_started"] is False
    assert "Safe mode" in (result["error"] or "")


def test_interact_with_open_file_dialog_uses_explicit_verified_context(monkeypatch):
    class Dialog:
        def exists(self):
            return True

        def is_visible(self):
            return True

    monkeypatch.setattr(file_dialog, "set_file_dialog_path", lambda dialog, path: (True, {"method": "direct_edit"}))
    monkeypatch.setattr(file_dialog, "confirm_file_dialog_open", lambda dialog: (True, {"method": "button"}))

    state = {"dialog_visible": True}

    def fake_safe_call(obj, method, default=None):
        if method == "exists":
            return state["dialog_visible"]
        if method == "is_visible":
            current = state["dialog_visible"]
            state["dialog_visible"] = False
            return current
        return default

    monkeypatch.setattr(file_dialog, "_safe_call", fake_safe_call)

    result = file_dialog.interact_with_open_file_dialog(
        Dialog(),
        r"C:\tmp\test.wwp",
        before_snapshot={"discovered_top_menus": ["Fájl"], "visible_top_windows": [], "main_window_title": "WinWatt"},
        after_snapshot_provider=lambda: {"discovered_top_menus": ["Fájl", "Projekt"], "visible_top_windows": [], "main_window_title": r"WinWatt - C:\tmp\test.wwp"},
        detected_dialog_snapshot={"title": "Projekt megnyitás", "class_name": "#32770", "handle": 123},
        dialog_context={"dialog_already_verified": True, "dialog_handle": 123, "dialog_title": "Projekt megnyitás", "dialog_class": "#32770"},
    )

    assert result.path_entry_attempted is True
    assert result.helper_dialog_revalidated is True
    assert result.helper_dialog_ready_for_interaction is True
    assert result.helper_received_dialog_context["dialog_already_verified"] is True


def test_interact_with_open_file_dialog_reports_revalidation_failure_without_false_not_detected(monkeypatch):
    class Dialog:
        def exists(self):
            return False

        def is_visible(self):
            return False

    monkeypatch.setattr(file_dialog, "_safe_call", lambda obj, method, default=None: False if method in {"exists", "is_visible"} else default)

    result = file_dialog.interact_with_open_file_dialog(
        Dialog(),
        r"C:\tmp\test.wwp",
        before_snapshot={"discovered_top_menus": [], "visible_top_windows": [], "main_window_title": "WinWatt"},
        after_snapshot_provider=lambda: {"discovered_top_menus": [], "visible_top_windows": [], "main_window_title": "WinWatt"},
        detected_dialog_snapshot={"title": "Projekt megnyitás", "class_name": "#32770", "handle": 123},
        dialog_context={"dialog_already_verified": True, "dialog_handle": 123, "dialog_title": "Projekt megnyitás", "dialog_class": "#32770"},
    )

    assert result.path_entry_attempted is False
    assert result.error == "dialog_revalidation_failed"
    assert result.dialog_found is True

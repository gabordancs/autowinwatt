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
        "path": r"C:\Users\dancsg\Documents\GitHub\autowinwatt\winwatt_automation\tests\testwwp.wwp",
        "dialog_found": True,
        "path_entered": True,
        "confirm_clicked": True,
        "dialog_closed": True,
        "project_state_changed": True,
        "detected_changes": ["top_menus_changed"],
        "error": None,
    }

    monkeypatch.setattr(program_mapper, "capture_state_snapshot", lambda _state_id: type("S", (), {"__dict__": {}})())
    monkeypatch.setattr(program_mapper, "asdict", lambda _obj: {"discovered_top_menus": ["Fájl"]})
    monkeypatch.setattr(program_mapper, "open_project_file_via_dialog_dict", lambda *args, **kwargs: expected)

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
        "error",
    }
    assert result["success"] is True


def test_open_test_project_safe_mode_blocks_non_test_path():
    result = program_mapper.open_test_project(r"C:\tmp\random.wwp", safe_mode="safe")

    assert result["success"] is False
    assert result["dialog_found"] is False
    assert "Safe mode" in (result["error"] or "")

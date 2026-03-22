from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import importlib.util
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "winwatt_open_project_accelerator_smoke.py"
spec = importlib.util.spec_from_file_location("open_project_accelerator_smoke", SCRIPT_PATH)
smoke = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules.setdefault("open_project_accelerator_smoke", smoke)
spec.loader.exec_module(smoke)


@dataclass
class _Snapshot:
    state_id: str


def test_run_smoke_passes_detected_dialog_context_into_helper(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "connect_to_winwatt", lambda: None)
    monkeypatch.setattr(smoke, "prepare_main_window_for_menu_interaction", lambda: None)
    monkeypatch.setattr(smoke, "ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr(smoke, "get_last_focus_guard_diagnostic", lambda: {})
    monkeypatch.setattr(smoke, "get_cached_main_window", lambda: type("MainWindow", (), {"process_id": lambda self: 55})())
    monkeypatch.setattr(smoke, "_visible_top_level_windows", lambda: [])
    monkeypatch.setattr(smoke, "describe_foreground_window", lambda: {"title": "WinWatt", "class_name": "TMainForm"})
    monkeypatch.setattr(smoke, "send_project_open_accelerator", lambda **kwargs: {"project_open_method": "ctrl_o", "sequence": ["CTRL+O"]})
    monkeypatch.setattr(smoke, "_detect_dialog", lambda **kwargs: {"dialog_detected": True, "dialog": {"title": "Projekt megnyitás", "class_name": "#32770", "handle": 101, "process_id": 55}, "candidate_count": 1})

    dialog_wrapper = object()
    monkeypatch.setattr(smoke, "_find_visible_window_by_handle", lambda handle: dialog_wrapper if handle == 101 else None)
    monkeypatch.setattr(smoke, "capture_state_snapshot", lambda state_id: _Snapshot(state_id=state_id))
    def fake_asdict(obj):
        if hasattr(obj, "state_id"):
            return {"state_id": obj.state_id}
        return obj.__dict__.copy()

    monkeypatch.setattr(smoke, "asdict", fake_asdict)
    monkeypatch.setattr(smoke, "recover_after_project_open", lambda **kwargs: {"success": True, "close_attempts": [], "diagnostics": {}})

    captured = {}

    def fake_interact(dialog, project_path, **kwargs):
        captured["dialog"] = dialog
        captured["kwargs"] = kwargs
        return type(
            "Result",
            (),
            {
                "success": False,
                "path": project_path,
                "dialog_found": True,
                "path_entry_attempted": True,
                "path_entered": False,
                "confirm_attempted": False,
                "confirm_clicked": False,
                "dialog_closed": False,
                "project_state_changed": False,
                "detected_changes": [],
                "project_open_method": "ctrl_o",
                "project_open_sequence": ["CTRL+O"],
                "detected_dialog_snapshot": kwargs.get("detected_dialog_snapshot"),
                "helper_received_dialog_context": kwargs.get("dialog_context"),
                "helper_dialog_revalidated": True,
                "helper_dialog_ready_for_interaction": True,
                "observed_main_window_title_after_open": "",
                "observed_project_path": None,
                "path_match_normalized": False,
                "error": "path_entry_failed",
            },
        )()

    monkeypatch.setattr(smoke, "interact_with_open_file_dialog", fake_interact)

    exit_code = smoke.run_smoke(
        timeout_s=0.1,
        step_delay_s=0.0,
        log_path=tmp_path / "smoke.json",
        project_path=r"C:\tmp\test.wwp",
        accelerator_mode="ctrl_o",
    )

    assert exit_code == 1
    assert captured["dialog"] is dialog_wrapper
    assert captured["kwargs"]["detected_dialog_snapshot"]["title"] == "Projekt megnyitás"
    assert captured["kwargs"]["dialog_context"]["dialog_already_verified"] is True
    assert captured["kwargs"]["dialog_context"]["dialog_class"] == "#32770"


def test_run_smoke_uses_specific_error_when_dialog_detected_but_wrapper_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "connect_to_winwatt", lambda: None)
    monkeypatch.setattr(smoke, "prepare_main_window_for_menu_interaction", lambda: None)
    monkeypatch.setattr(smoke, "ensure_main_window_foreground_before_click", lambda **kwargs: None)
    monkeypatch.setattr(smoke, "get_last_focus_guard_diagnostic", lambda: {})
    monkeypatch.setattr(smoke, "get_cached_main_window", lambda: type("MainWindow", (), {"process_id": lambda self: 55})())
    monkeypatch.setattr(smoke, "_visible_top_level_windows", lambda: [])
    monkeypatch.setattr(smoke, "describe_foreground_window", lambda: {"title": "WinWatt", "class_name": "TMainForm"})
    monkeypatch.setattr(smoke, "send_project_open_accelerator", lambda **kwargs: {"project_open_method": "ctrl_o", "sequence": ["CTRL+O"]})
    monkeypatch.setattr(smoke, "_detect_dialog", lambda **kwargs: {"dialog_detected": True, "dialog": {"title": "Projekt megnyitás", "class_name": "#32770", "handle": 101, "process_id": 55}, "candidate_count": 1})
    monkeypatch.setattr(smoke, "_find_visible_window_by_handle", lambda handle: None)
    monkeypatch.setattr(smoke, "capture_state_snapshot", lambda state_id: _Snapshot(state_id=state_id))
    monkeypatch.setattr(smoke, "asdict", lambda obj: {"state_id": obj.state_id} if hasattr(obj, "state_id") else obj.__dict__.copy())
    monkeypatch.setattr(smoke, "recover_after_project_open", lambda **kwargs: {"success": True, "close_attempts": [], "diagnostics": {}})

    log_path = tmp_path / "smoke.json"
    exit_code = smoke.run_smoke(
        timeout_s=0.1,
        step_delay_s=0.0,
        log_path=log_path,
        project_path=r"C:\tmp\test.wwp",
        accelerator_mode="ctrl_o",
    )

    payload = __import__("json").loads(log_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["dialog_detected"] is True
    assert payload["path_entry_attempted"] is False
    assert payload["project_open_error"] == "dialog_detected_but_not_bound_for_interaction"
    assert payload["helper_received_dialog_context"]["dialog_already_verified"] is True

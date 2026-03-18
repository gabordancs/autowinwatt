from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.runtime_logging.progress_display import write_progress_status
from winwatt_automation.runtime_logging.run_recorder import finalize_run, start_run, update_status


def test_write_progress_status_persists_payload(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_logging.run_recorder._project_root", lambda: tmp_path)
    monkeypatch.setattr("winwatt_automation.runtime_logging.progress_display.Path", Path)

    path = tmp_path / "status.json"
    write_progress_status(path, run_id="r1", state="running", message="mapping", details={"step": "menus"})

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "r1"
    assert payload["state"] == "running"
    assert payload["details"]["step"] == "menus"


def test_update_status_and_finalize_run_refresh_live_status(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("winwatt_automation.runtime_logging.run_recorder._project_root", lambda: tmp_path)

    run = start_run("python -m winwatt_automation.scripts.map_full_program", {"cwd": str(tmp_path), "safe_mode": "off"})
    update_status(run, "running", "Mapping in progress", {"step": "Fájl"})

    running_payload = json.loads(run.status_path.read_text(encoding="utf-8"))
    assert running_payload["state"] == "running"
    assert running_payload["details"]["step"] == "Fájl"

    finalize_run(run, success=True, exit_code=0, summary={"short_summary": "done"})
    finished_payload = json.loads(run.status_path.read_text(encoding="utf-8"))
    assert finished_payload["state"] == "finished"

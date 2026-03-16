from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.runtime_logging import finalize_run, record_event, start_run
import winwatt_automation.runtime_logging.run_recorder as recorder


def _prepare_repo(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(recorder, "_project_root", lambda: repo_root)
    return repo_root


def test_sequence_number_increments(tmp_path: Path, monkeypatch):
    repo_root = _prepare_repo(tmp_path, monkeypatch)

    run1 = start_run("python -m winwatt_automation.scripts.map_full_program", {"cwd": str(repo_root), "safe_mode": "safe"})
    finalize_run(run1, success=True, exit_code=0, summary={"short_summary": "first"})

    run2 = start_run("python -m winwatt_automation.scripts.map_full_program", {"cwd": str(repo_root), "safe_mode": "safe"})
    finalize_run(run2, success=True, exit_code=0, summary={"short_summary": "second"})

    assert run1.sequence_number == 1
    assert run2.sequence_number == 2


def test_latest_files_are_updated(tmp_path: Path, monkeypatch):
    repo_root = _prepare_repo(tmp_path, monkeypatch)

    run = start_run("python -m winwatt_automation.scripts.map_full_program --safe-mode safe", {"cwd": str(repo_root), "safe_mode": "safe"})
    record_event(run, "runtime_diff", {"enabled_changes": 1})
    finalize_run(run, success=True, exit_code=0, summary={"short_summary": "latest-check"})

    latest_txt = (repo_root / "data/run_logs/latest.txt").read_text(encoding="utf-8")
    latest_json = json.loads((repo_root / "data/run_logs/latest.json").read_text(encoding="utf-8"))

    assert run.run_id in latest_txt
    assert latest_json["run_id"] == run.run_id
    assert latest_json["success"] is True


def test_index_json_gets_new_entry(tmp_path: Path, monkeypatch):
    repo_root = _prepare_repo(tmp_path, monkeypatch)

    run = start_run("python -m winwatt_automation.scripts.map_full_program", {"cwd": str(repo_root), "safe_mode": "safe"})
    finalize_run(run, success=True, exit_code=0, summary={"short_summary": "index-check"})

    index = json.loads((repo_root / "data/run_logs/index.json").read_text(encoding="utf-8"))
    assert len(index["runs"]) == 1
    assert index["runs"][0]["sequence_number"] == 1
    assert index["runs"][0]["run_id"] == run.run_id


def test_summary_json_is_created(tmp_path: Path, monkeypatch):
    repo_root = _prepare_repo(tmp_path, monkeypatch)

    run = start_run("python -m winwatt_automation.scripts.map_full_program", {"cwd": str(repo_root), "safe_mode": "safe"})
    json_path = finalize_run(
        run,
        success=True,
        exit_code=0,
        summary={
            "short_summary": "summary",
            "no_project_top_menus": 6,
            "project_open_top_menus": 6,
            "diff_summary": {"enabled_changes": 3},
        },
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["no_project_top_menus"] == 6
    assert payload["summary"]["project_open_top_menus"] == 6
    assert payload["summary"]["diff_summary"]["enabled_changes"] == 3


def test_failed_run_is_logged(tmp_path: Path, monkeypatch):
    repo_root = _prepare_repo(tmp_path, monkeypatch)

    run = start_run("python -m winwatt_automation.scripts.map_full_program", {"cwd": str(repo_root), "safe_mode": "safe"})
    record_event(run, "run_failed", {"error": "boom"})
    json_path = finalize_run(run, success=False, exit_code=1, summary={"short_summary": "failed", "last_error": "boom"})

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["success"] is False
    assert payload["exit_code"] == 1
    assert payload["summary"]["last_error"] == "boom"

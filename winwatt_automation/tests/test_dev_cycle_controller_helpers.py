from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.controller.chat_brief_builder import ChatBriefInput, build_chat_brief
from winwatt_automation.controller.config import ControllerConfig
from winwatt_automation.controller.git_ops import GitOps
from winwatt_automation.controller.runlog_reader import RunLogReader
from winwatt_automation.controller.script_runner import ScriptRunner


def test_runlog_reader_reads_latest_files(tmp_path: Path):
    logs = tmp_path / "data" / "run_logs"
    logs.mkdir(parents=True)
    (logs / "latest.json").write_text(json.dumps({"run_id": "r1", "success": True, "summary": {"short": "ok"}}), encoding="utf-8")
    (logs / "latest.txt").write_text("run_id=r1", encoding="utf-8")
    (logs / "index.json").write_text(json.dumps({"runs": [{"run_id": "r1"}]}), encoding="utf-8")

    snapshot = RunLogReader(tmp_path).read_latest()

    assert snapshot.latest_json is not None
    assert snapshot.latest_json["run_id"] == "r1"
    assert snapshot.latest_txt == "run_id=r1"
    assert snapshot.index_json is not None


def test_chat_brief_builder_has_fallback_without_latest_json(tmp_path: Path):
    snapshot = RunLogReader(tmp_path).read_latest()

    brief = build_chat_brief(
        ChatBriefInput(
            goal="Teszt cél",
            branch="main",
            git_status_summary="clean",
            run_snapshot=snapshot,
            concrete_request="Következő lépés",
        )
    )

    assert "Cél:" in brief
    assert "Legfrissebb futás summary:" in brief
    assert "Nincs elérhető run log summary" in brief


def test_git_ops_status_runs_on_initialized_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = GitOps(repo)
    init = git.run("init")

    assert init.ok
    status = git.status(short=True)
    assert status.ok
    assert "##" in status.stdout


def test_script_runner_reports_timeout(tmp_path: Path):
    runner = ScriptRunner(tmp_path, "python")
    result = runner.run(
        script_name="python",
        timeout_seconds=1,
        passthrough_args=["-c", "import time; time.sleep(2)"],
        safe_mode=None,
    )

    assert result.timed_out is True
    assert result.status == "timeout"


def test_config_env_fallbacks(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("WWA_CONTROLLER_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("WWA_CONTROLLER_SAFE_MODE", raising=False)
    monkeypatch.delenv("WWA_CHAT_BRIEF_OUTPUT", raising=False)

    config = ControllerConfig.from_env(repo_root=tmp_path)

    assert config.default_timeout_seconds == 300
    assert config.default_safe_mode == "safe"
    assert str(config.chat_brief_output_path).endswith("data/chat_prep/latest_chat_brief.txt")

from __future__ import annotations

import json
from pathlib import Path

from winwatt_automation.controller.config import ControllerConfig
from winwatt_automation.controller.mapping_cycle_orchestrator import MappingCycleOrchestrator


def _init_repo(repo_root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True, capture_output=True, text=True)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo_root, check=True, capture_output=True, text=True)


def _seed_runlog(repo_root: Path) -> None:
    logs = repo_root / "data" / "run_logs"
    runs = logs / "runs"
    runs.mkdir(parents=True)
    (runs / "sample.log").write_text(
        "hello\nPLACEHOLDER_ACTION_OUTCOME ok\nDBG_PHASE_TIMING phase=subtree_traversal took=10\n",
        encoding="utf-8",
    )
    (logs / "latest.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "success": True,
                "command": "python -m winwatt_automation.scripts.map_full_program",
                "summary": {"diff_summary": {"shared_top_menus": 4}},
                "output_paths": {"log_path": "data/run_logs/runs/sample.log", "json_path": "data/run_logs/runs/sample.json"},
            }
        ),
        encoding="utf-8",
    )
    (logs / "latest.txt").write_text("run_id=r1\n", encoding="utf-8")
    (logs / "index.json").write_text(json.dumps({"runs": [{"run_id": "r1"}]}), encoding="utf-8")


def test_prepare_creates_status_and_prompt(tmp_path: Path):
    _init_repo(tmp_path)
    _seed_runlog(tmp_path)
    orchestrator = MappingCycleOrchestrator(ControllerConfig.from_env(repo_root=tmp_path))

    prompt_path = orchestrator.prepare(goal="Map placeholders", request="Generate next step", milestone="placeholder_traversal", state="active")
    status = json.loads((tmp_path / "data" / "mapping_cycle" / "status.json").read_text(encoding="utf-8"))

    assert prompt_path.exists()
    assert "Required Codex result schema" in prompt_path.read_text(encoding="utf-8")
    assert status["milestone"] == "placeholder_traversal"
    assert status["latest_prompt_path"] == "data/mapping_cycle/codex_prompt.txt"
    assert status["run_log_path"] == "data/run_logs/runs/sample.log"


def test_ingest_test_and_handoff_flow(tmp_path: Path):
    _init_repo(tmp_path)
    _seed_runlog(tmp_path)
    orchestrator = MappingCycleOrchestrator(ControllerConfig.from_env(repo_root=tmp_path))
    orchestrator.prepare()

    result_path = tmp_path / "data" / "mapping_cycle" / "codex_result.json"
    result_path.write_text(
        json.dumps(
            {
                "diagnosis": "Placeholder traversal still drops context.",
                "changes": ["Added focused traversal guard."],
                "files": ["src/winwatt_automation/controller/mapping_cycle_orchestrator.py"],
                "tests_run": ["python -c \"print('unit ok')\""],
                "test_results": ["unit ok"],
                "manual_run_command": "python -c \"print('manual ok')\"",
                "expected_logs": ["PLACEHOLDER_ACTION_OUTCOME", "DBG_PHASE_TIMING phase=subtree_traversal"],
                "open_risks": ["Menu focus may still drift."],
                "next_step": "Validate modal handling after placeholder clicks.",
                "commit": "abc123",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    test_result = orchestrator.run_tests(result_path)
    handoff_path = orchestrator.handoff(result_path)
    status = json.loads((tmp_path / "data" / "mapping_cycle" / "status.json").read_text(encoding="utf-8"))
    handoff = handoff_path.read_text(encoding="utf-8")
    log_extract = json.loads((tmp_path / "data" / "mapping_cycle" / "log_extract.json").read_text(encoding="utf-8"))

    assert len(test_result.tests) == 1
    assert test_result.tests[0].ok is True
    assert test_result.manual_run is not None and test_result.manual_run.ok is True
    assert any(item["pattern"] == "PLACEHOLDER_ACTION_OUTCOME" for item in log_extract)
    assert "## Rövid diagnózis" in handoff
    assert "abc123" in handoff
    assert status["recommended_next_step"] == "Validate modal handling after placeholder clicks."
    assert status["commit"] == "abc123"
